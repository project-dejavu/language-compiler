from .parser import Node, CallNode, ConstNode, IdenNode, ModuleDeclNode, DiscardNode, BinOpNode, AnonProcDeclNode, AssignNode, ForNode, ReturnNode, AssignAndReturnNode, AttrNode, WhileNode, TagNode, UseNode, BinOpType
import struct
from dataclasses import dataclass

MAGIC = b"Wklg\00\01\02\03"

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

@dataclass
class RunnableEntry:
    args: list[str]
    bytecode: bytearray | bytes

class ConstEntry:
    INT = 1
    FLOAT = 2
    STRING = 3
    RUNNABLE = 4

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

CONST_TYPE = int | float | str | RunnableEntry

class Module:
    def __init__(self):
        self.name: str | None = None
        self.bytecode: bytearray | None = None
        self.const_pool: list[CONST_TYPE] = []
    
    def push_const(self, const: CONST_TYPE):
        if const in self.const_pool:
            return self.const_pool.index(const)
        self.const_pool.append(const)
        return len(self.const_pool) - 1

    def set_name(self, name: str):
        self.name = name
    def get_name(self):
        if self.name is None:
            raise ValueError("Modules should have a name!")
        return self.name
    
    def dump(self):
        assert self.bytecode is not None
        intro_runnable = self.push_const(RunnableEntry([], self.bytecode))

        result = bytearray()

        result.extend(Encoder.str(self.get_name()))        
        result.extend(Encoder.int32(len(self.const_pool)))
        for entry in self.const_pool:
            if isinstance(entry, str):
                result.append(ConstEntry.STRING)
                result.extend(Encoder.str(entry))
            elif isinstance(entry, int):
                result.append(ConstEntry.INT)
                result.extend(Encoder.varint(entry))
            elif isinstance(entry, RunnableEntry):
                result.append(ConstEntry.RUNNABLE)
                result.append(len(entry.args))
                for i in entry.args:
                    result.extend(Encoder.str(i))
                result.extend(Encoder.int32(len(entry.bytecode)))
                result.extend(entry.bytecode)
            else:
                raise NotImplementedError(f"Cannot serialize const pool entry {entry}")

        result.extend(Encoder.int32(intro_runnable))
        return result

