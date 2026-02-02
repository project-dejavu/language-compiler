import enum
import importlib
from typing import cast
from .compiler import ConstEntry
from .assemblah import Opcodes
from .rtobjects import *

class Runnable:
    def __init__(self, module: 'WLModule', args: list[str], bytecode: bytes | bytearray):
        self.module = module
        self.args = args
        self.bytecode = bytecode
        self.parent_scope: RunnableContext | None = None

    def __call__(self, executor: 'Executor', args: list[WLObject]):
        ctx = RunnableContext(self.module, self.bytecode, self.parent_scope)
        assert len(args) == len(self.args)
        for my, given in zip(self.args, args):
            ctx.locals()[my] = given
        executor.push_ctx(ctx)

ConstType = int | str | float | Runnable

class WLModule:
    def __init__(self, name: str, root_runnable: Runnable, constpool: list[ConstType]):
        self.name = name
        self.root_runnable = root_runnable
        self.constpool = constpool
        self.globals: dict[str, WLObject] = {} | cast(dict[str, WLObject], importlib.import_module("worklang.stdlib").defaults)

class ExecutorStepResult(enum.Enum):
    CONTINUE = 1
    END = 2
    ASYNC_YIELD = 3

class BinOperation(enum.Enum):
    ADD = 1
    MULTIPLY = 2
    LT = 3

def operate_bi(left: WLObject, right: WLObject, op: BinOperation):
    match left.object_type:
        case Primitives.Number:
            assert right.object_type == left.object_type, "Only numbers can be operated together"
            v = 0
            match op:
                case BinOperation.ADD:
                    v = left.value + right.value
                case BinOperation.MULTIPLY:
                    v = left.value * right.value
                case BinOperation.LT:
                    return WLObject(Primitives.Bool, left.value < right.value)
                case _:
                    raise NotImplementedError(f"unknown op {op}")
            return WLObject(Primitives.Number, v)
        case _:
            raise NotImplementedError(f"cannot operate on {left.object_type}")

class RunnableContext:
    def __init__(self, module: WLModule, bytecode: bytearray | bytes, parent: 'RunnableContext | None'):
        self.module = module
        self.localsx: dict[str, WLObject] = {}
        self.stack: list[WLObject] = []
        self.bs = ByteStream(bytecode)
        self.parent: RunnableContext | None = parent
    
    def has(self, name: str):
        if name in self.locals():
            return True
        if self.parent and self.parent.has(name):
            return True
        return name in self.module.globals

    def get(self, name: str) -> WLObject:
        if name in self.locals():
            return self.locals()[name]
        if self.parent and self.parent.has(name):
            return self.parent.get(name)
        return self.module.globals[name]

    def globals(self):
        return self.module.globals
    def locals(self):
        return self.localsx

    def step(self, executor: 'Executor', vm: 'VM') -> tuple[ExecutorStepResult, WLObject | None]:
        if self.bs.over():
            return ExecutorStepResult.END, NIL
        opcode = self.bs.byte()

        
        if opcode == Opcodes.NOP:
            pass
        elif opcode == Opcodes.PUSH_CONST:
            ptr = self.bs.int32()
            raw_obj = self.module.constpool[ptr]
            if isinstance(raw_obj, str):
                self.stack.append(WLObject(Primitives.String, raw_obj))
            elif isinstance(raw_obj, int):
                self.stack.append(WLObject(Primitives.Number, raw_obj))
            elif isinstance(raw_obj, Runnable):
                self.stack.append(WLObject(Primitives.Runnable, raw_obj))
            else:
                raise NotImplementedError(f"Unknown raw object type {raw_obj}")
        elif opcode == Opcodes.SET:
            ptr = self.bs.int32()
            val = self.stack.pop()
            self.locals()[cast(str, self.module.constpool[ptr])] = val
        elif opcode == Opcodes.GET:
            ptr = self.bs.int32()
            iden = self.module.constpool[ptr]

            assert isinstance(iden, str)
            self.stack.append(executor.ctx().get(iden))
        elif opcode == Opcodes.INVOKE:
            argcount = self.bs.int16()
            callee = self.stack.pop()

            args: list[WLObject] = []
            for _ in range(argcount):
                args.insert(0, self.stack.pop())
            
            assert callee.object_type == Primitives.Runnable
            self.stack.append(callee.value(executor, args)) # type: ignore
        elif opcode == Opcodes.DISCARD:
            self.stack.pop()
        elif opcode == Opcodes.MULTIPLY:
            right = self.stack.pop()
            left = self.stack.pop()
            self.stack.append(operate_bi(left, right, BinOperation.MULTIPLY))
        elif opcode == Opcodes.ADD:
            right = self.stack.pop()
            left = self.stack.pop()
            self.stack.append(operate_bi(left, right, BinOperation.ADD))
        elif opcode == Opcodes.RETURN:
            return ExecutorStepResult.END, self.stack.pop()
        elif opcode == Opcodes.INJECT_PARENT_SCOPE:
            v = self.stack[-1]
            assert v.object_type == Primitives.Runnable
            r: Runnable = v.value
            r.parent_scope = self
        elif opcode == Opcodes.LOGICNOT:
            v = self.stack.pop()
            assert v.object_type == Primitives.Bool, f"got {v}"
            self.stack.append(WLObject(Primitives.Bool, not v.value)) # type: ignore
        elif opcode == Opcodes.JMP_IF:
            cond = self.stack.pop()
            reladdr = self.bs.int32_sign()

            assert cond.object_type == Primitives.Bool
            if cond.value:
                self.bs.idx += reladdr
        elif opcode == Opcodes.JMP:
            reladdr = self.bs.int32_sign()
            self.bs.idx += reladdr
        elif opcode == Opcodes.LESSTHAN:
            right = self.stack.pop()
            left = self.stack.pop()
            self.stack.append(operate_bi(left, right, BinOperation.LT))
        else:
            raise NotImplementedError(f"Unknown opcode {hex(opcode)}")
        return ExecutorStepResult.CONTINUE, None

