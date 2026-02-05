import string
import enum
from typing import Any
from .types import Span

CYRILLIC_LOWER = ''.join(chr(c) for c in range(0x0430, 0x044F + 1))
CYRILLIC_UPPER = ''.join(chr(c) for c in range(0x0410, 0x042F + 1))
CYRILLIC_NON_STANDARD = 'ёЁєЄіїІґҐ'

CYRILLIC_LETTERS = CYRILLIC_LOWER + CYRILLIC_UPPER + CYRILLIC_NON_STANDARD
ALL_LETTERS = string.ascii_letters + CYRILLIC_LETTERS + "_"
ALL_LETTERS_DIGITS = ALL_LETTERS + string.digits

WHITESPACE = " \t\r\n\v"

class TokenType(enum.Enum):
    EOF = -1
    
    Identifier = 1
    Number = 2
    String = 3
    Keyword = 4

    ParenOpen = "("
    ParenClose = ")"
    Semicolon = ";"
    Colon = ":"
    Dot = "."
    Comma = ","

    QuestionMark = "?"
    
    Assign = 1001
    Equ = 1002

    Plus = 1010
    Multiply = 1011

    InlineAdd = 1100
    InlineMul = 1101

class Keyword(enum.Enum):
    Use = "использовать"
    If = "если"
    Then = "тогда"
    New = "новый"
    While = "пока"
    As = "как"
    Module = "модуль"
    Proc = "процедура"
    End = "конец"
    Return = "вернуть"
    For = "для"
    In = "в"
    LessThan = "меньше"

DOUBLES = {
    "=": ("=", TokenType.Assign, TokenType.Equ),
    "+": ("=", TokenType.Plus, TokenType.InlineAdd),
    "*": ("=", TokenType.Multiply, TokenType.InlineMul)
}
DOUBLES_INIT = tuple(x[0][0] for x in DOUBLES.keys())

KEYWORDS = list(x.value for x in Keyword)
TOKENTYPES = list(x.value for x in TokenType)

class Token:
    def __init__(self, span: Span, token_type: TokenType, value: Any = None):
        self.span = span
        self.type = token_type
        self.value = value

    def __repr__(self):
        if self.value is not None:
            return f'Token({self.type}, {self.value})'
        return f'Token({self.type})'

class LexerException(Exception):
    pass

class Lexer:
    def __init__(self):
        self.reset()

    def reset(self, text: str | None = None):
        self.idx = -1
        self.ch: str | None = None
        self.text = text or ""
        self.line = 1
        self.col = 1

    def next(self, step: int = 1):
        self.idx += step
        self.col += step
        self.ch = self.text[self.idx] if self.idx < len(self.text) else None
        if self.ch == "\n":
            self.line += 1
            self.col = 1

    def run(self, data: str):
        self.reset(data + "\n")
        self.next()

        tokens: list[Token] = []

        while self.ch is not None:
            if self.ch in WHITESPACE:
                self.next()
            elif self.ch in TOKENTYPES:
                tokens.append(Token(Span(self.line, self.col, 1), TokenType(self.ch)))
                self.next()
            elif self.ch in ALL_LETTERS:
                pos = self.col
                iden = ""
                while self.ch in ALL_LETTERS_DIGITS:
                    iden += self.ch
                    self.next()

                if iden.lower() in KEYWORDS:
                    tokens.append(Token(Span(self.line, pos, len(iden)), TokenType.Keyword, Keyword(iden.lower())))
                else:
                    tokens.append(Token(Span(self.line, pos, len(iden)), TokenType.Identifier, iden))
            elif self.ch.isdigit():
                pos = self.col
                num = ""
                while self.ch is not None and self.ch.isdigit(): # type: ignore
                    num += self.ch
                    self.next()

                tokens.append(Token(Span(self.line, pos, len(num)), TokenType.Number, int(num)))
            elif self.ch in "\"'":
                pos = self.col
                stored = self.idx

                quote = self.ch
                self.next()

                s = ""
                while self.ch != quote:
                    s += self.ch
                    self.next()
                self.next()

                tokens.append(Token(Span(self.line, pos, self.idx-stored), TokenType.String, s))
            elif self.ch in DOUBLES_INIT:
                pos = self.col
                double = DOUBLES[self.ch]
                self.next()
                if self.ch == double[0]:
                    self.next()
                    tokens.append(Token(Span(self.line, pos, 2), double[2]))
                else:
                    tokens.append(Token(Span(self.line, pos, 1), double[1]))
            else:
                raise LexerException(f"Неизвестный символ '{self.ch}'")

        return tokens
    
    def save(self):
        return self.idx
    def restore(self, idx: int):
        self.idx = idx - 1
        self.next()