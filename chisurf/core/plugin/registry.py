from __future__ import annotations

import importlib
import logging
import pathlib
from contextlib import nullcontext
from typing import Any, Protocol

from chisurf.core.plugin.dependencies import (
    DependencyReport,
    log_problems,
    ordered_manifests,
)
from chisurf.core.plugin.discovery import PackageResolver
from chisurf.core.plugin.manifest import (
    PluginManifest,
    load_manifest,
    validate_manifest,
)

_log = logging.getLogger(__name__)


class _EntrypointLoader(Protocol):
    """Protocol for objects that can load a plugin entrypoint."""

    def load(self, entrypoint: str) -> Any: ...


class _DefaultLoader:
    """Default entrypoint loader using ``importlib``."""

    def load(self, entrypoint: str) -> Any:
        if ":" in entrypoint:
            module_path, attr_name = entrypoint.rsplit(":", 1)
            module = importlib.import_module(module_path)
            return getattr(module, attr_name)
        return importlib.import_module(entrypoint)


class PluginRegistry:
    """Discovers and manages plugins from ``manifest.json`` files.

    Supports both the new ``manifest.json`` format and the legacy AST-based
    metadata parsing from ``__init__.py`` as fallback.

    """

    def __init__(self, loader: _EntrypointLoader | None = None):
        self._loader = loader or _DefaultLoader()
        self._manifests: dict[str, PluginManifest] = {}
        self._legacy_plugins: list[dict[str, Any]] = []
        self._dependency_report: DependencyReport | None = None
        self._gui_windows: dict[int, Any] = {}

    # ── discovery ──────────────────────────────────────────────────

    def discover(
        self,
        search_paths: list[pathlib.Path] | None = None,
    ) -> list[PluginManifest]:
        """Walk plugin directories and load manifests.

        Parameters
        ----------
        search_paths : list of pathlib.Path, optional
            Directories to search. Defaults to ``chisurf.plugins.__path__``
            and ``~/.chisurf/plugins/``.

        Returns
        -------
        list of PluginManifest
            All successfully loaded manifests (deduplicated by directory).

        """
        if search_paths is None:
            search_paths = self._default_search_paths()

        importlib.invalidate_caches()
        packages = PackageResolver(search_paths)
        manifests: list[PluginManifest] = []
        legacy_plugins: list[dict[str, Any]] = []
        seen_dirs: set[pathlib.Path] = set()
        seen_ids: dict[str, pathlib.Path] = {}
        seen_modules: dict[tuple[str, ...], pathlib.Path] = {}

        for base_path in search_paths:
            if not base_path.exists():
                continue
            for init_py_path in sorted(base_path.rglob("__init__.py")):
                plugin_dir = init_py_path.parent
                if any(
                    part.startswith(".") or part == "__pycache__" or "{{" in part
                    for part in plugin_dir.relative_to(base_path).parts
                ):
                    continue
                resolved = plugin_dir.resolve()
                if resolved in seen_dirs:
                    continue
                seen_dirs.add(resolved)

                # Import identity exists even when metadata is absent or legacy.
                module_parts = plugin_dir.relative_to(base_path).parts
                if module_parts:
                    preferred = packages.preferred_directory(module_parts)
                    if preferred != resolved:
                        _log.warning(
                            "Shadowed plugin module %r at %s ignored; Python selects %s",
                            ".".join(module_parts), plugin_dir,
                            preferred or packages.parent_locations(module_parts),
                        )
                        continue
                if module_parts in seen_modules:
                    _log.warning(
                        "Duplicate plugin module %r at %s ignored; using %s",
                        ".".join(module_parts), plugin_dir, seen_modules[module_parts],
                    )
                    continue
                seen_modules[module_parts] = plugin_dir

                # Prefer manifest.json over legacy metadata
                manifest_path = plugin_dir / "manifest.json"
                manifest = load_manifest(manifest_path)

                if manifest is not None:
                    if manifest.id in seen_ids:
                        _log.warning(
                            "Duplicate plugin id %r at %s ignored; using %s",
                            manifest.id,
                            plugin_dir,
                            seen_ids[manifest.id],
                        )
                        continue
                    seen_ids[manifest.id] = plugin_dir
                    manifests.append(manifest)
                else:
                    if manifest_path.exists():
                        try:
                            import json

                            data = json.loads(manifest_path.read_text())
                            errors = validate_manifest(data)
                            if errors:
                                _log.warning(
                                    "Manifest %s has validation errors: %s",
                                    manifest_path,
                                    errors,
                                )
                        except Exception:
                            _log.warning(
                                "Manifest %s is unparseable; falling back to legacy",
                                manifest_path,
                            )
                    # Legacy fallback: parse __init__.py AST
                    legacy = _read_legacy_metadata(plugin_dir)
                    if legacy is not None:
                        legacy_plugins.append(legacy)

        # Ordering happens once, here: ``_manifests`` is what register_services,
        # register_cli, register_gui and the operation index all iterate, so
        # sorting the dict is what gives every one of them dependency order
        # instead of the filesystem order rglob happened to produce.
        manifests, report = ordered_manifests(manifests)
        log_problems(report)
        self._dependency_report = report
        self._manifests = {m.id: m for m in manifests}
        self._legacy_plugins = legacy_plugins
        return manifests

    @property
    def dependency_report(self) -> DependencyReport | None:
        """The resolution produced by the last :meth:`discover` call."""
        return self._dependency_report

    def get_manifest(self, plugin_id: str) -> PluginManifest | None:
        """Return the manifest for a given plugin ID."""
        return self._manifests.get(plugin_id)

    @property
    def all_manifests(self) -> list[PluginManifest]:
        """Return all registered manifests."""
        return list(self._manifests.values())

    # ── registration ───────────────────────────────────────────────

    def register_services(
        self,
        dispatcher: Any,
        exclude_entrypoints: set[str] | None = None,
    ) -> None:
        """Call each plugin's ``services`` entrypoint.

        Parameters
        ----------
        dispatcher : ServiceDispatcher
            The server's service dispatcher.
        exclude_entrypoints : set of str, optional
            Entrypoints already registered through central startup config.

        """
        # ``_manifests`` is in dependency order (see discover), so a plugin whose
        # services build on a sibling's finds them already registered. An
        # entrypoint in ``excluded`` is owned by the central startup config and
        # counts as satisfied for its dependants -- it is registered there, not
        # missing.
        excluded = exclude_entrypoints or set()
        for manifest in self._manifests.values():
            entrypoint = manifest.entrypoints.services
            if not entrypoint:
                continue
            if entrypoint in excluded:
                continue
            try:
                register_fn = self._loader.load(entrypoint)
                transaction = getattr(dispatcher, "registration_transaction", None)
                context = transaction(manifest.id) if callable(transaction) else nullcontext()
                with context:
                    register_fn(dispatcher)
                _log.info("Registered services for plugin %r", manifest.id)
            except ModuleNotFoundError as exc:
                # A plugin whose third-party dependency is not installed is
                # *unavailable*, not broken, and a stack trace at every start-up
                # says the opposite. The user cannot act on the traceback; they
                # can act on the module name.
                _log.warning(
                    "Plugin %r has no services: it needs %r, which is not "
                    "installed in this environment.",
                    manifest.id,
                    exc.name or str(exc),
                )
            except Exception:
                _log.exception(
                    "Failed to register services for plugin %r (%s)",
                    manifest.id,
                    entrypoint,
                )

    def register_cli(self, main_group: Any) -> None:
        """Attach each plugin's CLI command to a Click group.

        .. note::
           This is **not** how ``csc`` registers plugin commands. Attaching the
           command objects here imports every plugin CLI module — Qt, tttrlib and
           all — which ``csc --help`` cannot afford. Production registration lives
           in :mod:`chisurf.core.cli`, which reads the same manifest
           ``entrypoints.cli`` during its filesystem scan and imports a plugin only
           when its command is actually invoked. Use this method from in-process
           callers that have already paid the import cost.

        Parameters
        ----------
        main_group : click.Group
            The main CLI group.

        """
        for manifest in self._manifests.values():
            entrypoint = manifest.entrypoints.cli
            if not entrypoint:
                continue
            try:
                # The manifest owns the public name, not the Click object's
                # implementation name. Match the production lazy CLI path.
                alias, separator, target = entrypoint.partition("=")
                cmd_name = alias.strip() if separator else manifest.id.replace("_", "-")
                target = target.strip() if separator else entrypoint.strip()
                if not cmd_name or not target:
                    raise ValueError("CLI command alias and entrypoint must not be empty")
                commands = getattr(main_group, "commands", {})
                if isinstance(commands, dict) and cmd_name in commands:
                    _log.warning(
                        "Plugin %r CLI %r ignored; command is already registered",
                        manifest.id, cmd_name,
                    )
                    continue
                cli_obj = self._loader.load(target)
                main_group.add_command(cli_obj, name=cmd_name)
                _log.info("Registered CLI for plugin %r as %r", manifest.id, cmd_name)
            except Exception:
                _log.exception(
                    "Failed to register CLI for plugin %r (%s)",
                    manifest.id,
                    entrypoint,
                )

    def register_gui(self, menu: Any, context: Any = None) -> None:
        """Attach lazy plugin GUI actions without importing plugin code.

        The selected Qt/emtk factory is resolved only when an action is triggered,
        so a missing legacy Qt dependency cannot hide a working native factory.

        Parameters
        ----------
        menu : QMenu
            The plugins menu.

        """
        for manifest in self._manifests.values():
            if not (manifest.entrypoints.gui or manifest.entrypoints.emtk or manifest.entrypoints.action) or manifest.menu_hidden:
                continue
            try:
                action = menu.addAction(manifest.display_name or manifest.id)
                if manifest.entrypoints.action is not None:
                    declaration = manifest.entrypoints.action
                    available = not declaration.requires_main_window or getattr(context, "main_window", None) is not None
                    action.setToolTip(declaration.description if available else declaration.description + " " + _action_unavailable())
                    action.setEnabled(available)
                    action.triggered.connect(
                        lambda checked=False, manifest=manifest: execute_plugin_action(
                            manifest, context, loader=self._loader,
                        )
                    )
                else:
                    action.triggered.connect(
                        lambda checked=False, manifest=manifest: _show_plugin(
                            None, manifest, loader=self._loader, windows=self._gui_windows,
                        )
                    )
                _log.info("Registered GUI for plugin %r", manifest.id)
            except Exception:
                _log.exception("Failed to register GUI for plugin %r", manifest.id)

    # ── internals ──────────────────────────────────────────────────

    @staticmethod
    def _default_search_paths() -> list[pathlib.Path]:
        from chisurf.plugins import __path__ as plugin_paths
        from chisurf.plugins import user_plugins_dir

        paths = [pathlib.Path(p) for p in plugin_paths]
        paths.append(user_plugins_dir)
        return paths


