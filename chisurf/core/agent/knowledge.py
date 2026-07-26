"""What the agent needs in order to *program* ChiSurf, not just drive it.

Operating the program through tools needs no knowledge of the codebase.
Writing against it does, and that is knowledge no general-purpose model has:
`FitGroup`, `parameters_all_dict`, what a plugin manifest looks like, which
call is the supported one. Left to guess, a model writes plausible code
against an API that does not exist.

Two sources answer that, and they answer different questions:

``the source tree``
    *What exists and what does it take?* An AST index of every public class,
    function and method — signature, docstring, file and line. It is derived
    from the code, so it cannot be out of date.
``the prose``
    *Why is it like that, and what is the right way?* The OKF concepts under
    ``okf/`` and the guides under ``docs/`` carry the architecture and the
    conventions, which the signatures do not.

The index is cached under the settings directory and rebuilt when the source
tree changes.
"""

from __future__ import annotations

import ast
import json
import logging
import pathlib
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

#: Directories of the checkout that hold prose knowledge about the *codebase*.
PROSE_ROOTS = ("okf", "docs")

#: Parts of the tree that are not the public API.
_SKIPPED_PARTS = {"__pycache__", "test", "tests", "build", ".pixi"}


@dataclass(frozen=True)
class ApiSymbol:
    """One public class, function or method of the ChiSurf source tree."""

    name: str
    qualname: str
    module: str
    path: str
    line: int
    kind: str
    signature: str
    docstring: str = ""

    def one_line(self) -> str:
        """Return the symbol as a single reference line."""
        return f"{self.qualname} — {self.signature} ({self.path}:{self.line})"

    def summary(self, doc_chars: int = 400) -> dict[str, Any]:
        """Return a compact dict for a tool result."""
        first = (self.docstring or "").strip()
        return {
            "qualname": self.qualname,
            "kind": self.kind,
            "signature": self.signature,
            "location": f"{self.path}:{self.line}",
            "doc": first[:doc_chars],
        }


def repository_root() -> pathlib.Path:
    """Return the root of the ChiSurf checkout (the parent of the package)."""
    import chisurf

    return pathlib.Path(chisurf.__file__).resolve().parent.parent


