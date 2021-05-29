import argparse
import os
from typing import List, Tuple

import numpy

from phases.analyzer import DmaInfo, PeripheralRow, Peripheral, InfoFlag
from phases.recorder import ExecutionTrace, TraceEntry, trace_logging
from utilities import auto_int, naming_things


def contemplate_differences(peripheral: Peripheral, step_number: int, diff):
    if not diff.has_any_dfference(ignore_dma_value=True):
        print("Differences in step no %04d limited to the I/O value of deltas." % step_number)
        return

    print("Differences in step no %04d:" % step_number)
    # There is a difference, and it is not just the DMA values.
    if not (diff.pc_diff or diff.address_diff):
        # The pc and address are the same, it is either value or deltas or both.
        num_dma_1 = len(diff.async_deltas[0])
        num_dma_2 = len(diff.async_deltas[1])
        if num_dma_1 != num_dma_2:
            # The presence of DMA was changed.
            if num_dma_1 == 0:
                # Originally no DMA, now there is
                peripheral.flag(InfoFlag.UNEXPECTED_NEW_DMA)
            elif num_dma_2 == 0:
                # Originally there was DMA, now there isn't.
                peripheral.flag(InfoFlag.MISSING_OLD_DMA)
            else:
                # The exact number of DMA changed.
                pass
        else:
            # DMA did not change, it must be ignored deltas or the content value.
            if diff.value_diff:
                peripheral.flag(InfoFlag.VALUE_CHANGED)
            else:
                peripheral.flag(InfoFlag.IGNORED_DELTA_CHANGED)

    else:
        # It is either the PC or the address that changed, which means a desync from the trace.
        peripheral.flag(InfoFlag.DESYNC)



class PeripheralAnalyzer:
    dma_info: DmaInfo
    peripheral_row: PeripheralRow
    dummy_peripheral: Peripheral

    ram_base: int
    work_dir: str

    def __init__(self, dma_info: DmaInfo, peripheral_row: PeripheralRow, dummy_peripheral: Peripheral, ram_base: int,
                 work_dir: str):
        self.dma_info = dma_info
        self.peripheral_row = peripheral_row
        self.dummy_peripheral = dummy_peripheral

        self.ram_base = ram_base
        self.work_dir = work_dir

    def start(self):

        self._debug_print_instances_of_dma()

        self.analyse_run_length()

        global_trace_entries = self.dma_info.execution_trace.entries
        global_trace_length = len(global_trace_entries)

        for peripheral in self.peripheral_row.peripherals:
            print("Peripheral global info: 0x%X" % peripheral.start)

            current_trace_entries = peripheral.execution_trace.entries
            current_trace_length = len(current_trace_entries)

            lesser_trace_length = min(global_trace_length, current_trace_length)
            for i in range(lesser_trace_length):
                global_entry: TraceEntry = global_trace_entries[i]
                current_entry: TraceEntry = current_trace_entries[i]
                trace_diff = global_entry.difference_with(current_entry)
                if trace_diff.has_any_dfference():
                    contemplate_differences(peripheral, i, trace_diff)

            if global_trace_length > lesser_trace_length:
                spare_entries = global_trace_length - lesser_trace_length
                print("Did not process %d remaining entries in the full trace." % spare_entries)
            if current_trace_length > lesser_trace_length:
                spare_entries = current_trace_length - lesser_trace_length
                print("Did not process %d remaining entries in the current trace." % spare_entries)

            print("\n")

        # TODO is this a good idea?
        self.peripheral_row.append(self.dummy_peripheral)
        peripheral_out_file = os.path.join(self.work_dir, naming_things.PERIPHERAL_JSON_NAME)
        PeripheralRow.to_file(peripheral_out_file, self.peripheral_row)

        peripheral_out_file = os.path.join(self.work_dir, naming_things.PERIPHERAL_JSON_HR_NAME)
        PeripheralRow.to_file(peripheral_out_file, self.peripheral_row, max_depth=PeripheralRow.HUMAN_READABLE_DEPTH)

    def analyse_run_length(self):
        length_list = [len(x.execution_trace.entries) for x in self.peripheral_row.peripherals]
        length_list.append(len(self.dummy_peripheral.execution_trace.entries))
        length_list.append(len(self.dma_info.execution_trace.entries))
        length_mean = float(numpy.mean(length_list))
        length_std = float(numpy.std(length_list))
        lb = length_mean - length_std
        ub = length_mean + length_std
        for peripheral in self.peripheral_row.peripherals:
            print("Peripheral run at address: 0x%X" % peripheral.start)
            if len(peripheral.execution_trace.entries) < lb:
                peripheral.flag(InfoFlag.TERMINATED_EARLY)
            if len(peripheral.execution_trace.entries) > ub:
                peripheral.flag(InfoFlag.TERMINATED_LATE)
            print("\n")

    def _debug_print_instances_of_dma(self):
        global_trace_entries = self.dma_info.execution_trace.entries

        print("The full trace contains DMA-like behaviour in the following steps:")
        global_trace_entries_with_dma = [x for x in global_trace_entries if len(x.async_deltas) > 0]
        for indexed_entry in global_trace_entries_with_dma:
            ete_index = global_trace_entries.index(indexed_entry)
            print("\t - %d" % ete_index)
        print("\n")
        for p in self.peripheral_row.peripherals:
            print("The trace for the peripheral at address x%08X has DMA-like behaviour in:" % p.start)
            indexed_dma_entries: List[Tuple[int, TraceEntry]] = [
                (i, x) for i, x in enumerate(p.execution_trace.entries) if len(x.async_deltas) > 0
            ]
            for indexed_entry in indexed_dma_entries:
                print("\t - %d" % indexed_entry[0])
            print("\n")


