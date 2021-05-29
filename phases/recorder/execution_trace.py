# import csv
# import json
# import os.path
# from typing import List, Optional, Dict, Tuple
#
# from utilities import logging
# from utilities.naming_things import BEFORE_DUMP_NAME, AFTER_DUMP_NAME
#
#
# def read_bytes(file_path: str) -> bytes:
#     try:
#         with open(file_path, mode='rb') as binary:
#             return binary.read()
#     except FileNotFoundError:
#         return bytes()
#
#
# def get_diffs(before_file: str, after_file: str) -> List[Tuple[int, Tuple[int, int]]]:
#     before_bytes = read_bytes(before_file)
#     after_bytes = read_bytes(after_file)
#
#     diffs = []
#     for i in range(len(before_bytes)):
#         if before_bytes[i] != after_bytes[i]:
#             diffs.append((i, (before_bytes[i], after_bytes[i])))
#     return diffs
#
#
# class MemoryDelta:
#     address: int
#     anterior_value: int
#     posterior_value: int
#
#     def __init__(self, address: int, anterior_value: int, posterior_value: int):
#         self.address = address
#         self.anterior_value = anterior_value
#         self.posterior_value = posterior_value
#
#
# class TraceEntry:
#
#     index: int
#     instr: str
#     pc: int
#     value: int
#     addr: int
#     async_memory_deltas: Optional[List[MemoryDelta]]
#
#     def __init__(self, instruction: str, pc: int, value: int, addr: int,
#                  mem_delta: Optional[List[MemoryDelta]]):
#         self.index = -1
#         self.instr = instruction
#         self.pc = pc
#         self.value = value
#         self.addr = addr
#         self.async_memory_deltas = mem_delta
#
#
#     def to_json(self):
#         return json.dumps()
#
#     @classmethod
#     def from_dict(cls, entry_dict: Dict[str, any], memory_dumps_dir: Optional[str]) -> 'TraceEntry':
#         index = int(entry_dict['index'])
#         instruction = entry_dict['instruction']
#         pc = int(entry_dict['pc'])
#         value = int(entry_dict['value'])
#         addr = int(entry_dict['address'])
#
#         if isinstance(entry_dict['diffs'], list):
#             num_deltas = len(entry_dict['diffs'])
#         else:
#             num_deltas = int(entry_dict['diffs'])
#
#         if 'ignored' in entry_dict:
#             ignore_diffs_str = entry_dict['ignored']
#             if ignore_diffs_str == 'None':
#                 ignore_diffs = None
#             else:
#                 ignore_diffs = json.loads(ignore_diffs_str)
#         else:
#             ignore_diffs = None
#
#         if memory_dumps_dir is not None:
#             before_file = os.path.join(memory_dumps_dir, "%03d_%s" % (index, BEFORE_DUMP_NAME))
#             after_file = os.path.join(memory_dumps_dir, "%03d_%s" % (index, AFTER_DUMP_NAME))
#
#             mem_delta = get_diffs(before_file, after_file)
#             mem_delta = [x for x in mem_delta if x[0] not in ignore_diffs]
#             if num_deltas != len(mem_delta):
#                 raise Exception("Mismatch in diffs")
#
#         else:
#             # Add clear bogus values to get the same number of elements.
#             mem_delta = []
#             for i in range(num_deltas):
#                 mem_delta.append((-1, (-1, -1)))
#
#         te: TraceEntry = TraceEntry(instruction, pc, value, addr, mem_delta)
#         te.index = index
#         return te
#
#     @classmethod
#     def to_dict(cls, instruction: 'TraceEntry'):
#         keys = logging.RECORDING_CSV_HEADER.split(', ')
#         keys = [x.strip() for x in keys]
#         return {
#             keys[0]: instruction.index,
#             keys[1]: instruction.instr,
#             keys[2]: instruction.pc,
#             keys[3]: instruction.value,
#             keys[4]: instruction.addr,
#             keys[5]: instruction.async_memory_deltas,
#         }
#
#
# def check_header_match(header):
#     from utilities import logging
#     good_header = [x.strip() for x in logging.RECORDING_CSV_HEADER.split(',')]
#     if len(header) != len(good_header):
#         return False
#     for i in range(len(header)):
#         if header[i] != good_header[i]:
#             return False
#     return True
#
#
# class ExecutionTrace:
#     entries: List[TraceEntry]
#
#     def __init__(self):
#         self.entries = []
#
#     @property
#     def length(self) -> int:
#         return len(self.entries)
#
#     @property
#     def all_addresses(self) -> List[int]:
#         return [x.addr for x in self.entries]
#
#     def append(self, entry: TraceEntry):
#         if entry.index == -1:
#             entry.index = self.length
#         else:
#             if entry.index != self.length:
#                 raise Exception("Trying to add an entry to an invalid index.")
#         self.entries.append(entry)
#
#     def peek(self) -> TraceEntry:
#         return self.entries[-1]
#
#     def get(self, index: int) -> TraceEntry:
#         return self.entries[index]
#
#     def update_with_memory_dumps(self, dump_directory: str):
#         pass
#
#     @classmethod
#     def from_csv(cls, recording_csv: str, dumps_dir: Optional[str]) -> 'ExecutionTrace':
#         et: ExecutionTrace = ExecutionTrace()
#         with open(recording_csv, 'r', newline='') as csv_file:
#             reader = csv.reader(csv_file, quotechar='"', delimiter=',', skipinitialspace=True)
#             header = [x.strip() for x in next(reader)]
#             if not check_header_match(header):
#                 raise Exception("Invalid input file format for %s" % recording_csv)
#             for row in reader:
#                 entry_dict = {header[i]: row[i].strip() for i in range(len(row))}
#                 te: TraceEntry = TraceEntry.from_dict(entry_dict, dumps_dir)
#                 et.append(te)
#         return et


