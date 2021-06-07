# self.run_phase([
#     'python', './phases/07_summarize.py',
#     self.get_phase_directory(1),
#     self.get_phase_directory(2),
#     self.get_phase_directory(3),
#     self.get_phase_directory(4),
#     self.get_phase_directory(5),
#     self.get_phase_directory(6),
#     self.config_path,
#     '%d' % self.ram_region[0], '%d' % self.ram_region[1],
#     '%d' % self.peripheral_region[0], '%d' % self.peripheral_region[1],
#     self.get_phase_directory(7),
#     "--grace", '%d' % GRACE_STEPS,
# ])

import argparse
import datetime
import os
import random
from typing import Tuple, Optional

from phases.analyzer import DmaInfo, PeripheralRow, InfoFlag
from phases.recorder import trace_logging, ExecutionTrace
from utilities import auto_int, naming_things

LIST_OF_EXECUTION_AFFECTING_FLAGS = [
    InfoFlag.UNKNOWN,
    InfoFlag.TERMINATED_EARLY,
    InfoFlag.TERMINATED_LATE,
    InfoFlag.FAILED_TO_TERMINATE,
    InfoFlag.TIMED_OUT,
    InfoFlag.UNEXPECTED_NEW_DMA,
    InfoFlag.MISSING_OLD_DMA,
    # InfoFlag.VALUE_CHANGED,
    # InfoFlag.IGNORED_DELTA_CHANGED,
    InfoFlag.DESYNC,
]


def find_dma_ranges(first_trace):
    ranges = []
    current_range = None
    for index, entry in enumerate(first_trace.entries):
        has_dma = len(entry.async_deltas) > 0

        if has_dma:
            if current_range is None:
                current_range = index
            else:
                pass  # Extend the range
        else:
            if current_range is None:
                pass  # Do nothing
            else:
                ranges.append((current_range, index - current_range))
                current_range = None

    return ranges


