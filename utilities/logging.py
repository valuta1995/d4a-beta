import json
from os import path
from typing import Optional, List

RECORDING_CSV = "recording.csv"
RECORDING_CSV_HUMAN = "recording_hr.csv"

RECORDING_CSV_HEADER = "index, instruction, pc, value, address, diffs, ignored\n"
RECORDING_CSV_FORMAT = "%d, %s, %d, %d, %d, %d, %s\n"

RECORDING_CSV_HUMAN_FORMAT = "%6s, %12s, %12s, %12s, %12s, %6s, %s\n"
RECORDING_CSV_HUMAN_HEADER = "index , instruction , pc          , value       , address     , diffs , ignored\n"


def csv_reset(base_path: str):
    regular = path.join(base_path, RECORDING_CSV)
    human_readable = path.join(base_path, RECORDING_CSV_HUMAN)
    with open(regular, 'w') as csv_log:
        csv_log.write(RECORDING_CSV_HEADER)

    with open(human_readable, 'w') as csv_log:
        csv_log.write(RECORDING_CSV_HUMAN_HEADER)


def csv_append(
        base_path: str, index: int, instruction: str, pc: int, value: int, address: int, mem_delta: Optional[List[int]],
        ignored_delta: Optional[List[int]]
):
    # TODO improve mem_delta to be like ignored_delta

    ignored_delta_json = "\"%s\"" % json.dumps(ignored_delta)

    regular = path.join(base_path, RECORDING_CSV)
    human_readable = path.join(base_path, RECORDING_CSV_HUMAN)

    with open(regular, 'a') as csv_log:
        num_diffs = -1 if mem_delta is None else len(mem_delta)
        csv_log.write(RECORDING_CSV_FORMAT % (
            index, instruction, pc, value, address, num_diffs,
            "None" if ignored_delta is None else ignored_delta_json,
        ))

    with open(human_readable, 'a') as csv_log:
        csv_log.write(RECORDING_CSV_HUMAN_FORMAT % (
            "%d" % index,
            instruction,
            "0x%08X" % pc,
            "0x%X" % value,
            "0x%08X" % address,
            "None" if mem_delta is None else "%d: %s" % (len(mem_delta), mem_delta),
            "None" if ignored_delta is None else ignored_delta_json,
        ))
