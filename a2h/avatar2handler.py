from typing import Tuple, Callable, Dict, Optional

from avatar2 import OpenOCDTarget, Avatar, ARM_CORTEX_M3, Target
from avatar2.plugins.mmf_dispatcher import MemFaultDispatcher
from capstone import CsInsn

from utilities import TimeOut
from . import InstructionEffect


class Avatar2Handler:

    arch: ARM_CORTEX_M3

    avatar: Avatar
    target: OpenOCDTarget

    region_snapshot: Tuple[int, int]
    region_protect: Tuple[int, int]

    dispatcher: MemFaultDispatcher
    on_mmf: Optional[Callable[[], bool]]

    def __init__(self, cfg_path: str, protect: Tuple[int, int], snapshot: Tuple[int, int],
                 avatar_output_directory: str, arch):

        self.arch = arch

        self.avatar = Avatar(arch=arch, output_directory=avatar_output_directory)
        self.target = self.avatar.add_target(OpenOCDTarget, openocd_script=cfg_path)

        # Blanket coverage for default memory ranges
        self.avatar.add_memory_range(0x00000000, 0x20000000, "default_code")
        self.avatar.add_memory_range(0x20000000, 0x20000000, "default_sram")
        self.avatar.add_memory_range(0x60000000, 0x20000000, "default_RAM_wbwa")
        self.avatar.add_memory_range(0x80000000, 0x20000000, "default_RAM_wt")
        self.avatar.add_memory_range(0xA0000000, 0x20000000, "default_dev_shr")
        self.avatar.add_memory_range(0xC0000000, 0x20000000, "default_dev_nshr")
        self.avatar.add_memory_range(0xE0100000, 0x0FF00000, "default_vendor_sys_rsvd")
        self.avatar.add_memory_range(0xF0000000, 0x10000000, "default_vendor_sys")

        # This one seems favoured for vendor peripherals
        self.avatar.add_memory_range(0x40000000, 0x20000000, "default_peripheral")

        # This one contains the MPU on all Cortex M3 devices
        self.avatar.add_memory_range(0xE0000000, 0x00100000, "default_sys_ppb")

        # TODO enable these after updating avatar
        # self.avatar.add_memory_range(protect[0], protect[1], "mpu_blocked", overwrite=True)
        # self.avatar.add_memory_range(snapshot[0], snapshot[1], "snapshot-able", overwrite=True)
        self.region_protect = protect
        self.region_snapshot = snapshot

        self.avatar.init_targets()

        # For interpreting instructions we need
        self.avatar.load_plugin("disassembler")
        # For debugging we need
        self.avatar.load_plugin("cortex_m3_pretty_dump")
        # For attaching to fault we need
        self.avatar.load_plugin("mmf_dispatcher")

        # Since this reference has only just been loaded silence nosy IDEs
        # noinspection PyUnresolvedReferences
        self.dispatcher = self.target.mmf_dispatcher

        # TODO call this from downstream of a2h?
        self.force_enable_mpu(self.region_protect)

        self.dispatcher.late_init()
        self.dispatcher.add_callback(self._on_mmf)

        self.on_mmf = None

    def _on_mmf(self, target: Target) -> bool:
        if self.target is not target:
            raise Exception(
                "Got event for wrong target, D4A2 is only meant to be used in a single target setup. "
                "If you need this functionality, please contact the developer."
            )
        if self.on_mmf is not None:
            success = self.on_mmf()
            if not success:
                self.target.log.warn("Failure in handling MMF reported to A2H")
        else:
            self.target.log.warn("Event ignored, no mmf handler set in A2H")

        return False  # never remove from dispatcher callbacks

    def set_mmf_callback(self, on_fault: Callable[[], bool]) -> Optional[Callable[[], bool]]:
        old_callback = None
        if self.on_mmf is not None:
            old_callback = self.on_mmf
        self.on_mmf = on_fault
        return old_callback

    def get_mm_faulting_addr(self) -> Optional[int]:
        try:
            if self.arch.CFSR.read(self.target) & self.arch.CFSR.MASK_MMF_ADDR_STILL_VALID != 0:
                mmf_addr = self.arch.MMFAR.read(self.target)
                self.arch.CFSR.set_bit(self.target, self.arch.CFSR.MASK_MMF_ADDR_STILL_VALID, 0)
            else:
                mmf_addr = None
        except AttributeError:
            self.target.log.error("Provided architecture does not support register info.")
            mmf_addr = None
        return mmf_addr

    def make_snapshot(self, mem_range: Tuple[int, int], path: str) -> bytes:
        command = "dump_image %s 0x%X 0x%X" % (path, mem_range[0], mem_range[1])
        openocd = self.target.protocols.monitor
        openocd.execute_command(command)
        
        with open(path, mode='rb') as bin_file:
            return bin_file.read()

    def get_stack_frame_location(self, offset=0) -> int:
        sp = None
        lr_value = self.target.read_register('lr')
        msp_value = self.target.read_register('msp')
        psp_value = self.target.read_register('psp')

        if lr_value == 0xFFFFFFF1:
            # Handler mode MSP
            sp = msp_value

        elif lr_value == 0xFFFFFFF9:
            # Thread mode MSP
            sp = msp_value

        elif lr_value == 0xFFFFFFFD:  # Expected
            # Thread mode PSP
            sp = psp_value

        elif lr_value == 0xFFFFFFE1:
            # Handler mode MSP (FP)
            sp = msp_value
            print("FP detected")

        elif lr_value == 0xFFFFFFE9:
            # Thread mode MSP (FP)
            sp = msp_value
            print("FP detected")

        elif lr_value == 0xFFFFFFED:
            # Thread mode PSP (FP)
            sp = psp_value
            print("FP detected")

        return sp + offset

    def read_context(self, stack_frame_location: int) -> Dict[str, int]:
        values = self.target.read_memory(stack_frame_location, 4, 8)
        context = {self.arch.REGISTERS_ON_STACK[i]: values[i] for i in range(len(self.arch.REGISTERS_ON_STACK))}
        return context

    def write_context(self, stack_frame_location: int, context: Dict[str, int]) -> None:
        values = [context[reg] for reg in self.arch.REGISTERS_ON_STACK]
        self.target.write_memory(stack_frame_location, 4, values, 8)

    def get_instruction_effect(self, addr: int) -> InstructionEffect:
        instruction = self._disassemble_one(addr)
        effect = InstructionEffect.from_cs_insn(instruction)
        return effect

    def continue_and_wait(self, timeout: Optional[int] = None):
        # TODO check if timeout needs to be handled here?
        if timeout is not None:
            # print("\n\n\t\tTHIS FUNCTIONALITY IS UNTESTED, PLEASE REPORT BUGS\n\n\n")
            with TimeOut(timeout):
                self.target.cont()
                self.target.wait()
        else:
            self.target.cont()
            self.target.wait()

    def force_enable_mpu(self, target_region: Tuple[int, int], allow_ldr=False):
        # Disable the MPU so we can perform 'maintenance'
        self.arch.MpuCR.write(self.target, 0)

        # Select the last MPU slot
        # TODO look for unused slots instead of grabbing the last one
        tr = self.arch.MpuTR
        number_of_regions = (tr.read(self.target) & tr.MASK_DREGION) >> tr.SHIFT_DREGION
        if number_of_regions != 0x8:
            self.target.log.error("Unsupported amount of regions (%d)." % number_of_regions)
            exit(-1)
        else:
            self.target.log.error("Supported amount of regions (%d)." % number_of_regions)

        self.arch.MpuRNR.write(self.target, 7)

        # Set the base to the region we want to watch
        self.arch.MpuRBAR.write(self.target, target_region[0])

        # Calculate some of the not quite straight-forward values
        access_permissions = self.arch.MpuRASR.calculate_access_permission(allow_ldr, False, allow_ldr, False)
        size_number = self.arch.MpuRASR.calculate_size_value(target_region[1])

        # Set the settings
        self.arch.MpuRASR.write_advanced(
            self.target,
            xn=False,
            ap=access_permissions,
            tex=0,
            s=False,
            c=False,
            b=False,
            srd=0b00000000,
            size=size_number,
            enable=True,
        )

        # Enable the MPU
        self.arch.MpuCR.write(self.target, self.arch.MpuCR.MASK_ENABLE | self.arch.MpuCR.MASK_PRIV_DEF_ENA)

    def _disassemble_one(self, addr: int) -> CsInsn:
        if hasattr(self.target, 'disassemble'):
            instructions = self.target.disassemble(addr, detail=True)
            if len(instructions) != 1:
                raise Exception("Failed to disassemble exactly one instruction")
            return instructions[0]
        else:
            raise Exception("Disassembler plugin not loaded.")

