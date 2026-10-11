"""Every shell command a guide shows must be a command the installed package provides.

Plugin CLIs are subcommands of ``csc`` (``csc img-frc …``); only the entries of
``pyproject.toml``'s ``[project.scripts]`` / ``[project.gui-scripts]`` are executables of their own.
Guides that wrote the bare plugin name (``img-frc``, ``lightpath-simulator``, ``sm-image-mle``) showed a
reader a command their shell answered with "command not found".
"""

from __future__ import annotations

import pathlib
import tomllib

ROOT = pathlib.Path(__file__).resolve().parents[1]
#: Tools a reader's shell has anyway (and shell syntax), not provided by ChiSurf.
SHELL = {
    "awk", "brew", "cat", "cd", "conda", "cp", "curl", "done", "do", "echo", "env", "export", "for", "git",
    "jupyter", "ls", "make", "mamba", "mkdir", "mv", "open", "pip", "pixi", "pytest", "python", "python3",
    "rm", "set", "source", "sudo", "tar", "unzip", "wget", "which",
}
FENCES = ("```bash", "```sh", "```console", "```shell")


def _commands(text: str):
    """Yield ``(line_number, first_token, line)`` of every command line in the shell blocks of *text*."""
    in_block = continued = False
    for number, line in enumerate(text.split("\n"), 1):
        if line.startswith("```"):
            in_block = line.strip() in FENCES if not in_block else False
            continued = False
            continue
        if not in_block:
            continue
        stripped = line.strip()
        starts_command = stripped and not continued and not line[:1].isspace() and not stripped.startswith("#")
        continued = line.rstrip().endswith("\\")
        if not starts_command:
            continue
        token = stripped.split()[0].lstrip("$")
        if "=" in token:  # VAR=value command
            continue
        yield number, token, stripped


def test_every_guide_command_is_a_command_the_package_installs():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    known = set(project.get("scripts", {})) | set(project.get("gui-scripts", {})) | SHELL
    unknown = [
        f"{guide.relative_to(ROOT)}:{number}: {line[:100]}"
        for guide in sorted((ROOT / "docs" / "guides").glob("*.md"))
        for number, token, line in _commands(guide.read_text(encoding="utf-8"))
        if token not in known
    ]
    assert not unknown, "Plugin CLIs run as `csc <name> …`:\n" + "\n".join(unknown)


def _csc_commands() -> set[str]:
    """The subcommands ``csc`` registers, read from ``csc`` itself."""
    from chisurf.core import cli as csc

    csc._register_plugin_clis()
    return set(csc.cli.commands)


def test_every_csc_subcommand_a_guide_shows_is_registered():
    registered = _csc_commands()
    unknown = [
        f"{guide.relative_to(ROOT)}:{number}: {line[:100]}"
        for guide in sorted((ROOT / "docs" / "guides").glob("*.md"))
        for number, token, line in _commands(guide.read_text(encoding="utf-8"))
        if token == "csc"
        and len(line.split()) > 1
        and not line.split()[1].startswith("-")
        and line.split()[1] not in registered
    ]
    assert not unknown, "\n".join(unknown)
