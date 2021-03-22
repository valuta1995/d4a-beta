import argparse
import hashlib
import os
import signal
import time
from subprocess import Popen
from typing import Callable, Tuple, Dict, List

from utilities import auto_int, naming_things, csv_reset


def get_restart_function() -> Callable:
    def restart_request():
        input("Disconnect and reconnect the device under test and hit [enter] to continue.")

    try:  # Try to test import
        from pykush.pykush import YKUSH, YKUSHNotFound

        try:  # Try to open YKUSH device
            ykush = YKUSH()

            def restart_ykush():
                ykush.set_allports_state_down()
                time.sleep(1.5)
                ykush.set_allports_state_up()
                time.sleep(3.0)

            return restart_ykush

        except YKUSHNotFound:
            return restart_request

    except ImportError:
        return restart_request


restart_connected_devices: Callable[[], None] = get_restart_function()


class Controller:
    firmware_path: str
    config_path: str
    ram_region: Tuple[int, int]
    peripheral_region: Tuple[int, int]
    work_dir: str
    epsilon: int

    living_processes: Dict[str, Popen]

    def __init__(self, firmware_path: str, openocd_config_path: str,
                 ram_region: Tuple[int, int], peripheral_region: Tuple[int, int],
                 work_dir: str, epsilon: int):
        self.firmware_path = firmware_path
        self.config_path = openocd_config_path
        self.ram_region = ram_region
        self.peripheral_region = peripheral_region
        self.work_dir = work_dir
        self.epsilon = epsilon

        self.living_processes = dict()
        signal.signal(signal.SIGINT, self.handle_sigint)
        signal.signal(signal.SIGTERM, self.handle_sigint)

    def handle_sigint(self, sig, frame):
        print("Attempting to terminate all children")
        process: Popen
        for name, process in self.living_processes.items():
            print("\tRequesting `%s` to terminate." % name)
            process.terminate()
        if len(self.living_processes) == 0:
            print("\tNo children found")

        for name, process in self.living_processes.items():
            if process.poll():
                print("Forcibly killing `%s`" % name)
                process.kill()

        print("Children killed, halting.")
        exit(1)

    # region Computed Properties
    @property
    def phase_01_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 1)

    @property
    def phase_02_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 2)

    @property
    def phase_03_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 3)

    @property
    def phase_04_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 4)

    @property
    def phase_05_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 5)

    @property
    def phase_06_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 6)

    @property
    def phase_07_directory(self) -> str:
        return naming_things.setup_directory(self.work_dir, 7)
    # endregion

    def device_needs_flashing(self):
        last_flash_mark = os.path.join(self.phase_01_directory, naming_things.LAST_FLASH_MARKER)
        identifying_information = self.firmware_path + self.config_path
        expected_digest = hashlib.sha256(identifying_information.encode('utf-8')).hexdigest()

        if os.path.exists(last_flash_mark):
            with open(last_flash_mark, 'r') as marker:
                actual_digest = marker.read()
            if actual_digest == expected_digest:
                return False

        with open(last_flash_mark, 'w') as marker:
            marker.write(expected_digest)
        return True

    def run_phase(self, args: List[str]):
        process = Popen(args)
        self.living_processes[args[1]] = process
        process.wait()
        del self.living_processes[args[1]]

    def flash_firmware(self):
        restart_connected_devices()
        self.run_phase([
            'python', './phases/01_preparation.py',
            self.firmware_path,
            self.config_path,
            self.phase_01_directory,
        ])

    def record(self):
        restart_connected_devices()
        csv_reset(self.phase_02_directory)
        self.run_phase([
            'python', './phases/02_recording.py',
            self.config_path,
            '%d' % self.ram_region[0], '%d' % self.ram_region[1],
            '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
            self.phase_02_directory,
        ])

    def analyze(self):
        self.run_phase([
            'python', './phases/03_analysis.py',
            self.phase_02_directory,
            "%d" % self.ram_region[0],
            "%d" % self.epsilon,
            self.phase_03_directory,
        ])

    def start(self, skip_to: int = 0):
        if skip_to <= 1 or self.device_needs_flashing():
            self.flash_firmware()

        if skip_to <= 2:
            self.record()

        if skip_to <= 3:
            self.analyze()

        print("Sleeping for test purposes")
        time.sleep(10)


# noinspection DuplicatedCode
def main():
    parser = argparse.ArgumentParser()

    parser.add_argument('firmware', type=str, help="Path to the firmware file (elf) used for analysis.")
    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('-d', '--working-directory', dest="work_dir", type=str, default='./D4A2')
    parser.add_argument('-e', '--set-epsilon', dest="epsilon", type=auto_int, default=0x300)

    args = parser.parse_args()

    firmware_path: str = args.firmware
    if not os.path.exists(firmware_path):
        print("Firmware file not found")
        exit(1)

    openocd_config_path: str = args.openocd_cfg
    if not os.path.exists(openocd_config_path):
        print("OpenOCD config file not found")
        exit(1)

    ram_region: Tuple[int, int] = (args.ram_start, args.ram_size)
    intercept_region: Tuple[int, int] = (args.intercept_start, args.intercept_size)

    work_dir: str = args.work_dir
    if not os.path.exists(work_dir):
        os.mkdir(work_dir)
    if not os.path.isdir(work_dir):
        print("The specified working directory location is occupied.")
        exit(1)

    epsilon: int = args.epsilon

    controller: Controller = Controller(
        firmware_path=firmware_path,
        openocd_config_path=openocd_config_path,
        ram_region=ram_region,
        peripheral_region=intercept_region,
        work_dir=work_dir,
        epsilon=epsilon,
    )
    controller.start()


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()
