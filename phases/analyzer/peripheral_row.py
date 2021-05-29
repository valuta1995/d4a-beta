from enum import Enum
from typing import List, Optional, Dict

from phases.recorder import ExecutionTrace
from utilities import Storable


class InfoFlag(Enum):
    UNKNOWN = 0

    TERMINATED_EARLY = 1
    TERMINATED_LATE = 2
    FAILED_TO_TERMINATE = 3

    TIMED_OUT = 11

    UNEXPECTED_NEW_DMA = 21
    MISSING_OLD_DMA = 22

    VALUE_CHANGED = 31
    IGNORED_DELTA_CHANGED = 32
    DESYNC = 33


class Peripheral(Storable):
    start: int
    size: int

    registers: List[int]
    exit_reasons: List[str]

    __execution_trace: Optional[ExecutionTrace]
    __flags: Dict[int, bool]

    def __init__(self, start: int, size: int):
        self.start = start
        self.size = size

        self.registers = []
        self.exit_reasons = []

        self.__execution_trace = None
        self.__flags = dict()
        for flag in InfoFlag:
            self.__flags[flag.value] = False

    @property
    def end(self):
        return self.start + self.size

    @property
    def execution_trace(self) -> ExecutionTrace:
        if self.__execution_trace is None:
            raise Exception("Trying to access None-trace")
        return self.__execution_trace

    @execution_trace.setter
    def execution_trace(self, execution_trace: ExecutionTrace):
        if self.__execution_trace is None:
            self.__execution_trace = execution_trace
        else:
            raise Exception("Execution trace ws already set and should not be overwritten.")

    def append_register(self, reg: int):
        if not isinstance(reg, int):
            reg = int(reg)
        self.registers.append(reg)

    def append_exit_reason(self, line: str):
        self.exit_reasons.append(line)

    def is_sane(self) -> bool:
        if not isinstance(self.start, int) or self.start < -1:
            return False
        if not isinstance(self.size, int) or self.size < -1:
            return False

        if self.start == -1 or self.size == -1:
            if self.start != -1 or self.size != -1 or len(self.registers) > 0:
                return False

        if not isinstance(self.registers, list):
            return False
        for x in self.registers:
            if not isinstance(x, int) or x < 0:
                return False

        if not isinstance(self.exit_reasons, list):
            return False
        for x in self.exit_reasons:
            if not isinstance(x, str):
                return False

        if self.__execution_trace is not None:
            if not isinstance(self.__execution_trace, ExecutionTrace):
                return False
            if not self.__execution_trace.is_sane():
                return False

        old_dict = self.__flags
        self.__flags = dict()
        for key, value in old_dict.items():
            if not (isinstance(key, int) or isinstance(key, str)):
                return False
            if not isinstance(value, bool):
                return False

            try:
                self.__flags[int(key)] = value
            except ValueError:
                return False

        return True

    def flag(self, flag: InfoFlag, value=True):
        print("\t - %s" % flag.name)
        self.__flags[flag.value] = True

    def has_one_of_flags(self, flags_to_check_for: List[InfoFlag]):
        for flag in flags_to_check_for:
            has_flag = flag.value in self.__flags
            if has_flag:
                valid_flag = self.__flags[flag.value]
                if valid_flag:
                    return True
        return False

    def has_all_of_flags(self, flags_to_check_for: List[InfoFlag]):
        for flag in flags_to_check_for:
            if not self.__flags[flag.value]:
                return False
        return True


class PeripheralRow(Storable):
    HUMAN_READABLE_DEPTH = 5

    peripherals: List[Peripheral]

    def __init__(self):
        self.peripherals = []

    def append(self, peripheral: Peripheral):
        self.peripherals.append(peripheral)

    # @classmethod
    # def write_to_csv(cls, peripherals: 'PeripheralRow', store_path: str):
    #     with open(store_path, mode='w', newline='') as csv_file:
    #         writer = csv.writer(csv_file, delimiter=',', quotechar='"')
    #         writer.writerow(["index", "start", "size", "registers", "", ])
    #         for i in range(len(peripherals.peripherals)):
    #             peripheral = peripherals.peripherals[i]
    #             writer.writerow([
    #                 i,
    #                 peripheral.start,
    #                 peripheral.size,
    #                 json.dumps([int(x) for x in peripheral.registers])
    #             ])

    def is_sane(self) -> bool:
        if not isinstance(self.peripherals, list):
            return False

        for x in self.peripherals:
            if not isinstance(x, Peripheral) or not x.is_sane():
                return False

        return True
