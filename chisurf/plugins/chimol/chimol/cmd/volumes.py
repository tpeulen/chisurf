"""Commands for voxel maps: contour them, move the level, ask what is there.

PyMOL's names and argument order, per the compatibility contract, with ChiMOL's
own additions after them rather than in place of them.

The one thing these do differently from most commands here is that they report
the map's value range when a level is refused. A contour level means nothing
without knowing the scale of the data — an accessible volume runs 0 to 1, a
photon-count stack to a few hundred, a cryo-EM map to whatever the reconstruction
put there — so "level 3 is above this map's maximum of 1.0" is the useful answer
and a silent empty surface is not.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..colors import get_pymol_color
from .base import BaseCmd
from .registry import command


def _named_color(name: str, fallback=(0.5, 0.7, 1.0, 1.0)):
    """A colour name to RGBA, falling back rather than failing the command."""
    if not name:
        return fallback
    try:
        rgba = get_pymol_color(name)
    except Exception:
        return fallback
    if rgba is None:
        return fallback
    values = list(rgba)
    while len(values) < 4:
        values.append(1.0)
    return tuple(float(v) for v in values[:4])


class VolumeMixin(BaseCmd):
    """Loading, contouring and describing voxel maps."""

    # ------------------------------------------------------------------ #
    # Getting a map into the scene
    # ------------------------------------------------------------------ #
    @command("load_map", aliases=("load_mrc",))
    def load_map(self, path: str = "", name: str = "") -> None:
        """Load an MRC/CCP4/MAP file as a map object.

        The map keeps its own voxel size and origin, so it lands where the file
        says it does rather than at the scene origin -- which is the difference
        between a density around a model and one next to it.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        if not path:
            self._emit_error("Usage: load_map filename [, name]")
            return
        try:
            from ..io.mrc import load_mrc_grid

            grid = load_mrc_grid(Path(path))
        except Exception as exc:
            self._emit_error(f"load_map: {exc}")
            return

        object_id = viewer.add_volume(grid, name=name or grid.name)
        low, high = grid.value_range()
        self._emit_message(
            f"load_map: {grid.name} {grid.shape[0]}x{grid.shape[1]}x{grid.shape[2]}, "
            f"step {grid.step[0]:.3g}/{grid.step[1]:.3g}/{grid.step[2]:.3g}, "
            f"values {low:.4g} to {high:.4g}  [{object_id}]"
        )

    # ------------------------------------------------------------------ #
    # Contours
    # ------------------------------------------------------------------ #
    def _contour(self, style: str, name: str, selection: str, level: str,
                 color: str) -> None:
        """Shared body for :meth:`isosurface` and :meth:`isomesh`.

        One implementation, because the two differ only in whether the triangles
        are filled -- and two copies of a contour rule would drift.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        object_id = self._resolve_map_object(viewer, selection)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)

        if level.strip():
            try:
                value = float(level)
            except ValueError:
                self._emit_error(f"{style}: level must be a number, not {level!r}")
                return
        else:
            value = grid.default_level()

        low, high = grid.value_range()
        if not (low < value < high):
            self._emit_error(
                f"{style}: level {value:.4g} is outside this map, which runs "
                f"{low:.4g} to {high:.4g} -- nothing would be drawn"
            )
            return

        levels = list(viewer.get_volume_levels(object_id) or [])
        levels.append(
            {
                "level": value,
                "color": _named_color(color),
                "style": "mesh" if style == "isomesh" else "surface",
                "name": name or f"{style}_{len(levels) + 1}",
            }
        )
        viewer.set_volume_levels(levels, object_id=object_id)
        self._emit_message(
            f"{style}: {grid.name} at {value:.4g} "
            f"({(np.asarray(grid.values) >= value).mean() * 100:.1f}% of voxels)"
        )

    @command("isosurface")
    def isosurface(self, name: str = "", selection: str = "", level: str = "",
                   color: str = "") -> None:
        """Contour a map as a solid surface (``isosurface name, map, level``).

        With no level, one is derived from the data as ``mean + 1 sigma`` -- the
        conventional starting contour, and the only scale-free choice when a map
        might be an accessible volume, an electron density or a photon count.
        """
        self._contour("isosurface", name, selection, level, color)

    @command("isomesh")
    def isomesh(self, name: str = "", selection: str = "", level: str = "",
                color: str = "") -> None:
        """Contour a map as a wireframe (``isomesh name, map, level``).

        The same contour as :meth:`isosurface`, drawn open, so a structure inside
        the density stays visible.
        """
        self._contour("isomesh", name, selection, level, color)

    @command("volume_level", aliases=("map_level",))
    def volume_level(self, selection: str = "", level: str = "") -> None:
        """Move a map's contour, replacing whatever levels it has.

        With no level, reports the ones in place and the map's value range, which
        is what you need in order to pick the next one.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        object_id = self._resolve_map_object(viewer, selection)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)
        low, high = grid.value_range()

        if not level.strip():
            levels = viewer.get_volume_levels(object_id) or []
            shown = ", ".join(f"{entry['level']:.4g}" for entry in levels) or "none"
            self._emit_message(
                f"volume_level: {grid.name} at {shown}; values run "
                f"{low:.4g} to {high:.4g}"
            )
            return

        try:
            value = float(level)
        except ValueError:
            self._emit_error(f"volume_level: level must be a number, not {level!r}")
            return
        if not (low < value < high):
            self._emit_error(
                f"volume_level: {value:.4g} is outside this map, which runs "
                f"{low:.4g} to {high:.4g}"
            )
            return

        existing = list(viewer.get_volume_levels(object_id) or [])
        colour = existing[0].get("color") if existing else (0.5, 0.7, 1.0, 1.0)
        style = existing[0].get("style") if existing else "surface"
        viewer.set_volume_levels(
            [{"level": value, "color": colour, "style": style}], object_id=object_id
        )
        self._emit_message(f"volume_level: {grid.name} at {value:.4g}")

    @command("map_info")
    def map_info(self, selection: str = "") -> None:
        """Describe a map: size, voxel step, origin and value range."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        object_id = self._resolve_map_object(viewer, selection)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)
        low, high = grid.value_range()
        finite = np.asarray(grid.values)[np.isfinite(grid.values)]
        stride = grid.stride_for_limit()
        self._emit_message(
            f"{grid.name}: {grid.shape[0]} x {grid.shape[1]} x {grid.shape[2]} "
            f"= {grid.voxel_count:,} voxels\n"
            f"  step   {grid.step[0]:.4g}, {grid.step[1]:.4g}, {grid.step[2]:.4g}\n"
            f"  origin {grid.origin[0]:.4g}, {grid.origin[1]:.4g}, "
            f"{grid.origin[2]:.4g}\n"
            f"  values {low:.4g} to {high:.4g}, "
            f"mean {float(finite.mean()):.4g}, sd {float(finite.std()):.4g}\n"
            f"  drawn at stride {stride}"
            + ("" if stride == 1 else " (over the voxel budget at full detail)")
        )

    @command("volume")
    def volume(self, name: str = "", selection: str = "") -> None:
        """Direct volume rendering -- **not implemented yet**.

        Registered rather than missing, so the command reports the gap instead
        of raising, and says what to use instead. See PRD-57.
        """
        self._emit_error(
            "volume: direct volume rendering is not implemented yet. "
            "Use `isosurface` or `isomesh` to contour the map."
        )

    # ------------------------------------------------------------------ #
    # Finding the map a command was aimed at
    # ------------------------------------------------------------------ #
    def _resolve_map_object(self, viewer, selection: str):
        """The object id of the map named, or the only one loaded.

        Reports what is available when the answer is ambiguous or absent, rather
        than picking one and leaving the user to wonder which.
        """
        wanted = (selection or "").strip()
        maps = []
        for object_id, entry in viewer._objects.items():
            if getattr(entry.state, "volume", None) is not None:
                maps.append((object_id, getattr(entry, "name", object_id)))

        if not maps:
            self._emit_error(
                "no maps are loaded; `load_map file.mrc` reads one"
            )
            return None
        if wanted:
            for object_id, name in maps:
                if wanted in (object_id, name):
                    return object_id
            available = ", ".join(name for _oid, name in maps)
            self._emit_error(f"no map called {wanted!r}; loaded maps: {available}")
            return None
        if len(maps) == 1:
            return maps[0][0]
        available = ", ".join(name for _oid, name in maps)
        self._emit_error(
            f"several maps are loaded, so one has to be named: {available}"
        )
        return None


__all__ = ["VolumeMixin"]