def _module_name(path: pathlib.Path, package_root: pathlib.Path) -> str:
    """Return the dotted module name for a source path."""
    relative = path.relative_to(package_root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(["chisurf", *parts])


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Return a readable signature for a function node."""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    try:
        arguments = ast.unparse(node.args)
    except Exception:
        arguments = "..."
    returns = ""
    if node.returns is not None:
        try:
            returns = f" -> {ast.unparse(node.returns)}"
        except Exception:
            returns = ""
    return f"{prefix} {node.name}({arguments}){returns}"


def iter_api_symbols(package_root: pathlib.Path | None = None) -> list[ApiSymbol]:
    """Extract the public API of the ChiSurf package from its source.

    Parameters
    ----------
    package_root : pathlib.Path, optional
        The ``chisurf`` package directory.

    Returns
    -------
    list of ApiSymbol
        Public classes, functions and methods, in file order.
    """
    root = package_root or (repository_root() / "chisurf")
    symbols: list[ApiSymbol] = []
    for path in sorted(root.rglob("*.py")):
        if any(part in _SKIPPED_PARTS for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
        except (OSError, SyntaxError, ValueError):
            continue
        module = _module_name(path, root)
        display = path.relative_to(root.parent).as_posix()

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                if node.name.startswith("_"):
                    continue
                symbols.append(
                    ApiSymbol(
                        name=node.name,
                        qualname=f"{module}.{node.name}",
                        module=module,
                        path=display,
                        line=node.lineno,
                        kind="class",
                        signature=f"class {node.name}",
                        docstring=ast.get_docstring(node) or "",
                    )
                )
                for child in node.body:
                    if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if child.name.startswith("_") and child.name != "__init__":
                        continue
                    symbols.append(
                        ApiSymbol(
                            name=child.name,
                            qualname=f"{module}.{node.name}.{child.name}",
                            module=module,
                            path=display,
                            line=child.lineno,
                            kind="method",
                            signature=_signature(child),
                            docstring=ast.get_docstring(child) or "",
                        )
                    )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                symbols.append(
                    ApiSymbol(
                        name=node.name,
                        qualname=f"{module}.{node.name}",
                        module=module,
                        path=display,
                        line=node.lineno,
                        kind="function",
                        signature=_signature(node),
                        docstring=ast.get_docstring(node) or "",
                    )
                )
    return symbols


def _cache_path() -> pathlib.Path:
    """Return the on-disk location of the cached index."""
    from chisurf.core.settings import get_path

    return pathlib.Path(get_path("settings")) / "agent_api_index.json"


def _tree_fingerprint(package_root: pathlib.Path) -> str:
    """Return a cheap fingerprint of the source tree's state.

    The newest modification time and the file count are enough to notice that
    the checkout moved on, without walking file contents.
    """
    newest = 0.0
    count = 0
    for path in package_root.rglob("*.py"):
        if any(part in _SKIPPED_PARTS for part in path.parts):
            continue
        try:
            newest = max(newest, path.stat().st_mtime)
        except OSError:
            continue
        count += 1
    return f"{count}:{newest:.0f}"


class ApiIndex:
    """A searchable index of the ChiSurf source API."""

    def __init__(self, symbols: list[ApiSymbol]):
        self.symbols = symbols

    # ── construction ──────────────────────────────────────────────────

    @classmethod
    def build(cls, package_root: pathlib.Path | None = None) -> ApiIndex:
        """Index the source tree from scratch."""
        return cls(iter_api_symbols(package_root))

    @classmethod
    def load(cls, refresh: bool = False) -> ApiIndex:
        """Return the index, using the cache when the source has not changed.

        Parameters
        ----------
        refresh : bool
            Rebuild even when the cache looks current.

        Returns
        -------
        ApiIndex
        """
        package_root = repository_root() / "chisurf"
        fingerprint = _tree_fingerprint(package_root)
        cache = _cache_path()

        if not refresh and cache.is_file():
            try:
                payload = json.loads(cache.read_text(encoding="utf-8"))
                if payload.get("fingerprint") == fingerprint:
                    return cls([ApiSymbol(**entry) for entry in payload.get("symbols", [])])
            except Exception:
                logger.debug("agent API index cache unreadable; rebuilding", exc_info=True)

        index = cls.build(package_root)
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps(
                    {
                        "fingerprint": fingerprint,
                        "symbols": [asdict(symbol) for symbol in index.symbols],
                    }
                ),
                encoding="utf-8",
            )
        except Exception:
            logger.debug("could not cache the agent API index", exc_info=True)
        return index

    # ── search ────────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 12, kind: str = "") -> list[ApiSymbol]:
        """Return the symbols most relevant to *query*, best first.

        Ranking prefers an exact name, then a name that contains the query,
        then the qualified name, then the docstring — a model looking for
        ``FitGroup`` should get the class, not every function that mentions
        it in passing.

        Parameters
        ----------
        query : str
            A symbol name, part of one, or a phrase.
        limit : int
            Maximum number of results.
        kind : str
            Restrict to ``"class"``, ``"function"`` or ``"method"``.

        Returns
        -------
        list of ApiSymbol
        """
        terms = [term for term in re.split(r"[^\w]+", str(query).lower()) if term]
        if not terms:
            return []

        # Names here are snake_case, and a caller rarely has the exact one: an
        # RPC method called ``fret.compute_from_efficiency`` is implemented by
        # ``compute_fret_from_efficiency``, and searching the former found
        # nothing at all, because ``_`` is a word character so the query stayed
        # one unsplittable term. Words are therefore also matched individually,
        # below the weight of a whole-phrase hit so precision is kept.
        words = [word for term in terms for word in term.split("_") if len(word) > 2]

        scored: list[tuple[float, ApiSymbol]] = []
        for symbol in self.symbols:
            if kind and symbol.kind != kind:
                continue
            name = symbol.name.lower()
            qualname = symbol.qualname.lower()
            doc = (symbol.docstring or "").lower()
            score = 0.0
            for term in terms:
                if name == term:
                    score += 10.0
                elif term in name:
                    score += 5.0
                if term in qualname:
                    score += 2.0
                if term in doc:
                    score += 1.0
            if words:
                name_words = set(re.split(r"[^\w]+|_", name))
                present = sum(1 for word in words if word in name_words or word in name)
                if present == len(words):
                    score += 4.0            # every word of the query is in the name
                elif present:
                    score += present * 0.5
            if score:
                # A shorter qualname is usually the more public entry point.
                score += max(0.0, 3.0 - qualname.count(".") * 0.5)
                scored.append((score, symbol))

        scored.sort(key=lambda item: (-item[0], item[1].qualname))
        return [symbol for _, symbol in scored[: max(1, int(limit))]]

    def get(self, qualname: str) -> ApiSymbol | None:
        """Return the symbol with this exact qualified name, or ``None``."""
        wanted = str(qualname).strip()
        for symbol in self.symbols:
            if symbol.qualname == wanted:
                return symbol
        for symbol in self.symbols:
            if symbol.qualname.endswith("." + wanted) or symbol.name == wanted:
                return symbol
        return None


def read_definition(symbol: ApiSymbol, max_lines: int = 120) -> str:
    """Return the source text of a symbol's definition.

    Parameters
    ----------
    symbol : ApiSymbol
        The symbol to read.
    max_lines : int
        Maximum number of lines to return.

    Returns
    -------
    str
        The source, or an empty string when the file cannot be read.
    """
    path = repository_root() / symbol.path
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    start = max(0, symbol.line - 1)
    body = lines[start : start + max(1, int(max_lines))]

    # Stop at the next top-level definition so a class does not swallow the
    # rest of the module.
    indent = len(body[0]) - len(body[0].lstrip()) if body else 0
    cut = len(body)
    for offset, line in enumerate(body[1:], start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        current = len(line) - len(line.lstrip())
        if current <= indent and (stripped.startswith(("def ", "class ", "@"))):
            cut = offset
            break
    return "\n".join(body[:cut])


#: Documents that record *what changed* rather than *how things work*. They
#: are enormous and mention everything, so by raw hit count they would win
#: every search while answering no question.
_CHANGELOG_NAMES = {"log.md", "changelog.md", "history.md", "assessment.md"}


def knowledge_base_root() -> pathlib.Path:
    """Return the assistant's own knowledge bundle, shipped with the package.

    This is deliberately separate from the repository's ``okf/``: that bundle
    describes how ChiSurf is *built*, this one what fluorescence analysis and
    ChiSurf's objects *mean*. Both are searched, because a question can land
    in either.
    """
    return pathlib.Path(__file__).parent / "knowledge_base"


def iter_prose_documents(roots: Iterable[str] = PROSE_ROOTS) -> list[pathlib.Path]:
    """Return every markdown document the assistant can consult.

    That is the assistant's own knowledge bundle plus the repository's
    documentation and OKF concepts.
    """
    base = repository_root()
    documents: list[pathlib.Path] = []
    bundle = knowledge_base_root()
    if bundle.is_dir():
        documents.extend(sorted(bundle.rglob("*.md")))
    for name in roots:
        directory = base / name
        if not directory.is_dir():
            continue
        documents.extend(
            path
            for path in sorted(directory.rglob("*.md"))
            if "_build" not in path.parts
            and "__pycache__" not in path.parts
            and path.name.lower() not in _CHANGELOG_NAMES
        )
    return documents


def _display_document(path: pathlib.Path, base: pathlib.Path) -> str:
    """Return the identifier a caller can pass back to ``read_doc``."""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.name


def search_prose(query: str, limit: int = 6, context_lines: int = 8) -> list[dict[str, Any]]:
    """Search the OKF concepts and guides for a phrase.

    Signatures say what exists; the prose says why it is that way and what the
    conventions are. Both are needed to write code that belongs in this
    codebase rather than merely running.

    Parameters
    ----------
    query : str
        Words to look for.
    limit : int
        Maximum number of documents to report.
    context_lines : int
        Lines of context around the best match in each document.

    Returns
    -------
    list of dict
        ``{"document", "title", "score", "excerpt"}`` per hit.
    """
    terms = [term for term in re.split(r"[^\w]+", str(query).lower()) if len(term) > 2]
    if not terms:
        return []

    base = repository_root()
    bundle_root = knowledge_base_root()
    hits: list[tuple[float, dict[str, Any]]] = []
    for path in iter_prose_documents():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lowered = text.lower()
        raw = sum(lowered.count(term) for term in terms)
        if not raw:
            continue
        # Normalise by length: a long document mentioning the word often is
        # not more relevant than a short one that is about it.
        score = raw / max(1.0, (len(text) / 4000.0) ** 0.5)
        # A title match counts double — a document *about* the thing beats one
        # that mentions it in passing.
        if any(term in path.stem.lower() for term in terms):
            score *= 2
        # The assistant's own bundle is written for exactly this purpose and
        # is deliberately concise; the repository's documentation is larger
        # and aimed at developers. Prefer the former when both match.
        if bundle_root in path.parents:
            score *= 1.5

        lines = text.splitlines()
        best_line, best_hits = 0, 0
        for number, line in enumerate(lines):
            line_hits = sum(term in line.lower() for term in terms)
            if line_hits > best_hits:
                best_line, best_hits = number, line_hits
        start = max(0, best_line - context_lines // 2)
        excerpt = "\n".join(lines[start : start + context_lines])

        hits.append(
            (
                float(score),
                {
                    "document": _display_document(path, base),
                    "title": next(
                        (line.lstrip("# ").strip() for line in lines if line.startswith("#")),
                        path.stem,
                    ),
                    "score": float(score),
                    "excerpt": excerpt,
                },
            )
        )

    hits.sort(key=lambda item: -item[0])
    return [payload for _, payload in hits[: max(1, int(limit))]]