def _read_legacy_metadata(plugin_dir: pathlib.Path) -> dict[str, Any] | None:
    """Read legacy plugin metadata from ``__init__.py`` AST."""
    try:
        from chisurf.plugins import _read_plugin_metadata  # type: ignore

        init_py = plugin_dir / "__init__.py"
        name, description, cli_entrypoint, cli_only, menu_hidden = _read_plugin_metadata(init_py)
        if not name:
            return None
        return {
            "id": plugin_dir.name,
            "display_name": name,
            "description": description,
            "cli_entrypoint": cli_entrypoint,
            "cli_only": cli_only,
            "menu_hidden": menu_hidden,
            "package_dir": plugin_dir,
        }
    except Exception:
        return None


def _action_unavailable() -> str:
    """Explain why a contextual action cannot run in a standalone invocation."""
    from chisurf.core.support.i18n import tr

    return tr("This action requires an open ChiSurf main window.")


def execute_plugin_action(manifest: PluginManifest, context: Any = None, *, loader: _EntrypointLoader | None = None) -> dict[str, Any]:
    """Invoke one declared action through the existing non-replayable action dispatcher."""
    from chisurf.core.api.context import PluginContext

    declaration = manifest.entrypoints.action
    if declaration is None:
        raise ValueError(f"Plugin {manifest.id!r} has no action entrypoint")
    if context is None:
        context = PluginContext()
    if not isinstance(context, PluginContext):
        return {"ok": False, "available": False, "error": "Plugin actions require PluginContext."}
    if declaration.requires_main_window and context.main_window is None:
        return {"ok": False, "available": False, "error": _action_unavailable()}
    from chisurf.core.actions import ActionDispatcher, ActionRegistry, ActionSpec

    action_registry = ActionRegistry()
    name = "plugin." + manifest.id
    try:
        target = (loader or _DefaultLoader()).load(declaration.target)
        if not callable(target):
            raise TypeError(f"Plugin action {declaration.target!r} is not callable")
        action_registry.register(ActionSpec(
            name=name, schema={"context": PluginContext}, replayable=False,
            side_effect_class="ui", handler=target,
        ))
        result = ActionDispatcher(action_registry, history_provider=lambda: None).execute(
            name, payload={"context": context}, summary=declaration.description,
        )
        if not isinstance(result, dict) or type(result.get("ok")) is not bool:
            raise TypeError("Plugin actions must return a result dictionary with boolean 'ok'")
        return result
    except Exception as error:
        _log.exception("Plugin action %r failed", manifest.id)
        return {"ok": False, "available": True, "error": f"Plugin action {manifest.id!r} failed: {error}"}


