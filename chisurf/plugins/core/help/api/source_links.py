"""Links from the documentation into the source, addressed by symbol.

The documentation constantly names code — ``chisurf/core/fitting/fit.py``,
``sample_fit``, ``BurstWorkflow.register_all``. Written as plain text those are
three lines a reader has to go and find; written as a link they should open the
**code editor** at that place.

Addressed by **symbol, not by line number**. A line number is correct for
exactly as long as nobody edits the file above it, and then it silently points
at the wrong thing — which is worse than pointing nowhere, because it still
looks right. A function or class name survives every edit that does not rename
it, and a rename breaks the link *loudly*: the target is simply not found and
the reader is told so.

Address forms, all resolved by :func:`resolve`:

``chisurf/core/fitting/fit.py``
    the file.
``chisurf/core/fitting/fit.py#sample_fit``
    the function or class in it.
``chisurf/core/fitting/fit.py#Fit.get_score``
    the method of a class.
``src:chisurf/core/fitting/fit.py#Fit.get_score``
    the same, written with an explicit scheme where the context needs one.

Nothing here needs Qt: resolution is reading a file and parsing it, and the
same answer serves the browser, the ``?`` modal and any tooling.
"""

from __future__ import annotations

import ast
import functools
import pathlib
import re
from dataclasses import dataclass

__all__ = ["SourceTarget", "is_source_path", "link_label", "resolve", "symbol_line"]

#: Suffixes treated as source rather than as documentation.
SOURCE_SUFFIXES = (
    ".py",
    ".pyx",
    ".pyi",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".ui",
    ".qss",
    ".sh",
    ".js",
    ".ts",
)

#: An explicit scheme, for places where a bare path would be ambiguous.
_SCHEME = re.compile(r"^(?:src|code|source):", re.IGNORECASE)


@dataclass
class SourceTarget:
    """A resolved link into the source."""

    path: pathlib.Path
    symbol: str = ""
    line: int = 0
    #: Whether *symbol* was asked for but not found.
    missing_symbol: bool = False

    @property
    def label(self) -> str:
        """How the link should read when the page gives no caption."""
        return f"{self.path.name}::{self.symbol}" if self.symbol else self.path.name


def repository_root() -> pathlib.Path:
    """Return the directory holding ``docs/`` — the repo or install root."""
    from chisurf.plugins.core.help.api.toc import repository_root as root

    return root()


def is_source_path(target: str) -> bool:
    """Whether *target* names source rather than a documentation page.

    Parameters
    ----------
    target : str
        A link target, with or without an ``#anchor`` and scheme.

    Returns
    -------
    bool
        *True* for a path with a source suffix, or an explicit ``src:`` scheme.

    """
    text = str(target or "").strip()
    if not text:
        return False
    if _SCHEME.match(text):
        return True
    path = text.split("#", 1)[0]
    return pathlib.Path(path).suffix.lower() in SOURCE_SUFFIXES


def resolve(target: str, base: pathlib.Path | None = None) -> SourceTarget | None:
    """Resolve a source link to a file and, where asked for, a line.

    Parameters
    ----------
    target : str
        ``path``, ``path#symbol``, or the same with a ``src:`` scheme.
    base : pathlib.Path, optional
        Directory to resolve a relative path against, tried before the
        repository root.

    Returns
    -------
    SourceTarget or None
        ``None`` when the file does not exist. A *symbol* that cannot be found
        still returns the file, with ``missing_symbol`` set — the reader is
        better served by the file than by nothing.

    """
    text = _SCHEME.sub("", str(target or "").strip())
    if not text:
        return None
    path_part, _, symbol = text.partition("#")
    path = _locate(path_part.strip(), base)
    if path is None:
        return None
    symbol = symbol.strip()
    if not symbol:
        return SourceTarget(path=path)
    line = symbol_line(path, symbol)
    return SourceTarget(path=path, symbol=symbol, line=line or 0, missing_symbol=line is None)


def _locate(relative: str, base: pathlib.Path | None) -> pathlib.Path | None:
    """Find the file a link names."""
    if not relative:
        return None
    candidate = pathlib.Path(relative)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    for root in ([base] if base is not None else []) + [repository_root()]:
        if root is None:
            continue
        resolved = (root / candidate).resolve()
        if resolved.is_file():
            return resolved
    return None


@functools.lru_cache(maxsize=256)
def _symbol_table(path: str, stamp: float) -> dict:
    """Return ``{qualified name: line}`` for a Python file.

    Cached against the file's modification time, so an edited file is re-parsed
    and an unedited one costs nothing.
    """
    table: dict[str, int] = {}
    file = pathlib.Path(path)
    if file.suffix.lower() not in (".py", ".pyi"):
        return table
    try:
        tree = ast.parse(file.read_text(encoding="utf-8"))
    except Exception:
        return table

    def walk(node, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            name = getattr(child, "name", None)
            if name and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified = f"{prefix}{name}"
                table.setdefault(qualified, child.lineno)
                # The bare name too, so ``#get_score`` finds ``Fit.get_score``.
                table.setdefault(name, child.lineno)
                walk(child, f"{qualified}.")
            else:
                walk(child, prefix)

    walk(tree)
    return table


def symbol_line(path: pathlib.Path, symbol: str) -> int | None:
    """Return the 1-based line where *symbol* is defined, or ``None``.

    Python files are parsed; for any other language the symbol is searched for
    as a whole word on a definition-looking line, which is enough for the JSON
    and YAML keys the documentation points at.
    """
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None

    table = _symbol_table(str(path), stamp)
    if table:
        return table.get(symbol)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    pattern = re.compile(rf"^\s*[\"\']?{re.escape(symbol)}[\"\']?\s*[:=]")
    for number, line in enumerate(text.splitlines(), 1):
        if pattern.match(line):
            return number
    return None


#: ``{src}`path#symbol``` / ``{src}`text <path#symbol>``` in a page.
SRC_ROLE = re.compile(r"\{src\}`([^`]+)`")


def link_label(written: str, target: SourceTarget | None = None) -> str:
    """Return how a source link should read when the page gives no caption.

    The **path as written**, because a "See also" list naming five files from
    four directories is unreadable as five bare basenames; a symbol is appended
    as ``file.py::name`` so the reader can see it goes to a definition rather
    than to the top of the file.
    """
    path, _, symbol = _SCHEME.sub("", str(written or "").strip()).partition("#")
    symbol = symbol.strip() or (target.symbol if target is not None else "")
    return f"{path.strip()}::{symbol}" if symbol else path.strip()


def expand_source_roles(text: str) -> str:
    """Rewrite every ``{src}`` role into an ordinary Markdown link.

    The link target keeps the ``path#symbol`` form, which the browser routes to
    the code editor; the *text* becomes the symbol, or the caption the page
    gave.
    """

    def _replace(match: re.Match[str]) -> str:
        body = match.group(1).strip()
        caption = ""
        if "<" in body and body.endswith(">"):
            caption, body = body[: body.index("<")].strip(), body[body.index("<") + 1 : -1]
        resolved = resolve(body)
        label = caption or link_label(body, resolved)
        return f"[`{label}`]({body})"

    return SRC_ROLE.sub(_replace, str(text))
