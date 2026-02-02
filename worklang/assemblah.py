import enum
import struct
from typing import Any, cast

class Encoder:
    @classmethod
    def str(cls, s: str):
        encoded = s.encode()
        return cls.int32(len(encoded)) + encoded
    
    @classmethod
    def int32_signed(cls, i: int):
        return i.to_bytes(4, "big", signed=True)

    @classmethod
    def int32(cls, i: int):
        return i.to_bytes(4, "big")
    @classmethod
    def int16(cls, i: int):
        return i.to_bytes(2, "big")
    @classmethod
    def varint(cls, i: int):
        if i == 0:
            return bytearray([1, 0])
        b = i.to_bytes((i.bit_length() + 8) // 8, "big", signed=True)
        return bytearray([len(b), *b])

    @classmethod
    def float(cls, f: float):
        return struct.pack("f", f)

class Opcodes:
    NOP = 0x00 # not used by compiler, but must be implemented in VM
    PUSH_CONST = 0x01
    PUSH_NIL = 0x02
    DUP = 0x03

    GET = 0x0A
    SET_GLOBAL = 0x0B
    SET = 0x0C

    INVOKE = 0x10
    INJECT_PARENT_SCOPE = 0x11

    ADD = 0x20
    MULTIPLY = 0x21
    SUB = 0x22
    DIV = 0x23
    LESSTHAN = 0x24

    LOGICNOT = 0x30

    GETATTR = 0x40

    JMP = 0x50
    JMP_IF = 0x51

    RETURN = 0x7F
    DISCARD = 0x80

class I(enum.Enum):
    Nop = 1
    PushConst = 2
    PushNil = 3
    Set = 4
    Label = 5
    GetAttr = 6
    Dup = 7
    LogicNot = 8
    Jump = 9
    JumpIf = 10
    Bytecode = 11
    Return = 12
    InjectParentScope = 13
    Invoke = 14
    BinOp = 15
    Discard = 16
    Get = 17
    IterStopSentinel = 18
    Equ = 19

class Assemblah:
    @classmethod
    def compile(cls, *instructions: tuple[I, *tuple[Any, ...]]) -> bytearray | bytes:
        code = bytearray()
        label_second_run = {}

        for instr in instructions:
            if instr[0] == I.PushConst:
                ptr = cast(int, instr[1])
                code.extend([Opcodes.PUSH_CONST, *Encoder.int32(ptr)])
            elif instr[0] == I.Get:
                ptr = cast(int, instr[1])
                code.extend([Opcodes.GET, *Encoder.int32(ptr)])
            elif instr[0] == I.Bytecode:
                bc = cast(bytearray, instr[1])
                code.extend(bc)
            elif instr[0] == I.Invoke:
                args = cast(int, instr[1])
                code.extend([Opcodes.INVOKE, *Encoder.int16(args)])
            elif instr[0] == I.Discard:
                code.append(Opcodes.DISCARD)
            else:
                raise ValueError(f"Unknown instruction {instr}")
        
        return code