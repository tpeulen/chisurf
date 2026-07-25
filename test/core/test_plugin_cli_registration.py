"""Every plugin CLI declared in a manifest must reach the ``csc`` command line.

Plugin CLIs were historically registered from a module-level ``cli_entrypoint``
assignment that ``chisurf/core/cli.py`` finds by AST scan, while the plugin
contract (``manifest.json``) declares the same thing under ``entrypoints.cli``.
Plugins that filled in only the manifest — the majority — were silently absent
from ``csc``. These tests pin the manifest as the authoritative source so the two
cannot drift apart again.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parents[2] / "chisurf" / "plugins"


def _manifest_clis() -> dict[str, str]:
    """Return ``{plugin directory: entrypoints.cli}`` for every built-in manifest."""
    out: dict[str, str] = {}
    for manifest_path in sorted(PLUGIN_ROOT.rglob("manifest.json")):
        if any("{{" in part for part in manifest_path.parts):
            continue  # cookiecutter scaffold, not a real plugin
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        entry = (manifest.get("entrypoints") or {}).get("cli")
        if isinstance(entry, str) and entry.strip():
            out[str(manifest_path.parent.relative_to(PLUGIN_ROOT))] = entry.strip()
    return out


def _module_cli(plugin_dir: pathlib.Path) -> str | None:
    """Return the module-level ``cli_entrypoint`` of a plugin, if it has one."""
    init_py = plugin_dir / "__init__.py"
    if not init_py.exists():
        return None
    try:
        tree = ast.parse(init_py.read_text(encoding="utf-8"))
    except Exception:
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == "cli_entrypoint":
                value = node.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    return value.value.strip()
    return None


@pytest.fixture(scope="module")
def registered_commands() -> set[str]:
    """Return the command names ``csc`` exposes after plugin registration."""
    from chisurf.core.cli import _register_plugin_clis, cli

    _register_plugin_clis()
    return set(cli.commands)


def test_manifests_declare_cli_entrypoints():
    """The scan finds the plugin CLIs (guards against an empty-scan false pass)."""
    assert len(_manifest_clis()) > 20


@pytest.mark.parametrize("plugin_dir,entry", sorted(_manifest_clis().items()))
def test_manifest_cli_is_registered(plugin_dir, entry, registered_commands):
    """Each manifest-declared CLI is reachable as a ``csc`` subcommand."""
    from chisurf.core.cli import _parse_cli_entrypoint

    default_alias = pathlib.Path(plugin_dir).name.replace("_", "-")
    command_name, module_path, _ = _parse_cli_entrypoint(entry, default_alias)
    assert command_name in registered_commands, (
        f"{plugin_dir} declares CLI {entry!r} but 'csc {command_name}' does not exist"
    )
    assert module_path.startswith(("chisurf.", "mmfdb.", "ndxplorer"))


def test_manifest_and_module_entrypoints_agree():
    """Where a plugin declares its CLI twice, both declarations must match."""
    mismatched = []
    for plugin_dir, entry in _manifest_clis().items():
        module_entry = _module_cli(PLUGIN_ROOT / plugin_dir)
        if module_entry and module_entry != entry:
            mismatched.append((plugin_dir, entry, module_entry))
    assert not mismatched, f"manifest/module CLI drift: {mismatched}"


def test_no_scaffold_commands_are_registered(registered_commands):
    """The cookiecutter template must not leak into the command line."""
    assert not [name for name in registered_commands if "{{" in name or "cookiecutter" in name]


def test_command_names_are_cli_shaped(registered_commands):
    """Registered commands are plain kebab-case names, not module paths."""
    for name in registered_commands:
        assert ":" not in name and "/" not in name and " " not in name
        assert name == name.lower()
