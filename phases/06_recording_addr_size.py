import argparse
import json
import os.path
import signal
from subprocess import Popen
from typing import Dict, Tuple, List, Optional

import numpy

from phases.analyzer import DmaInfo, PeripheralRow, InfoFlag
from phases.analyzer.clusteringanalyzer import static_find_first_dma_incidence
from phases.recorder import TraceEntry, ExecutionTrace, trace_logging
from phases.recorder.execution_trace import TraceEntryDiff
from utilities import auto_int, naming_things, restart_connected_devices

LIST_OF_EXECUTION_AFFECTING_FLAGS = [
    InfoFlag.UNKNOWN,
    InfoFlag.TERMINATED_EARLY,
    InfoFlag.TERMINATED_LATE,
    InfoFlag.FAILED_TO_TERMINATE,
    InfoFlag.TIMED_OUT,
    InfoFlag.UNEXPECTED_NEW_DMA,
    InfoFlag.MISSING_OLD_DMA,
    InfoFlag.VALUE_CHANGED,
    InfoFlag.IGNORED_DELTA_CHANGED,
    InfoFlag.DESYNC,
]


def process_diff(diff: TraceEntryDiff) -> List[InfoFlag]:
    # if not diff.has_any_dfference():
    #     return []

    # Only process actually significant differences
    if not diff.has_any_dfference(ignore_dma_value=True):
        return []

    flags: List[InfoFlag] = list()
    if not (diff.pc_diff or diff.address_diff):
        # The pc and address are the same, it is either value or deltas or both.
        num_dma_1 = len(diff.async_deltas[0])
        num_dma_2 = len(diff.async_deltas[1])
        if num_dma_1 != num_dma_2:
            # The presence of DMA was changed.
            if num_dma_1 == 0:
                # Originally no DMA, now there is
                flags.append(InfoFlag.UNEXPECTED_NEW_DMA)
            elif num_dma_2 == 0:
                # Originally there was DMA, now there isn't.
                flags.append(InfoFlag.MISSING_OLD_DMA)
            else:
                # The exact number of DMA changed.
                pass
        else:
            # DMA did not change, it must be ignored deltas or the content value.
            if diff.value_diff:
                flags.append(InfoFlag.VALUE_CHANGED)
            else:
                flags.append(InfoFlag.IGNORED_DELTA_CHANGED)

    else:
        # It is either the PC or the address that changed, which means a desync from the trace.
        flags.append(InfoFlag.DESYNC)

    return flags


def test_entry_address_matches(entry: TraceEntry, test_value: int) -> bool:
    new_incidence_address = min([x.address for x in entry.async_deltas])
    if new_incidence_address == test_value:
        return True
    return False


def find_first_incidence_with_dma_at_addr(run_dir: str, test_value: int) -> Optional[TraceEntry]:
    new_trace: ExecutionTrace = ExecutionTrace.from_file(os.path.join(run_dir, trace_logging.RECORDING_JSON))
    new_first_incidence = static_find_first_dma_incidence(new_trace)
    if new_first_incidence is None:
        return None

    if test_entry_address_matches(new_first_incidence, test_value):
        return new_first_incidence

    print("Warning, DMA may have occurred in a different configuration")
    for entry in new_trace.entries:
        if len(entry.async_deltas) > 0:
            if test_entry_address_matches(entry, test_value):
                print("Another entry does have the target value.")
                return entry

    return None


def test_entry_size_matches(entry: TraceEntry, test_value: int, prior_value: int) -> bool:
    delta_addresses = [x.address for x in entry.async_deltas]
    new_incidence_size = max(delta_addresses) - min(delta_addresses)

    # Exact matches are likely good
    if new_incidence_size == test_value:
        return True

    # Exactly the old value likely means no change at all
    if new_incidence_size == prior_value:
        return False

    # Check if it is closer to the test value than the prior value
    max_offset = abs(prior_value - test_value) / 2

    actual_offset = abs(new_incidence_size - test_value)
    if actual_offset <= max_offset:
        return True
    else:
        # Either we are closer to the prior value, or too far away from both.
        return False


