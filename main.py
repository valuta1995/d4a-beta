import argparse
import hashlib
import os
import signal
import subprocess
from subprocess import Popen
from typing import Tuple, Dict, List

from utilities import auto_int, naming_things

GRACE_STEPS = 32


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
                print("\tForcibly killing `%s`" % name)
                process.kill()

        ps_proc = Popen(['ps', '-A'], stdout=subprocess.PIPE)
        out, err = ps_proc.communicate()
        for line in out.splitlines():
            if b'openocd' in line:
                print("Found an openocd process, killing it.")
                pid = int(line.split(None, 1)[0])
                os.kill(pid, signal.SIGKILL)

        print("Children killed, halting.")
        exit(1)

    def get_phase_directory(self, phase_no: int):
        return naming_things.setup_directory(self.work_dir, phase_no)

    def device_needs_flashing(self):
        last_flash_mark = os.path.join(self.get_phase_directory(1), naming_things.LAST_FLASH_MARKER)
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

    def flash_firmware_step01(self):
        self.run_phase([
            'python', './phases/01_preparation.py',
            self.firmware_path,
            self.config_path,
            self.get_phase_directory(1),
        ])

    def record_step02(self):
        self.run_phase([
            'python', './phases/02_recording.py',
            self.config_path,
            '%d' % self.ram_region[0], '%d' % self.ram_region[1],
            '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
            self.get_phase_directory(2),
            "--grace", '%d' % GRACE_STEPS,
        ])

    def analyze_step03(self):
        self.run_phase([
            'python', './phases/03_global_analysis.py',
            self.get_phase_directory(2),
            "%d" % self.ram_region[0],
            "%d" % self.epsilon,
            self.get_phase_directory(3),
        ])

    def record_peripherals_step04(self):
        self.run_phase([
            'python', './phases/04_recording_peripherals.py',
            # self.get_phase_directory(2),
            self.get_phase_directory(3),
            self.config_path,
            '%d' % self.ram_region[0], '%d' % self.ram_region[1],
            '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
            self.get_phase_directory(4),
            "--grace", '%d' % GRACE_STEPS,
        ])

    def analyze_peripherals_step05(self):
        self.run_phase([
            'python', './phases/05_peripheral_analysis.py',
            self.get_phase_directory(2),
            self.get_phase_directory(3),
            self.get_phase_directory(4),
            "%d" % self.ram_region[0],
            self.get_phase_directory(5),
        ])

    def record_addr_size_step06(self):
        self.run_phase([
            'python', './phases/06_recording_addr_size.py',
            # self.get_phase_directory(2),
            self.get_phase_directory(3),
            self.get_phase_directory(5),
            self.config_path,
            '%d' % self.ram_region[0], '%d' % self.ram_region[1],
            '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
            self.get_phase_directory(6),
            "--grace", '%d' % GRACE_STEPS,
        ])

    def summarize_step07(self):
        self.run_phase([
            'python', './phases/07_summarize.py',
            self.get_phase_directory(1),
            self.get_phase_directory(2),
            self.get_phase_directory(3),
            self.get_phase_directory(4),
            self.get_phase_directory(5),
            self.get_phase_directory(6),
            self.firmware_path,
            self.config_path,
            '%d' % self.ram_region[0], '%d' % self.ram_region[1],
            '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
            self.get_phase_directory(7),
            "--grace", '%d' % GRACE_STEPS,
        ])

    def start(self, skip_to: int = 0, stop_after: int = -1):
        with open(os.path.join(self.get_phase_directory(7), "mark"), mode='w') as mark:
            mark.write("started run")

        if skip_to > stop_after:
            if stop_after == -1:
                stop_after = len(naming_things.PHASE_NAMES)
            else:
                print("Warning, stop < start, assuming stop == start.")
                stop_after = skip_to

        if skip_to <= 1 <= stop_after and self.device_needs_flashing():
            self.flash_firmware_step01()

        if skip_to <= 2 <= stop_after:
            self.record_step02()

        if skip_to <= 3 <= stop_after:
            self.analyze_step03()

        if skip_to <= 4 <= stop_after:
            self.record_peripherals_step04()

        if skip_to <= 5 <= stop_after:
            self.analyze_peripherals_step05()

        if skip_to <= 6 <= stop_after:
            self.record_addr_size_step06()

        if skip_to <= 7 <= stop_after:
            self.summarize_step07()


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

    parser.add_argument('-s', '--start', dest="start_at", type=int, default=0)
    parser.add_argument('-t', '--stop', dest="stop_after", type=int, default=-1)

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
    controller.start(skip_to=args.start_at, stop_after=args.stop_after)


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()

# Step 7 csv output list:
# end_time, device, firmware, taken_time, dma_presence, dma_base, dma_size,
#   base_instructions, size_instructions, trigger_instructions, report_path
