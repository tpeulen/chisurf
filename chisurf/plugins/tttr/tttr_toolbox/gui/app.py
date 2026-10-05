"""TTTR Tools: the photon-level TTTR tools in one native hub.

The rail, header, Back / Next, help, tour and input routing are the shared
:class:`chisurf.emtk.tool_hub.ToolHubApp`. This module adds the panel list
(``panels.json``, which the legacy Qt shell reads too) and resolves each panel's
native app from its plugin's manifest at the moment it is opened.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

from chisurf.emtk.tool_hub import HEADER, PLUGINS, ToolHubApp

__all__ = ["HEADER", "TttrToolboxApp", "load_panels", "make_app", "manifest_path", "resolve_factory"]

RESOURCES = Path(__file__).parent


def load_panels():
    """The panel list declared in ``panels.json``."""
    return json.loads((RESOURCES / "panels.json").read_text(encoding="utf-8"))["panels"]


def plugin_dir(panel) -> str:
    """The plugin folder (relative to ``chisurf/plugins``) a panel's Qt entrypoint lives in."""
    module = panel["entrypoint"].split(":", 1)[0].split(".gui.", 1)[0]
    return "/".join(module.split(".")[2:])


def manifest_path(panel):
    """The manifest of the plugin behind *panel*, found without importing its Qt GUI."""
    return PLUGINS / plugin_dir(panel) / "manifest.json"


def resolve_factory(panel):
    """``(factory, route)`` of a panel's native app, read from its manifest at use time."""
    data = json.loads(manifest_path(panel).read_text(encoding="utf-8"))
    spec = data.get("entrypoints", {}).get("emtk")
    if not spec:
        return None, ""
    module, attribute = spec.split(":", 1)
    return getattr(importlib.import_module(module), attribute), spec


def _with_plugin(panel):
    """A panel that also names its plugin folder, so the hub reads its maturity flags and help."""
    if panel.get("separator") or "entrypoint" not in panel:
        return dict(panel)
    return {**panel, "plugin": panel.get("plugin") or plugin_dir(panel)}


class TttrToolboxApp(ToolHubApp):
    """TTTR Tools on the shared native hub."""

    def __init__(self, panels=None, resolver=None):
        super().__init__(
            "TTTR Tools",
            [_with_plugin(p) for p in (load_panels() if panels is None else panels)],
            help_resource=RESOURCES / "help.md",
            guide=RESOURCES / "guide.json",
            # Looked up at call time, so a patched ``manifest_path`` is honoured.
            resolver=resolver or (lambda panel: resolve_factory(panel)),
        )


def make_app(**kwargs):
    from chisurf.emtk.i18n import install

    install()
    from .translations import install_translations

    install_translations()
    return TttrToolboxApp(panels=kwargs.get("panels"), resolver=kwargs.get("resolver"))
