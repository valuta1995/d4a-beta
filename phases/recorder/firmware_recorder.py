import os
import random
from datetime import datetime
from typing import Tuple, List, Dict, Optional

from avatar2 import ARM_CORTEX_M3, Target

from a2h import Avatar2Handler
from utilities import naming_things
from . import ExecutionTrace, TraceEntry, ExecutionLogger, MemoryDelta


def recurse_has_loops(items: list, loop_items: list, amount: int) -> bool:
    if amount == 0:
        # Done finding
        return True

    loop_length = len(loop_items)
    items_length = len(items)
    if items_length < amount * loop_length:
        # Wouldn't fit
        return False

    # Now two things must be true
    # The loop items must match the last set
    candidate_items = items[-loop_length:]
    if candidate_items == loop_items:
        return recurse_has_loops(items[0:-loop_length], loop_items, amount - 1)
    else:
        # Did not match
        return False


def calculate_memory_delta(before_mem: bytes, after_mem: bytes, ignore: Tuple[int, int], ram_base: int
                           ) -> Tuple[List[MemoryDelta], List[MemoryDelta]]:
    """
    :param before_mem: State of the memory before our changes
    :param after_mem: State of the memory after our changes (and a small delay)
    :param ignore: Section of memory to ignore
    :param ram_base: Base address of the region that is captured.
    :return:
    """
    diffs: List[MemoryDelta] = []
    ignored: List[MemoryDelta] = []
    for index, pair in enumerate(zip(before_mem, after_mem)):
        if pair[0] != pair[1]:
            md = MemoryDelta(ram_base + index, pair[0], pair[1])
            if not ignore[0] <= index < ignore[0] + ignore[1]:
                diffs.append(md)
            else:
                ignored.append(md)
                print("Ignored a diff at 0x%08X due to ignore region." % index)
    return diffs, ignored


def find_bx_lr(target: Target):
    c_pc = target.read_register('pc')
    while True:
        c_instr = target.read_memory(c_pc, 2)
        if c_instr == 0x4770:
            return c_pc
        c_pc += 2