class Concludermancy:

    def __init__(
            self, flash_dir: str, old_trace: ExecutionTrace, hr_trace_path: str, hr_old_dma_path: str,
            old_dma_info: DmaInfo, old_peripheral_info: PeripheralRow, rec_peripherals_dir: str,
            hr_peripherals_path: str, peripherals: PeripheralRow, hr_dma_info_path: str, dma_info: DmaInfo, fw_img: str,
            openocd_cfg: str, ram_area: Tuple[int, int], intercept_area: Tuple[int, int], grace: int, work_dir: str
    ):
        self.work_dir = work_dir

        # 01
        self.flash_dir = flash_dir

        # 02
        self.first_trace = old_trace
        self.human_readable_first_trace = hr_trace_path

        # 03
        self.human_readable_first_dma_info = hr_old_dma_path
        self.first_dma_info = old_dma_info
        self.first_peripherals = old_peripheral_info

        # 04
        self.per_peripheral_dir = rec_peripherals_dir

        # 05
        self.human_readable_peripherals = hr_peripherals_path
        self.peripherals = peripherals

        # 06
        self.human_readable_dma_info = hr_dma_info_path
        self.dma_info = dma_info

        # 07 extra
        self.firmware_image = fw_img
        self.openocd_cfg = openocd_cfg
        self.ram_area = ram_area
        self.intercept_area = intercept_area
        self.grace = grace

        self.time_taken = self.calculate_time_taken()

    @property
    def device_name(self):
        return os.path.basename(self.openocd_cfg).rsplit(".", 1)[0]

    @property
    def firmware_name(self):
        return os.path.basename(self.firmware_image).rsplit(".", 1)[0]

    def cast(self):
        report_path = self.write_hr_report()
        self.write_csv_line(report_path)

    def write_csv_line(self, report_path: str):
        csv_line_path = os.path.join(self.work_dir, naming_things.CSV_LINE_FILE_NAME)
        with open(csv_line_path, mode='w') as single_line:
            single_line.write(", ".join([
                # Run finish time
                str(datetime.datetime.now().timestamp()),

                # Device
                os.path.abspath(self.openocd_cfg),

                # Firmware
                os.path.abspath(self.firmware_image),

                # Time taken
                str(self.time_taken),

                # Dma present
                str(self.dma_info.index_of_first_incidence if self.dma_info is not None else ""),

                # Dma location
                str(self.dma_info.dma_region_base if self.dma_info is not None else ""),
                str(self.dma_info.dma_region_size if self.dma_info is not None else ""),

                # Instructions (base, size, trigger)
                "^".join(
                    [str(x) for x in self.dma_info.indices_of_set_base_instructions]
                ) if self.dma_info is not None else "",
                "^".join(
                    [str(x) for x in self.dma_info.indices_of_set_size_instructions]
                ) if self.dma_info is not None else "",
                "^".join(
                    [str(x) for x in self.dma_info.indices_of_trigger_instructions]
                ) if self.dma_info is not None else "",

                # Regions (ram, intercept)
                str(self.ram_area),
                str(self.intercept_area),

                # Conclusion file
                report_path,
            ]))

    def write_hr_report(self):
        report_path = os.path.join(self.work_dir, naming_things.REPORT_MD)
        with open(report_path, mode='w') as f:
            f.write("# Run report\n")
            f.write(f"_{self.device_name}: {self.firmware_name}_\n")

            #
            # Flashing 01
            #
            f.write("## Flashing (01)\n")
            f.write(f"Device: {self.device_name}\n{os.path.abspath(self.openocd_cfg)}\n\n")
            f.write(f"Firmware: {self.firmware_name}\n{os.path.abspath(self.firmware_image)}\n\n")
            f.write(f"Directory: {self.flash_dir}\n\n")

            #
            # Exploratory 02
            #
            f.write("## Exploratory execution (02)\n")
            f.write(
                f"Original trace showed dma at the following locations: {find_dma_ranges(self.first_trace)} as such it "
                f"stopped the run after {len(self.first_trace.entries) - 1} steps.\n\n"
            )
            f.write(f"For a human-readable overview open: {os.path.abspath(self.human_readable_first_trace)}\n\n")
            step_02_dir = os.path.dirname(os.path.abspath(self.human_readable_first_trace))
            f.write(f"Directory: {step_02_dir}\n\n")

            #
            # Analysis 03
            #
            f.write("## Initial analysis (03)\n")
            f.write(
                f"Analysis shows peripheral accesses at {self.first_dma_info.indices_of_set_base_instructions} are "
                f"candidates for setting the base address to {self.first_dma_info.dma_region_base}. Moreover, the "
                f"accesses at {self.first_dma_info.indices_of_set_size_instructions} could be responsible for setting "
                f"the size to {self.first_dma_info.dma_region_size}. Finally, {len(self.peripherals.peripherals)} "
                f"possible peripheral clusters were identified."
            )
            f.write("### Set base candidates\n")
            for e in self.first_dma_info.entries_of_set_base_instructions:
                f.write(" - %s\n" % e)
            f.write("\n")

            f.write("### Set size candidates\n")
            for e in self.first_dma_info.entries_of_set_size_instructions:
                f.write(" - %s\n" % e)
            f.write("\n")

            f.write("### Peripheral clusters\n")
            for p in self.first_peripherals.peripherals:
                f.write(" - %s\n" % p)
            f.write("\n")

            f.write(f"For a human-readable overview open: {os.path.abspath(self.human_readable_first_dma_info)}\n\n")
            f.write(f"Directory: {os.path.dirname(os.path.abspath(self.human_readable_first_dma_info))}\n\n")

            #
            # Per-peripheral 04
            #
            f.write("## Per-peripheral execution (04)\n")
            f.write("There is no info that can quickly be gleaned from the output of this step, conclusions will be "
                    "drawn in step 05. However, to get the full detail of the behaviour of a certain peripheral "
                    "(cluster) you can find them in this directory.\n")
            f.write(f"Directory: {self.per_peripheral_dir}\n\n")

            #
            # Peripheral analysis 05
            #
            f.write("## Peripheral analysis (05)\n")
            if self.dma_info is None:
                f.write("No peripheral analysis was done as no DMA was detected.\n\n")
            else:
                affecting_peripherals = [
                    p for p in self.peripherals.peripherals
                    if p.has_one_of_flags(LIST_OF_EXECUTION_AFFECTING_FLAGS)
                ]
                non_affecting_peripherals = [
                    p for p in self.peripherals.peripherals
                    if not p.has_one_of_flags(LIST_OF_EXECUTION_AFFECTING_FLAGS)
                ]
                f.write(f"Of all the peripheral clusters, {len(affecting_peripherals)} are filtered and "
                        f"{len(non_affecting_peripherals)} are not.\n")

                f.write("### Peripherals")
                for p in self.peripherals.peripherals:
                    f.write(" - %s\n" % p)

                f.write(f"For a human-readable overview open: {os.path.abspath(self.human_readable_peripherals)}\n\n")
            f.write(f"Directory: {os.path.dirname(os.path.abspath(self.human_readable_peripherals))}\n\n")

            #
            # Verification step 06
            #
            f.write("## Verification (06)\n")
            if self.dma_info is None:
                f.write("No verification was done as no DMA was detected.")
            else:
                f.write(
                    f"Of the {len(self.first_dma_info.indices_of_set_base_instructions)} candidates that could have "
                    f"set the base address, {len(self.dma_info.indices_of_set_base_instructions)} were recorded to "
                    f"actually modify the base address. Moreover, of the "
                    f"{len(self.first_dma_info.indices_of_set_size_instructions)} size candidates, "
                    f"{len(self.dma_info.indices_of_set_size_instructions)} were recorded to change the size. Finally, "
                    f"a total of {len(self.dma_info.indices_of_trigger_instructions)} registers affected  dma in some "
                    f"way. Either they trigger dma or provide other required input such as a source.\n\n"
                )

                blocked = []
                f.write("### Base modifying instructions\n")
                for e_idx in self.dma_info.indices_of_set_base_instructions:
                    blocked.append(e_idx)
                    e = self.dma_info.execution_trace.entries[e_idx]
                    f.write(" - %s\n" % e)
                f.write("\n")

                f.write("### Size modifying instruction\n")
                for e_idx in self.dma_info.indices_of_set_size_instructions:
                    blocked.append(e_idx)
                    e = self.dma_info.execution_trace.entries[e_idx]
                    f.write(" - %s\n" % e)
                f.write("\n")

                f.write("### Otherwise affecting instructions\n")
                for e_idx in self.dma_info.indices_of_trigger_instructions:
                    if e_idx in blocked:
                        f.write(" - _%s_\t (repeated entry)\n" % e)
                    else:
                        f.write(" - %s\n" % e)
                        blocked.append(e_idx)
                f.write("\n")

                f.write(f"For a human-readable overview open: {os.path.abspath(self.human_readable_dma_info)}\n\n")
            f.write(f"Directory: {os.path.dirname(os.path.abspath(self.human_readable_dma_info))}\n\n")

            #
            # Additional information
            #
            f.write("## Extra information\n")
            f.write(
                "Selected RAM region was: 0x%08X through 0x%08X (size: %d)\n\n" %
                (self.ram_area[0], self.ram_area[0] + self.ram_area[1] - 1, self.ram_area[1])
            )
            f.write(
                "Selected Peripheral region was: 0x%08X through 0x%08X (size: %d)\n\n" %
                (self.intercept_area[0], self.intercept_area[0] + self.intercept_area[1] - 1, self.intercept_area[1])
            )
            f.write("The entire run took %s\n" % self.time_taken)
        return report_path

    def calculate_time_taken(self):
        import pathlib
        import datetime
        f_name = pathlib.Path(os.path.join(self.work_dir, "mark"))
        start_time = datetime.datetime.fromtimestamp(f_name.stat().st_mtime)
        end_time = datetime.datetime.now()
        total_time = end_time - start_time
        return total_time


