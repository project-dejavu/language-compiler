from .parser import Node, CallNode, ConstNode, IdenNode, ModuleDeclNode, DiscardNode, BinOpNode, AnonProcDeclNode, AssignNode, ForNode, ReturnNode, AssignAndReturnNode, AttrNode, WhileNode, TagNode, UseNode, BinOpType
from dataclasses import dataclass
from .assemblah import Assemblah, I, Encoder

MAGIC = b"Wklg\00\01\02\03"

@dataclass
class RunnableEntry:
    args: list[str]
    bytecode: bytearray | bytes

class ConstEntry:
    INT = 1
    FLOAT = 2
    STRING = 3
    RUNNABLE = 4


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

        return Assemblah.compile(
            (I.Set, name_ptr)
        )

    def visit_node_AssignNode(self, node: AssignNode):
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.value)), 
            (I.Bytecode, self.assign_node_setter(node.to))
        )

    def visit_node_AttrNode(self, node: AttrNode):
        attr_ptr = self.module_stack[-1].push_const(node.attr)
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.obj)),
            (I.GetAttr, attr_ptr)
        )

    def visit_node_AssignAndReturnNode(self, node: AssignAndReturnNode):
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.value)),
            (I.Dup,),
            (I.Bytecode, self.assign_node_setter(node.to))
        )

    def visit_node_WhileNode(self, node: WhileNode):
        body = b"".join(self.visit_node(x) for x in node.body)
        return Assemblah.compile(
            (I.Label, "before_while"),
            (I.Bytecode, self.visit_node(node.cond)),
            (I.LogicNot,),
            (I.JumpIf, "after_while"),
            (I.Bytecode, body),
            (I.Jump, "before_while"),
            (I.Label, "after_while")
        )

    def visit_node_ReturnNode(self, node: ReturnNode):
        if node.value is None:
            return Assemblah.compile(
                (I.PushNil,),
                (I.Return,)
            )
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.value)),
            (I.Return,)
        )

    def visit_node_ForNode(self, node: ForNode):
        """
        _temp_123123 = iterator(thing)
        :l
            get _temp_123123
            getattr "_iter_next"
            invoke 0
            dup
            iterstop
            eq
            jmpif :end
            set forvar
            LOOP_BODY
            jmp :l
        :end
            pop
        """
        iter_varname_ptr = self.module_stack[-1].push_const(f"_temp_iter_{self.get_uid()}")
        attr_ptr = self.module_stack[-1].push_const(f"_iter_next")
        forvar_ptr = self.module_stack[-1].push_const(node.var)
        
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.value)),
            (I.Get, "_Сис_Итератор"),
            (I.Invoke, 1),
            (I.Set, iter_varname_ptr),
        (I.Label, "before"),
            (I.Get, iter_varname_ptr),
            (I.GetAttr, attr_ptr),
            (I.Invoke, 0),
            (I.IterStopSentinel,),
            (I.Equ,),
            (I.JumpIf, "end"),
            (I.Set, forvar_ptr),
            *map(lambda x: (I.Bytecode, self.visit_node(x)), node.body),
            (I.Jump, "before"),
        (I.Label, "end"),
            (I.Discard,)
        )
        

    def visit_node_AnonProcDeclNode(self, node: AnonProcDeclNode):
        bytecode = bytearray()

        for i in node.body:
            bytecode.extend(self.visit_node(i))

        ptr_runnable = self.module_stack[-1].push_const(RunnableEntry(node.args, bytecode))

        return Assemblah.compile(
            (I.PushConst, ptr_runnable),
            (I.InjectParentScope,)
        )

    def visit_node_ModuleDeclNode(self, node: ModuleDeclNode):
        self.module_stack[-1].set_name(".".join(node.modname))
        return bytearray()

    def visit_node_CallNode(self, node: CallNode):
        return Assemblah.compile(
            *map(lambda x: (I.Bytecode, self.visit_node(x)), node.args),
            (I.Bytecode, self.visit_node(node.callee)),
            (I.Invoke, len(node.args))
        )
    
    def visit_node_BinOpNode(self, node: BinOpNode):
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.left)),
            (I.Bytecode, self.visit_node(node.right)),
            (I.BinOp, node.op)
        )

    def visit_node_DiscardNode(self, node: DiscardNode):
        return Assemblah.compile(
            (I.Bytecode, self.visit_node(node.value)),
            (I.Discard,)
        )
    
    def visit_node_ConstNode(self, node: ConstNode):
        ptr = self.module_stack[-1].push_const(node.value)

        return Assemblah.compile(
            (I.PushConst, ptr)
        )
    
    def visit_node_IdenNode(self, node: IdenNode):
        ptr = self.module_stack[-1].push_const(node.iden)
        return Assemblah.compile(
            (I.Get, ptr)
        )

    def dump_vfs(self):
        vfs: dict[str, bytearray | bytes] = {}
        
        for module in self.module_cache.values():
            vfs[module.get_name()] = module.dump()

        return vfs