class FirmwareRecorder:
    work_dir: str
    snapshot_dir: str
    exit_reason_path: str

    a2h: Avatar2Handler
    original_trace: Optional[ExecutionTrace]
    logger: ExecutionLogger

    stopped: bool
    step_counter: int

    shadow_realm: Dict[int, int]
    mocked_regions: List[Tuple[int, int]]
    shimmed_regions: List[Tuple[int, int, int]]

    snapshot_region: Tuple[int, int]
    peripheral_region: Tuple[int, int]

    abort_step_timer: int
    abort_grace_steps: int
    abort_after_deviation: bool
    abort_after_dma: bool
    abort_after_loops: int
    abort_after_pc: int
    abort_after_iterations: int
    abort_per_step_timeout: int

    def __init__(
            self,
            openocd_cfg: str, mem_ram: Tuple[int, int], mem_peripheral: Tuple[int, int],
            mocked_regions: List[Tuple[int, int]], shimmed_regions: List[Tuple[int, int, int]],
            work_dir: str,
            original_trace: Optional[ExecutionTrace] = None,
            abort_grace_steps=0,
            abort_after_deviation=False,
            abort_after_dma=False,
            abort_after_loops=-1,
            abort_after_pc=-1,
            abort_at_step=-1,
            abort_per_step_timeout=-1
    ):
        """
        :param openocd_cfg: Path to the OpenOCD configuration file for the board/chip under test
        :param mem_ram: (start, size) of the region of ram that might contain DMA target buffers
        :param mem_peripheral: (start, size) of the region of memory that contains the DMA controller)
        :param mocked_regions: A list of (start, size)s of regions where writes to HW are redirected
        :param shimmed_regions: A list of (start, size, mock_value)s of regions where writes to HW are redirected
        :param work_dir: Directory to store data for the current run in.

        :param original_trace: Optional ExecutionTrace object with the original trace
        :param abort_grace_steps: Amount of steps to keep running after a non critical abort (0 to disable).
        :param abort_after_deviation: Abort this many steps after execution (requires original trace)
        :param abort_after_dma: Flag to enable aborting after the first instance of detected DMA
        :param abort_after_loops: Minimum number of repetitions of any length to trigger abort (-1 to disable).
        :param abort_after_pc: A specific PC that triggers abort when reached (-1 to disable).
        :param abort_at_step: Critically abort when reaching this step number (-1 to disable) (no grace).
        :param abort_per_step_timeout: If any step takes longer that this amount of seconds, critically abort.
        """

        avatar_output_directory = os.path.join(work_dir, naming_things.AVATAR_OUTPUT_DIRECTORY)
        if not os.path.exists(avatar_output_directory):
            os.mkdir(avatar_output_directory)
        if not os.path.isdir(avatar_output_directory):
            raise Exception("Failed to create directory.")

        snapshot_dir = os.path.join(work_dir, naming_things.MEMORY_SNAPSHOT_DIRECTORY)
        if not os.path.exists(snapshot_dir):
            os.mkdir(snapshot_dir)
        if not os.path.isdir(snapshot_dir):
            raise Exception("Failed to create directory.")

        exit_reason_path = os.path.join(work_dir, naming_things.EXIT_REASON_FILE)
        with open(exit_reason_path, 'w') as exit_reason_file:
            current_time = datetime.now().time()
            exit_reason_file.write("Started at %02d:%02d:%02d\n" % (
                current_time.hour, current_time.minute, current_time.second
            ))

        # TODO infer architecture or get architecture from parameters, as opposed to using hardcoded value
        architecture = ARM_CORTEX_M3
        a2h = Avatar2Handler(openocd_cfg, mem_peripheral, mem_ram, avatar_output_directory, architecture)
        a2h.set_mmf_callback(self.on_fault)

        if original_trace is None and abort_after_deviation:
            raise Exception("Cannot check deviation without a trace")

        # Store directory and file paths
        self.work_dir = work_dir
        self.snapshot_dir = snapshot_dir
        self.exit_reason_path = exit_reason_path

        # Store objects for interaction
        self.a2h = a2h
        self.original_trace = original_trace
        self.logger = ExecutionLogger(self.work_dir)

        # Keep track os the state
        self.stopped = True
        self.step_counter = -1

        # Keep track of fake memory
        self.shadow_realm = dict()
        self.mocked_regions = mocked_regions
        self.shimmed_regions = shimmed_regions

        # Track the two interesting memory regions
        self.snapshot_region = mem_ram
        self.peripheral_region = mem_peripheral

        # Track the abort status and configuration
        self.abort_step_timer = -1
        self.abort_grace_steps = abort_grace_steps
        self.abort_after_deviation = abort_after_deviation
        self.abort_after_dma = abort_after_dma
        self.abort_after_loops = abort_after_loops
        self.abort_after_pc = abort_after_pc
        self.abort_after_iterations = abort_at_step
        self.abort_per_step_timeout = abort_per_step_timeout

        # Final setup
        self.bx_lr_location = find_bx_lr(self.a2h.target)

    def append_exit_reason(self, msg: str):
        with open(self.exit_reason_path, 'a') as exit_reason_file:
            exit_reason_file.write(msg + "\n")

    def test_for_loop(self) -> bool:
        current_history: List[TraceEntry] = self.logger.execution_trace.entries
        for i in range(1, 1 + len(current_history) // self.abort_after_loops):
            search_part = current_history[:-i]
            loop_part = current_history[-i:]
            if recurse_has_loops(search_part, loop_part, self.abort_after_loops - 1):
                return True
        return False

    def has_deviated(self) -> bool:
        original_trace_entries = self.original_trace.entries
        current_trace_entries = self.logger.execution_trace.entries

        current_index = len(current_trace_entries) - 1
        original_item = original_trace_entries[current_index]
        current_item = current_trace_entries[current_index]

        if original_item.address != current_item.address or original_item.pc != current_item.pc:
            # TODO reduce aggressiveness if needed?
            # For example, if it is not exact, it may be any other value that appears at least twice.
            return True
        return False

    def dma_occurred(self) -> bool:
        last_item = self.logger.execution_trace.entries[-1]
        if len(last_item.async_deltas) != 0:
            # TODO reduce aggressiveness if needed?
            # For example, at least two mem locations need changing
            return True
        return False

    def test_abort_conditions(self, faulting_addr: int, faulting_pc: int):
        # First test the timed aborts, only if we're not already counting down.
        number_of_events = len(self.logger.execution_trace.entries)
        if self.abort_step_timer == -1:
            # First, check abort_after_deviation
            if self.abort_after_deviation and self.has_deviated():
                self.write_log_reason_set_timer(
                    naming_things.REASON_DEVIATION,
                    "Terminating after %d events; deviation from trace." % number_of_events
                )

            # Second, check abort_after_dma
            if self.abort_after_dma and self.dma_occurred():
                self.write_log_reason_set_timer(
                    naming_things.REASON_DMA,
                    "Terminating after %d events; some dma detected." % number_of_events
                )

            # Third, check abort_after_loops
            if self.abort_after_loops != -1 and self.test_for_loop():
                self.write_log_reason_set_timer(
                    naming_things.REASON_LOOPS,
                    "Terminating after %d events; looped %d times" % (number_of_events, self.abort_after_loops)
                )

            # Fourth, check abort_after_pc
            if self.abort_after_pc != -1 and faulting_pc == self.abort_after_pc:
                self.write_log_reason_set_timer(
                    naming_things.REASON_PC,
                    "Terminating after %d events; reached set PC 0x%X" % (number_of_events, self.abort_after_pc)
                )

            if self.abort_after_iterations != -1 and number_of_events >= self.abort_after_iterations:
                self.write_log_reason_set_timer(
                    naming_things.REASON_STEPS,
                    "Terminating after %d events; limit reached." % number_of_events
                )
        else:
            print("Aborting in %d steps" % self.abort_step_timer)

    def write_log_reason_set_timer(self, reason, message):
        with open(self.exit_reason_path, 'a') as exit_reason_file:
            exit_reason_file.write("%s\n" % reason)
        self.a2h.target.log.info(message)
        # Set the abort countdown to the desired length
        self.abort_step_timer = self.abort_grace_steps

    def on_fault(self) -> bool:
        faulting_addr = self.a2h.get_mm_faulting_addr()

        if faulting_addr is None:
            self.a2h.target.log.error("MMF cause address is stale, this can cause skipped steps.")
            return False  # Unsuccessful
        if not self.peripheral_region[0] <= faulting_addr < self.peripheral_region[0] + self.peripheral_region[1]:
            self.a2h.target.log.info("MMF cause address is not in the peripheral region. Ignoring.")
            return True  # Successful, we just don't care

        # DONE figure out how to abort_per_step_timeout
        # https://medium.com/@chaoren/how-to-timeout-in-python-726002bf2291
        # self.event_index += 1 is handled through appending to the history

        # TODO determine when snapshotting is not interesting (add a parameter later?)
        skip_snapshot = False

        before_mem: Optional[bytes]
        number_of_events = len(self.logger.execution_trace.entries)
        if not skip_snapshot:
            snapshot_name = "%03d_%s" % (number_of_events, naming_things.BEFORE_DUMP_NAME)
            before_mem = self.a2h.make_snapshot(self.snapshot_region, os.path.join(self.snapshot_dir, snapshot_name))
        else:
            before_mem = None

        # Get the full context at the fault_moment
        stack_frame_location = self.a2h.get_stack_frame_location()
        context = self.a2h.read_context(stack_frame_location)
        faulting_pc = context['pc']

        # Parse the instruction that caused the fault
        effect, instruction = self.a2h.get_instruction_effect(faulting_pc)
        try:
            accessed_addr = effect.compute_memory_address(self.a2h.target, context)
        except KeyError as err:
            print(err)
            print("Couldn't process a register...")
            raise KeyError("With %s" % instruction)
        if accessed_addr != faulting_addr:
            raise Exception("The instruction's computed accessed address does not match the fault information.")

        # Replay or spoof the memory operation that caused the fault
        value_to_shim = self.should_be_shimmed(accessed_addr)
        should_mock = self.should_be_mocked(accessed_addr)
        if should_mock or value_to_shim is not None:
            print("\t\t\t\t\t\t\t\t\tRunning alternate mode")
        if effect.mode == 'str':
            value = effect.get_register_value(self.a2h.target, context)
            # Spoof or Replay store
            if value_to_shim is not None:
                self.shadow_realm[accessed_addr] = value
                self.a2h.target.write_memory(accessed_addr, effect.size, value_to_shim)

            elif should_mock:
                self.shadow_realm[accessed_addr] = value

            else:
                self.a2h.target.write_memory(accessed_addr, effect.size, value)

        elif effect.mode == 'ldr':
            # Spoof or Replay load
            if value_to_shim is not None:
                if accessed_addr in self.shadow_realm:
                    value = self.shadow_realm[accessed_addr]
                else:
                    self.a2h.avatar.log.warn("Substituting hardware-read value as no shadow value is present.")
                    value = self.a2h.target.read_memory(accessed_addr, effect.size)

            elif should_mock:
                if accessed_addr in self.shadow_realm:
                    value = self.shadow_realm[accessed_addr]
                else:
                    self.a2h.avatar.log.warn("Substituting hardware-read value as no shadow value is present.")
                    value = self.a2h.target.read_memory(accessed_addr, effect.size)

            else:
                value = self.a2h.target.read_memory(accessed_addr, effect.size)
            effect.set_register_value(self.a2h.target, context, value)

        else:
            raise Exception("Faulting condition triggered by a non str/ldr instruction. What!?")

        # self.append_log moved to after second snapshot.
        # Move the program counter and store changed memory values
        context['pc'] += effect.instruction_bytes
        self.a2h.write_context(stack_frame_location, context)

        # Move the actual PC to any BX, LR; instruction to exit the fault handler.
        self.a2h.target.write_register('pc', self.bx_lr_location)

        after_mem: Optional[bytes]
        if not skip_snapshot:
            # time.sleep(1)
            snapshot_name = "%03d_%s" % (number_of_events, naming_things.AFTER_DUMP_NAME)
            after_mem = self.a2h.make_snapshot(self.snapshot_region, os.path.join(self.snapshot_dir, snapshot_name))
            ignore_region = stack_frame_location - self.snapshot_region[0], 4 * len(context)
            mem_delta, ignored = calculate_memory_delta(before_mem, after_mem, ignore_region, self.snapshot_region[0])
        else:
            mem_delta = None
            ignored = None

        # entry = TraceEntry(effect.mode, faulting_pc, value, faulting_addr, mem_delta, ignored)
        # Side effect, entry is now indexed properly
        self.logger.add_entry(effect.mode, faulting_pc, value, faulting_addr, mem_delta, ignored)
        # self.log_entry(entry, ignored)

        self.test_abort_conditions(faulting_addr, faulting_pc)

        return True  # Successful

    def start(self):
        self.stopped = False
        self.logger.initialize()

        # go_go_gadget_ipython(self.a2h.target, {'a2h': self.a2h})

        while not self.stopped:
            # Count the current steps
            self.step_counter += 1

            # If there are steps left, keep track
            if self.abort_step_timer > 0:
                self.abort_step_timer -= 1

            # If this was the last step, prepare for termination
            if self.abort_step_timer == 0:
                self.stopped = True
                self.append_exit_reason("Abort step timer ran out.")

            # if self.step_counter >= self.abort_after_iterations:
            #     self.stopped = True
            #     self.append_exit_reason("Stopped after %d steps." % self.abort_after_iterations)

            # print("Starting at %d" % self.history.length)
            # if self.history.length >= 205:
            #     print("\n\n======================[ %d ]======================\n" % self.history.length)
            #     go_go_gadget_ipython(self.a2h.target, {'a2h': self.a2h})
            # else:
            #     self.a2h.continue_and_wait()
            # print("   Finished %d\n\n" % self.history.length)

            if self.abort_per_step_timeout > -1:
                try:
                    self.a2h.continue_and_wait(timeout=self.abort_per_step_timeout)
                except TimeoutError:
                    self.stopped = True
                    self.append_exit_reason("Step took more than %d seconds." % self.abort_per_step_timeout)
            else:
                self.a2h.continue_and_wait()

        self.a2h.target.log.info("Firmware_recorder.py:start() has finished.")
        self.logger.finalize()

    def should_be_mocked(self, accessed_addr) -> bool:
        for region in self.mocked_regions:
            if region[0] < 0 or region[1] <= 0:
                print("Ignoring mocked region at %d of size %d" % (region[0], region[1]))
                continue
            if region[0] <= accessed_addr < region[0] + region[1]:
                return True
        return False

    def should_be_shimmed(self, accessed_addr) -> Optional[int]:
        for region in self.shimmed_regions:
            if region[0] < 0 or region[1] <= 0:
                print("Ignoring shimmed region at %d of size %d" % (region[0], region[1]))
                continue
            if region[0] <= accessed_addr < region[0] + region[1]:
                return region[2]
        return None

    def poison(self):
        # stuff = random.randbytes(self.snapshot_region[1])
        # TODO speed this up (way too slow)
        print("Starting memory poisoning")
        print("  0.0%", end='')
        last = 0
        chunk_size = 4
        for i in range(0, self.snapshot_region[1], chunk_size):
            percentage = (100 * i / self.snapshot_region[1])
            if percentage > last + 0.25:
                print("\b\b\b\b\b\b%5.1f%%" % percentage, end='')
                last = percentage

            stuff = random.randint(0, 255)
            self.a2h.target.write_memory(self.snapshot_region[0] + i, chunk_size, stuff)
        print("\nMemory poisoning done")
