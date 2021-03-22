from typing import List, Optional


class TraceEntry:
    index: int
    instr: str
    pc: int
    value: int
    addr: int
    mem_delta: Optional[List[int]]

    def __init__(self, instruction: str, pc: int, value: int, addr: int, mem_delta: Optional[List[int]]):
        self.index = -1
        self.instr = instruction
        self.pc = pc
        self.value = value
        self.addr = addr
        self.mem_delta = mem_delta


class ExecutionTrace:
    entries: List[TraceEntry]

    def __init__(self):
        self.entries = []

    @property
    def length(self) -> int:
        return len(self.entries)

    def append(self, entry: TraceEntry):
        entry.index = self.length
        self.entries.append(entry)

    def peek(self) -> TraceEntry:
        return self.entries[-1]

    def get(self, index: int) -> TraceEntry:
        return self.entries[index]


def read_trace(recording_path: str) -> ExecutionTrace:
    # TODO implement trace parsing
    raise NotImplementedError("TODO implement trace parsing")