def select_gui_entrypoint(manifest: PluginManifest, mode: str = "auto") -> tuple[str, str] | None:
    """Choose ``("emtk", spec)`` or ``("qt", spec)`` for a plugin launch."""
    mode = str(mode or "auto").lower()
    native = getattr(manifest.entrypoints, "emtk", None)
    legacy = getattr(manifest.entrypoints, "gui", None)
    if mode == "emtk":
        return ("emtk", native) if native else (("qt", legacy) if legacy else None)
    if mode == "qt":
        return ("qt", legacy) if legacy else (("emtk", native) if native else None)
    # Auto: a plugin whose emtk port is still a preview keeps its Qt tool (see emtk_readiness).
    if native and legacy:
        from chisurf.core.plugin.emtk_readiness import is_preview

        if is_preview(getattr(manifest, "id", "")):
            return ("qt", legacy)
    return ("emtk", native) if native else (("qt", legacy) if legacy else None)


def build_plugin_widget(
    manifest: PluginManifest,
    widget_class: Any = None,
    *,
    loader: _EntrypointLoader | None = None,
) -> Any:
    """Build a plugin's window, honouring the EMTK/Qt runtime selection.

    Every launch path — the registry menus, the ribbon, the macro launcher —
    goes through here so a plugin with a native factory opens as one no matter
    which entry opened it. EMTK apps are wrapped in a ``ControlHost``; Qt
    widgets come from *widget_class* (imported from the ``gui`` entrypoint when
    not given).
    """
    mode = "auto"
    try:
        import chisurf as cs
        mode = str(cs.core.settings.cs_settings.get("plugins", {}).get("gui_mode", "auto")).lower()
    except Exception:
        pass
    selected = select_gui_entrypoint(manifest, mode)
    if selected is None:
        raise ValueError(f"Plugin {manifest.id!r} has no GUI entrypoint")
    kind, spec = selected
    entrypoint_loader = loader or _DefaultLoader()
    if kind == "emtk":
        factory = entrypoint_loader.load(spec)
        from emtk.qt_host import ControlHost
        widget = ControlHost(factory())
        widget.is_emtk_native_host = True
        widget.setWindowTitle(manifest.display_name or manifest.id)
        return widget
    if widget_class is None:
        widget_class = entrypoint_loader.load(spec)
    return widget_class()


