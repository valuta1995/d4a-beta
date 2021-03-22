from typing import Dict

from avatar2 import Target
from capstone import CsInsn
from capstone.arm_const import ARM_INS_STR, ARM_INS_LDR, ARM_INS_STRB, ARM_INS_LDRB, ARM_OP_REG, ARM_OP_MEM, \
    ARM_SFT_LSL, ARM_SFT_INVALID


def load_reg_value(reg_name: str, target: Target, context: Dict[str, int]) -> int:
    if reg_name in context:
        return context[reg_name]
    else:
        return target.read_register(reg_name)


def store_reg_value(reg: str, target: Target, context: Dict[str, int], value: int) -> None:
    if reg in context:
        context[reg] = value
    else:
        target.write_register(reg, value)


def get_instruction_size(instruction: CsInsn):
    if instruction.id in [ARM_INS_STR, ARM_INS_LDR]:
        size = 4
    elif instruction.id in [ARM_INS_STRB, ARM_INS_LDRB]:
        size = 1
    else:
        print(instruction)
        raise Exception("Unsupported instruction.")
    return size


def get_instruction_mode(instruction: CsInsn):
    if instruction.id in [ARM_INS_STR, ARM_INS_STRB]:
        mode = "str"
    elif instruction.id in [ARM_INS_LDR, ARM_INS_LDRB]:
        mode = "ldr"
    else:
        raise Exception("Unsupported instruction.")
    return mode


class InstructionEffect:
    def __init__(
            self, mode: str, size: int, instruction_bytes: int,
            reg: str, mem_base: str, mem_index: str, mem_offset: int, mem_shift_amount: int):
        self.mode = mode
        self.size = size
        self.instruction_bytes = instruction_bytes

        self.reg = reg
        self.mem_base = mem_base
        self.mem_index = mem_index
        self.mem_offset = mem_offset
        self.mem_shift_amount = mem_shift_amount

    def compute_memory_address(self, target: Target, context: Dict[str, int]) -> int:
        base = load_reg_value(self.mem_base, target, context)
        index = 0 if self.mem_index is None else load_reg_value(self.mem_index, target, context)
        offset = 0 if self.mem_offset is None else self.mem_offset

        index = index << self.mem_shift_amount

        if index != 0 and offset != 0:
            raise Exception("Cannot have both index and immediate.")
        return base + index + offset

    def get_register_value(self, target: Target, context: Dict[str, int]) -> int:
        return load_reg_value(self.reg, target, context)

    def set_register_value(self, target: Target, context: Dict[str, int], value: int) -> None:
        store_reg_value(self.reg, target, context, value)

    @classmethod
    def from_cs_insn(cls, instruction: CsInsn) -> 'InstructionEffect':
        mem_size = get_instruction_size(instruction)
        mode = get_instruction_mode(instruction)

        operands = instruction.operands

        reg_operand = operands[0]
        if reg_operand.type != ARM_OP_REG:
            raise Exception("Register operand is not a register")
        reg = instruction.reg_name(reg_operand.value.reg)

        mem_operand = operands[1]
        if mem_operand.type != ARM_OP_MEM:
            raise Exception("Memory operand is not a memory operand")
        mem_base = instruction.reg_name(mem_operand.value.mem.base)
        mem_index = instruction.reg_name(mem_operand.value.mem.index)
        mem_offset = mem_operand.value.mem.disp

        shift_type = mem_operand.shift.type
        if shift_type == ARM_SFT_INVALID:
            mem_shift_amount = 0
        elif shift_type == ARM_SFT_LSL:
            mem_shift_amount = mem_operand.shift.value
        else:
            raise Exception("Unknown shift type: %d" % shift_type)

        effect = InstructionEffect(
            mode, mem_size, instruction.size, reg, mem_base, mem_index, mem_offset, mem_shift_amount
        )
        return effect
