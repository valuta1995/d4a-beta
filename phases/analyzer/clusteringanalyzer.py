import json
import os.path
from typing import Optional, List

from phases.analyzer.peripheral_row import PeripheralRow, Peripheral
from phases.recorder import ExecutionTrace, TraceEntry
from utilities import naming_things


def homogenize_size_align(peripherals):
    """ Ensure that all peripherals have the same size. """
    # TODO implement if needed
    return peripherals


class ClusteringAnalyzer:

    def __init__(self, entries: ExecutionTrace, ram_base: int, work_dir: str = "."):
        self.entries = entries
        self.ram_base = ram_base
        self.work_dir = work_dir

    def start(self, epsilon: float):
        print("Analysis over %d entries (e = %.4d)" % (self.entries.length, epsilon))

        peripherals = self.cluster_peripherals(epsilon)
        peripherals = homogenize_size_align(peripherals)

        self.store_peripherals(peripherals)

        # The instruction with the first incidence of the largest incidence
        triggering_instruction = self.find_first_incidence()
        if triggering_instruction is None:
            print("\n")
            print("Failed to find an instruction with a non-zero number of changed bytes. Assuming no DMA\n")
            print("\n")
            with open(os.path.join(self.work_dir, naming_things.DMA_INFO_JSON), mode='w') as json_file:
                json.dump({
                    "start_instruction": None,
                    "set_addr_instruction": None,
                    "set_size_instruction": None,
                    "dma_region_start": None,
                    "dma_region_size": None,
                }, json_file, indent=4, sort_keys=True)
        else:
            diffs_at_trigger = sorted(triggering_instruction.mem_delta)

            first_diff = diffs_at_trigger[0]
            first_diff_offset = first_diff[0]

            dma_region_base = first_diff_offset + self.ram_base
            set_base_candidates = self.find_set_base_candidates(dma_region_base, triggering_instruction.index)
            if len(set_base_candidates) == 0:
                raise Exception("Unable to find instruction responsible for the base.")

            last_diff = diffs_at_trigger[-1]
            last_diff_offset = last_diff[0]

            dma_region_size = 1 + (last_diff_offset - first_diff_offset)
            set_size_candidates = self.find_set_size_instruction(dma_region_size, triggering_instruction.index)
            if len(set_size_candidates) == 0:
                raise Exception("Unable to find instruction responsible for the base.")

            with open(os.path.join(self.work_dir, naming_things.DMA_INFO_JSON), mode='w') as json_file:
                json.dump({
                    "start_instruction": TraceEntry.to_dict(triggering_instruction),
                    "set_addr_instruction": TraceEntry.to_dict(set_base_candidates[-1]),
                    "set_addr_alternatives": [TraceEntry.to_dict(x) for x in set_base_candidates],
                    "set_size_instruction": TraceEntry.to_dict(set_size_candidates[-1]),
                    "set_size_alternatives": [TraceEntry.to_dict(x) for x in set_size_candidates],
                    "dma_region_start": dma_region_base,
                    "dma_region_size": dma_region_size,
                }, json_file, indent=4, sort_keys=True)

    def cluster_peripherals(self, epsilon: float):
        from numpy import reshape, unique, where
        from sklearn.cluster import DBSCAN

        peripherals: PeripheralRow = PeripheralRow()

        addresses = self.entries.all_addresses
        big_x = reshape(addresses, (-1, 1))
        model = DBSCAN(min_samples=2, eps=epsilon)
        y_hat = model.fit_predict(big_x)
        cluster_names = unique(y_hat)

        for cluster_name in cluster_names:
            row_ix = where(y_hat == cluster_name)

            cluster_addresses_matrix = big_x[row_ix, 0]
            cluster_addresses = cluster_addresses_matrix[0]
            registers = unique(sorted(cluster_addresses))
            lo_reg = registers[0]
            hi_reg = registers[-1]
            peripheral_size = hi_reg - lo_reg
            peripheral_p2_sz = 1 << int(peripheral_size - 1).bit_length()
            peripheral_start = (lo_reg // peripheral_p2_sz) * peripheral_p2_sz

            peripheral: Peripheral = Peripheral(peripheral_start, peripheral_p2_sz)
            for reg in registers:
                peripheral.append_register(reg)

            peripherals.append(peripheral)

        return peripherals

    def store_peripherals(self, peripherals):
        csv_path = os.path.join(self.work_dir, naming_things.PERIPHERAL_CSV_NAME)
        PeripheralRow.write_to_csv(peripherals, csv_path)

    def find_first_incidence(self) -> Optional[TraceEntry]:
        entry: TraceEntry
        candidate: Optional[TraceEntry] = None
        for entry in self.entries.entries:
            if candidate is None:
                if len(entry.mem_delta) <= 0:
                    pass  # There was no candidate, there still is none
                else:
                    candidate = entry
            elif len(entry.mem_delta) > len(candidate.mem_delta):
                candidate = entry
        return candidate

    def find_set_base_candidates(self, dma_region_base: int, index_limit: int) -> List[TraceEntry]:
        entry: TraceEntry
        hard_matches: List[TraceEntry] = []
        for entry in self.entries.entries:
            # Only instructions before the start of DMA can affect it
            if entry.index > index_limit:
                break

            # TODO soft match heuristics
            # TODO proxied locations
            if entry.value == dma_region_base:
                hard_matches.append(entry)
        return hard_matches

    def find_set_size_instruction(self, dma_region_size: int, index_limit: int) -> List[TraceEntry]:
        size_candidates = [dma_region_size, dma_region_size // 2, dma_region_size // 4]
        size_candidates = [x for x in size_candidates if x > 0]

        entry: TraceEntry
        hard_matches: List[TraceEntry] = []
        for entry in self.entries.entries:
            # Only instruction before the start of DMA can affect the DMA operation
            if entry.index > index_limit:
                break

            # TODO soft(er) match heuristics
            # TODO proxied values
            if entry.value in size_candidates:
                hard_matches.append(entry)

        return hard_matches
