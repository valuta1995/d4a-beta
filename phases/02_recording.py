import argparse
import os
from typing import Tuple

from phases.recorder import FirmwareRecorder
from utilities import auto_int


def record_firmware(openocd_cfg: str, mem_ram: Tuple[int, int], mem_peripheral: Tuple[int, int], work_dir: str,
                    timeout: int, max_steps: int, grace_steps: int, solve_the_halting_problem: int):
    mock_regions = []
    shim_regions = []
    # TODO read configuration for hardcoded parameters
    recorder = FirmwareRecorder(
        openocd_cfg, mem_ram, mem_peripheral, mock_regions, shim_regions, work_dir,
        original_trace_path=None,
        abort_grace_steps=grace_steps,
        abort_after_deviation=False,
        abort_after_dma=True,
        abort_after_loops=solve_the_halting_problem,
        abort_after_pc=-1,
        abort_at_step=max_steps,
        abort_per_step_timeout=timeout
    )

    recorder.start()


# noinspection DuplicatedCode
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('work_dir', type=str, help="Working directory.")

    parser.add_argument('-t', '--timeout', default=30, type=int, help="Set the time-out for each step in seconds.")
    parser.add_argument('-s', '--max_steps', default=999, type=int, help="Limit the amount of steps that are executed.")
    parser.add_argument('-g', '--grace_steps', default=50, type=int, help="Continue for a bit after an abort triggers.")
    parser.add_argument(
        '--solve_the_halting_problem', default=4, type=int,
        help="Abort if peripherals are accessed exactly the same way this many times in a row."
    )

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

    timeout: int = args.timeout
    max_steps: int = args.max_steps
    grace_steps: int = args.grace_steps
    solve_the_halting_problem: int = args.abort_loops

    record_firmware(openocd_config_path, mem_ram, mem_peripheral, work_dir_path, timeout, max_steps, grace_steps,
                    solve_the_halting_problem)


if __name__ == '__main__':
    main()