def find_first_incidence_with_dma_of_size(run_dir, test_value, prior_value) -> Optional[TraceEntry]:
    new_trace: ExecutionTrace = ExecutionTrace.from_file(os.path.join(run_dir, trace_logging.RECORDING_JSON))
    new_first_incidence = static_find_first_dma_incidence(new_trace)
    if new_first_incidence is None:
        return None

    if test_entry_size_matches(new_first_incidence, test_value, prior_value):
        return new_first_incidence

    print("Warning, DMA may have occurred in a different configuration")
    for entry in new_trace.entries:
        if len(entry.async_deltas) > 0:
            if test_entry_size_matches(entry, test_value, prior_value):
                print("Another entry does have the target value.")
                return entry

    return None


def test_no_dma_near_addr_and_size(run_dir, original_address, original_size):
    """ Returns True IFF no dma was found matching either size or address"""
    new_trace: ExecutionTrace = ExecutionTrace.from_file(os.path.join(run_dir, trace_logging.RECORDING_JSON))
    for entry in new_trace.entries:
        if len(entry.async_deltas) == 0:
            # This entry has no DMA, check the next
            continue

        # As we haven't yet left, there is some DMA, check its addr and size.
        if test_entry_address_matches(entry, original_address):
            print("Found DMA at original address, assuming cancel failed.")
            return False
        # TODO add a flag to disable this
        if test_entry_size_matches(entry, original_size, original_size * 1.25):
            print("Found DMA near the original size, assuming cancel failed.")
            return False

    return True


def recap_results(addr_entry, size_entry, start_entries):
    print("Results recap")
    print("Addr result:")
    print(None if addr_entry is None else [addr_entry[0].__dict__, addr_entry[1].__dict__])
    print("Size result:")
    print(None if size_entry is None else [size_entry[0].__dict__, size_entry[1].__dict__])
    print("Start result:")
    for entry in start_entries:
        print(entry.__dict__)


