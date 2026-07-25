"""Agent tools that drive the computer, not just ChiSurf.

Analysis rarely stops at the application boundary: data arrives as an archive
to unpack, a vendor converter has to run first, a fitted result feeds a script
somebody else wrote, results go into a repository.  An assistant that can only
reach ChiSurf's own functions leaves the user to do all of that by hand.

These tools therefore run arbitrary programs on the machine.  They sit in the
``dangerous`` tier, which means two things in practice: they are absent
altogether below that tier (the GUI's *ChiSurf tools* mode, ``--safety
write``), and where they are available each call goes through the
confirmation callback — a dialog in the GUI, a prompt on the terminal —
unless the user has explicitly waived it with ``--yes``.

Nothing here is sandboxed. That is deliberate: a sandbox that blocked the
vendor converter would defeat the purpose. The protection is that the user
sees the exact command before it runs and can say no.
"""

from __future__ import annotations

import logging
import os
import pathlib
import shlex
import shutil
import subprocess
import time
from typing import Any

from chisurf.core.agent.context import AgentContext
from chisurf.core.agent.spec import SAFETY_DANGEROUS, SAFETY_READ, ToolError, ToolRegistry

logger = logging.getLogger(__name__)

registry = ToolRegistry()

#: Commands that destroy broadly and are almost never what a fitting
#: assistant means.  They are refused outright rather than confirmed: a
#: confirmation dialog is a poor last line of defence against ``rm -rf /``,
#: and any legitimate use of these is better done by the user directly.
_REFUSED_PATTERNS = (
    "rm -rf /",
    "rm -rf ~",
    "rm -rf *",
    ":(){",
    "mkfs",
    "dd if=/dev/zero of=/dev",
    "> /dev/sda",
    "chmod -r 777 /",
    "shutdown",
    "reboot",
)


def _refuse_if_catastrophic(command: str) -> None:
    """Raise when *command* matches a pattern that destroys indiscriminately.

    Parameters
    ----------
    command : str
        The command line as it would be run.

    Raises
    ------
    ToolError
        When the command matches a refused pattern.
    """
    normalised = " ".join(str(command).lower().split())
    for pattern in _REFUSED_PATTERNS:
        if pattern in normalised:
            raise ToolError(
                f"refusing to run a command matching {pattern!r}. If you really "
                f"mean it, the user should run it themselves."
            )


