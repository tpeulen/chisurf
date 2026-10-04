"""Section/plot registry for view-spec driven model editors.

Built-in plot keys and custom sections register on first lookup so
:class:`~chisurf.gui.widgets.models.auto_model_widget.AutoModelWidget` can
resolve a model's :class:`~chisurf.core.models.view_spec.ModelView`.
"""

from __future__ import annotations

from .registry import (
    get_plot_class,
    get_section_factory,
    register_plot,
    register_section,
    resolve_plot_specs,
)

__all__ = [
    "register_plot",
    "register_section",
    "get_plot_class",
    "get_section_factory",
    "resolve_plot_specs",
]
