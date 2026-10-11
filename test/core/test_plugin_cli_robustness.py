"""Exercise the production lazy CLI's metadata/import identity and invocation."""

from __future__ import annotations

import importlib
import json
import pathlib
import sys
import types

import click
import pytest
from click.testing import CliRunner

cli_module = importlib.import_module("chisurf.core.cli")


@pytest.fixture
def roots(tmp_path, monkeypatch):
    """Redirect both production roots without touching installed user plugins."""
    built_in = tmp_path / "checkout" / "plugins"
    user = tmp_path / "home" / ".chisurf" / "plugins"
    built_in.mkdir(parents=True)
    user.mkdir(parents=True)
    monkeypatch.setattr(cli_module, "__file__", str(tmp_path / "checkout/core/cli/__init__.py"))
    monkeypatch.setattr(pathlib.Path, "home", classmethod(lambda cls: tmp_path / "home"))
    return built_in, user


def _package(root, name, *, plugin_id=None, entrypoint=None, manifest=None, source=None):
    """Write a metadata-only fixture whose initializer must never execute."""
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "__init__.py").write_text(
        source or 'raise RuntimeError("discovery imported fixture")\n',
        encoding="utf-8",
    )
    if plugin_id is not None:
        data = {"id": plugin_id, "version": "1.0", "display_name": f"Tools:{plugin_id}"}
        if entrypoint is not None:
            data["entrypoints"] = {"cli": entrypoint}
        if manifest is not None:
            data.update(manifest)
        (directory / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    return directory


def test_shadowed_package_cannot_advertise_another_command(roots, caplog):
    first, second = roots
    chosen = _package(first, "same", plugin_id="first", entrypoint="first=fixture:cli")
    ignored = _package(second, "same", plugin_id="second", entrypoint="second=fixture:cli")
    records = list(cli_module._discover_plugin_metadata())
    assert [record["plugin_id"] for record in records] == ["first"]
    assert str(chosen) in caplog.text and str(ignored) in caplog.text


@pytest.mark.parametrize("first_kind", ["manifest", "legacy", "unnamed"])
def test_regular_parent_hides_later_descendants(roots, first_kind):
    first, second = roots
    options = {"plugin_id": "parent"} if first_kind == "manifest" else {}
    if first_kind == "legacy":
        options["source"] = 'name = "Tools:Legacy"\nraise RuntimeError("no import")\n'
    _package(first, "category", **options)
    _package(second, "category/tool", plugin_id="hidden", entrypoint="hidden=fixture:cli")
    assert not any(r["plugin_id"] == "hidden" for r in cli_module._discover_plugin_metadata())


def test_namespace_parents_merge_without_importing_initializers(roots):
    first, second = roots
    _package(first, "category/one", plugin_id="one", entrypoint="one=fixture:cli")
    _package(second, "category/two", plugin_id="two", entrypoint="two=fixture:cli")
    assert [r["plugin_id"] for r in cli_module._discover_plugin_metadata()] == ["one", "two"]


def test_later_regular_parent_wins_over_namespace_portion(roots):
    first, second = roots
    _package(first, "category/hidden", plugin_id="hidden", entrypoint="hidden=fixture:cli")
    _package(second, "category")
    _package(second, "category/chosen", plugin_id="chosen", entrypoint="chosen=fixture:cli")
    assert [r["plugin_id"] for r in cli_module._discover_plugin_metadata()] == ["chosen"]


def test_duplicate_manifest_ids_keep_first_owner(roots, caplog):
    first, second = roots
    chosen = _package(first, "one", plugin_id="same", entrypoint="one=fixture:cli")
    ignored = _package(second, "two", plugin_id="same", entrypoint="two=fixture:cli")
    assert [r["module_name"] for r in cli_module._discover_plugin_metadata()] == ["one"]
    assert str(chosen) in caplog.text and str(ignored) in caplog.text


@pytest.mark.parametrize(
    "invalid", [{"version": []}, {"version": None}, {"id": []}, {"requires": []}]
)
def test_invalid_manifest_cli_does_not_bypass_shared_validation(roots, invalid, caplog):
    first, _ = roots
    broken = _package(
        first, "broken", plugin_id="broken", entrypoint="broken=fixture:cli", manifest=invalid
    )
    _package(first, "healthy", plugin_id="healthy", entrypoint="healthy=fixture:cli")
    assert [r["plugin_id"] for r in cli_module._discover_plugin_metadata()] == ["healthy"]
    assert str(broken) in caplog.text


@pytest.mark.parametrize("entrypoints", [{}, {"cli": None}])
def test_valid_manifest_without_cli_suppresses_stale_legacy_command(roots, entrypoints):
    first, _ = roots
    _package(
        first,
        "one",
        plugin_id="same",
        manifest={"entrypoints": entrypoints},
        source='name = "Tools:Legacy"\ncli_entrypoint = "stale=fixture:cli"\n',
    )
    _package(first, "two", plugin_id="same", entrypoint="other=fixture:cli")
    records = list(cli_module._discover_plugin_metadata())
    assert len(records) == 1
    assert records[0]["cli_entrypoint"] is None


@pytest.fixture
def invoke_plugin(monkeypatch):
    """Execute a real command through the production lazy forwarding callback."""
    module = types.ModuleType("cli_robustness_fixture")
    monkeypatch.setitem(sys.modules, module.__name__, module)

    def invoke(target, args, **kwargs):
        module.command = target

        @click.group()
        def group():
            pass

        @group.command(
            "public",
            context_settings={
                "ignore_unknown_options": True,
                "allow_extra_args": True,
                "help_option_names": [],
            },
        )
        @click.pass_context
        def lazy(ctx):
            cli_module._forward_plugin_cli(
                ctx, module_path=module.__name__, attr_name="command", command_name="public"
            )

        return CliRunner().invoke(group, ["public", *args], **kwargs)

    return invoke


@pytest.mark.parametrize("status", [2, 7, 130])
def test_click_exit_status_is_preserved(invoke_plugin, status):
    @click.command()
    @click.pass_context
    def command(ctx, value):
        ctx.exit(status)

    # Provide a valid accepted argument so explicit callback exit, not parsing, is tested.
    command.params.append(click.Argument(["value"]))
    result = invoke_plugin(command, ["run"])
    assert result.exit_code == status, result.output
    assert "exited with status" not in result.output


def test_click_group_inherits_host_context_and_public_command_path(invoke_plugin):
    closed = []

    @click.group()
    def command():
        pass

    @command.command()
    @click.option("--value", default="unset")
    @click.pass_context
    def child(ctx, value):
        ctx.call_on_close(lambda: closed.append(value))
        click.echo(f"{ctx.obj['session']}|{ctx.command_path}|{value}")

    result = invoke_plugin(
        command,
        ["child"],
        obj={"session": "host-session"},
        default_map={"public": {"child": {"value": "inherited-default"}}},
    )
    assert result.exit_code == 0, repr(result.exception)
    assert result.output == "host-session|group public child|inherited-default\n"
    assert closed == ["inherited-default"]


@pytest.mark.parametrize("args", [[], ["--help"]])
def test_click_help_uses_full_public_path_without_importing_siblings(invoke_plugin, args):
    @click.command(name="private-implementation")
    def command():
        """Real plugin help."""

    result = invoke_plugin(command, args)
    assert result.exit_code == 0, result.output
    assert "Usage: group public" in result.output
    assert "Real plugin help." in result.output
    assert "private-implementation" not in result.output


def test_click_usage_error_retains_status_and_has_one_error(invoke_plugin):
    @click.command()
    @click.option("--count", type=int)
    def command(count):
        pass

    result = invoke_plugin(command, ["--count", "not-an-int"])
    assert result.exit_code == 2
    assert "Usage: group public" in result.output
    assert result.output.count("Error:") == 1
    assert "exited with status" not in result.output


def test_callback_integer_return_is_not_an_exit_status(invoke_plugin):
    @click.command()
    @click.argument("value")
    def command(value):
        return 19

    assert invoke_plugin(command, ["run"]).exit_code == 0


@pytest.mark.parametrize("args,status", [(["--status", "7"], 7), (["--bad"], 2), (["--help"], 0)])
def test_plain_argparse_callable_preserves_exit_and_restores_argv(invoke_plugin, args, status):
    import argparse

    old_argv = sys.argv
    old_values = list(sys.argv)

    def command():
        parser = argparse.ArgumentParser()
        parser.add_argument("--status", type=int, default=0)
        parsed = parser.parse_args()
        raise SystemExit(parsed.status)

    assert invoke_plugin(command, args).exit_code == status
    assert sys.argv == old_values
    # The previous contract restored values, not necessarily list identity.
    sys.argv = old_argv


def test_plain_callable_failure_restores_argv(invoke_plugin):
    before = list(sys.argv)

    def command():
        assert sys.argv == ["public", "argument"]
        raise RuntimeError("actual callable failure")

    result = invoke_plugin(command, ["argument"])
    assert isinstance(result.exception, RuntimeError)
    assert sys.argv == before


def test_duck_main_remains_supported(invoke_plugin):
    seen = []

    class Command:
        def main(self, **kwargs):
            seen.append(kwargs)
            raise SystemExit(9)

    result = invoke_plugin(Command(), ["--custom"])
    assert result.exit_code == 9
    assert seen == [{"args": ["--custom"], "prog_name": "public", "standalone_mode": True}]


def test_non_callable_target_has_actionable_failure(invoke_plugin):
    result = invoke_plugin(42, ["run"])
    assert result.exit_code == 1
    assert "not callable" in result.output


@pytest.mark.parametrize("contents", [b"{", b"[]", b"\xff"])
def test_invalid_manifest_keeps_explicit_legacy_fallback(roots, contents):
    first, _ = roots
    directory = _package(
        first, "legacy", source='name = "Tools:Legacy"\ncli_entrypoint = "legacy=fixture:cli"\n'
    )
    (directory / "manifest.json").write_bytes(contents)
    records = list(cli_module._discover_plugin_metadata())
    assert len(records) == 1
    assert records[0]["plugin_id"] is None
    assert records[0]["cli_entrypoint"] == "legacy=fixture:cli"


def test_hidden_descendants_are_excluded_not_the_user_root(roots):
    _, user = roots
    _package(user, "visible", plugin_id="visible", entrypoint="visible=fixture:cli")
    for name in (".hidden/tool", "__pycache__/tool", "{{cookie}}/tool"):
        _package(user, name, plugin_id="hidden", entrypoint="hidden=fixture:cli")
    assert [r["plugin_id"] for r in cli_module._discover_plugin_metadata()] == ["visible"]


def test_discovery_refreshes_stale_python_finder_cache(roots):
    import os
    from importlib.machinery import PathFinder

    first, _ = roots
    stat = first.stat()
    assert PathFinder.find_spec("new_cli_tool", [str(first)]) is None
    _package(first, "new_cli_tool", plugin_id="new_cli_tool", entrypoint="new=fixture:cli")
    os.utime(first, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    assert PathFinder.find_spec("new_cli_tool", [str(first)]) is None
    assert [r["plugin_id"] for r in cli_module._discover_plugin_metadata()] == ["new_cli_tool"]


def test_valid_manifest_selection_agrees_with_registry(roots):
    from chisurf.core.plugin.registry import PluginRegistry

    first, second = roots
    _package(first, "one", plugin_id="chosen", entrypoint="one=fixture:cli")
    _package(second, "duplicate", plugin_id="chosen", entrypoint="other=fixture:cli")
    _package(second, "one", plugin_id="shadowed", entrypoint="shadowed=fixture:cli")
    _package(second, "new", plugin_id="healthy", entrypoint="new=fixture:cli")
    registry = PluginRegistry()
    registry.discover(list(roots))
    records = list(cli_module._discover_plugin_metadata())
    assert {r["plugin_id"] for r in records} == {m.id for m in registry.all_manifests}


def test_fresh_top_level_help_is_plugin_and_toolkit_import_free():
    import os
    import subprocess

    script = """
import sys
from chisurf.core.cli import cli
from click.testing import CliRunner
result = CliRunner().invoke(cli, ["--help"])
assert result.exit_code == 0, result.output
assert len(cli.commands) > 20
plugins = [name for name in sys.modules if name == "chisurf.plugins" or name.startswith("chisurf.plugins.")]
assert not plugins, plugins
heavy = [name for name in sys.modules if name.split(".")[0] in {"jsonschema", "qtpy", "PyQt5", "PyQt6", "PySide6"}]
assert not heavy, heavy
print("HELP_IMPORT_FREE_OK")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "HELP_IMPORT_FREE_OK" in result.stdout
