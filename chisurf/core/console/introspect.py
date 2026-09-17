"""Object introspection: calltips and the ``obj?`` / ``obj??`` reports."""

from __future__ import annotations

import dataclasses
import inspect
import re
import typing

__all__ = ["CallTip", "calltip", "info", "format_info"]

_SAFE_EXPR = re.compile(r"^[A-Za-z_]\w*(?:\.\w+|\[[^\]\[()]*\])*$")
_OPENERS = {")": "(", "]": "[", "}": "{"}


@dataclasses.dataclass
class CallTip:
    """A signature tooltip.

    Attributes
    ----------
    name : str
    signature : str
    doc : str
    argument : int
        Index of the argument the cursor is on, so the widget can emphasise it.
    """

    name: str
    signature: str
    doc: str = ""
    argument: int = 0


def _signature_of(obj: typing.Any) -> str:
    """Return a printable signature for *obj*.

    Parameters
    ----------
    obj : object

    Returns
    -------
    str
        Empty when no signature can be determined -- true for many C functions,
        where the first docstring line is used instead.
    """
    try:
        return str(inspect.signature(obj))
    except (TypeError, ValueError):
        pass
    text = getattr(obj, "__text_signature__", None)
    if text:
        return text
    doc = inspect.getdoc(obj) or ""
    first = doc.splitlines()[0] if doc else ""
    if "(" in first and first.endswith(")"):
        return first[first.index("(") :]
    return ""


def calltip(
    line: str, cursor_pos: int, namespace: typing.Mapping[str, typing.Any]
) -> CallTip | None:
    """Return the calltip for the call the cursor sits inside.

    Parameters
    ----------
    line : str
        The current input buffer.
    cursor_pos : int
    namespace : mapping
        Evaluated against, so the tip reflects the live object.

    Returns
    -------
    CallTip or None
    """
    head = line[:cursor_pos]
    depth = 0
    index = len(head) - 1
    commas = 0
    in_string: str | None = None

    while index >= 0:
        char = head[index]
        if in_string is not None:
            if char == in_string:
                in_string = None
            index -= 1
            continue
        if char in "'\"":
            in_string = char
            index -= 1
            continue
        if char in ")]}":
            depth += 1
        elif char in "([{":
            if depth == 0:
                if char != "(":
                    return None
                break
            depth -= 1
        elif char == "," and depth == 0:
            commas += 1
        index -= 1

    if index < 0:
        return None

    expr_end = index
    start = expr_end
    while start > 0:
        char = head[start - 1]
        if char.isalnum() or char in "_.":
            start -= 1
        else:
            break
    expression = head[start:expr_end]
    if not expression or not _SAFE_EXPR.match(expression):
        return None

    try:
        obj = eval(expression, dict(namespace))  # noqa: S307 - guarded above
    except Exception:
        return None
    if not callable(obj):
        return None

    doc = inspect.getdoc(obj) or ""
    return CallTip(
        name=expression,
        signature=_signature_of(obj),
        doc="\n".join(doc.splitlines()[:20]),
        argument=commas,
    )


def info(obj: typing.Any, name: str = "", detail_level: int = 0) -> dict:
    """Collect what ``obj?`` reports.

    Parameters
    ----------
    obj : object
    name : str, optional
        How the user spelled it.
    detail_level : int, optional
        ``1`` adds the source, as ``obj??`` does.

    Returns
    -------
    dict
    """
    result: dict[str, typing.Any] = {"name": name, "type": type(obj).__name__}

    with _quiet():
        result["string_form"] = _truncate(repr(obj), 400)
    with _quiet():
        if hasattr(obj, "__len__"):
            result["length"] = len(obj)
    with _quiet():
        result["file"] = inspect.getsourcefile(obj) or inspect.getfile(obj)
    with _quiet():
        result["line"] = inspect.getsourcelines(obj)[1]

    if callable(obj):
        signature = _signature_of(obj)
        if signature:
            result["signature"] = f"{name or getattr(obj, '__name__', '')}{signature}"

    if inspect.isclass(obj):
        bases = [base.__name__ for base in getattr(obj, "__mro__", ())[1:]]
        if bases:
            result["bases"] = ", ".join(bases)
        with _quiet():
            init_signature = _signature_of(obj.__init__)
            if init_signature:
                result["init"] = f"__init__{init_signature}"

    if inspect.ismodule(obj):
        exported = getattr(obj, "__all__", None)
        if exported:
            result["exports"] = ", ".join(sorted(exported)[:60])

    doc = inspect.getdoc(obj)
    if doc:
        result["docstring"] = doc

    if detail_level > 0:
        with _quiet():
            result["source"] = inspect.getsource(obj)

    return result


def format_info(data: dict) -> str:
    """Render :func:`info` output for display.

    Parameters
    ----------
    data : dict

    Returns
    -------
    str
    """
    order = (
        ("name", "Name"),
        ("type", "Type"),
        ("string_form", "String form"),
        ("length", "Length"),
        ("file", "File"),
        ("signature", "Signature"),
        ("init", "Init"),
        ("bases", "Bases"),
        ("exports", "Exports"),
    )
    width = max(len(label) for _key, label in order) + 2
    lines: list[str] = []
    for key, label in order:
        if key not in data:
            continue
        value = str(data[key])
        if "\n" in value:
            value = value.splitlines()[0] + " ..."
        lines.append(f"{label + ':':<{width}}{value}")

    if "docstring" in data:
        lines.append("")
        lines.append("Docstring:")
        lines.extend("    " + line for line in str(data["docstring"]).splitlines())

    if "source" in data:
        lines.append("")
        lines.append("Source:")
        lines.extend("    " + line for line in str(data["source"]).splitlines())

    return "\n".join(lines) + "\n"


def _truncate(text: str, limit: int) -> str:
    """Return *text* shortened to *limit* characters.

    Parameters
    ----------
    text : str
    limit : int

    Returns
    -------
    str
    """
    return text if len(text) <= limit else text[: limit - 3] + "..."


class _quiet:
    """Context manager swallowing introspection failures.

    Introspecting an arbitrary object routinely raises -- a property with a
    side effect, a C extension with no source, a ``__repr__`` that throws. Each
    field is best-effort and its absence is the correct outcome.
    """

    def __enter__(self) -> _quiet:
        """Enter the block.

        Returns
        -------
        _quiet
        """
        return self

    def __exit__(self, *exc_info) -> bool:
        """Swallow whatever was raised.

        Returns
        -------
        bool
            Always ``True``.
        """
        return True
