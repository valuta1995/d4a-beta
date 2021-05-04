import csv
import json
from typing import List, Any


class Peripheral:
    registers: List[int]

    def __init__(self, start: int, size: int):
        self.start = start
        self.size = size

        self.registers = []

    @property
    def end(self):
        return self.start + self.size

    def append_register(self, reg: int):
        self.registers.append(reg)


class PeripheralRow:

    peripherals: List[Peripheral]

    def __init__(self):
        self.peripherals = []

    def append(self, peripheral: Peripheral):
        self.peripherals.append(peripheral)

    @classmethod
    def write_to_csv(cls, peripherals: 'PeripheralRow', store_path: str):
        with open(store_path, mode='w', newline='') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quotechar='"')
            writer.writerow(["index", "start", "size", "registers", "", ])
            for i in range(len(peripherals.peripherals)):
                peripheral = peripherals.peripherals[i]
                writer.writerow([
                    i,
                    peripheral.start,
                    peripheral.size,
                    json.dumps([int(x) for x in peripheral.registers])
                ])
