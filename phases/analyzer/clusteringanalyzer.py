import os.path
from typing import Optional, List, Tuple

from phases.analyzer.peripheral_row import PeripheralRow, Peripheral
from phases.recorder import ExecutionTrace, TraceEntry
from utilities import naming_things

from . import DmaInfo


def homogenize_size_align(peripherals):
    """ Ensure that all peripherals have the same size. """
    # TODO implement if needed
    return peripherals


def static_find_first_dma_incidence(trace):
    candidate: Optional[TraceEntry] = None
    for entry in trace.entries:
        if candidate is None:
            if len(entry.async_deltas) <= 0:
                pass  # There was no candidate, there still is none
            else:
                candidate = entry
        elif len(entry.async_deltas) > len(candidate.async_deltas):
            candidate = entry
    return candidate


class ClusteringAnalyzer:

    def __init__(self, execution_trace: ExecutionTrace, ram_base: int, work_dir: str = "."):
        self.execution_trace = execution_trace
        self.ram_base = ram_base
        self.work_dir = work_dir
        self.dma_info = DmaInfo(execution_trace)

    def start(self, epsilon: float):
        number_of_entries = len(self.execution_trace.entries)
        print("Analysis over %d entries (e = %.4d)" % (number_of_entries, epsilon))

        peripherals = self.cluster_peripherals(epsilon)
        peripherals = homogenize_size_align(peripherals)

        self.store_peripherals(peripherals)

        # The instruction with the first incidence of the largest incidence
        triggering_instruction = self.find_dma_incidence()
        if triggering_instruction is None:
            self.fail_no_dma()
            return

        triggering_instruction_index = self.execution_trace.entries.index(triggering_instruction)
        self.dma_info.index_of_first_incidence = triggering_instruction_index
        self.dma_info.indices_of_trigger_instructions = [triggering_instruction_index]

        list_of_deltas = triggering_instruction.async_deltas
        list_of_delta_addresses = [x.address for x in list_of_deltas]

        lb = min(list_of_delta_addresses)
        ub = max(list_of_delta_addresses)

        # Look up to n instructions ahead and expand the range to catch more slow moving DMA traffic.
        for i in range(10):
            next_instruction_index = triggering_instruction_index + 1
            if next_instruction_index >= len(self.execution_trace.entries):
                break
            next_instruction = self.execution_trace.entries[next_instruction_index]

            overlap = False
            next_instruction_delta_addresses = []
            for delta in next_instruction.async_deltas:
                address = delta.address
                next_instruction_delta_addresses.append(address)
                if lb <= address <= ub:
                    overlap = True

            if overlap:
                list_of_delta_addresses += next_instruction_delta_addresses
            else:
                break

            lb = min(list_of_delta_addresses)
            ub = max(list_of_delta_addresses)

        first_diff_address = lb
        self.dma_info.dma_region_base = first_diff_address

        set_base_candidates, set_base_indices = self.find_set_base_candidates(first_diff_address,
                                                                              triggering_instruction_index)
        if len(set_base_candidates) == 0:
            raise Exception("Unable to find instruction responsible for the base.")
        else:
            self.dma_info.indices_of_set_base_instructions = set_base_indices

        last_diff_address = ub

        dma_region_size = 1 + (last_diff_address - first_diff_address)
        self.dma_info.dma_region_size = dma_region_size
        set_size_candidates, set_size_indices = self.find_set_size_instruction(dma_region_size,
                                                                               triggering_instruction_index)
        if len(set_size_candidates) == 0:
            raise Exception("Unable to find instruction responsible for the size.")
        else:
            self.dma_info.indices_of_set_size_instructions = set_size_indices

        out_path = os.path.join(self.work_dir, naming_things.DMA_INFO_JSON)
        DmaInfo.to_file(out_path, self.dma_info)

        out_path = os.path.join(self.work_dir, naming_things.DMA_INFO_HR_JSON)
        DmaInfo.to_file(out_path, self.dma_info, max_depth=DmaInfo.MAX_DEPTH_HR)
        # with open(out_path, mode='w') as json_file:
        #     json.dump({
        #         "start_instruction": TraceEntry.to_dict(triggering_instruction),
        #         "set_addr_instruction": TraceEntry.to_dict(set_base_candidates[-1]),
        #         "set_addr_alternatives": [TraceEntry.to_dict(x) for x in set_base_candidates],
        #         "set_size_instruction": TraceEntry.to_dict(set_size_candidates[-1]),
        #         "set_size_alternatives": [TraceEntry.to_dict(x) for x in set_size_candidates],
        #         "dma_region_start": dma_region_base,
        #         "dma_region_size": dma_region_size,
        #     }, json_file, indent=4, sort_keys=True)

    def fail_no_dma(self):
        print("\n")
        print("Failed to find an instruction with a non-zero number of changed bytes. Assuming no DMA\n")
        print("\n")

        out_path = os.path.join(self.work_dir, naming_things.DMA_INFO_JSON)

        DmaInfo.to_file(out_path, self.dma_info)
        #
        # with open(out_path, mode='w') as json_file:
        #     json.dump({
        #         "start_instruction": None,
        #         "set_addr_instruction": None,
        #         "set_size_instruction": None,
        #         "dma_region_start": None,
        #         "dma_region_size": None,
        #     }, json_file, indent=4, sort_keys=True)

    def cluster_peripherals(self, epsilon: float):
        from numpy import reshape, unique, where
        from sklearn.cluster import DBSCAN

        peripherals: PeripheralRow = PeripheralRow()

        addresses = [x.address for x in self.execution_trace.entries]
        big_x = reshape(addresses, (-1, 1))
        model = DBSCAN(min_samples=2, eps=epsilon)
        y_hat = model.fit_predict(big_x)
        cluster_names = unique(y_hat)

        for cluster_name in cluster_names:
            row_ix = where(y_hat == cluster_name)

            cluster_addresses_matrix = big_x[row_ix, 0]
            cluster_addresses = cluster_addresses_matrix[0]
            registers = unique(sorted(cluster_addresses))

            if cluster_name == -1:
                # This is a list of all non-clustered registers.
                for register in registers:
                    peripheral: Peripheral = Peripheral(int(register), int(1))
                    peripheral.append_register(int(register))
                    peripherals.append(peripheral)

            else:
                # This is a regular cluster of registers
                lo_reg = registers[0]
                hi_reg = registers[-1]
                peripheral_size = hi_reg - lo_reg
                peripheral_p2_sz = 1 << int(peripheral_size - 1).bit_length()
                peripheral_start = (lo_reg // peripheral_p2_sz) * peripheral_p2_sz

                if not isinstance(peripheral_start, int):
                    peripheral_start = int(peripheral_start)
                if not isinstance(peripheral_p2_sz, int):
                    peripheral_p2_sz = int(peripheral_p2_sz)
                peripheral: Peripheral = Peripheral(peripheral_start, peripheral_p2_sz)
                for reg in registers:
                    peripheral.append_register(reg)

                peripherals.append(peripheral)

        return peripherals

    def store_peripherals(self, peripherals):
        out_path = os.path.join(self.work_dir, naming_things.PERIPHERAL_JSON_NAME)
        PeripheralRow.to_file(out_path, peripherals)

    def find_dma_incidence(self) -> Optional[TraceEntry]:
        """Find the largest incidence, or the first of the largest if there are multiple of the same size. """
        trace = self.execution_trace
        entry: TraceEntry
        return static_find_first_dma_incidence(trace)

    def find_set_base_candidates(self, dma_region_base: int, index_limit: int) -> Tuple[List[TraceEntry], List[int]]:
        entry: TraceEntry

        hard_matches: List[TraceEntry] = []
        hard_match_indices: List[int] = []

        soft_matches: List[TraceEntry] = []
        soft_match_indices: List[int] = []

        for i in range(len(self.execution_trace.entries)):
            # Only instructions before the initial occurrence of DMA can affect it
            if i > index_limit:
                break

            entry: TraceEntry = self.execution_trace.entries[i]

            # TODO proxied locations
            if entry.value == dma_region_base:
                hard_matches.append(entry)
                hard_match_indices.append(i)
            elif abs(entry.value - dma_region_base) <= 2:
                soft_matches.append(entry)
                soft_match_indices.append(i)

        if len(hard_matches) > 0:
            return hard_matches, hard_match_indices
        elif len(soft_matches) > 0:
            return soft_matches, soft_match_indices
        else:
            return [], []

    def find_set_size_instruction(self, dma_region_size: int, index_limit: int) -> Tuple[List[TraceEntry], List[int]]:
        size_candidates = [
            dma_region_size,  # Actual size
            dma_region_size // 2,  # Divide by 2.
            dma_region_size // 4,  # Divide by 4
            (dma_region_size + 1) // 2,  # Round up to the nearest multiple of 2, divide by 2.
            (dma_region_size + 3) // 4,  # Round up to the nearest multiple of 4, divide by 4
        ]
        size_candidates = [x for x in size_candidates if x > 0]

        entry: TraceEntry
        hard_matches: List[TraceEntry] = []
        hard_match_indices: List[int] = []
        for i in range(len(self.execution_trace.entries)):
            # Only instruction before the start of DMA can affect the DMA operation
            if i > index_limit:
                break

            entry: TraceEntry = self.execution_trace.entries[i]

            # TODO soft(er) match heuristics
            # TODO proxied values
            if entry.value in size_candidates:
                hard_matches.append(entry)
                hard_match_indices.append(i)

        return hard_matches, hard_match_indices