class Executor:
    def __init__(self, vm: 'VM'):
        self.ctx_stack: list[RunnableContext] = []
        self.vm = vm

    def push_ctx(self, ctx: RunnableContext):
        self.ctx_stack.append(ctx)
    def pop_ctx(self):
        return self.ctx_stack.pop()
    def ctx(self):
        return self.ctx_stack[-1]

    def step(self, vm: 'VM'):
        r, v = self.ctx().step(self, vm)
        if r == ExecutorStepResult.CONTINUE:
            return r
        elif r == ExecutorStepResult.END:
            self.pop_ctx()

            assert v is not None
            if len(self.ctx_stack) > 0:
                self.ctx().stack.append(v)
                return ExecutorStepResult.CONTINUE
            return ExecutorStepResult.END
        else:
            raise NotImplementedError("asdf")

class ByteStream:

    def __init__(self, arr: bytearray | bytes):
        self.arr = arr
        self.idx = 0
    def byte(self):
        val = self.arr[self.idx]
        self.idx += 1
        return val
    def int16(self):
        val = int.from_bytes(self.arr[self.idx:self.idx+2], "big")
        self.idx += 2
        return val
    def int32(self):
        val = int.from_bytes(self.arr[self.idx:self.idx+4], "big")
        self.idx += 4
        return val
    def int32_sign(self):
        val = int.from_bytes(self.arr[self.idx:self.idx+4], "big", signed=True)
        self.idx += 4
        return val
    def str(self):
        length = self.int32()
        val = self.arr[self.idx:self.idx+length].decode("utf-8")
        self.idx += length
        return val
    def bytes(self, amt: int):
        val = self.arr[self.idx:self.idx+amt]
        self.idx += amt
        return val
    def varint(self):
        amt = self.byte()
        return int.from_bytes(self.bytes(amt), "big", signed=True)
    def over(self):
        return self.idx >= len(self.arr)

class ModSource:
    def get_module(self, name: str) -> bytearray | bytes | None:
        raise NotImplementedError
class VirtualSource(ModSource):
    def __init__(self, mods: dict[str, bytearray | bytes]):
        self.mods = mods

    def get_module(self, name: str):
        for mod_name, code in self.mods.items():
            if mod_name == name:
                return code            

class VM:
    def __init__(self):
        self.module_cache: dict[str, WLModule] = {}
        self.executor_stack: list[Executor] = []
        self.sources: list[ModSource] = []

    def add_modsource(self, src: ModSource):
        self.sources.append(src)

    def load_from_bytes(self, thing: bytearray | bytes):
        s = ByteStream(thing)
        module_name = s.str()

        const_pool: list[ConstType] = []
        module = WLModule(module_name, cast(Runnable, None), const_pool)

        const_count = s.int32()
        for _ in range(const_count):
            typ = s.byte()
            if typ == ConstEntry.STRING:
                const_pool.append(s.str())
            elif typ == ConstEntry.INT:
                const_pool.append(s.varint())
            elif typ == ConstEntry.RUNNABLE:
                argcount = s.byte()
                args: list[str] = []
                for _ in range(argcount):
                    args.append(s.str())
                bytecode_len = s.int32()
                bytecode = s.bytes(bytecode_len)

                const_pool.append(Runnable(module, args, bytecode))
            else:
                raise NotImplementedError(f"Unknown const pool entry {typ}")
        
        bytecode_runnable_id = s.int32()
        module.root_runnable = cast(Runnable, const_pool[bytecode_runnable_id])
        
        self.module_cache[module_name] = module
        return module

    def get_module_source(self, name: str):
        for src in self.sources:
            if (s := src.get_module(name)) is not None:
                return s
        raise NameError(f"Could not find module {name}")

    def load_module(self, name: str):
        if name in self.module_cache:
            return self.module_cache[name]
        
        mod = self.load_from_bytes(self.get_module_source(name))
        ctx = RunnableContext(mod, mod.root_runnable.bytecode, None)

        executor = Executor(self)
        executor.push_ctx(ctx)

        self.executor_stack.append(executor)
        while True:
            if len(self.executor_stack) == 0:
                break
            ex = self.executor_stack[-1]
            res = ex.step(self)
            if res == ExecutorStepResult.CONTINUE:
                pass
            elif res == ExecutorStepResult.END:
                self.executor_stack.pop()
            else:
                raise NotImplementedError(f"Step {res}")
