"""The map panel: a histogram of the data with contour levels dragged along it.

The panel is an :class:`~chisurf.gui.autoform.AutoForm` over
``volume.view.json``; the editor itself is chisurf's shared ``level_histogram``
section, so every tool that has to ask for a threshold gets the same one.

The idea it embodies is Chimera's, which is the authority for voxel maps here
(see the carve-out in the target spec): **choosing a contour is an act of looking
at the data**. Nobody knows in advance what level shows an accessible volume, a
photon-count stack or a reconstruction — they share no units and no order of
magnitude — so a number typed blind is a guess followed by a re-render. Drawing
the value distribution and dragging the level along it replaces that with one
continuous motion.

The view model holds no copy of the contours. ``levels`` reads and writes the
map object through the viewer, so the panel is a view of the map's own state and
the two cannot drift.
"""

from __future__ import annotations

import logging
import pathlib
from typing import Optional

from qtpy import QtWidgets

from chisurf.gui.autoform import AutoForm

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "volume.view.json"


class VolumeViewModel:
    """State and logic for the map panel (no Qt).

    Tracks whichever object is active and has a map, falling back to the first
    map in the scene so the panel is useful without hunting for the right
    object first.
    """

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``volume.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self, viewer) -> None:
        self._viewer = viewer
        self._object_id: Optional[str] = None

    # ------------------------------------------------------------------ #
    # Which map
    # ------------------------------------------------------------------ #
    def _grid(self):
        """The map to edit, and the object it belongs to, or ``(None, None)``."""
        viewer = self._viewer
        try:
            objects = getattr(viewer, "_objects", {}) or {}
            active = viewer.get_active_object_id()
            entry = objects.get(active)
            if entry is not None and getattr(entry.state, "volume", None) is not None:
                self._object_id = active
                return entry.state.volume
            for candidate, other in objects.items():
                if getattr(other.state, "volume", None) is not None:
                    self._object_id = candidate
                    return other.state.volume
        except Exception:
            logger.debug("map panel: no viewer state to read", exc_info=True)
        self._object_id = None
        return None

    # ------------------------------------------------------------------ #
    # What the sections read. Methods, not properties: AutoForm resolves a
    # `source` by calling it, and a property leaves the section blank.
    # ------------------------------------------------------------------ #
    def summary(self) -> str:
        """One line naming the map, its size, and how it is being drawn."""
        grid = self._grid()
        if grid is None:
            return "No map loaded. `load_map file.mrc` reads one."
        shape = grid.shape
        low, high = grid.value_range()
        stride = grid.stride_for_limit()
        text = (
            f"{grid.name} — {shape[0]}×{shape[1]}×{shape[2]} voxels, "
            f"step {grid.step[0]:.3g}/{grid.step[1]:.3g}/{grid.step[2]:.3g}, "
            f"values {low:.4g} to {high:.4g}"
        )
        if stride > 1:
            text += f" (drawn at stride {stride}: over the voxel budget in full)"
        return text

    def level_histogram_data(self):
        """``(counts, edges)`` of the map's values, or ``None`` without a map."""
        grid = self._grid()
        if grid is None:
            return None
        return grid.histogram(bins=200)

    def value_range(self):
        """``(low, high)`` of the map, for clamping levels."""
        grid = self._grid()
        return None if grid is None else grid.value_range()

    # ------------------------------------------------------------------ #
    # The contours themselves, read and written straight through the map
    # ------------------------------------------------------------------ #
    @property
    def levels(self) -> list:
        if self._grid() is None or self._object_id is None:
            return []
        try:
            return list(self._viewer.get_volume_levels(self._object_id) or [])
        except Exception:
            return []

    @levels.setter
    def levels(self, value) -> None:
        if self._object_id is None:
            return
        try:
            self._viewer.set_volume_levels(list(value), object_id=self._object_id)
        except Exception:
            logger.warning("map panel: could not set contour levels", exc_info=True)

    def apply_levels(self) -> None:
        """Called after an edit. The setter already redrew; this is the hook."""
        return None


class VolumeDock(QtWidgets.QWidget):
    """Map panel — content widget, no outer ``QDockWidget``."""

    def __init__(self, parent, viewer, margins=(0, 0, 0, 0), spacing=4) -> None:
        super().__init__(parent)
        self.model = VolumeViewModel(viewer)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(*margins)
        layout.setSpacing(spacing)
        self.auto_form = AutoForm(self.model)
        layout.addWidget(self.auto_form)
        self.refresh()

    def refresh(self) -> None:
        """Re-read the viewer. Called when objects or maps change."""
        try:
            self.auto_form.sync_fields()
            self.auto_form.refresh_plots()
        except Exception:
            logger.debug("map panel: refresh failed", exc_info=True)


__all__ = ["VolumeDock", "VolumeViewModel"]
