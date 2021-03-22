import argparse
import os

from avatar2 import Avatar, ARM_CORTEX_M3, OpenOCDTarget


def flash_board(firmware_path, openocd_config_path, work_dir_path):
    print("Phase 01 started")
    import time
    time.sleep(10)
    avatar: Avatar = Avatar(arch=ARM_CORTEX_M3, output_directory=work_dir_path)
    target: OpenOCDTarget = avatar.add_target(OpenOCDTarget, openocd_script=openocd_config_path)

    avatar.init_targets()
    cmd = "program %s verify reset" % firmware_path
    print("Flashing board: `%s`" % cmd)
    target.protocols.monitor.execute_command(cmd)

    target.shutdown()
    avatar.stop()
    avatar.shutdown()
    print("Phase 01 done")


# noinspection DuplicatedCode
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('firmware', type=str, help="Path to the firmware file (elf) used for analysis.")
    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")
    parser.add_argument('work_dir', type=str, help="Working directory.")

    args = parser.parse_args()

    firmware_path: str = args.firmware
    if not os.path.exists(firmware_path):
        print("Firmware file not found")
        exit(1)

    openocd_config_path: str = args.openocd_cfg
    if not os.path.exists(openocd_config_path):
        print("OpenOCD config file not found")
        exit(1)

    work_dir_path: str = args.work_dir
    if not os.path.exists(openocd_config_path) or not os.path.isdir(work_dir_path):
        print("Working directory is not available")
        exit(1)

    flash_board(firmware_path, openocd_config_path, work_dir_path)


if __name__ == '__main__':
    main()