# noinspection DuplicatedCode
def main():
    # region Parse arguments
    parser = argparse.ArgumentParser()

    parser.add_argument('flash_dir', type=str, help="Path to the directory with the device flash logs.")
    parser.add_argument('recording_dir', type=str, help="Path to the directory with the full recording data.")
    parser.add_argument('analysis_dir', type=str, help="Path to the directory with the global analysis results.")
    parser.add_argument('rec_peripheral_dir', type=str,
                        help="Path to the directory with the peripheral recording data.")
    parser.add_argument('peripheral_dir', type=str, help="Path to the directory with the peripheral analysis results.")
    parser.add_argument('rec_addr_size_dir', type=str, help="Path to the directory with the verification run data.")

    parser.add_argument('firmware', type=str, help="Path to the firmware file (elf) used for analysis.")
    parser.add_argument('openocd_cfg', type=str, help="Path to the openocd configuration file for the DuT.")

    parser.add_argument('ram_start', type=auto_int, help="Start address of the device RAM.")
    parser.add_argument('ram_size', type=auto_int, help="Size of the device RAM.")

    parser.add_argument('intercept_start', type=auto_int, help="Start address of the device peripheral region.")
    parser.add_argument('intercept_size', type=auto_int, help="Size of the device peripheral region.")

    parser.add_argument('work_dir', type=str, help="Working directory.")

    parser.add_argument('--grace', dest='abort_grace_steps', type=int, default=5,
                        help="Keep recording this many steps after aborts.")

    args = parser.parse_args()
    # endregion

    # Step 01
    flash_dir: str = args.flash_dir

    # Step 02
    recording_dir: str = args.recording_dir
    hr_trace_path: str = os.path.join(recording_dir, trace_logging.HUMAN_CSV)

    old_trace_path: str = os.path.join(recording_dir, trace_logging.RECORDING_JSON)
    old_trace: ExecutionTrace = ExecutionTrace.from_file(old_trace_path)

    # Step 03
    analysis_dir: str = args.analysis_dir
    hr_old_dma_path: str = os.path.join(analysis_dir, naming_things.DMA_INFO_HR_JSON)

    old_dma_info_path: str = os.path.join(analysis_dir, naming_things.DMA_INFO_JSON)
    old_dma_info: DmaInfo = DmaInfo.from_file(old_dma_info_path)

    has_dma = old_dma_info.index_of_first_incidence >= 0

    old_peripheral_info_path: str = os.path.join(analysis_dir, naming_things.PERIPHERAL_JSON_NAME)
    old_peripheral_info: PeripheralRow = PeripheralRow.from_file(old_peripheral_info_path)

    # Step 04
    rec_peripherals_dir: str = args.rec_peripheral_dir

    # Step 05
    peripheral_dir: str = args.peripheral_dir
    hr_peripherals_path: str = os.path.join(peripheral_dir, naming_things.PERIPHERAL_JSON_HR_NAME)

    peripherals_path: str = os.path.join(peripheral_dir, naming_things.PERIPHERAL_JSON_NAME)
    peripherals: PeripheralRow = PeripheralRow.from_file(peripherals_path)

    # Step 06
    rec_addr_size_dir: str = args.rec_addr_size_dir
    hr_dma_info_path: str = os.path.join(rec_addr_size_dir, naming_things.DMA_INFO_HR_JSON)

    dma_info_path: str = os.path.join(rec_addr_size_dir, naming_things.DMA_INFO_JSON)
    if has_dma:
        dma_info: Optional[DmaInfo] = DmaInfo.from_file(dma_info_path)
    else:
        dma_info: Optional[DmaInfo] = None

    # Other info
    firmware: str = args.firmware
    openocd_cfg: str = args.openocd_cfg
    ram_area: Tuple[int, int] = (args.ram_start, args.ram_size)
    intercept_area: Tuple[int, int] = (args.intercept_start, args.intercept_size)
    grace: int = args.abort_grace_steps

    work_dir: str = args.work_dir

    c = Concludermancy(
        flash_dir, old_trace, hr_trace_path, hr_old_dma_path, old_dma_info, old_peripheral_info, rec_peripherals_dir,
        hr_peripherals_path, peripherals, hr_dma_info_path, dma_info, firmware, openocd_cfg, ram_area, intercept_area,
        grace, work_dir
    )

    c.cast()

    print("Done runner")


if __name__ == '__main__':
    main()
