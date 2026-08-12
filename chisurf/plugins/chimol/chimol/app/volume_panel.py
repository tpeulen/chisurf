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

logger = logging.getLogger(__name__)

_VIEW_JSON = pathlib.Path(__file__).parent / "volume.view.json"


class VolumeViewModel:
    """State and logic for the map panel (no Qt).

    Tracks whichever object is active and has a map, falling back to the first
    map in the scene so the panel is useful without hunting for the right
    object first.
    """

    @property
    def model(self):
        """Self-reference so call sites expecting a container with `.model` work."""
        return self

    def view_spec(self):
        """Resolve AutoForm's view spec from the authored ``volume.view.json``."""
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_VIEW_JSON)

    def __init__(self, viewer) -> None:
        self._viewer = viewer
        self._object_id: str | None = None

    # ------------------------------------------------------------------ #
    # Which map
    # ------------------------------------------------------------------ #
    def _grid(self):
        """The map to edit, or ``None``.

        The active object's map when it has one; otherwise the **most recently
        loaded** map. Newest rather than first, and that is the whole of a
        reported bug: loading a second map while something else is active left
        the panel editing the first one, because ``_objects`` is
        insertion-ordered and the search walked it forwards. The levels and the
        histogram then described a map that was not the one on screen.

        The active object is still preferred, so clicking a map in the object
        list picks it — "newest" only decides where to look when nothing has
        been chosen.
        """
        viewer = self._viewer
        try:
            objects = getattr(viewer, "_objects", {}) or {}
            active = viewer.get_active_object_id()
            entry = objects.get(active)
            if entry is not None and getattr(entry.state, "volume", None) is not None:
                self._object_id = active
                return entry.state.volume
            for candidate, other in reversed(list(objects.items())):
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

    # ------------------------------------------------------------------ #
    # What the in-viewport window needs on top
    # ------------------------------------------------------------------ #
    def set_levels(self, value, *, rebuild: bool = True, preview: bool = False) -> None:
        """Write the levels, optionally **without** re-contouring.

        ``rebuild=False`` stores the level and draws nothing — the marker
        moves, the map does not. ``preview=True`` re-contours under the
        viewer's reduced drag budget, which is what lets the surface follow
        the marker; the release writes once more with ``preview=False`` and
        gets the full-quality contour.
        """
        if self._object_id is None:
            return
        try:
            self._viewer.set_volume_levels(
                list(value), object_id=self._object_id,
                rebuild=rebuild, preview=preview,
            )
        except Exception:
            logger.warning("map panel: could not set contour levels", exc_info=True)

    def display_mode(self) -> str:
        """``surface``, ``mesh`` or ``solid``."""
        try:
            return self._viewer.get_volume_mode(self._object_id)
        except Exception:
            return "surface"

    def set_display_mode(self, mode: str) -> None:
        """Switch how the map is drawn."""
        if self._object_id is None:
            return
        try:
            self._viewer.set_volume_mode(mode, object_id=self._object_id)
        except Exception:
            logger.warning("map panel: could not set the display mode", exc_info=True)

    def map_visible(self) -> bool:
        """Whether the map object is currently shown in the scene."""
        if self._object_id is None:
            return True
        try:
            entry = self._viewer._objects.get(self._object_id)
            return bool(entry is None or entry.visible)
        except Exception:
            return True

    def set_map_visible(self, visible: bool) -> None:
        """Show or hide the map object -- the panel's eye button."""
        if self._object_id is None:
            return
        try:
            self._viewer.set_object_visible(self._object_id, bool(visible))
        except Exception:
            logger.warning("map panel: could not toggle the map", exc_info=True)

    def close_map(self) -> None:
        """Unload the map object -- the panel's close button."""
        if self._object_id is None:
            return
        try:
            self._viewer.remove_object(self._object_id)
            self._object_id = None
        except Exception:
            logger.warning("map panel: could not close the map", exc_info=True)

    def display_quality(self) -> str:
        """``coarse``, ``normal``, ``smooth`` or ``fine``."""
        try:
            return self._viewer.get_volume_quality(self._object_id)
        except Exception:
            return "normal"

    def set_display_quality(self, quality: str) -> None:
        """Re-contour under a surface-quality preset."""
        if self._object_id is None:
            return
        try:
            self._viewer.set_volume_quality(quality, object_id=self._object_id)
        except Exception:
            logger.warning(
                "map panel: could not set the surface quality", exc_info=True
            )


__all__ = ["VolumeViewModel"]