def _show_plugin(
    widget_class: Any,
    manifest: PluginManifest,
    *,
    loader: _EntrypointLoader | None = None,
    windows: dict[int, Any] | None = None,
) -> Any | None:
    """Open a plugin and retain its window until an accepted close destroys it."""
    widget = None
    key = None
    try:
        widget = build_plugin_widget(manifest, widget_class, loader=loader)
        apply_manifest_statefulness(widget, manifest)
        if windows is not None:
            from qtpy.QtCore import Qt

            widget.setAttribute(Qt.WA_DeleteOnClose)
            key = id(widget)
            windows[key] = widget
            widget.destroyed.connect(
                lambda _object=None, key=key: windows.pop(key, None)
            )
        widget.show()
        widget.raise_()
        widget.activateWindow()
        if hasattr(widget, "setFocus"):
            widget.setFocus()
        return widget
    except Exception:
        if windows is not None and key is not None:
            windows.pop(key, None)
        if widget is not None:
            try:
                widget.deleteLater()
            except Exception:
                _log.debug("Failed to dispose plugin %r after launch failure", manifest.id, exc_info=True)
        _log.exception("Failed to show plugin %r", manifest.id)
        return None


def resolve_plugin_statefulness(
    manifest: PluginManifest,
    plugin_settings: dict[str, Any] | None = None,
) -> bool:
    """Resolve whether a plugin should persist window state."""
    if plugin_settings is None:
        try:
            import chisurf as cs

            plugin_settings = cs.core.settings.cs_settings.get("plugins", {})
        except Exception:
            plugin_settings = {}
    if not isinstance(plugin_settings, dict):
        plugin_settings = {}

    statefulness_settings = plugin_settings.get("statefulness", {})
    if not isinstance(statefulness_settings, dict):
        statefulness_settings = {}

    overrides = statefulness_settings.get("per_plugin", {})
    if not isinstance(overrides, dict):
        overrides = {}

    for key in (manifest.id, manifest.state_namespace, manifest.display_name):
        if key not in overrides:
            continue
        override = overrides[key]
        if isinstance(override, str) and override.lower() == "plugin_default":
            continue
        return bool(override)

    mode = str(statefulness_settings.get("mode", "plugin_default")).lower()
    if mode in {"enabled", "force_enabled", "true"}:
        return True
    if mode in {"disabled", "force_disabled", "false"}:
        return False
    return manifest.statefulness.enabled


