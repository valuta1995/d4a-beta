import argparse
import json
import os
from typing import List, Dict, Optional

from phases.recorder import ExecutionTrace, TraceEntry
from utilities import auto_int, naming_things, logging, parse_dma_info, parse_peripherals


class PeripheralAnalyzer:

    def __init__(self, full_trace: ExecutionTrace, dma_info: dict, peripherals: List[Dict[str, any]], ram_base: int,
                 work_dir: str):
        self.full_trace = full_trace
        self.dma_info = dma_info
        self.peripherals = peripherals
        self.ram_base = ram_base
        self.work_dir = work_dir

    def start(self):
        ft_entries = self.full_trace.entries
        ft_length = len(ft_entries)

        print("Full trace")
        etes_with_dma = [x for x in ft_entries if len(x.async_memory_deltas) > 0]
        for ete in etes_with_dma:
            print(ete.index)
        print("Done ---\n\n")

        for p in self.peripherals:
            print("Peripheral trace %d" % p['index'])
            etes_with_dma = [x for x in p['trace'].entries if len(x.async_memory_deltas) > 0]
            for ete in etes_with_dma:
                print(ete.index)
            print("Done ---\n\n")

        for p in self.peripherals:
            print("Comparing the trace of peripheral %d." % p['index'])
            ct_entries = p['trace'].entries
            ct_length = len(ct_entries)
            lowest_limit = min(ft_length, ct_length)

            for i in range(lowest_limit):
                fte: TraceEntry = ft_entries[i]
                fte_dict = fte.__dict__.copy()
                fte_dict['mem_delta'] = len(fte_dict['mem_delta'])

                cte: TraceEntry = ct_entries[i]
                cte_dict = cte.__dict__.copy()
                cte_dict['mem_delta'] = len(cte_dict['mem_delta'])

                symmetric_difference: set = fte_dict.items() ^ cte_dict.items()
                if len(symmetric_difference) > 0:
                    # info = json.dumps(list(symmetric_difference), sort_keys=True, indent=4)
                    print("Step no %04d: %s" % (i, symmetric_difference))

            if ft_length > lowest_limit:
                print("Did not process %d remaining entries in the full trace." % (ft_length - lowest_limit))

            if ct_length > lowest_limit:
                print("Did not process %d remaining entries in the current trace." % (ct_length - lowest_limit))

            print("\n\n")

        pass


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")
    parser.add_argument('peripheral_recording_dir', type=str, help="Path to the directory with peripheral recordings")
    parser.add_argument('ram_base', type=auto_int, help="Base address (offset) of the start of the dump snapshots.")
    parser.add_argument('work_dir', type=str, help="Working directory.")

    args = parser.parse_args()
    dump_dir = os.path.join(args.recording_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
    recording_csv = os.path.join(args.recording_dir, logging.RECORDING_CSV)
    vanilla_trace: ExecutionTrace = ExecutionTrace.from_csv(recording_csv, dumps_dir=dump_dir)

    dma_info = parse_dma_info(os.path.join(args.analysis_dir, naming_things.DMA_INFO_JSON))
    peripherals = parse_peripherals(os.path.join(args.analysis_dir, naming_things.PERIPHERAL_CSV_NAME), add_dummy=True)

    if not os.path.exists(args.work_dir):
        os.mkdir(args.work_dir)

    if not os.path.isdir(args.work_dir):
        raise Exception("%s is not a directory." % args.work_dir)

    for peripheral in peripherals:
        current_index = peripheral['index']
        run_name = "run_%04d" % current_index
        run_dir = os.path.join(args.peripheral_recording_dir, run_name + "/")
        peripheral_dump_dir = os.path.join(run_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
        peripheral_recording_csv = os.path.join(run_dir, logging.RECORDING_CSV)
        if os.path.exists(peripheral_recording_csv):
            current_trace = ExecutionTrace.from_csv(peripheral_recording_csv, peripheral_dump_dir)
            peripheral['trace'] = current_trace
        with open(os.path.join(run_dir, naming_things.EXIT_REASON_FILE), mode='r') as exit_file:
            peripheral['exit_reason'] = exit_file.readlines()

    a = PeripheralAnalyzer(vanilla_trace, dma_info, peripherals, args.ram_base, args.work_dir)
    a.start()


if __name__ == '__main__':
    main()
