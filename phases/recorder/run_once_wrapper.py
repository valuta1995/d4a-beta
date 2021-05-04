import argparse
import json
import os
from typing import Tuple

from phases.recorder import FirmwareRecorder
from utilities import auto_int


# noinspection DuplicatedCode
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('shadow_ban_json', type=str,
                        help="Json list of [start, end] pairs.")
    parser.add_argument('shim_value_json', type=str,
                        help="Json list of [start, end, value] triples.")
    parser.add_argument('original_trace_path', type=str,
                        help="Path to the 'recording.csv'. ('None' to disable)")
    parser.add_argument('abort_grace_steps', type=int,
                        help="Grace steps recorded after abort (0=off, 5=default).")
    parser.add_argument('abort_after_deviation', type=bool,
                        help="Abort if deviating from trace. (Requires path).")
    parser.add_argument('abort_after_dma', type=bool,
                        help="Abort after DMA is first detected.")
    parser.add_argument('abort_after_loops', type=int,
                        help="Abort after the same steps have been done 'n' times. (-1=off, 4=default).")
    parser.add_argument('abort_after_pc', type=auto_int,
                        help="Abort after this program counter. (-1=off)")
    parser.add_argument('abort_at_step', type=int,
                        help="Abort after this many steps (-1=off)")
    parser.add_argument('abort_per_step_timeout', type=int,
                        help="Abort if a step takes longer than this many seconds. (-1=off)")

    parser.add_argument('work_dir', type=str, help="Working directory.")

    args = parser.parse_args()

    openocd_config_path: str = args.openocd_cfg
    if not os.path.exists(openocd_config_path):
        print("OpenOCD config file not found")
        exit(1)

    work_dir_path: str = args.work_dir
    if not os.path.exists(openocd_config_path) or not os.path.isdir(work_dir_path):
        print("Working directory is not available")
        exit(1)

    mem_ram: Tuple[int, int] = (args.ram_start, args.ram_size)
    mem_peripheral: Tuple[int, int] = (args.intercept_start, args.intercept_size)

    mocked_regions = json.loads(args.shadow_ban_json)
    mocked_regions = [(x[0], x[1]) for x in mocked_regions]

    shimmed_regions = json.loads(args.shim_json)
    shimmed_regions = [(x[0], x[1], x[2]) for x in shimmed_regions]

    original_trace_path = None if args.original_trace_path == "None" else args.original_trace_path

    recorder = FirmwareRecorder(
        args.openocd_cfg, mem_ram, mem_peripheral, mocked_regions, shimmed_regions, args.work_dir,
        original_trace_path=original_trace_path,
        abort_grace_steps=args.abort_grace_steps,
        abort_after_deviation=args.abort_after_deviation,
        abort_after_dma=args.abort_after_dma,
        abort_after_loops=args.abort_after_loops,
        abort_after_pc=args.abort_after_pc,
        abort_at_step=args.abort_at_step,
        abort_per_step_timeout=args.abort_per_step_timeout
    )

    recorder.start()


if __name__ == '__main__':
    main()
