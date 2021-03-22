import argparse
import os
from typing import Tuple

from phases.recorder.firmware_recorder import FirmwareRecorder
from utilities import auto_int


def record_firmware(openocd_cfg: str, mem_ram: Tuple[int, int], mem_peripheral: Tuple[int, int], work_dir: str):
    shadow_banned_regions = []
    # TODO read configuration for hardcoded parameters
    recorder = FirmwareRecorder(
        openocd_cfg, mem_ram, mem_peripheral, shadow_banned_regions, work_dir,
        original_trace_path=None,
        abort_grace_steps=5,
        abort_after_deviation=False,
        abort_after_dma=True,
        abort_after_loops=4,
        abort_after_pc=-1,
        abort_at_step=512,
        abort_per_step_timeout=20
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
    record_firmware(openocd_config_path, mem_ram, mem_peripheral, work_dir_path)


if __name__ == '__main__':
    main()
