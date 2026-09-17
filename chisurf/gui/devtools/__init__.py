"""
Dev Tools for ChiSurf Development Mode.

This package provides developer utilities for ChiSurf, including:
- Source jumping (resolve widget/object source locations)
- Code badge buttons (floating `</>` buttons to open source)
"""

from .source_jump import (
    make_resolver,
    make_widget_resolver,
    open_in_editor,
    resolve_experiment_panel_source,
    resolve_fit_window_source,
    resolve_focused_widget_source,
    resolve_object_source,
    resolve_parameter_group_source,
    resolve_widget_source,
)

__all__ = [
    "resolve_widget_source",
    "resolve_object_source",
    "resolve_focused_widget_source",
    "resolve_fit_window_source",
    "resolve_parameter_group_source",
    "resolve_experiment_panel_source",
    "open_in_editor",
    "make_resolver",
    "make_widget_resolver",
]