@registry.add(
    name="run_command",
    description=(
        "Run a program on the computer and return its output — a converter, "
        "an archive tool, a script, git, anything installed.\n"
        "Use this for work that happens outside ChiSurf: unpacking data, "
        "converting a vendor format, calling another analysis program, moving "
        "results into place. For anything inside the session (loading, "
        "fitting, exporting) use the ChiSurf tools instead; they know about "
        "the objects, a shell command does not.\n"
        "The user is shown the command and can refuse it. State plainly what "
        "you are about to do and why, especially when it writes or deletes."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command line to run, e.g. 'unzip data.zip -d raw'.",
            },
            "cwd": {
                "type": "string",
                "description": "Directory to run in. Default: the working directory.",
            },
            "timeout_s": {
                "type": "number",
                "description": "Seconds before the command is killed. Default 120.",
            },
            "purpose": {
                "type": "string",
                "description": "One sentence on why this is being run (shown to the user).",
            },
        },
        "required": ["command"],
    },
    safety=SAFETY_DANGEROUS,
)
def run_command(
    context: AgentContext,
    command: str,
    cwd: str | None = None,
    timeout_s: float = 120.0,
    purpose: str | None = None,
) -> dict[str, Any]:
    """Run *command* through the shell and capture its output."""
    if not context.allow_code_execution:
        raise ToolError(
            "running programs is disabled in this session; ask the user to enable full control"
        )
    text = str(command).strip()
    if not text:
        raise ToolError("no command given")
    _refuse_if_catastrophic(text)

    directory = context.resolve_path(cwd) if cwd else pathlib.Path(context.working_directory)
    if not directory.is_dir():
        raise ToolError(f"working directory does not exist: {directory}")

    started = time.perf_counter()
    try:
        completed = subprocess.run(  # noqa: S602 - running programs is the point
            text,
            shell=True,
            cwd=str(directory),
            capture_output=True,
            text=True,
            timeout=max(1.0, float(timeout_s)),
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        raise ToolError(
            f"command timed out after {timeout_s:g}s: {text!r}. Raise timeout_s, "
            f"or run something that finishes."
        ) from None
    except Exception as error:
        raise ToolError(f"could not run {text!r}: {type(error).__name__}: {error}") from error

    limit = context.max_result_chars
    result: dict[str, Any] = {
        "ok": completed.returncode == 0,
        "command": text,
        "cwd": str(directory),
        "exit_code": completed.returncode,
        "stdout": (completed.stdout or "")[:limit],
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }
    if purpose:
        result["purpose"] = purpose
    stderr = (completed.stderr or "")[:limit]
    if stderr:
        result["stderr"] = stderr
    if completed.returncode != 0:
        result["error"] = f"the command exited with status {completed.returncode}" + (
            f": {stderr.strip().splitlines()[-1]}" if stderr.strip() else ""
        )
    return result


@registry.add(
    name="which_program",
    description=(
        "Check whether a program is installed and where it lives.\n"
        "Use this before building a command around a tool you are not sure "
        "exists — reporting 'convert is not installed' is far more useful "
        "than a command that fails with 'not found'."
    ),
    parameters={
        "type": "object",
        "properties": {
            "program": {"type": "string", "description": "Program name, e.g. 'ffmpeg'."}
        },
        "required": ["program"],
    },
    safety=SAFETY_READ,
)
def which_program(context: AgentContext, program: str) -> dict[str, Any]:
    """Report whether *program* is on the PATH."""
    path = shutil.which(str(program).strip())
    return {
        "ok": True,
        "program": str(program).strip(),
        "installed": path is not None,
        "path": path,
    }


@registry.add(
    name="list_directory",
    description=(
        "List what is in a directory, including sub-directories and files of "
        "any type.\n"
        "This is the general listing; list_files is the one that knows about "
        "measurement formats and is what you want when looking for data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "directory": {
                "type": "string",
                "description": "Directory to list. Default: the working directory.",
            },
            "pattern": {"type": "string", "description": "Glob to filter names. Default '*'."},
            "limit": {"type": "integer", "description": "Maximum entries to return. Default 200."},
        },
    },
    safety=SAFETY_READ,
)
def list_directory(
    context: AgentContext,
    directory: str | None = None,
    pattern: str = "*",
    limit: int = 200,
) -> dict[str, Any]:
    """Return the entries of a directory with sizes."""
    root = context.resolve_path(directory) if directory else pathlib.Path(context.working_directory)
    if not root.exists():
        raise ToolError(
            f"directory does not exist: {root}. The {context.describe_working_directory()}"
        )
    if not root.is_dir():
        raise ToolError(f"not a directory: {root}")

    entries: list[dict[str, Any]] = []
    for entry in sorted(root.glob(pattern)):
        try:
            is_dir = entry.is_dir()
            entries.append(
                {
                    "name": entry.name + ("/" if is_dir else ""),
                    "type": "directory" if is_dir else "file",
                    "size_kb": None if is_dir else round(entry.stat().st_size / 1024.0, 1),
                }
            )
        except OSError:
            continue
        if len(entries) >= int(limit):
            break
    return {"ok": True, "directory": str(root), "n_entries": len(entries), "entries": entries}


def quote(value: str) -> str:
    """Return *value* quoted for safe inclusion in a shell command.

    Parameters
    ----------
    value : str
        A path or argument that may contain spaces.

    Returns
    -------
    str

    Examples
    --------
    >>> quote("215-268 D0.dat")
    "'215-268 D0.dat'"
    """
    return shlex.quote(str(value))
