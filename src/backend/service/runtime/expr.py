"""受限表达式：路径、字面量、==/!=、not/and/or。禁止 eval。"""

from __future__ import annotations

from service.runtime.state_path import get_path

_TRUE = object()
_FALSE = object()
_NULL = object()


class ExprError(ValueError):
    """表达式非法。"""


def eval_expr(expr: str, state: dict[str, object]) -> object:
    tokens = _tokenize(expr)
    value, index = _parse_or(tokens, 0, state)
    if index != len(tokens):
        raise ExprError(f"表达式尾部多余: {expr}")
    return value


def router_key(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


def _tokenize(expr: str) -> list[object]:
    raw = expr.strip()
    if not raw:
        raise ExprError("表达式为空")
    tokens: list[object] = []
    i = 0
    length = len(raw)
    while i < length:
        ch = raw[i]
        if ch.isspace():
            i += 1
            continue
        if raw.startswith("==", i):
            tokens.append("==")
            i += 2
            continue
        if raw.startswith("!=", i):
            tokens.append("!=")
            i += 2
            continue
        if ch in "()":
            tokens.append(ch)
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            buf: list[str] = []
            while i < length and raw[i] != quote:
                if raw[i] == "\\" and i + 1 < length:
                    buf.append(raw[i + 1])
                    i += 2
                    continue
                buf.append(raw[i])
                i += 1
            if i >= length:
                raise ExprError("字符串未闭合")
            i += 1
            tokens.append("".join(buf))
            continue
        if ch.isdigit() or (ch == "-" and i + 1 < length and raw[i + 1].isdigit()):
            j = i + 1
            while j < length and (raw[j].isdigit() or raw[j] == "."):
                j += 1
            number = raw[i:j]
            tokens.append(float(number) if "." in number else int(number))
            i = j
            continue
        if ch.isalpha() or ch == "_":
            j = i + 1
            while j < length and (raw[j].isalnum() or raw[j] in "._"):
                j += 1
            word = raw[i:j]
            if word == "true":
                tokens.append(_TRUE)
            elif word == "false":
                tokens.append(_FALSE)
            elif word == "null":
                tokens.append(_NULL)
            elif word in {"and", "or", "not"}:
                tokens.append(word)
            else:
                tokens.append(("path", word))
            i = j
            continue
        raise ExprError(f"非法字符: {ch}")
    return tokens


def _parse_or(tokens: list[object], index: int, state: dict[str, object]) -> tuple[object, int]:
    left, index = _parse_and(tokens, index, state)
    while index < len(tokens) and tokens[index] == "or":
        right, index = _parse_and(tokens, index + 1, state)
        left = bool(left) or bool(right)
    return left, index


def _parse_and(tokens: list[object], index: int, state: dict[str, object]) -> tuple[object, int]:
    left, index = _parse_not(tokens, index, state)
    while index < len(tokens) and tokens[index] == "and":
        right, index = _parse_not(tokens, index + 1, state)
        left = bool(left) and bool(right)
    return left, index


def _parse_not(tokens: list[object], index: int, state: dict[str, object]) -> tuple[object, int]:
    if index < len(tokens) and tokens[index] == "not":
        value, index = _parse_not(tokens, index + 1, state)
        return (not bool(value)), index
    return _parse_compare(tokens, index, state)


def _parse_compare(
    tokens: list[object], index: int, state: dict[str, object]
) -> tuple[object, int]:
    left, index = _parse_atom(tokens, index, state)
    if index < len(tokens) and tokens[index] in {"==", "!="}:
        op = tokens[index]
        right, index = _parse_atom(tokens, index + 1, state)
        equal = left == right
        return (equal if op == "==" else not equal), index
    return left, index


def _parse_atom(tokens: list[object], index: int, state: dict[str, object]) -> tuple[object, int]:
    if index >= len(tokens):
        raise ExprError("表达式不完整")
    token = tokens[index]
    if token == "(":
        value, index = _parse_or(tokens, index + 1, state)
        if index >= len(tokens) or tokens[index] != ")":
            raise ExprError("缺少右括号")
        return value, index + 1
    if token is _TRUE:
        return True, index + 1
    if token is _FALSE:
        return False, index + 1
    if token is _NULL:
        return None, index + 1
    if isinstance(token, tuple) and token[0] == "path":
        return get_path(state, token[1]), index + 1
    if isinstance(token, (str, int, float)):
        return token, index + 1
    raise ExprError(f"非法 token: {token}")
