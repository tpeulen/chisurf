"""Section/plot registry for view-spec driven model editors.

Importing this package registers the built-in plot keys and custom sections so
:class:`~chisurf.gui.widgets.models.auto_model_widget.AutoModelWidget` can
resolve a model's :class:`~chisurf.core.models.view_spec.ModelView`.
"""

from __future__ import annotations

from . import (
    builtin,  # noqa: F401  (side effect: populate the registry)
    chimol_section,  # noqa: F401  (registers the "chimol" section)
    data_source_section,  # noqa: F401  (registers the "data_source" section)
    decay_conv_section,  # noqa: F401  (registers the "decay_conv" section)
    embed_section,  # noqa: F401  (registers the "embed" section)
    equation_editor_section,  # noqa: F401  (registers the "equation_editor" section)
    global_parameter_table,  # noqa: F401  (registers the "global_parameter_table" section)
    help_section,  # noqa: F401  (registers the "help" section)
    image_browser_section,  # noqa: F401  (registers the "image_browser" section)
    path_list_section,  # noqa: F401  (registers the "path_list" section)
    phasor_section,  # noqa: F401  (registers the "phasor" section)
    progress_section,  # noqa: F401  (registers the "progress" section)
    rate_matrix_section,  # noqa: F401  (registers the "rate_matrix" section)
    level_histogram_section,  # noqa: F401  (registers "level_histogram")
    region_list_section,  # noqa: F401  (registers the "region_list" section)
    scalar_table_section,  # noqa: F401  (registers the "scalar_table" section)
    setup_selector_section,  # noqa: F401  (registers the "setup_selector" section)
    state_table_section,  # noqa: F401  (registers the "state_table" section)
    waterfall_section,  # noqa: F401  (registers the "waterfall" section)
)
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