class Compiler:
    def __init__(self):
        self.module_stack: list[Module] = []

        self.module_cache: dict[str, Module] = {}

        self._uid = 0

    def get_uid(self):
        self._uid += 1
        return self._uid

    def compile_module(self, module_ast: list[Node]):
        self.module_stack.append(Module())
        bytecode = bytearray()

        for i in module_ast:
            bytecode.extend(self.visit_node(i))
        mod = self.module_stack.pop()

        assert mod.get_name() not in self.module_cache
        self.module_cache[mod.get_name()] = mod

        mod.bytecode = bytecode

        return mod

    def visit_node(self, node: Node) -> bytearray:
        return getattr(self, "visit_node_" + node.__class__.__name__, self.no_node_visitor)(node)
    def no_node_visitor(self, node: Node) -> bytearray:
        raise NotImplementedError(f"No visitor for node {node}")
    
    def visit_node_UseNode(self, node: UseNode):
        return self.visit_node(AssignNode(IdenNode(node.as_name), CallNode(IdenNode("__СисВызов_ИмпортМодуля"), [ConstNode(".".join(node.name))])))
    
    def visit_node_TagNode(self, node: TagNode):
        if node.value is None:
            return self.visit_node(CallNode(IdenNode("__СисВызов_СоздатьТэг1"), [ConstNode(node.tag)]))
        return self.visit_node(CallNode(IdenNode("__СисВызов_СоздатьТэг2"), [ConstNode(node.tag), node.value]))

    def assign_node_setter(self, to: Node):
        assert isinstance(to, IdenNode), f"TODO {to}"

        name_ptr = self.module_stack[-1].push_const(to.iden)

        return bytearray([Opcodes.SET, *Encoder.int32(name_ptr)])

    def visit_node_AssignNode(self, node: AssignNode):
        return bytearray([*self.visit_node(node.value), *self.assign_node_setter(node.to)])

    def visit_node_AttrNode(self, node: AttrNode):
        attr_ptr = self.module_stack[-1].push_const(node.attr)
        return bytearray([*self.visit_node(node.obj), Opcodes.GETATTR, *Encoder.int32(attr_ptr)])

    def visit_node_AssignAndReturnNode(self, node: AssignAndReturnNode):
        return bytearray([*self.visit_node(node.value), Opcodes.DUP, *self.assign_node_setter(node.to)])

    def visit_node_WhileNode(self, node: WhileNode):
        body = b"".join(self.visit_node(x) for x in node.body)
        intro = bytearray([*self.visit_node(node.cond), Opcodes.LOGICNOT, Opcodes.JMP_IF, *Encoder.int32_signed(len(body) + 5)])
        outro = bytearray([Opcodes.JMP, *Encoder.int32_signed(-len(intro)-len(body)-5)])
        return bytearray([*intro, *body, *outro])

    def visit_node_ReturnNode(self, node: ReturnNode):
        if node.value is None:
            return bytearray([Opcodes.PUSH_NIL, Opcodes.RETURN])
        return bytearray([*self.visit_node(node.value), Opcodes.RETURN])

    def visit_node_ForNode(self, node: ForNode):
        """
        _temp_123123 = iterator(thing)
        :l
            get _temp_123123
            getattr "_iter_next"
            dup
            invoke 0
            iterstop
            eq
            jmpif :end
            set forvar
            LOOP_BODY
            jmp :l
        :end
            pop
        """
        iter_varname = f"_temp_iter_{self.get_uid()}"
        intro = bytearray()
        assert False
        

    def visit_node_AnonProcDeclNode(self, node: AnonProcDeclNode):
        bytecode = bytearray()

        for i in node.body:
            bytecode.extend(self.visit_node(i))

        ptr_runnable = self.module_stack[-1].push_const(RunnableEntry(node.args, bytecode))

        return bytearray([Opcodes.PUSH_CONST, *Encoder.int32(ptr_runnable), Opcodes.INJECT_PARENT_SCOPE])

    def visit_node_ModuleDeclNode(self, node: ModuleDeclNode):
        self.module_stack[-1].set_name(".".join(node.modname))
        return bytearray()

    def visit_node_CallNode(self, node: CallNode):
        result = bytearray()

        for arg in node.args:
            result.extend(self.visit_node(arg))
        result.extend(self.visit_node(node.callee))
        result.append(Opcodes.INVOKE)
        result.extend(Encoder.int16(len(node.args)))

        return result
    
    def visit_node_BinOpNode(self, node: BinOpNode):
        ops = {
            BinOpType.Add: Opcodes.ADD,
            BinOpType.Mul: Opcodes.MULTIPLY,
            BinOpType.Lt: Opcodes.LESSTHAN
        }
        return bytearray([*self.visit_node(node.left), *self.visit_node(node.right), ops[node.op]])

    def visit_node_DiscardNode(self, node: DiscardNode):
        return self.visit_node(node.value) + bytearray([Opcodes.DISCARD])
    
    def visit_node_ConstNode(self, node: ConstNode):
        ptr = self.module_stack[-1].push_const(node.value)

        return bytearray([Opcodes.PUSH_CONST, *Encoder.int32(ptr)])
    
    def visit_node_IdenNode(self, node: IdenNode):
        ptr = self.module_stack[-1].push_const(node.iden)
        return bytearray([Opcodes.GET, *Encoder.int32(ptr)])

    def dump_vfs(self):
        vfs: dict[str, bytearray | bytes] = {}
        
        for module in self.module_cache.values():
            vfs[module.get_name()] = module.dump()

        return vfs