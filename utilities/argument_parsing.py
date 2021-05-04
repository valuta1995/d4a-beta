import csv
import json
from typing import List, Dict


def auto_int(x):
    return int(x, 0)


def parse_dma_info(dma_info_file):
    with open(dma_info_file, mode='r') as json_file:
        dma_info = json.load(json_file)
    return dma_info


def try_for_int(input_text):
    try:
        return int(input_text)
    except ValueError:
        return input_text


def parse_peripherals(peripheral_csv_path, add_dummy: bool = False) -> List[Dict[str, any]]:
    peripherals = []
    if add_dummy:
        dummy_peripheral = {
            'index': -1,
            'start': -1,
            'size': 0,
            'registers': [],
        }
        peripherals.append(dummy_peripheral)

    with open(peripheral_csv_path, mode='r', newline='') as csv_file:
        reader = csv.reader(csv_file, delimiter=',', quotechar='"')
        header = [x.strip() for x in next(reader)]
        for row in reader:
            peripheral = {header[i]: try_for_int(row[i].strip()) for i in range(len(row))}
            peripheral['registers'] = json.loads(peripheral['registers'])
            peripherals.append(peripheral)

    return peripherals