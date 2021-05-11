import argparse
import json
import os.path
import signal
from subprocess import Popen
from typing import Dict, Tuple, List, Optional

from phases.recorder import TraceEntry, ExecutionTrace
from utilities import auto_int, naming_things, logging, parse_dma_info, csv_reset, restart_connected_devices


def same_instruction(i1, i2):
    return i1.index == i2.index and \
           i1.value == i2.value and \
           len(i1.mem_delta) == len(i2.mem_delta) and \
           i1.addr == i2.addr and \
           i1.pc == i2.pc


class InstanceRunner:
    trigger_instruction: TraceEntry
    set_addr_options: List[TraceEntry]
    set_size_options: List[TraceEntry]
    subprocesses: Dict[str, Popen]

    def __init__(self, dma_info: dict, original_trace_path: str, openocd_cfg: str, grace_steps: int, limit_by_pc: bool,
                 ram_area: Tuple[int, int], intercept_area: Tuple[int, int], work_dir: str):
        start_candidate = dma_info['start_instruction']
        if start_candidate is None:
            print("No DMA found, exiting")
            exit()
        self.trigger_instruction = TraceEntry.from_dict(start_candidate, None)
        self.set_addr_options = [TraceEntry.from_dict(x, None) for x in dma_info['set_addr_alternatives']]
        self.set_size_options = [TraceEntry.from_dict(x, None) for x in dma_info['set_size_alternatives']]

        self.original_recording_path = original_trace_path
        self.abort_grace_steps = grace_steps
        self.limit_by_pc = limit_by_pc

        self.openocd_cfg = openocd_cfg
        self.ram_area = ram_area
        self.intercept_area = intercept_area
        self.work_dir = work_dir

        self.subprocesses = dict()
        signal.signal(signal.SIGINT, self.kill_subprocesses)
        signal.signal(signal.SIGTERM, self.kill_subprocesses)

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
    def run_a_run(self, name, peripheral_address, new_value=0x1337):
        run_dir = os.path.join(self.work_dir, "run_%s/" % name)
        return run_dir

        if not os.path.exists(run_dir):
            os.mkdir(run_dir)
        csv_reset(run_dir)
        mock_regions = json.dumps([])
        # TODO make sure 4 bytes is ok.
        shim_regions = json.dumps([(peripheral_address, 4, new_value)])

        parameters = [
            'python', './phases/recorder/run_once_wrapper.py',
            self.openocd_cfg,  # OpenOCD configuration
            str(self.ram_area[0]), str(self.ram_area[1]),  # RAM definition (snapshotting)
            str(self.intercept_area[0]), str(self.intercept_area[1]),  # Peripheral area (for MPU protecting)
            mock_regions,  # Shadow ban this peripheral
            shim_regions,  # Shadow ban this peripheral
            self.original_recording_path,  # Path to the OG trace
            str(self.abort_grace_steps),  # Grace steps
            str(True),  # Abort after deviating from the trace
            str(False),  # Do not abort after DMA (pc covers this)
            str(-1),  # Do not abort after loops (pc covers this)

            # For the first iteration we assume the PC is only visited once by the triggering instruction.
            str(self.trigger_instruction.pc) if self.limit_by_pc else str(-1),
            str(-1) if self.limit_by_pc else str(self.trigger_instruction.index),

            # Alternatively abort at the index where we assume DMA to begin
            # -1,
            # trigger_instruction['index'],

            str(30),  # Wait for at most 30s per step
            run_dir,
            '--poison'
        ]
        # TODO check if we need to reboot?
        current_proc = Popen(parameters)
        self.subprocesses[name] = current_proc
        current_proc.wait()
        del self.subprocesses[name]

        return run_dir

    def get_new_entry(self, run_dir) -> Optional[TraceEntry]:
        target_index = self.trigger_instruction.index
        trace_path = os.path.join(run_dir, logging.RECORDING_CSV)
        dumps_path = os.path.join(run_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
        et = ExecutionTrace.from_csv(trace_path, dumps_path)
        if target_index >= len(et.entries):
            return None
        new_te: TraceEntry = et.entries[target_index]
        if new_te.index != target_index:
            raise Exception("No!")
        return new_te

    def figure_out_test(self):
        run_name = "test"
        run_dir = self.run_a_run(run_name, -10, new_value=-1)
        new_trigger_instruction = self.get_new_entry(run_dir)
        if not same_instruction(self.trigger_instruction, new_trigger_instruction):
            raise Exception("Test run failed sanity check.")
        return new_trigger_instruction

    def addr_changed_to(self, run_dir: str, test_value: int) -> Optional[TraceEntry]:
        new_trigger_te = self.get_new_entry(run_dir)
        if new_trigger_te is None:
            return None
        mem_delta = new_trigger_te.mem_delta
        if len(mem_delta) > 0:
            start_addr = min([x[0] for x in mem_delta]) + self.ram_area[0]
            if start_addr == test_value:
                return new_trigger_te
        return None

    def figure_out_addr(self) -> Optional[TraceEntry]:
        already_processed_addresses: List[int] = []
        candidate: TraceEntry
        for candidate in reversed(self.set_addr_options):
            run_name = "set_addr_%d" % candidate.index
            test_value = candidate.value + 0x4
            run_addr = candidate.addr
            if run_addr in already_processed_addresses:
                continue

            run_dir = self.run_a_run(run_name, run_addr, new_value=test_value)
            new_te = self.addr_changed_to(run_dir, test_value)
            if new_te is not None:
                return new_te
        return None

    def size_changed_to(self, run_dir: str, test_value: int) -> bool:
        new_trigger_te = self.get_new_entry(run_dir)
        if new_trigger_te is None:
            return False

        mem_delta = new_trigger_te.mem_delta
        if len(mem_delta) == test_value:
            return True
        return False

    def figure_out_size(self) -> Optional[TraceEntry]:
        already_processed_addresses: List[int] = []
        candidate: TraceEntry
        for candidate in reversed(self.set_size_options):
            run_name = "set_size_%d" % candidate.index
            test_value = candidate.value * 2
            run_addr = candidate.addr
            if run_addr in already_processed_addresses:
                continue

            run_dir = self.run_a_run(run_name, run_addr, new_value=test_value)
            if self.size_changed_to(run_dir, test_value):
                return candidate
        return None

    def dma_now_disabled(self, run_dir):
        new_trigger_te = self.get_new_entry(run_dir)
        if new_trigger_te is None:
            return False
        if len(new_trigger_te.mem_delta) == 0:
            return True
        return False

    def figure_out_start(self):
        full_trace = ExecutionTrace.from_csv(self.original_recording_path, None)
        already_processed_addresses: List[int] = []
        candidate: TraceEntry
        for candidate in reversed(full_trace.entries[0:self.trigger_instruction.index]):
            run_name = "test_start_%d" % candidate.index

            # TODO is this aggressive enough
            test_value = candidate.value & (~0x1)
            run_addr = candidate.addr
            if run_addr in already_processed_addresses:
                continue

            run_dir = self.run_a_run(run_name, run_addr, new_value=test_value)
            if self.dma_now_disabled(run_dir):
                return candidate

    def start(self):
        # Perform a clean run to check for system sanity
        # restart_connected_devices()
        # test_entry = self.figure_out_test()
        # print(TraceEntry.to_dict(test_entry))

        # First do the easy one, figure out which of the potential addr-setting instructions is 'the one'
        restart_connected_devices()
        addr_entry = self.figure_out_addr()
        print(TraceEntry.to_dict(addr_entry))

        restart_connected_devices()
        size_entry = self.figure_out_size()
        print(TraceEntry.to_dict(size_entry))

        restart_connected_devices()
        start_entry = self.figure_out_start()
        print(TraceEntry.to_dict(start_entry))


# noinspection DuplicatedCode
def main():
    # region Parse arguments
    parser = argparse.ArgumentParser()

    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")

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
    dma_info = parse_dma_info(dma_info_file)

    trace_path = os.path.join(args.recording_dir, logging.RECORDING_CSV)

    ram_area = (args.ram_start, args.ram_size)
    intercept_area = (args.intercept_start, args.intercept_size)

    runner: InstanceRunner = InstanceRunner(dma_info, trace_path, args.openocd_cfg, args.abort_grace_steps, limit_by_pc,
                                            ram_area, intercept_area, args.work_dir)
    runner.start()
    print("Done runner")


if __name__ == '__main__':
    main()
