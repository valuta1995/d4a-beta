import os
from typing import List

from . import ExecutionTrace, MemoryDelta, TraceEntry

RECORDING_JSON = "trace.json"
HUMAN_CSV = "trace_hr.csv"

CSV_ITEMS = [
    ("index", 8, "%d"),
    ("instr.", 8, "%s"),
    ("pc", 12, "0x%08X"),
    ("value", 12, "0x%X"),
    ("address", 12, "0x%08X"),
    ("#diffs", 8, "%d"),
    ("#ignore", 8, "%d"),
]


# def csv_reset(base_path: str):
#     regular = path.join(base_path, RECORDING_CSV)
#     human_readable = path.join(base_path, RECORDING_CSV_HUMAN)
#     with open(regular, 'w') as csv_log:
#         csv_log.write(RECORDING_CSV_HEADER)
#
#     with open(human_readable, 'w') as csv_log:
#         csv_log.write(RECORDING_CSV_HUMAN_HEADER)
#
#
# def csv_append(
#         base_path: str,
#         index: int,
#         instruction: str,
#         pc: int,
#         value: int,
#         address: int,
#         mem_delta: Optional[List[int]],
#         ignored_delta: Optional[List[int]]
# ):
#     # TODO improve mem_delta to be like ignored_delta
#
#     ignored_delta_json = "\"%s\"" % json.dumps(ignored_delta)
#
#     regular = path.join(base_path, RECORDING_CSV)
#     human_readable = path.join(base_path, RECORDING_CSV_HUMAN)
#
#     with open(regular, 'a') as csv_log:
#         num_diffs = -1 if mem_delta is None else len(mem_delta)
#         csv_log.write(RECORDING_CSV_FORMAT % (
#             index, instruction, pc, value, address, num_diffs,
#             "None" if ignored_delta is None else ignored_delta_json,
#         ))
#
#     with open(human_readable, 'a') as csv_log:
#         csv_log.write(RECORDING_CSV_HUMAN_FORMAT % (
#             "%d" % index,
#             instruction,
#             "0x%08X" % pc,
#             "0x%X" % value,
#             "0x%08X" % address,
#             "None" if mem_delta is None else "%d: %s" % (len(mem_delta), mem_delta),
#             "None" if ignored_delta is None else ignored_delta_json,
#         ))

class ExecutionLogger:
    execution_trace: ExecutionTrace
    directory: str
    human_readable_file: str
    machine_readable_file: str

    def __init__(self, output_directory: str):
        self.execution_trace = ExecutionTrace()
        self.directory = output_directory
        self.human_readable_file = os.path.join(self.directory, HUMAN_CSV)
        self.machine_readable_file = os.path.join(self.directory, RECORDING_JSON)

    def initialize(self):
        header_string = ", ".join(["%*s" % (x[1], x[0]) for x in CSV_ITEMS])
        with open(self.human_readable_file, mode='w') as csv_file:
            csv_file.write(header_string)
            csv_file.write("\n")

        with open(self.machine_readable_file, mode='w') as json_file:
            json_file.write("")

    def add_entry(self, instruction: str, pc: int, value: int, address: int,
                  async_deltas: List[MemoryDelta], ignored_deltas: List[MemoryDelta]):
        trace_entry = TraceEntry(instruction, pc, value, address, async_deltas, ignored_deltas)
        new_index = len(self.execution_trace.entries)
        self.execution_trace.append(trace_entry)

        args = [new_index, instruction, pc, value, address, len(async_deltas), len(ignored_deltas)]
        sizes = [x[1] for x in CSV_ITEMS]
        formats = [x[2] for x in CSV_ITEMS]
        formatted = [x[0] % x[1] for x in zip(formats, args)]
        sized = ["%*s" % (x[0], x[1]) for x in zip(sizes, formatted)]
        entry_string = ", ".join(sized)
        with open(self.human_readable_file, mode='a') as csv_file:
            csv_file.write(entry_string)
            csv_file.write("\n")

    def finalize(self):
        ExecutionTrace.to_file(self.machine_readable_file, self.execution_trace)
