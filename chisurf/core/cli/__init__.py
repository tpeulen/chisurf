#!/usr/bin/env python

from __future__ import annotations

import ast
import importlib
import logging
import pathlib
import sys
from collections.abc import Iterable
from typing import Dict, Optional, Tuple

import click

from chisurf.core.cli.support import DidYouMeanGroup


class PluginCLI(DidYouMeanGroup):
    """Click group that registers plugin CLIs before parsing arguments.

    Inherits the *did you mean* suggestions, so a mistyped plugin subcommand
    (``csc burst-backgroud``) lists the closest registered names.
    """

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        """Register plugin CLIs before Click resolves subcommands."""
        _register_plugin_clis()
        return super().parse_args(ctx, args)


@click.group(cls=PluginCLI, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(package_name="chisurf", prog_name="csc")
def cli() -> None:
    """Command-line interface for chisurf tools and plugins.

    Use this command as a single entry point to run the CLIs provided by
    installed chisurf plugins. Each subcommand corresponds to one tool and
    comes with its own help and options.

    \b
    Examples:
      csc lltf --help
      csc burst-background --help
      csc count-rate analyze --help
    """
    # Ensure plugin-provided CLIs are registered the first time the
    # top-level CLI group is invoked, without doing any plugin discovery
    # at import time.
    _register_plugin_clis()


_LOG = logging.getLogger(__name__)

_PLUGINS_REGISTERED = False


def _parse_cli_entrypoint(
    entrypoint: str, default_alias: str | None = None
) -> tuple[str, str, str]:
    """Parse strings of the form ``alias=module:attr``.

    A few manifests omit the ``alias=`` part and give only ``module:attr``; with a
    *default_alias* (the plugin id) those still register, under that name, instead
    of being dropped silently.
    """
    spec = (entrypoint or "").strip()
    if not spec:
        raise ValueError("Entry point must be in the form 'alias=module[:attr]'")
    if "=" in spec:
        alias, target = spec.split("=", 1)
        alias = alias.strip()
    elif default_alias:
        alias, target = str(default_alias).strip(), spec
    else:
        raise ValueError("Entry point must be in the form 'alias=module[:attr]'")
    if not alias:
        raise ValueError("Alias (command name) is empty")
    module_path, _, attr = target.partition(":")
    module_path = module_path.strip()
    attr = attr.strip() or "cli"
    if not module_path:
        raise ValueError("Module path is empty")
    return alias, module_path, attr


def _forward_plugin_cli(
    ctx: click.Context,
    *,
    module_path: str,
    attr_name: str,
    friendly_name: str | None = None,
    command_name: str | None = None,
) -> None:
    """Import the plugin CLI object and forward the current args."""
    try:
        module = importlib.import_module(module_path)
        target = getattr(module, attr_name)
    except Exception as exc:
        raise click.ClickException(
            f"Failed to import plugin CLI '{friendly_name or module_path}:{attr_name}': {exc}"
        )

    argv = list(ctx.args)
    if not argv:
        argv = ["--help"]

    if isinstance(target, click.Command):
        # Replace the lazy proxy, not its parent: this preserves shared context,
        # defaults and full command paths without duplicating the public alias.
        # invoke propagates explicit Exit separately from callback return values.
        with target.make_context(ctx.info_name, argv, parent=ctx.parent) as plugin_ctx:
            target.invoke(plugin_ctx)
        return

    runner = getattr(target, "main", None)
    if callable(runner):
        prog = command_name or (friendly_name or module_path).split(".")[-1]
        runner(args=argv, prog_name=prog, standalone_mode=True)
        return

    # Fall back to calling the object directly if it behaves like a callable CLI.
    if callable(target):
        old_argv = list(sys.argv)
        try:
            # Simulate a classic ``if __name__ == '__main__'`` style CLI by
            # injecting our arguments into ``sys.argv``. This allows us to
            # wrap argparse-based entry points such as
            # ``chisurf.plugins.tttr.microtime_histogram.__main__.main``.
            prog = command_name or (friendly_name or module_path).split(".")[-1]
            sys.argv = [prog, *argv]
            target()  # type: ignore[call-arg]
        finally:
            sys.argv = old_argv
        return

    raise click.ClickException(f"Plugin CLI target '{module_path}:{attr_name}' is not callable")


def _read_plugin_metadata(init_py: pathlib.Path) -> tuple[str | None, str | None, str | None]:
    if not init_py.exists():
        return None, None, None
    # Parse the raw bytes so the PEP 263 coding cookie decides the encoding, the
    # way the interpreter does on import; decoding as UTF-8 here dropped any
    # plugin declaring another source encoding from ``csc`` without a word.
    try:
        source = init_py.read_bytes()
    except Exception:
        return None, None, None
    try:
        tree = ast.parse(source, filename=str(init_py))
    except Exception:
        return None, None, None
    description = ast.get_docstring(tree) or "No description available."
    plugin_name = None
    cli_entrypoint = None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in getattr(node, "targets", []):
            if not isinstance(target, ast.Name):
                continue
            value = node.value
            # A string literal is an ``ast.Constant``; the ``ast.Str`` alias has
            # not been produced since 3.8 and is scheduled for removal.
            if not (isinstance(value, ast.Constant) and isinstance(value.value, str)):
                continue
            if target.id == "name":
                plugin_name = value.value
            elif target.id == "cli_entrypoint":
                cli_entrypoint = value.value.strip()
    return plugin_name, description, cli_entrypoint


def _read_manifest_cli(plugin_dir: pathlib.Path) -> tuple[str | None, str | None, str | None]:
    """Return ``(cli_entrypoint, plugin_id, display_name)`` from a plugin manifest.

    ``manifest.json`` is the plugin contract, so its ``entrypoints.cli`` and
    ``display_name`` are the authoritative declarations; the module-level
    ``cli_entrypoint`` and ``name`` assignments are the older, AST-scanned
    convention kept as a fallback for plugins that ship no manifest. Reading the
    manifest is a plain filesystem read — no plugin package is imported.
    """
    from chisurf.core.plugin.manifest import load_manifest

    manifest = load_manifest(plugin_dir / "manifest.json")
    if manifest is None:
        return None, None, None
    entry = manifest.entrypoints.cli
    return (
        entry.strip() if entry and entry.strip() else None,
        manifest.id,
        manifest.display_name or None,
    )


def _discover_plugin_metadata() -> Iterable[dict[str, object]]:
    """Yield metadata for built-in and user plugins **without importing packages**.

    This function performs a pure filesystem + AST scan over the built-in
    plugin tree (``chisurf/plugins``) and the user plugin directory
    (``~/.chisurf/plugins``). It never imports ``chisurf.plugins`` or any
    individual plugin modules, so CLI startup does not trigger any GUI
    initialization or heavy dependencies.
    """
    built_in_root = pathlib.Path(__file__).resolve().parents[2] / "plugins"
    user_root = pathlib.Path.home() / ".chisurf" / "plugins"

    search_roots = [
        ("built-in", built_in_root),
        ("user", user_root),
    ]

    from chisurf.core.plugin.discovery import PackageResolver

    importlib.invalidate_caches()
    packages = PackageResolver([root for _, root in search_roots])
    seen: set[pathlib.Path] = set()
    seen_ids: dict[str, pathlib.Path] = {}

    for source, root in search_roots:
        if not root.exists():
            continue
        try:
            root_resolved = root.resolve()
        except Exception:
            root_resolved = root

        # Each __init__.py below the root corresponds to a candidate plugin
        # package under the chisurf.plugins.* namespace.
        #
        # Sorted, because ``_register_plugin_clis`` resolves a duplicate command
        # name by keeping the first one it sees. Bare ``rglob`` yields in
        # ``os.scandir`` order, which made that tiebreak depend on the filesystem
        # -- the same two plugins could win on one machine and lose on another.
        for init_py in sorted(root_resolved.rglob("__init__.py")):
            try:
                rel_dir = init_py.parent.relative_to(root_resolved)
            except Exception:
                # Outside of the root we care about.
                continue

            # Skip template/scaffold trees (cookiecutter), caches and hidden dirs —
            # they are not importable module paths.
            if any(
                part.startswith(".") or part == "__pycache__" or "{{" in part
                for part in rel_dir.parts
            ):
                continue

            # Skip the root package itself (e.g. chisurf.plugins).
            if str(rel_dir) == ".":
                continue

            parts = rel_dir.parts
            module_name = ".".join(parts)
            module_path = f"chisurf.plugins.{module_name}"

            resolved = init_py.parent.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            preferred = packages.preferred_directory(parts)
            if preferred != resolved:
                _LOG.warning(
                    "Shadowed plugin module %r at %s ignored; Python selects %s",
                    module_name,
                    init_py.parent,
                    preferred or packages.parent_locations(parts),
                )
                continue

            plugin_name, description, cli_entrypoint = _read_plugin_metadata(init_py)
            manifest_cli, plugin_id, display_name = _read_manifest_cli(init_py.parent)
            if plugin_id:
                if plugin_id in seen_ids:
                    _LOG.warning(
                        "Duplicate plugin id %r at %s ignored; using %s",
                        plugin_id,
                        init_py.parent,
                        seen_ids[plugin_id],
                    )
                    continue
                seen_ids[plugin_id] = init_py.parent
            if plugin_id:
                if cli_entrypoint and cli_entrypoint != manifest_cli:
                    _LOG.warning(
                        "Plugin '%s' declares two different CLI entry points "
                        "(manifest %r, module %r); using the manifest.",
                        module_path,
                        manifest_cli,
                        cli_entrypoint,
                    )
                cli_entrypoint = manifest_cli
            # The manifest is the contract for the display name too, exactly as it
            # is for the entry point above and as GUI discovery already reads it
            # (``chisurf.plugins._read_manifest_metadata``). The module-level
            # ``name`` literal is the older convention and only fills in for a
            # plugin that ships no manifest.
            plugin_name = display_name or plugin_name

            # For CLI purposes we only care about packages that either
            # advertise a human-readable plugin name or explicitly opt into
            # the CLI (manifest ``entrypoints.cli`` or a module-level
            # ``cli_entrypoint``). Plain namespace packages are skipped
            # entirely so they are never touched during CLI startup.
            if not plugin_name and not cli_entrypoint:
                continue

            yield {
                "module_path": module_path,
                "module_name": parts[-1],
                "package_dir": init_py.parent,
                "source": source,
                "plugin_name": plugin_name,
                "description": description,
                "cli_entrypoint": cli_entrypoint,
                "plugin_id": plugin_id,
            }


def _register_plugin_clis() -> None:
    """Discover plugin-provided CLI entry points and attach them to the main group.

    This function is idempotent and safe to call multiple times.
    """
    global _PLUGINS_REGISTERED

    if _PLUGINS_REGISTERED:
        return

    try:
        plugins = list(_discover_plugin_metadata())
    except Exception as exc:  # pragma: no cover - defensive
        _LOG.warning("Unable to discover plugins for CLI registration: %s", exc)
        return

    registered_specs = []  # for logging

    for metadata in plugins:
        entry_spec = metadata.get("cli_entrypoint")
        if not entry_spec:
            continue
        try:
            default_alias = str(metadata.get("plugin_id") or metadata.get("module_name") or "")
            command_name, module_path, attr_name = _parse_cli_entrypoint(
                entry_spec, default_alias.replace("_", "-") or None
            )
        except ValueError as exc:
            _LOG.warning(
                "Skipping CLI entrypoint for plugin '%s': %s",
                metadata.get("module_path"),
                exc,
            )
            continue

        if command_name in cli.commands:
            _LOG.debug(
                "Skipping CLI entrypoint '%s' from plugin '%s' (command already defined)",
                command_name,
                metadata.get("module_path"),
            )
            continue

        # Derive a short help text from the plugin's docstring without
        # importing the plugin. We use the first non-empty line of the
        # description parsed from ``__init__.py``; if that is missing, fall
        # back to the human-readable plugin name or the module name.
        raw_desc = (metadata.get("description") or "").strip()
        if raw_desc:
            summary_line = raw_desc.splitlines()[0].strip()
        else:
            summary_line = ""

        help_text = summary_line or str(
            metadata.get("plugin_name") or metadata.get("module_name") or command_name
        )

        def _callback(
            ctx: click.Context,
            _command_name: str = command_name,
            _module_path: str = module_path,
            _attr_name: str = attr_name,
            _plugin_label: str | None = metadata.get("plugin_name"),
        ) -> None:
            _forward_plugin_cli(
                ctx,
                module_path=_module_path,
                attr_name=_attr_name,
                friendly_name=_plugin_label or _module_path,
                command_name=_command_name,
            )

        command = click.Command(
            name=command_name,
            callback=click.pass_context(_callback),
            context_settings={
                "ignore_unknown_options": True,
                "allow_extra_args": True,
                "help_option_names": [],
            },
            help=help_text,
        )
        cli.add_command(command)

        # Only record the public command alias for logging, not the full
        # module path, to keep the startup message compact.
        registered_specs.append(command_name)

    _PLUGINS_REGISTERED = True

    if registered_specs:
        _LOG.debug("Registered plugin CLIs: %s", ", ".join(registered_specs))


def _log_preloaded_plugin_modules() -> None:
    """Report any plugin modules that were already imported during CLI startup."""
    preloaded = sorted(
        name for name in sys.modules if name.startswith("chisurf.plugins.") and name.count(".") >= 2
    )
    if preloaded:
        _LOG.info(
            "Plugin modules already imported during chisurf.core.cli initialization: %s",
            ", ".join(preloaded),
        )


def main(argv: list[str] | None = None) -> int:
    """Entry-point compatible wrapper.

    This allows calling chisurf.core.cli:main as well as chisurf.core.cli:cli.
    """
    if argv is None:
        argv = sys.argv[1:]

    # When invoked via python -m chisurf.core.cli or the installed console
    # script, register plugin CLIs and log any preloaded plugin modules
    # before delegating to Click's main dispatcher.
    _register_plugin_clis()
    _log_preloaded_plugin_modules()

    try:
        cli.main(args=argv, standalone_mode=True)
    except SystemExit as exc:  # normal click exit path
        return exc.code
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
