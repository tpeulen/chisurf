"""Agent tools that run Python inside the live ChiSurf session.

``run_python`` is the escape hatch that makes the agent useful beyond the
curated tools: anything the user can do from the ChiSurf console -- custom
analysis, plotting, exporting, driving a plugin -- the agent can do by
writing a short script.

The code runs **in the calling process**, so it sees the same datasets and
fits as the rest of the session.  That is the entire point (a subprocess
would see an empty session), and it is also why the tool is in the
``dangerous`` safety tier and is gated by
:attr:`AgentContext.allow_code_execution <chisurf.core.agent.context.AgentContext.allow_code_execution>`
and the confirmation callback.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import pathlib
import time
import traceback
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_DANGEROUS, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

registry = ToolRegistry()

_CODE_PREAMBLE = """\
Available names: cs (the chisurf package), datasets (chisurf.imported_datasets),
fits (chisurf.fits), np (numpy), Path (pathlib.Path), result (set it to return
a value)."""


def build_namespace(context: AgentContext) -> dict[str, Any]:
    """Return the globals a ``run_python`` snippet is executed with.

    Parameters
    ----------
    context : AgentContext
        Execution context; its working directory becomes ``WORKDIR``.

    Returns
    -------
    dict
        Module-level namespace for :func:`exec`.
    """
    import numpy as np

    import chisurf as cs

    namespace: dict[str, Any] = {
        "__name__": "__chisurf_agent__",
        "__builtins__": __builtins__,
        "cs": cs,
        "chisurf": cs,
        "np": np,
        "Path": pathlib.Path,
        "WORKDIR": str(context.working_directory),
        "datasets": getattr(cs, "imported_datasets", []),
        "fits": getattr(cs, "fits", []),
        "result": None,
    }
    api = getattr(cs, "api", None)
    if api is not None:
        namespace["api"] = api
    return namespace


@contextlib.contextmanager
def working_directory(context: AgentContext):
    """Run the body with the process directory set to the agent's.

    Every other tool resolves paths against ``context.working_directory``, so
    a snippet that does not is a trap: ``Path("analysis").glob("*.bur")`` finds
    nothing, silently, because it looked wherever the *program* was started.
    That happened to a real model — it wrote the recipe correctly, got "No
    objects to concatenate" from an empty glob, and spent the rest of its
    budget trying to work out why the files it had just listed did not exist.

    Parameters
    ----------
    context : AgentContext
        Supplies the directory.

    Yields
    ------
    None
    """
    previous = os.getcwd()
    try:
        target = pathlib.Path(context.working_directory).expanduser()
        if target.is_dir():
            os.chdir(target)
        yield
    finally:
        try:
            os.chdir(previous)
        except OSError:  # pragma: no cover - the old directory went away
            logger.debug("could not restore the working directory", exc_info=True)


@registry.add(
    name="run_python",
    description=(
        "Run a short Python script inside the running ChiSurf session and "
        "return its printed output.\n"
        f"{_CODE_PREAMBLE}\n"
        "Use this for anything the other tools do not cover: custom analysis, "
        "exporting numbers, driving a plugin, or writing a helper script for "
        "the user. Prefer the dedicated tools for loading data and fitting — "
        "they handle the awkward details for you.\n"
        "The script runs synchronously, so keep it short and print what you "
        "need to see."
    ),
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source to execute."},
            "purpose": {
                "type": "string",
                "description": "One sentence on what the script is for (shown to the user).",
            },
        },
        "required": ["code"],
    },
    safety=SAFETY_DANGEROUS,
)
def run_python(
    context: AgentContext,
    code: str,
    purpose: str | None = None,
) -> dict[str, Any]:
    """Execute *code* in-process and capture its output."""
    if not context.allow_code_execution:
        raise ToolError(
            "code execution is disabled in this session; use the other tools "
            "or ask the user to enable it"
        )
    if not str(code).strip():
        raise ToolError("no code given")

    namespace = build_namespace(context)
    stdout, stderr = io.StringIO(), io.StringIO()
    started = time.perf_counter()
    error: str | None = None
    try:
        with (
            working_directory(context),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exec(compile(str(code), "<agent>", "exec"), namespace)  # noqa: S102
    except BaseException as exception:  # noqa: BLE001 - reported back to the model
        error = "".join(traceback.format_exception_only(type(exception), exception)).strip()
        logger.debug("run_python failed", exc_info=True)

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    limit = context.max_result_chars
    result: dict[str, Any] = {
        "ok": error is None,
        "stdout": stdout.getvalue()[:limit],
        "elapsed_ms": elapsed_ms,
    }
    if purpose:
        result["purpose"] = purpose
    captured_stderr = stderr.getvalue()[:limit]
    if captured_stderr:
        result["stderr"] = captured_stderr
    value = namespace.get("result")
    if value is not None:
        result["result"] = repr(value)[:limit]
    if error is not None:
        result["error"] = error
    return result


@registry.add(
    name="write_file",
    description=(
        "Write a text file (a script, a note, a small data export) to disk.\n"
        "Use this when the user asks for a reusable script rather than a "
        "one-off calculation."
    ),
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target path."},
            "content": {"type": "string", "description": "Full file content."},
        },
        "required": ["path", "content"],
    },
    safety=SAFETY_DANGEROUS,
)
def write_file(context: AgentContext, path: str, content: str) -> dict[str, Any]:
    """Write *content* to *path*."""
    if not context.allow_code_execution:
        raise ToolError("writing files is disabled in this session")
    target = context.resolve_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(str(content), encoding="utf-8")
    return {
        "ok": True,
        "path": str(target),
        "overwritten": existed,
        "n_lines": str(content).count("\n") + 1,
    }


@registry.add(
    name="read_file",
    description="Read a text file from disk (e.g. to inspect a script or a small data file).",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to read."},
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to return. Default 200.",
            },
        },
        "required": ["path"],
    },
    safety="read",
)
def read_file(context: AgentContext, path: str, max_lines: int = 200) -> dict[str, Any]:
    """Return the first *max_lines* lines of a text file."""
    target = context.resolve_path(path)
    if not target.is_file():
        raise ToolError(f"not a file: {target}")
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as error:
        raise ToolError(f"cannot read {target}: {error}") from error
    lines = text.splitlines()
    truncated = len(lines) > int(max_lines)
    return {
        "ok": True,
        "path": str(target),
        "n_lines": len(lines),
        "truncated": truncated,
        "content": "\n".join(lines[: int(max_lines)])[: context.max_result_chars],
    }
