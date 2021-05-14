import csv
import json
import os.path
from typing import List, Optional, Dict, Tuple

from utilities import logging
from utilities.naming_things import BEFORE_DUMP_NAME, AFTER_DUMP_NAME


def read_bytes(file_path: str) -> bytes:
    try:
        with open(file_path, mode='rb') as binary:
            return binary.read()
    except FileNotFoundError:
        return bytes()


def get_diffs(before_file: str, after_file: str) -> List[Tuple[int, Tuple[int, int]]]:
    before_bytes = read_bytes(before_file)
    after_bytes = read_bytes(after_file)

    diffs = []
    for i in range(len(before_bytes)):
        if before_bytes[i] != after_bytes[i]:
            diffs.append((i, (before_bytes[i], after_bytes[i])))
    return diffs


class MemoryDelta:
    address: int
    anterior_value: int
    posterior_value: int

    def __init__(self, address: int, anterior_value: int, posterior_value: int):
        self.address = address
        self.anterior_value = anterior_value
        self.posterior_value = posterior_value


class TraceEntry:

    index: int
    instr: str
    pc: int
    value: int
    addr: int
    async_memory_deltas: Optional[List[MemoryDelta]]

    def __init__(self, instruction: str, pc: int, value: int, addr: int,
                 mem_delta: Optional[List[MemoryDelta]]):
        self.index = -1
        self.instr = instruction
        self.pc = pc
        self.value = value
        self.addr = addr
        self.async_memory_deltas = mem_delta


    def to_json(self):
        return json.dumps()

    @classmethod
    def from_dict(cls, entry_dict: Dict[str, any], memory_dumps_dir: Optional[str]) -> 'TraceEntry':
        index = int(entry_dict['index'])
        instruction = entry_dict['instruction']
        pc = int(entry_dict['pc'])
        value = int(entry_dict['value'])
        addr = int(entry_dict['address'])

        if isinstance(entry_dict['diffs'], list):
            num_deltas = len(entry_dict['diffs'])
        else:
            num_deltas = int(entry_dict['diffs'])

        if 'ignored' in entry_dict:
            ignore_diffs_str = entry_dict['ignored']
            if ignore_diffs_str == 'None':
                ignore_diffs = None
            else:
                ignore_diffs = json.loads(ignore_diffs_str)
        else:
            ignore_diffs = None

        if memory_dumps_dir is not None:
            before_file = os.path.join(memory_dumps_dir, "%03d_%s" % (index, BEFORE_DUMP_NAME))
            after_file = os.path.join(memory_dumps_dir, "%03d_%s" % (index, AFTER_DUMP_NAME))

            mem_delta = get_diffs(before_file, after_file)
            mem_delta = [x for x in mem_delta if x[0] not in ignore_diffs]
            if num_deltas != len(mem_delta):
                raise Exception("Mismatch in diffs")

        else:
            # Add clear bogus values to get the same number of elements.
            mem_delta = []
            for i in range(num_deltas):
                mem_delta.append((-1, (-1, -1)))

        te: TraceEntry = TraceEntry(instruction, pc, value, addr, mem_delta)
        te.index = index
        return te

    @classmethod
    def to_dict(cls, instruction: 'TraceEntry'):
        keys = logging.RECORDING_CSV_HEADER.split(', ')
        keys = [x.strip() for x in keys]
        return {
            keys[0]: instruction.index,
            keys[1]: instruction.instr,
            keys[2]: instruction.pc,
            keys[3]: instruction.value,
            keys[4]: instruction.addr,
            keys[5]: instruction.async_memory_deltas,
        }


def check_header_match(header):
    from utilities import logging
    good_header = [x.strip() for x in logging.RECORDING_CSV_HEADER.split(',')]
    if len(header) != len(good_header):
        return False
    for i in range(len(header)):
        if header[i] != good_header[i]:
            return False
    return True


class ExecutionTrace:
    entries: List[TraceEntry]

    def __init__(self):
        self.entries = []

    @property
    def length(self) -> int:
        return len(self.entries)

    @property
    def all_addresses(self) -> List[int]:
        return [x.addr for x in self.entries]

    def append(self, entry: TraceEntry):
        if entry.index == -1:
            entry.index = self.length
        else:
            if entry.index != self.length:
                raise Exception("Trying to add an entry to an invalid index.")
        self.entries.append(entry)

    def peek(self) -> TraceEntry:
        return self.entries[-1]

    def get(self, index: int) -> TraceEntry:
        return self.entries[index]

    def update_with_memory_dumps(self, dump_directory: str):
        pass

    @classmethod
    def from_csv(cls, recording_csv: str, dumps_dir: Optional[str]) -> 'ExecutionTrace':
        et: ExecutionTrace = ExecutionTrace()
        with open(recording_csv, 'r', newline='') as csv_file:
            reader = csv.reader(csv_file, quotechar='"', delimiter=',', skipinitialspace=True)
            header = [x.strip() for x in next(reader)]
            if not check_header_match(header):
                raise Exception("Invalid input file format for %s" % recording_csv)
            for row in reader:
                entry_dict = {header[i]: row[i].strip() for i in range(len(row))}
                te: TraceEntry = TraceEntry.from_dict(entry_dict, dumps_dir)
                et.append(te)
        return et