# noinspection DuplicatedCode
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")
    parser.add_argument('peripheral_recording_dir', type=str, help="Path to the directory with peripheral recordings")
    parser.add_argument('ram_base', type=auto_int, help="Base address (offset) of the start of the dump snapshots.")
    parser.add_argument('work_dir', type=str, help="Working directory.")

    args = parser.parse_args()

    dma_info_path = os.path.join(args.analysis_dir, naming_things.DMA_INFO_JSON)
    global_dma_info: DmaInfo = DmaInfo.from_file(dma_info_path)

    peripheral_path = os.path.join(args.analysis_dir, naming_things.PERIPHERAL_JSON_NAME)
    peripheral_row: PeripheralRow = PeripheralRow.from_file(peripheral_path)

    if not os.path.exists(args.work_dir):
        os.mkdir(args.work_dir)

    if not os.path.isdir(args.work_dir):
        raise Exception("%s is not a directory." % args.work_dir)

    peripheral: Peripheral
    for peripheral in peripheral_row.peripherals:
        peripheral_address = peripheral.start
        run_name = naming_things.create_peripheral_run_name(peripheral_address)
        run_dir = os.path.join(args.peripheral_recording_dir, run_name + "/")

        peripheral_trace_path = os.path.join(run_dir, trace_logging.RECORDING_JSON)
        peripheral_trace: ExecutionTrace = ExecutionTrace.from_file(peripheral_trace_path)
        peripheral.execution_trace = peripheral_trace

        exit_reason_path = os.path.join(run_dir, naming_things.EXIT_REASON_FILE)
        with open(exit_reason_path, mode='r') as exit_file:
            for line in exit_file.readlines():
                peripheral.append_exit_reason(line.strip())

    dummy_peripheral = Peripheral(-1, -1)
    test_run_dir = os.path.join(args.peripheral_recording_dir, "test_run/")
    peripheral_trace_path = os.path.join(test_run_dir, trace_logging.RECORDING_JSON)
    peripheral_trace: ExecutionTrace = ExecutionTrace.from_file(peripheral_trace_path)
    dummy_peripheral.execution_trace = peripheral_trace

    exit_reason_path = os.path.join(test_run_dir, naming_things.EXIT_REASON_FILE)
    with open(exit_reason_path, mode='r') as exit_file:
        for line in exit_file.readlines():
            dummy_peripheral.append_exit_reason(line.strip())

    a = PeripheralAnalyzer(global_dma_info, peripheral_row, dummy_peripheral, args.ram_base, args.work_dir)
    a.start()


if __name__ == '__main__':
    main()