from typing import List, Tuple

from utilities import Storable


class MemoryDelta(Storable):
    address: int
    anterior_value: int
    posterior_value: int

    def __init__(self, address: int, anterior_value: int, posterior_value: int):
        self.address = address
        self.anterior_value = anterior_value
        self.posterior_value = posterior_value

    def is_sane(self):
        if not isinstance(self.address, int) or not self.address >= 0:
            return False
        if not isinstance(self.anterior_value, int):
            return False
        if not isinstance(self.posterior_value, int):
            return False
        return True

    def __repr__(self):
        return "(0x%08X, 0x%02X >> 0x%02X)" % (self.address, self.anterior_value, self.posterior_value)

    def equals(self, other, ignore_value=False):
        if not isinstance(other, MemoryDelta):
            return False
        addr_match = self.address == other.address
        if addr_match and ignore_value:
            return True
        anterior_match = self.anterior_value == other.anterior_value
        posterior_match = self.posterior_value == other.posterior_value
        return addr_match and anterior_match and posterior_match


class TraceEntryDiff:
    instruction: Tuple[str, str]
    pc: Tuple[int, int]
    value: Tuple[int, int]
    address: Tuple[int, int]
    async_deltas: Tuple[List[MemoryDelta], List[MemoryDelta]]
    ignored_deltas: Tuple[List[MemoryDelta], List[MemoryDelta]]

    def __init__(self):
        pass

    def set_instruction(self, instruction1, instruction2):
        self.instruction = (instruction1, instruction2)

    def set_pc(self, pc1, pc2):
        self.pc = (pc1, pc2)

    def set_value(self, value1, value2):
        self.value = (value1, value2)

    def set_address(self, address1, address2):
        self.address = (address1, address2)

    def set_async_deltas(self, async_deltas1, async_deltas2):
        self.async_deltas = (async_deltas1, async_deltas2)

    def set_ignored_deltas(self, ignored_deltas1, ignored_deltas2):
        self.ignored_deltas = (ignored_deltas1, ignored_deltas2)

    @property
    def instruction_diff(self) -> bool:
        return self.instruction[0] != self.instruction[1]

    @property
    def pc_diff(self) -> bool:
        return self.pc[0] != self.pc[1]

    @property
    def value_diff(self) -> bool:
        return self.value[0] != self.value[1]

    @property
    def address_diff(self) -> bool:
        return self.address[0] != self.address[1]

    def async_deltas_diff(self, ignore_value=False) -> bool:
        for delta_1, delta_2 in zip(self.async_deltas[0], self.async_deltas[1]):
            if not delta_1.equals(delta_2, ignore_value=ignore_value):
                return True
        return False

    def ignored_deltas_diff(self, ignore_value=False) -> bool:
        for delta_1, delta_2 in zip(self.ignored_deltas[0], self.ignored_deltas[1]):
            if not delta_1.equals(delta_2, ignore_value=ignore_value):
                return True
        return False

    def has_any_dfference(self, ignore_dma_value=False):
        instruction = self.instruction_diff
        pc = self.pc_diff
        val = self.value_diff
        addr = self.address_diff
        deltas = self.async_deltas_diff(ignore_value=ignore_dma_value)
        ignored = self.ignored_deltas_diff()
        any_one = instruction or pc or val or addr or deltas or ignored
        return any_one


