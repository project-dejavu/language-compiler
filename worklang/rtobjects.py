import enum
from typing import Any

class Primitives(enum.Enum):
    Number = 1
    String = 2
    Bool = 3
    Runnable = 4
    Module = 5
    Sentinel = 6
    Nil = -67

class WLObject:
    def __init__(self, object_type: Primitives, value: Any = None):
        self.object_type = object_type
        self.value = value
    def __eq__(self, other: 'WLObject | Any'):
        if not isinstance(other, WLObject):
            return False
        if self.object_type != other.object_type:
            return False
        return self.value == other.value
    def __repr__(self):
        if self.object_type == Primitives.String:
            return self.value
        elif self.object_type == Primitives.Number:
            return str(self.value)
        else:
            return repr(self.object_type)

NIL = WLObject(Primitives.Nil)
ITERSTOP = WLObject(Primitives.Sentinel)