class InstanceRunner:
    dma_info: DmaInfo
    peripheral_info: PeripheralRow

    trigger_candidates: List[int]
    set_base_candidates: List[int]
    set_size_candidates: List[int]

    openocd_cfg: str
    abort_grace_steps: int
    limit_by_pc: bool
    ram_area: Tuple[int, int]
    intercept_area: Tuple[int, int]
    work_dir: str

    dma_info_path: str

    subprocesses: Dict[str, Popen]

    def __init__(self, dma_info: DmaInfo, dma_info_path: str, peripheral_info: PeripheralRow, openocd_cfg: str,
                 grace_steps: int,
                 limit_by_pc: bool, ram_area: Tuple[int, int], intercept_area: Tuple[int, int], work_dir: str):

        if dma_info.index_of_first_incidence == -1:
            print("No Dma found in earlier step, cancelling current step.")
            exit()

        self.dma_info = dma_info
        self.peripheral_info = peripheral_info

        self.trigger_candidates = dma_info.indices_of_trigger_instructions
        self.set_base_candidates = dma_info.indices_of_set_base_instructions
        self.set_size_candidates = dma_info.indices_of_set_size_instructions

        # self.trigger_instruction = TraceEntry.from_dict(start_candidate, None)
        # self.set_addr_options = [TraceEntry.from_dict(x, None) for x in dma_info['set_addr_alternatives']]
        # self.set_size_options = [TraceEntry.from_dict(x, None) for x in dma_info['set_size_alternatives']]

        self.openocd_cfg = openocd_cfg
        self.abort_grace_steps = grace_steps
        self.limit_by_pc = limit_by_pc
        self.ram_area = ram_area
        self.intercept_area = intercept_area
        self.work_dir = work_dir

        self.subprocesses = dict()
        signal.signal(signal.SIGINT, self.kill_subprocesses)
        signal.signal(signal.SIGTERM, self.kill_subprocesses)

        self.dma_info_path = dma_info_path

    def kill_subprocesses(self, sig, frame):
        print("\tAttempting to kill sub-runs")
        process: Popen
        for name, process in self.subprocesses.items():
            print("\t\tRequesting `%s` to terminate." % name)
            process.terminate()
        if len(self.subprocesses) == 0:
            print("\t\tNo children found")

        for name, process in self.subprocesses.items():
            if process.poll():
                print("\t\tForcibly killing `%s`" % name)
                process.kill()

        exit(-sig)

    # noinspection DuplicatedCode
    def run_a_run(self, name, peripheral_address, new_value: Optional[int] = 0x1337):
        run_dir = os.path.join(self.work_dir, "run_%s/" % name)
        # return run_dir

        if not os.path.exists(run_dir):
            os.mkdir(run_dir)

        if peripheral_address % 4 == 0:
            size = 4
        elif peripheral_address % 2 == 0:
            size = 2
        else:
            # This address is not aligned
            size = 1
        # TODO make sure 4 bytes is ok.
        # TODO if aligned to 4 bytes use 4 bytes, if fewer, use fewer.
        if new_value is None:
            shim_regions = json.dumps([])
            mock_regions = json.dumps([
                (peripheral_address, size),
            ])
        else:
            mock_regions = json.dumps([])
            shim_regions = json.dumps([
                (peripheral_address, size, new_value),
            ])

        parameters = [
            'python', './phases/recorder/run_once_wrapper.py',
            self.openocd_cfg,  # OpenOCD configuration
            str(self.ram_area[0]), str(self.ram_area[1]),  # RAM definition (snapshotting)
            str(self.intercept_area[0]), str(self.intercept_area[1]),  # Peripheral area (for MPU protecting)
            mock_regions,  # Shadow ban this peripheral
            shim_regions,  # Shadow ban this peripheral
            self.dma_info_path,  # Path to the OG trace
            str(self.abort_grace_steps),  # Grace steps
            str(True),  # Abort after deviating from the trace
            str(False),  # Do not abort after DMA (pc covers this)
            str(-1),  # Do not abort after loops (pc covers this)

            # For the first iteration we assume the PC is only visited once by the triggering instruction.
            str(self.dma_info.entry_of_first_incidence.pc) if self.limit_by_pc else str(-1),
            str(-1) if self.limit_by_pc else str(self.dma_info.index_of_first_incidence),

            # Alternatively abort at the index where we assume DMA to begin
            # -1,
            # trigger_instruction['index'],

            str(30),  # Wait for at most 30s per step
            run_dir,
            '--poison'
        ]
        restart_connected_devices()
        current_proc = Popen(parameters)
        self.subprocesses[name] = current_proc
        current_proc.wait()
        del self.subprocesses[name]

        return run_dir

    # def get_new_entry(self, run_dir) -> Optional[TraceEntry]:
    #     target_index = self.trigger_instruction.index
    #     trace_path = os.path.join(run_dir, trace_logging.RECORDING_CSV)
    #     dumps_path = os.path.join(run_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
    #     et = ExecutionTrace.from_csv(trace_path, dumps_path)
    #     if target_index >= len(et.__execution_trace):
    #         return None
    #     new_te: TraceEntry = et.__execution_trace[target_index]
    #     if new_te.index != target_index:
    #         raise Exception("No!")
    #     return new_te

    def figure_out_test(self):
        run_name = "test"
        run_dir = self.run_a_run(run_name, -10, new_value=-1)
        trace_path = os.path.join(run_dir, trace_logging.RECORDING_JSON)
        trace = ExecutionTrace.from_file(trace_path)
        diff = self.get_trace_diff(trace)

        fail = False
        for flag, state in diff.items():
            if state:
                print("Test run Failure caused by %s" % flag.name)
                fail = True
        if fail:
            raise Exception("Test run failed sanity check.")
        return trace

    def figure_out_addr(self, fast=True) -> List[Tuple[int, TraceEntry]]:
        """ Where the first returned value is the Trace Entry that was modified to test and the second is the
        resulting first incidence """
        already_processed_addresses: List[int] = []
        candidate: TraceEntry
        valid_entries = []
        for candidate_index in reversed(self.set_base_candidates):
            candidate = self.dma_info.execution_trace.entries[candidate_index]
            run_addr = candidate.address
            if run_addr in already_processed_addresses:
                continue

            already_processed_addresses.append(run_addr)

            run_name = "set_addr_x%08X" % candidate.address
            test_value = candidate.value + 0x4

            run_dir = self.run_a_run(run_name, run_addr, new_value=test_value)
            new_first_incidence = find_first_incidence_with_dma_at_addr(run_dir, test_value)
            if new_first_incidence is not None:
                valid_entries.append((candidate_index, candidate))
                if fast:
                    return valid_entries
        return valid_entries

    def figure_out_size(self, fast=True) -> List[Tuple[int, TraceEntry]]:
        """
        Fast true causes early return on first valid value
        Fast false will process all possible options
        """
        already_processed_addresses: List[int] = []
        candidate: TraceEntry
        valid_entries = []
        for candidate_index in reversed(self.set_size_candidates):
            candidate = self.dma_info.execution_trace.entries[candidate_index]
            run_addr = candidate.address
            if run_addr in already_processed_addresses:
                continue

            already_processed_addresses.append(run_addr)

            run_name = "set_size_x%08X" % candidate.address
            if -64 <= candidate.value <= 64:
                test_value = candidate.value * 2
            else:
                test_value = candidate.value * 2

            run_dir = self.run_a_run(run_name, run_addr, new_value=test_value)
            prior_size = self.dma_info.dma_region_size
            new_first_incidence = find_first_incidence_with_dma_of_size(run_dir, test_value, prior_size)
            if new_first_incidence is not None:
                valid_entries.append((candidate_index, candidate))
                if fast:
                    return valid_entries
        return valid_entries

    def figure_out_start(self) -> List[Tuple[int, TraceEntry]]:
        already_processed_addresses: List[int] = []
        results: List[Tuple[int, TraceEntry]] = list()

        # sources = self.dma_info.execution_trace.entries[:self.dma_info.index_of_first_incidence + 1]
        # indexed_sources = enumerate(sources)
        # reversed_indexed_sources = reversed(list(indexed_sources))

        for candidate_index in self.trigger_candidates:
            candidate = self.dma_info.execution_trace.entries[candidate_index]
            if candidate.address in already_processed_addresses:
                continue

            already_processed_addresses.append(candidate.address)

            print(candidate_index)
            if self.process_single_start_candidate(candidate):
                results.append((candidate_index, candidate))

        return results

    def process_single_start_candidate(self, candidate):
        run_name = "test_start_x%08X" % candidate.address

        # test_value = candidate.value & (~0x1)
        run_dir = self.run_a_run(run_name, candidate.address, new_value=None)
        if test_no_dma_near_addr_and_size(run_dir, self.dma_info.dma_region_base, self.dma_info.dma_region_size):
            return True
        return False

    def start(self):
        # Perform a clean run to check for system sanity
        trace = self.figure_out_test()
        print("Test result:")
        print(None if trace is None else trace)

        self.populate_triggers()
        self.filter_out_irrelevant_peripherals()

        verified_base_set_entries: List[Tuple[int, TraceEntry]] = self.process_addr()
        verified_size_set_entries: List[Tuple[int, TraceEntry]] = self.process_size()
        verified_triggering_entries: List[Tuple[int, TraceEntry]] = self.process_triggers()

        verified_bse_indices = [x for x, y in verified_base_set_entries]
        self.dma_info.indices_of_set_base_instructions = verified_bse_indices
        verified_sse_indices = [x for x, y in verified_size_set_entries]
        self.dma_info.indices_of_set_size_instructions = verified_sse_indices

        self.dma_info.indices_of_trigger_instructions = [
            x for x, y in verified_triggering_entries
            if x not in verified_bse_indices and x not in verified_sse_indices
        ]

        out_path = os.path.join(self.work_dir, naming_things.DMA_INFO_JSON)
        DmaInfo.to_file(out_path, self.dma_info)

        out_path = os.path.join(self.work_dir, naming_things.DMA_INFO_HR_JSON)
        DmaInfo.to_file(out_path, self.dma_info, max_depth=DmaInfo.MAX_DEPTH_HR)

    def process_triggers(self):
        # Finally, even more unlikely try the triggering entries.
        start_entries = self.figure_out_start()
        print("Start result:")
        for entry in start_entries:
            print(entry)
        return start_entries

    def process_size(self):
        # While this will not always work, try the size entry
        verified_size_set_entries = self.figure_out_size()
        print("Size result:")
        if len(verified_size_set_entries) == 0:
            print("\tNo results")
        else:
            for index, entry in verified_size_set_entries:
                print("\t%d: %s", index, entry.__dict__)
        return verified_size_set_entries

    def process_addr(self):
        # First do the easy one, figure out which of the potential addr-setting instructions is 'the one'
        verified_base_set_entries = self.figure_out_addr()
        print("Addr result:")
        if len(verified_base_set_entries) == 0:
            print("\tNo results")
        else:
            for index, entry in verified_base_set_entries:
                print("\t%d: %s", index, entry.__dict__)
        return verified_base_set_entries

    def get_trace_diff(self, trace: ExecutionTrace) -> Dict[InfoFlag, bool]:
        accumulator: Dict[InfoFlag, bool] = dict()
        for flag in InfoFlag:
            accumulator[flag] = False

        for te_original, te_current in zip(self.dma_info.execution_trace.entries, trace.entries):
            diff: TraceEntryDiff = te_original.difference_with(te_current)
            flags: List[InfoFlag] = process_diff(diff)
            for flag in flags:
                accumulator[flag] = True

        length_list = [len(x.execution_trace.entries) for x in self.peripheral_info.peripherals]
        length_list.append(len(self.dma_info.execution_trace.entries))
        current_trace_length = len(trace.entries)
        length_list.append(current_trace_length)

        length_mean = float(numpy.mean(length_list))
        length_std = float(numpy.std(length_list))
        lb = length_mean - length_std
        ub = length_mean + length_std

        if current_trace_length < lb:
            accumulator[InfoFlag.TERMINATED_EARLY] = True
        elif current_trace_length > ub:
            accumulator[InfoFlag.TERMINATED_LATE] = True

        return accumulator

    def filter_out_irrelevant_peripherals(self):
        # TODO refresh memory on why this is written the way it is written. It seems the wrong way around but it works?
        for peripheral in self.peripheral_info.peripherals:
            if peripheral.has_one_of_flags(LIST_OF_EXECUTION_AFFECTING_FLAGS):
                # This peripheral has changed execution somehow
                print("Dumping a peripheral")
                len1 = len(self.set_base_candidates)
                self.set_base_candidates = [
                    x for x in self.set_base_candidates
                    if not (peripheral.start <= self.dma_info.execution_trace.entries[x].address < peripheral.end)
                ]
                len2 = len(self.set_base_candidates)
                if len1 != len2:
                    print("Set base candidates reduced from %d to %d" % (len1, len2))

                len1 = len(self.set_size_candidates)
                self.set_size_candidates = [
                    x for x in self.set_size_candidates
                    if not (peripheral.start <= self.dma_info.execution_trace.entries[x].address < peripheral.end)
                ]
                len2 = len(self.set_size_candidates)
                if len1 != len2:
                    print("Set size candidates reduced from %d to %d" % (len1, len2))

                len1 = len(self.trigger_candidates)
                self.trigger_candidates = [
                    x for x in self.trigger_candidates
                    if not (peripheral.start <= self.dma_info.execution_trace.entries[x].address < peripheral.end)
                ]
                len2 = len(self.trigger_candidates)
                if len1 != len2:
                    print("Trigger candidates reduced from %d to %d" % (len1, len2))

    def populate_triggers(self):
        self.trigger_candidates = list(range(self.dma_info.index_of_first_incidence, -1, -1))


