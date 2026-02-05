from dataclasses import dataclass
from enum import Enum

@dataclass(frozen=True)
class Span:
    line: int
    pos: int
    length: int

    @property
    def end(self) -> int:
        return self.pos + self.length
    
class BinOpType(Enum):
    Add = 1
    Mul = 2
    Sub = 3
    Div = 4
    Lt = 5