class TraceEntry(Storable):
    # index: int

    instruction: str
    pc: int
    value: int
    address: int
    async_deltas: List[MemoryDelta]
    ignored_deltas: List[MemoryDelta]

    def __init__(self, instruction: str, pc: int, value: int, address: int,
                 async_deltas: List[MemoryDelta], ignored_deltas: List[MemoryDelta]):
        self.instruction = instruction
        self.pc = pc
        self.value = value
        self.address = address
        self.async_deltas = async_deltas
        self.ignored_deltas = ignored_deltas

    def is_sane(self):
        if not isinstance(self.instruction, str) or self.instruction not in ["str", "ldr"]:
            return False
        if not isinstance(self.pc, int) or not self.pc >= 0:
            return False
        if not isinstance(self.value, int):
            return False
        if not isinstance(self.address, int) or not self.address >= 0:
            return False
        if not isinstance(self.async_deltas, list):
            return False
        for async_delta in self.async_deltas:
            if not isinstance(async_delta, MemoryDelta):
                return False
            if not async_delta.is_sane():
                return False

        return True

    def difference_with(self, other: 'TraceEntry') -> TraceEntryDiff:
        diff: TraceEntryDiff = TraceEntryDiff()
        diff.set_instruction(self.instruction, other.instruction)
        diff.set_pc(self.pc, other.pc)
        diff.set_value(self.value, other.value)
        diff.set_address(self.address, other.address)
        diff.set_async_deltas(self.async_deltas, other.async_deltas)
        diff.set_ignored_deltas(self.ignored_deltas, other.ignored_deltas)
        return diff

    def __repr__(self):
        if self.instruction == 'str':
            return 'STR %10s  to  0x%08X, at 0x%08X' % ("0x%X" % self.value, self.address, self.pc)
        elif self.instruction == 'ldr':
            return 'LDR %10s from 0x%08X, at 0x%08X' % ("0x%X" % self.value, self.address, self.pc)
        else:
            raise ValueError("Non-str/ldr instruction.")


class ExecutionTrace(Storable):
    entries: List[TraceEntry]

    def __init__(self):
        self.entries = []

    def is_sane(self):
        if not isinstance(self.entries, list):
            return False
        for entry in self.entries:
            if not isinstance(entry, TraceEntry):
                return False
            if not entry.is_sane():
                return False

        return True

    def append(self, trace_entry: TraceEntry):
        self.entries.append(trace_entry)

    def __repr__(self):
        return f'ExecutionTrace with {len(self.entries)} entries: [{", ".join([str(x) for x in self.entries]) }]'