# noinspection DuplicatedCode
def main():
    # region Parse arguments
    parser = argparse.ArgumentParser()

    # parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")
    parser.add_argument('peripheral_dir', type=str, help="Path to the directory with the peripheral analysis results.")

    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('work_dir', type=str, help="Working directory.")

    parser.add_argument('--grace', dest='abort_grace_steps', type=int, default=5,
                        help="Keep recording this many steps after aborts.")

    # TODO perhaps make an argument
    limit_by_pc = False

    args = parser.parse_args()
    # endregion

    dma_info_file = os.path.join(args.analysis_dir, naming_things.DMA_INFO_JSON)
    dma_info: DmaInfo = DmaInfo.from_file(dma_info_file)

    # trace_path = os.path.join(args.recording_dir, trace_logging.RECORDING_JSON)

    peripheral_info_path = os.path.join(args.peripheral_dir, naming_things.PERIPHERAL_JSON_NAME)
    peripheral_info: PeripheralRow = PeripheralRow.from_file(peripheral_info_path)

    ram_area = (args.ram_start, args.ram_size)
    intercept_area = (args.intercept_start, args.intercept_size)

    runner: InstanceRunner = InstanceRunner(dma_info, dma_info_file, peripheral_info, args.openocd_cfg,
                                            args.abort_grace_steps,
                                            limit_by_pc, ram_area, intercept_area, args.work_dir)
    runner.start()
    print("Done runner")


if __name__ == '__main__':
    main()