def apply_manifest_statefulness(widget: Any, manifest: PluginManifest) -> None:
    """Apply manifest-declared window-state persistence to a widget."""
    _apply_manifest_statefulness(widget, manifest)


def _apply_manifest_statefulness(widget: Any, manifest: PluginManifest) -> None:
    """Apply window-state persistence declared in a plugin manifest."""
    if not resolve_plugin_statefulness(manifest):
        return
    if not manifest.statefulness.window.enabled:
        return
    if getattr(widget, "_manifest_statefulness_applied", False):
        return
    if getattr(widget, "_persist_plugin_name", None):
        return

    settings_key = (
        manifest.statefulness.window.settings_key or manifest.state_namespace or manifest.id
    )

    try:
        from PyQt5.QtCore import Qt as _Qt

        widget.setAttribute(_Qt.WA_DeleteOnClose)
    except Exception:
        pass

    try:
        from chisurf.gui.misc_helpers import (
            restore_plugin_window_state,
            save_plugin_window_state,
        )
    except Exception:
        _log.debug(
            "Failed to import plugin window-state helpers for %r",
            manifest.id,
            exc_info=True,
        )
        return

    orig_show = getattr(widget, "showEvent", None)
    orig_close = getattr(widget, "closeEvent", None)

    def _restore_state(event: Any) -> None:
        if not getattr(widget, "_manifest_state_restored", False):
            setattr(widget, "_manifest_state_restored", True)
            try:
                restore_plugin_window_state(widget, settings_key)
            except Exception:
                _log.debug(
                    "Failed to restore window state for plugin %r",
                    manifest.id,
                    exc_info=True,
                )
        if orig_show is not None:
            orig_show(event)
        elif hasattr(event, "accept"):
            event.accept()

    def _save_state(event: Any) -> None:
        try:
            save_plugin_window_state(widget, settings_key)
        except Exception:
            _log.debug(
                "Failed to save window state for plugin %r",
                manifest.id,
                exc_info=True,
            )
        if orig_close is not None:
            orig_close(event)
        elif hasattr(event, "accept"):
            event.accept()

    setattr(widget, "_manifest_statefulness_applied", True)
    setattr(widget, "_manifest_statefulness_key", settings_key)
    setattr(widget, "_manifest_state_restored", False)
    widget.showEvent = _restore_state
    widget.closeEvent = _save_state
