"""General ``level_histogram`` AutoForm section — thresholds picked by eye.

Any tool that asks a user for a level over a distribution gets the whole editor
from its ``.view.json``::

    {"type": "custom", "key": "level_histogram", "target": "levels",
     "title": "Contour levels",
     "options": {"source": "level_histogram_data",
                 "range_source": "value_range",
                 "on_change": "apply_levels",
                 "styles": ["surface", "mesh"]},
     "description": "Drag a marker to move a level; click to add one."}

The point is that choosing a threshold is an act of **looking at the data**. The
scales differ by orders of magnitude between one dataset and the next — a
density, a burst brightness, a photon count — so a number typed blind is a guess
followed by a re-render. Drawing the distribution and dragging the level along it
replaces that with one motion.

Options
-------
``source`` : str
    Name of a **method** returning ``(counts, edges)``. It has to be a method:
    AutoForm resolves sources by calling them, and a ``@property`` renders the
    section blank with no error at all.
``range_source`` : str, optional
    Method returning ``(low, high)`` to clamp levels against. Falls back to the
    histogram edges.
``on_change`` : str, optional
    Method called after each edit, so the model can redraw whatever the levels
    control.
``styles`` : list of str, optional
    Per-level style choices (e.g. ``["surface", "mesh"]``). Omitted means no
    style control is shown.
``log_counts`` : bool, default ``True``
    Log-scale the bars. Most distributions here are overwhelmingly background,
    and on a linear axis the part worth thresholding is a flat line at zero.
``allow_add``, ``allow_remove`` : bool, default ``True``
    Whether the user may add or remove levels, as opposed to only moving the
    ones the model provides.
``placeholder`` : str
    Shown when ``source`` returns nothing.

``target`` names the model attribute holding the levels — a list of dicts with
``level`` and optionally ``color`` and ``style``. A bare list of numbers is
accepted and normalised. The model owns them; the widget never keeps a second
copy, so the two cannot drift.
"""

from __future__ import annotations

from chisurf.gui.autoform.sections.registry import register_section


@register_section("level_histogram")
def _level_histogram_section_factory(model, target: str = "levels", **options):
    """Custom-section factory for the shared level editor."""
    from chisurf.gui.widgets.level_histogram import LevelHistogramWidget

    return LevelHistogramWidget(model, target or "levels", **options)


__all__ = []
