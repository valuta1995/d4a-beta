import os
from typing import List

# Directory names
PHASE_01_FIRMWARE_PREPARATION = \
    "01_preparation"
PHASE_02_INITIAL_RECORDING = \
    "02_recording"
PHASE_03_INITIAL_ANALYSIS = \
    "03_global_analysis"
PHASE_04_PERIPHERAL_RECORDING = \
    "04_recording_peripherals"
PHASE_05_PERIPHERAL_ANALYSIS = \
    "05_peripheral_analysis"
PHASE_06_ADDR_SIZE_RECORDING = \
    "06_recording_addr_size"
PHASE_07_SUMMARIZE = \
    "07_summarize"

PHASE_NAMES: List[str] = [
    "INVALID_OPTION",
    PHASE_01_FIRMWARE_PREPARATION,
    PHASE_02_INITIAL_RECORDING,
    PHASE_03_INITIAL_ANALYSIS,
    PHASE_04_PERIPHERAL_RECORDING,
    PHASE_05_PERIPHERAL_ANALYSIS,
    PHASE_06_ADDR_SIZE_RECORDING,
    PHASE_07_SUMMARIZE,
]

MEMORY_SNAPSHOT_DIRECTORY = "snapshots"
AVATAR_OUTPUT_DIRECTORY = "avatar_output"

# File names
LAST_FLASH_MARKER = "last_flash"

BEFORE_DUMP_NAME = "anterior.bin"
AFTER_DUMP_NAME = "posterior.bin"
EXIT_REASON_FILE = "exit_reason.txt"
DMA_INFO_JSON = "dma_info.json"
DMA_INFO_HR_JSON = "dma_info_hr.json"
REPORT_MD = "report.md"
CSV_LINE_FILE_NAME = "single_csv_line.csv"

# PERIPHERAL_CSV_NAME = "peripherals.csv"
PERIPHERAL_JSON_NAME = "peripherals.json"
PERIPHERAL_JSON_HR_NAME = "peripherals_hr.json"


# Exit reason strings
REASON_DEVIATION = "deviation_from_trace"
REASON_DMA = "possible_dma_detected"
REASON_LOOPS = "number_of_loops"
REASON_PC = "exact_pc"
REASON_STEPS = "exceeded_steps_limit"


def setup_directory(base_path: str, phase_id: int) -> str:
    dir_path = os.path.join(base_path, PHASE_NAMES[phase_id])
    if not os.path.exists(dir_path):
        os.mkdir(dir_path)
    if not os.path.isdir(dir_path):
        raise Exception("Unable to create directory for phase %d" % phase_id)
    return dir_path


def create_peripheral_run_name(peripheral_base: int):
    return "run_x%08X" % peripheral_base
