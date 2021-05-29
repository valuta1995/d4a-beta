from typing import List

from phases.recorder import ExecutionTrace, TraceEntry
from utilities import Storable


class DmaInfo(Storable):
    MAX_DEPTH_HR = 3
    execution_trace: ExecutionTrace

    index_of_first_incidence: int

    indices_of_trigger_instructions: List[int]
    indices_of_set_base_instructions: List[int]
    indices_of_set_size_instructions: List[int]

    dma_region_base: int
    dma_region_size: int

    def __init__(self, execution_trace: ExecutionTrace):
        self.execution_trace = execution_trace

        self.index_of_first_incidence = -1

        self.indices_of_trigger_instructions = []
        self.indices_of_set_base_instructions = []
        self.indices_of_set_size_instructions = []

        self.dma_region_base = -1
        self.dma_region_size = -1

    # noinspection DuplicatedCode
    def is_sane(self) -> bool:
        if not self.execution_trace.is_sane():
            return False

        if not isinstance(self.index_of_first_incidence, int):
            return False

        if not isinstance(self.indices_of_trigger_instructions, list):
            return False
        if not isinstance(self.indices_of_set_base_instructions, list):
            return False
        if not isinstance(self.indices_of_set_size_instructions, list):
            return False

        for x in self.indices_of_trigger_instructions:
            if not isinstance(x, int):
                return False
        for x in self.indices_of_set_base_instructions:
            if not isinstance(x, int):
                return False
            if self.dma_region_base != -1:
                if self.execution_trace.entries[x].value != self.dma_region_base:
                    print("Mismatch in trace-entry value and actual base address.")
                    return False

        for x in self.indices_of_set_size_instructions:
            if not isinstance(x, int):
                return False

        if not isinstance(self.dma_region_base, int) or self.dma_region_base < -1:
            return False
        if not isinstance(self.dma_region_size, int) or self.dma_region_size < -1:
            return False

        return True

    @property
    def entry_of_first_incidence(self) -> TraceEntry:
        return self.execution_trace.entries[self.index_of_first_incidence]

    @property
    def entries_of_trigger_instructions(self) -> List[TraceEntry]:
        return [self.execution_trace.entries[x] for x in self.indices_of_trigger_instructions]

    @property
    def entries_of_set_size_instructions(self) -> List[TraceEntry]:
        return [self.execution_trace.entries[x] for x in self.indices_of_set_size_instructions]

    @property
    def entries_of_set_base_instructions(self) -> List[TraceEntry]:
        return [self.execution_trace.entries[x] for x in self.indices_of_set_base_instructions]
