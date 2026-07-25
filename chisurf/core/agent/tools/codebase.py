"""Agent tools for writing code *against* ChiSurf, not just driving it.

A model asked to write a plugin, a model class or a script will otherwise
invent an API: plausible names, plausible arguments, none of them real. These
tools let it look the answer up instead — the signatures come from the source
tree, so they cannot be stale, and the prose comes from the OKF concepts and
the guides, which is where the conventions live.

Looking things up is free and guessing is expensive, so all of this is in the
read tier.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_READ, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

registry = ToolRegistry()


@registry.add(
    name="search_api",
    description=(
        "Look up ChiSurf's own classes, functions and methods by name or "
        "topic, with their real signatures and docstrings.\n"
        "Use this before writing any code that calls ChiSurf — the index "
        "comes from the source tree, so it is what actually exists. Guessing "
        "an API is the most common way for generated ChiSurf code to fail."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "A symbol name, part of one, or a phrase (e.g. 'FitGroup', 'add fit').",
            },
            "kind": {
                "type": "string",
                "description": "Restrict to 'class', 'function' or 'method'.",
            },
            "limit": {"type": "integer", "description": "Maximum results. Default 10."},
        },
        "required": ["query"],
    },
    safety=SAFETY_READ,
)
def search_api(
    context: AgentContext,
    query: str,
    kind: str = "",
    limit: int = 10,
) -> dict[str, Any]:
    """Search the ChiSurf source API."""
    from chisurf.core.agent.knowledge import ApiIndex

    index = context.extras.get("api_index")
    if index is None:
        index = ApiIndex.load()
        context.extras["api_index"] = index

    if kind and kind not in ("class", "function", "method"):
        raise ToolError("'kind' must be 'class', 'function' or 'method'")

    matches = index.search(query, limit=limit, kind=kind)
    if not matches:
        raise ToolError(
            f"nothing in the ChiSurf API matches {query!r}. Try a shorter or "
            f"different word, or search_docs for the concept."
        )
    return {
        "ok": True,
        "query": query,
        "n_results": len(matches),
        "results": [symbol.summary() for symbol in matches],
    }


@registry.add(
    name="read_api_source",
    description=(
        "Show the source of one ChiSurf class, function or method.\n"
        "Use it when a signature is not enough — to see what a function "
        "actually does, what it returns, or how an existing implementation "
        "solves the same problem you are about to."
    ),
    parameters={
        "type": "object",
        "properties": {
            "qualname": {
                "type": "string",
                "description": "Qualified name from search_api, e.g. 'chisurf.core.fitting.fit.FitGroup'.",
            },
            "max_lines": {"type": "integer", "description": "Maximum lines. Default 120."},
        },
        "required": ["qualname"],
    },
    safety=SAFETY_READ,
)
def read_api_source(
    context: AgentContext,
    qualname: str,
    max_lines: int = 120,
) -> dict[str, Any]:
    """Return the source text of a ChiSurf definition."""
    from chisurf.core.agent.knowledge import ApiIndex, read_definition

    index = context.extras.get("api_index")
    if index is None:
        index = ApiIndex.load()
        context.extras["api_index"] = index

    symbol = index.get(qualname)
    if symbol is None:
        candidates = [match.qualname for match in index.search(qualname, limit=5)]
        raise ToolError(
            f"no ChiSurf symbol called {qualname!r}."
            + (f" Did you mean one of {candidates}?" if candidates else "")
        )
    source = read_definition(symbol, max_lines=max_lines)
    if not source:
        raise ToolError(f"the source for {symbol.qualname} could not be read")
    return {
        "ok": True,
        **symbol.summary(doc_chars=800),
        "source": source[: context.max_result_chars],
    }


@registry.add(
    name="search_docs",
    description=(
        "Search ChiSurf's own documentation — the architecture concepts and "
        "the user guides — for how something works or how it should be "
        "done.\n"
        "Signatures tell you what exists; this tells you the conventions and "
        "the reasoning. Use it before designing anything that has to fit into "
        "the codebase: plugins, models, a new tool."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "What to look for, e.g. 'plugin manifest' or 'how fits are stored'.",
            },
            "limit": {"type": "integer", "description": "Maximum documents. Default 5."},
        },
        "required": ["query"],
    },
    safety=SAFETY_READ,
)
def search_docs(context: AgentContext, query: str, limit: int = 5) -> dict[str, Any]:
    """Search the OKF concepts and the guides."""
    from chisurf.core.agent.knowledge import search_prose

    hits = search_prose(query, limit=limit)
    if not hits:
        raise ToolError(
            f"the documentation has nothing on {query!r}. Try search_api for a "
            f"symbol, or different words."
        )
    return {"ok": True, "query": query, "n_results": len(hits), "documents": hits}


@registry.add(
    name="read_doc",
    description=(
        "Read one of ChiSurf's documentation files in full, by the path search_docs reported."
    ),
    parameters={
        "type": "object",
        "properties": {
            "document": {
                "type": "string",
                "description": "Repository-relative path, e.g. 'okf/subsystems/fitting.md'.",
            },
            "max_lines": {"type": "integer", "description": "Maximum lines. Default 250."},
        },
        "required": ["document"],
    },
    safety=SAFETY_READ,
)
def read_doc(context: AgentContext, document: str, max_lines: int = 250) -> dict[str, Any]:
    """Return the text of a documentation file."""
    from chisurf.core.agent.knowledge import repository_root

    base = repository_root()
    target = (base / str(document).strip()).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ToolError("only ChiSurf's own documentation can be read this way") from error
    if not target.is_file():
        raise ToolError(f"no such document: {document}. Use search_docs to find one.")

    lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    return {
        "ok": True,
        "document": target.relative_to(base).as_posix(),
        "n_lines": len(lines),
        "truncated": len(lines) > int(max_lines),
        "content": "\n".join(lines[: int(max_lines)])[: context.max_result_chars],
    }


@registry.add(
    name="list_plugins",
    description=(
        "List ChiSurf's plugins with what each one is for.\n"
        "The quickest way to find a worked example: a new plugin is best "
        "written by reading the closest existing one."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Filter by name or description, e.g. 'burst' or 'calculator'.",
            }
        },
    },
    safety=SAFETY_READ,
)
def list_plugins(context: AgentContext, query: str = "") -> dict[str, Any]:
    """List the plugin manifests found in the source tree."""
    import json

    from chisurf.core.agent.knowledge import repository_root

    base = repository_root()
    plugins: list[dict[str, Any]] = []
    wanted = str(query).strip().lower()
    for manifest_path in sorted((base / "chisurf" / "plugins").rglob("manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entry = {
            "id": str(manifest.get("id", "")),
            "display_name": str(manifest.get("display_name", "")),
            "description": str(manifest.get("description", ""))[:200],
            "path": manifest_path.parent.relative_to(base).as_posix(),
        }
        haystack = " ".join(entry.values()).lower()
        if wanted and wanted not in haystack:
            continue
        plugins.append(entry)

    if not plugins:
        raise ToolError(f"no plugin matches {query!r}")
    return {"ok": True, "n_plugins": len(plugins), "plugins": plugins[:60]}


@registry.add(
    name="check_python",
    description=(
        "Check a piece of Python for syntax errors and lint problems before "
        "you write it to a file or run it.\n"
        "Catching a typo here costs one call; catching it after the user has "
        "run the script costs their time."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "The source to check."},
            "path": {
                "type": "string",
                "description": "Existing file to check instead of 'code'.",
            },
        },
    },
    safety=SAFETY_READ,
)
def check_python(
    context: AgentContext,
    code: str = "",
    path: str = "",
) -> dict[str, Any]:
    """Compile the code and, when available, run the project's linter."""
    import subprocess
    import tempfile

    source = code
    if path and not code:
        target = context.resolve_path(path)
        if not target.is_file():
            raise ToolError(f"not a file: {target}")
        source = target.read_text(encoding="utf-8", errors="replace")
    if not source.strip():
        raise ToolError("nothing to check — pass 'code' or an existing 'path'")

    result: dict[str, Any] = {"ok": True, "syntax_ok": True, "issues": []}
    try:
        compile(source, path or "<agent>", "exec")
    except SyntaxError as error:
        result["ok"] = False
        result["syntax_ok"] = False
        result["error"] = f"line {error.lineno}: {error.msg}"
        return result

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as handle:
        handle.write(source)
        temporary = pathlib.Path(handle.name)
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argument list
            ["ruff", "check", "--output-format", "concise", str(temporary)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        issues = [
            line.replace(str(temporary), path or "<code>")
            for line in (completed.stdout or "").splitlines()
            if line.strip()
        ]
        result["issues"] = issues[:40]
        result["n_issues"] = len(issues)
    except FileNotFoundError:
        result["issues"] = []
        result["note"] = "ruff is not installed; only the syntax was checked"
    except Exception as error:
        logger.debug("ruff check failed", exc_info=True)
        result["note"] = f"the linter could not run: {error}"
    finally:
        temporary.unlink(missing_ok=True)
    return result
