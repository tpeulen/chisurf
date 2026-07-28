"""Generic argument tokenizer and signature binder for the command language.

Ports PyMOL's ``parse_arg`` (tokenize a command line into positional / keyword
argument pairs, bracket- and quote-aware) and ``prepare_call`` (bind those pairs
to a function's *real* signature, coercing strings per parameter annotation).
One central implementation replaces the per-command comma-splitting that the
old ``_cmd_x(args: List[str])`` handlers each did by hand.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable

from .selection_types import Selection


class CommandError(Exception):
    """Raised for argument-binding errors; surfaced to the user by ``do()``."""


_OPEN = {"(": ")", "[": "]", "{": "}"}
_CLOSE = set(")]}")


def _split_top_level(arg_str: str, max_parts: int | None = None, sep: str = ",") -> list[str]:
    """Split on top-level *sep*, ignoring separators inside brackets/quotes.

    When ``max_parts`` is given, splitting stops after that many parts and the
    remainder (verbatim) becomes the final element — used for the raw modes.
    """
    parts: list[str] = []
    depth = 0
    quote: str | None = None
    buf: list[str] = []
    for ch in arg_str:
        if quote is not None:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch in _OPEN:
            depth += 1
            buf.append(ch)
            continue
        if ch in _CLOSE:
            depth = max(0, depth - 1)
            buf.append(ch)
            continue
        if ch == sep and depth == 0:
            if max_parts is not None and len(parts) + 1 >= max_parts:
                buf.append(ch)  # keep remaining separators verbatim in the last part
                continue
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return parts


def split_statements(line: str) -> list[str]:
    """Split a command line into its ``;``-separated statements.

    PyMOL's compound line — ``hide everything, obj; show cartoon, obj`` is two
    commands. A ``;`` inside quotes or brackets belongs to an argument and is
    kept. Empty statements are dropped, so a trailing ``;`` is harmless.

    This is the one place the separator is defined; every panel that turns a
    menu entry into commands routes through it (see ``BaseCmd.do``).
    """
    parts = _split_top_level(line or "", sep=";")
    return [stripped for stripped in (part.strip() for part in parts) if stripped]


def tokenize(arg_str: str, mode: str = "normal") -> list[tuple[str | None, str]]:
    """Tokenize the argument string into ``(name|None, value)`` pairs.

    ``name`` is set for ``key=value`` arguments, else ``None`` (positional).
    ``mode`` ``"raw1"``/``"raw2"`` keeps everything after the 1st/2nd comma as a
    single verbatim value (for ``alter``/``iterate``/``set``/``label``).
    """
    arg_str = (arg_str or "").strip()
    if arg_str == "":
        return []

    max_parts = None
    if mode == "raw1":
        max_parts = 2
    elif mode == "raw2":
        max_parts = 3

    raw_parts = _split_top_level(arg_str, max_parts=max_parts)
    result: list[tuple[str | None, str]] = []
    for idx, part in enumerate(raw_parts):
        # In a raw mode, the final captured element is never treated as key=value.
        is_raw_tail = max_parts is not None and idx == len(raw_parts) - 1 and idx >= (max_parts - 1)
        value = part.strip()
        if not is_raw_tail:
            eq = _leading_keyword(part)
            if eq is not None:
                name, val = eq
                result.append((name, val))
                continue
        result.append((None, value))
    return result


def _leading_keyword(part: str) -> tuple[str, str] | None:
    """Return ``(name, value)`` if ``part`` is ``name=value`` (name a bare word)."""
    stripped = part.strip()
    eq = stripped.find("=")
    if eq <= 0:
        return None
    name = stripped[:eq].strip()
    if not name.replace("_", "").isalnum() or name[0].isdigit():
        return None
    # Avoid mistaking ==, <=, >= comparisons for a keyword arg.
    if stripped[eq + 1: eq + 2] == "=":
        return None
    return name, stripped[eq + 1:].strip()


_ANN_BY_NAME = {"int": int, "float": float, "bool": bool, "str": str, "Selection": Selection}


def _coerce(value, annotation):
    """Coerce a string ``value`` to ``annotation`` (int/float/bool/str/Selection).

    ``annotation`` may be a real type or, under ``from __future__ import
    annotations`` (PEP 563), the annotation *string* — both are handled. Complex
    annotations that don't name a simple scalar fall through as the raw string.
    """
    if not isinstance(value, str):
        return value  # already a real value (Python-API call)
    ann = annotation
    if isinstance(ann, str):
        ann = _ANN_BY_NAME.get(ann.strip())
    if ann in (Selection, str, inspect.Parameter.empty, None):
        return value
    if ann is int:
        return int(float(value)) if ("." in value or "e" in value.lower()) else int(value)
    if ann is float:
        return float(value)
    if ann is bool:
        low = value.strip().lower()
        if low in ("1", "true", "on", "yes", "y"):
            return True
        if low in ("0", "false", "off", "no", "n", ""):
            return False
        raise CommandError(f"expected a boolean, got {value!r}")
    return value


def bind_and_call(
    func: Callable[..., object],
    pairs: list[tuple[str | None, str]],
) -> object:
    """Bind ``(name|None, value)`` pairs to ``func``'s signature and call it.

    Positional pairs map to parameters by order; named pairs by name; strings are
    coerced per each parameter's annotation. Missing required parameters raise
    :class:`CommandError`.
    """
    sig = inspect.signature(func)
    params = [
        p
        for p in sig.parameters.values()
        if p.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]
    has_var_positional = any(
        p.kind is inspect.Parameter.VAR_POSITIONAL for p in sig.parameters.values()
    )
    by_name = {p.name: p for p in params}

    bound: dict = {}
    pos_index = 0
    positional_params = [
        p for p in params if p.kind is not inspect.Parameter.KEYWORD_ONLY
    ]
    extra_positional: list[str] = []
    for name, value in pairs:
        if name is not None:
            param = by_name.get(name)
            if param is None:
                raise CommandError(f"unexpected keyword argument '{name}'")
            bound[name] = _coerce(value, param.annotation)
        else:
            if pos_index < len(positional_params):
                param = positional_params[pos_index]
                bound[param.name] = _coerce(value, param.annotation)
                pos_index += 1
            elif has_var_positional:
                extra_positional.append(value)
            else:
                raise CommandError("too many positional arguments")

    for param in params:
        if param.name not in bound and param.default is inspect.Parameter.empty:
            raise CommandError(f"missing required argument '{param.name}'")

    call_args = list(extra_positional)
    return func(*[], **bound) if not call_args else func(*call_args, **bound)


__all__ = ["CommandError", "tokenize", "bind_and_call"]
