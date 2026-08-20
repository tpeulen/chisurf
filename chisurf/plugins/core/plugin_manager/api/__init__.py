"""Qt-free plugin-manager logic: rows, settings, install.

The manager used to be one 1856-line widget in which the data model, the
settings writer, the installer and an AI icon client were all tangled into Qt
callbacks -- so none of it could be tested without a display, and the existing
tests reached into the widget with ``SimpleNamespace`` stand-ins to get at the
pure functions. This package is that logic, extracted and importable on its own.
"""

from chisurf.plugins.core.plugin_manager.api.icons import AIIconRateLimitError
from chisurf.plugins.core.plugin_manager.api.records import (
    PluginRow,  # noqa: F401 - re-exported
    collect_rows,
    dependants_of,
    health_of,
    read_module_docstring,
)
from chisurf.plugins.core.plugin_manager.api.settings_io import (
    PluginSettings,
)

__all__ = [
    "AIIconRateLimitError",
    "PluginRow",
    "PluginSettings",
    "collect_rows",
    "dependants_of",
    "health_of",
    "read_module_docstring",
]
