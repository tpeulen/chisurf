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
            f"different word, or search_documentation for the concept."
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
        # Asking for a *module* is the natural move after finding a plugin —
        # "read chisurf.plugins.x.core.algorithms" — and the index holds only
        # the definitions inside it. Answering with its contents is what was
        # meant, and beats a near-miss guess from the fuzzy search.
        wanted = str(qualname).strip().rstrip(".")
        inside = [s for s in index.symbols if s.module == wanted]
        if inside:
            return {
                "ok": True,
                "module": wanted,
                "n_symbols": len(inside),
                "symbols": [s.summary(doc_chars=200) for s in inside[:40]],
                "next_step": (
                    f"{wanted} is a module. Call read_api_source again with one "
                    f"of the qualified names above to see its source."
                ),
            }
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
        # A plugin's RPC method names are often the only searchable term a user
        # would think of ("kappa2", "2cde"), and knowing a plugin exists is
        # useless without knowing how to reach it, so both are reported.
        entry.update(plugin_entry_points(manifest, manifest_path.parent))
        haystack += " " + " ".join(str(v) for v in entry.get("rpc_methods", []))
        if wanted and wanted not in haystack.lower():
            continue
        plugins.append(entry)

    if not plugins:
        raise ToolError(
            f"no plugin matches {query!r}. Call list_plugins with no query to "
            f"see all of them, or search the source with search_api."
        )
    result: dict[str, Any] = {"ok": True, "n_plugins": len(plugins), "plugins": plugins[:60]}
    # Most manifests declare a method's name and summary but leave its
    # parameter schema empty, so the names alone are not enough to call one.
    if any(entry.get("rpc_methods") for entry in plugins):
        result["next_step"] = (
            "An RPC method's arguments are usually not in the manifest. Read "
            "them from the function that implements it — search_api for the "
            "plugin's core/api module, then read_api_source — and call that "
            "function directly with run_python."
        )
    return result


def plugin_entry_points(manifest: dict[str, Any], directory: Any) -> dict[str, Any]:
    """Return how a plugin can be driven without its GUI.

    Three routes exist and a plugin may offer any of them: a declared RPC
    method (callable over the server, and the documented contract), a command
    line, or plain Python in its ``api``/``core`` package. Reporting them turns
    "this plugin exists" into "here is how to call it".

    Parameters
    ----------
    manifest : dict
        Parsed ``manifest.json``.
    directory : pathlib.Path
        The plugin's directory.

    Returns
    -------
    dict
        Only the keys that apply, so a plugin with no head-less route is
        visibly bare rather than padded with empty fields.
    """
    found: dict[str, Any] = {}

    methods = manifest.get("rpc_methods") or []
    if isinstance(methods, list) and methods:
        found["rpc_methods"] = [
            {
                "name": str(method.get("name", "")),
                "summary": str(method.get("summary", ""))[:160],
                **({"long_running": True} if method.get("long_running") else {}),
            }
            for method in methods
            if isinstance(method, dict)
        ][:12]

    for candidate in ("cli.py", "cli"):
        if (directory / candidate).exists():
            found["cli"] = (
                str(directory.name) if candidate == "cli" else f"{directory.name}.cli"
            )
            break
    for candidate in ("api", "core"):
        if (directory / candidate).is_dir():
            found.setdefault("python_packages", []).append(candidate)
    return found


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
