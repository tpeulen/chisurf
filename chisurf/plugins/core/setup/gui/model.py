"""Validated configuration documents and native settings routes."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml

PLUGIN_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Panel:
    """One destination of the hub.

    ``plugin`` names the plugin whose manifest declares the accepted emtk app; ``entry`` overrides it with an
    explicit ``module:factory`` (the Packages tab is a second app of the updater plugin, the Acquisition panel
    lives in this plugin). ``filename`` is only used by the one destination that edits a settings file.
    """

    key: str
    label: str
    plugin: str | None
    filename: str
    description: str
    entry: str | None = None
    #: The list's pictogram where the plugin's own would be missing or shared with another row.
    icon: str = ""


PANELS = [
    Panel(
        "boarding",
        "Getting Started",
        "core/boarding",
        "settings_chisurf.yaml",
        "Review settings, detectors and FCS definitions before loading data.",
    ),
    Panel(
        "chisurf",
        "ChiSurf Settings",
        None,
        "settings_chisurf.yaml",
        "Edit application settings and retain their YAML value types.",
        icon="🛠️",
    ),
    Panel(
        "acq",
        "Acquisition",
        None,
        "settings_chisurf.yaml",
        "Acquisition settings and simulator/device configuration.",
        entry="chisurf.plugins.core.setup.gui.acq_app:make_app",
        icon="🎚️",
    ),
    Panel(
        "style",
        "Styles",
        "core/style_manager",
        "settings_colors.yaml",
        "Colors and user style configuration.",
    ),
    Panel(
        "plots",
        "Plots",
        "core/plot_settings",
        "settings_chisurf.yaml",
        "Plot appearance, colors and backend settings in gui.plot.",
    ),
    Panel(
        "models",
        "Models",
        "core/model_manager",
        "settings_chisurf.yaml",
        "Model registration and enablement preferences.",
    ),
    Panel(
        "users",
        "User Editor",
        "core/user_editor",
        "settings_chisurf.yaml",
        "MMFDB user configuration and active-user preferences.",
    ),
    Panel(
        "ai",
        "AI Settings",
        "ai_settings",
        "settings_chisurf.yaml",
        "Configure AI providers, models and editor integration.",
        icon="🤖",
    ),
    Panel(
        "plugins",
        "Plugins",
        "core/plugin_manager",
        "settings_chisurf.yaml",
        "Discover, enable, configure and inspect native plugins.",
    ),
    Panel(
        "updates",
        "Updates",
        "core/updater",
        "settings_chisurf.yaml",
        "Update preferences and updater configuration.",
        entry="chisurf.plugins.core.setup.gui.hosted:make_updates",
    ),
    Panel(
        "packages",
        "Packages",
        "core/updater",
        "settings_chisurf.yaml",
        "Package-manager preferences and environment configuration.",
        entry="chisurf.plugins.core.updater.gui.package_app:make_package_app",
        icon="📚",
    ),
    Panel(
        "channels",
        "Channel Definition",
        "core/setup_channel_definition",
        "detector_setups.json",
        "Detector channels, PIE windows, calibration, LUT and optical setup.",
    ),
    Panel(
        "fcs",
        "FCS Definitions",
        "fcs/fcs_channel_preset",
        "fcs_channel_setups.json",
        "FCS channel-pair definitions and correlation settings.",
    ),
    Panel(
        "lut",
        "TTTR LUT Tools",
        "tttr/tttr_lut_tools",
        "detector_setups.json",
        "TAC linearization lookup-table settings.",
        entry="chisurf.plugins.core.setup.gui.hosted:make_lut_tools",
    ),
    Panel(
        "check",
        "Plugin Check",
        "core/plugin_check",
        "settings_chisurf.yaml",
        "Check plugin contracts, dependencies and native runtime.",
    ),
]


#: The one destination that edits a settings file itself (the Qt tool's own ``SettingsEditor``).
FILE_EDITOR = "chisurf"
DEFAULT_PANEL = "boarding"


def resolve_factory(panel):
    """The ``make_app`` of a destination: its explicit ``entry``, else the plugin manifest's ``entrypoints.emtk``."""
    if panel.entry:
        module, name = panel.entry.split(":", 1)
        return getattr(importlib.import_module(module), name)
    if not panel.plugin:
        return None
    path = PLUGIN_ROOT / panel.plugin / "manifest.json"
    data = json.loads(path.read_text())
    entry = data.get("entrypoints", {}).get("emtk")
    if not entry:
        return None
    module, name = entry.split(":", 1)
    return getattr(importlib.import_module(module), name)


def visible_panels(panels, query):
    """The destinations whose name contains *query* (case-insensitive), as the Qt navigation filters them."""
    query = (query or "").strip().casefold()
    return [p for p in panels if not query or query in p.label.casefold()]


def step_target(panels, current, delta):
    """The key one step *delta* (-1 or +1) from *current* in the full list, or ``None`` at an end."""
    keys = [p.key for p in panels]
    if current not in keys:
        return None
    index = keys.index(current) + delta
    return keys[index] if 0 <= index < len(keys) else None


class SettingsDocument:
    """A YAML/JSON document with validated atomic saves.

    With ``merge_defaults`` the main settings file is shown as the application loads it (packaged defaults under the
    user's values, as the Qt editor does) and a save writes only what differs from the defaults.
    """

    def __init__(self, path, merge_defaults=False):
        self.path = Path(path)
        self.merge_defaults = merge_defaults
        self.text = ""
        self.saved_text = ""
        self.reload()

    @property
    def merged(self):
        return self.merge_defaults and self.path.name == "settings_chisurf.yaml"

    @property
    def dirty(self):
        return self.text != self.saved_text

    def reload(self):
        if self.merged:
            from chisurf.core.settings.settings_utils import get_chisurf_settings

            self.text = yaml.safe_dump(
                get_chisurf_settings(self.path, use_source_folder=False), sort_keys=False
            )
        else:
            self.text = self.path.read_text(encoding="utf-8") if self.path.exists() else "{}\n"
        self.saved_text = self.text

    def _overrides(self, value):
        """*value* without what equals the packaged defaults (the user's file records only their choices)."""
        import chisurf.core.settings as package
        from chisurf.core.settings.settings_utils import prune_defaults

        packaged = Path(package.__file__).parent / "settings_chisurf.yaml"
        if not packaged.is_file():
            return value
        defaults = yaml.safe_load(packaged.read_text(encoding="utf-8")) or {}
        pruned = prune_defaults(value, defaults)
        return pruned if isinstance(pruned, dict) else value

    def parse(self):
        if self.path.suffix.lower() == ".json":
            value = json.loads(self.text)
        else:
            value = yaml.safe_load(self.text)
        if not isinstance(value, (dict, list)):
            raise ValueError("Configuration must contain a mapping or list.")
        return value

    def save(self, path=None):
        # Validate before replacing any file. Keep exactly the edited text,
        # including comments and strings containing pipes.
        target = Path(path) if path is not None else self.path
        old = self.path
        self.path = target
        try:
            value = self.parse()
        except Exception:
            self.path = old
            raise
        text = self.text
        if self.merged and isinstance(value, dict):
            text = yaml.safe_dump(self._overrides(value), sort_keys=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="." + target.name + ".", dir=target.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                stream.write(text)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.saved_text = self.text
        return value
