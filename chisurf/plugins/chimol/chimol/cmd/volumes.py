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

    @command("info_panel")
    def info_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the system-info panel.

        A command because the toolbar button is one -- the Qt row toggled it
        through a Qt slot, which is the coupling the viewport toolbar removes.
        """
        _window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        wanted = str(action).strip().lower() or "toggle"
        if wanted in ("on", "show", "1", "true"):
            visible = True
        elif wanted in ("off", "hide", "0", "false"):
            visible = False
        else:
            visible = not bool(getattr(viewer, "_info_visible", False))
        viewer.set_system_info_visible(visible)
        # Asked for explicitly, so it stays until it is asked to go: a click in
        # empty space dismisses a panel that opened *itself*, not one the user
        # opened. The same control turns it off again.
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is not None:
            gui.info_pinned = bool(visible)

    @command("hierarchy_panel")
    def hierarchy_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the hierarchy **inside the viewport**.

        The same `HierarchyNode` tree the Qt dock read, drawn by the chrome --
        expand/collapse and a switch per subtree, which is what the panel is
        actually used for.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("hierarchy_panel: this renderer draws no chrome")
            return

        wanted = str(action).strip().lower() or "toggle"
        existing = gui.window("hierarchy")
        if wanted in ("off", "hide", "0", "false"):
            if existing is not None:
                existing.visible = False
            viewer._update_view()
            return

        if existing is None:
            from ..renderer.hierarchy_window import HierarchyWindow

            apply_rows = getattr(window, "_apply_hidden_rows", None)
            panel = HierarchyWindow(viewer, on_change=apply_rows)
            panel.attach(gui)
            viewer._hierarchy_controls = panel
            existing = gui.add_window(panel.window())
        elif wanted == "toggle" and existing.visible:
            existing.visible = False
            viewer._update_view()
            return

        existing.visible = True
        gui.raise_window("hierarchy")
        gui.layout(gui._width, gui._height)
        viewer._update_view()

    @command("density_panel")
    def density_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the density controls **inside the viewport**.

        The contour levels and the display mode, in a window drawn by the
        renderer rather than a Qt dock -- so the same panel serves the desktop
        app and the browser. See `renderer/density_window.py` for why the drag
        no longer re-contours on every mouse move.

        Parameters
        ----------
        action : str, optional
            ``toggle`` (the default), ``on``/``show``, or ``off``/``hide``.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        if gui is None:
            self._emit_error("density_panel: this renderer draws no chrome")
            return

        wanted = str(action).strip().lower() or "toggle"
        existing = gui.window("density")
        if wanted in ("off", "hide", "0", "false"):
            if existing is not None:
                existing.visible = False
            viewer._update_view()
            return

        if existing is None:
            from ..renderer.density_window import DensityWindow

            # The Qt window keeps a `volume_panel`; the toolkit-free host and
            # the browser do not, and this panel exists precisely so that all
            # three get the same density controls. Borrowing the model from a
            # Qt dock meant the in-viewport panel refused to open on the hosts
            # it was written for -- "no map view model to drive" on every one
            # of them.
            #
            # `VolumeViewModel` is documented as "state and logic for the map
            # panel (no Qt)" and takes the viewer, so where there is no dock
            # this makes one.
            panel = getattr(window, "volume_panel", None)
            model = getattr(panel, "model", None)
            if model is None:
                from ..app.volume_panel import VolumeViewModel

                model = VolumeViewModel(viewer)
                # Kept on the viewer for the same reason the controls are: the
                # window holds callbacks into it.
                viewer._volume_view_model = model
            controls = DensityWindow(model)
            # Kept on the viewer so it outlives this call and the callbacks the
            # window holds stay alive with it.
            viewer._density_controls = controls
            existing = gui.add_window(controls.window())
        elif wanted in ("toggle",) and existing.visible:
            existing.visible = False
            viewer._update_view()
            return

        existing.visible = True
        gui.raise_window("density")
        gui.layout(gui._width, gui._height)
        viewer._update_view()

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

        # An EMDB map opens at the *deposited* contour level when one is
        # published: the depositors chose it for this map, and the densest-1%
        # rank is only the guess for maps that come with no recommendation.
        # `default_levels` prefers `recommended_level` whenever it is set.
        if grid.recommended_level is None:
            import re  # noqa: PLC0415

            stem = Path(path).name.lower()
            digits = re.search(r"\d{4,}", stem)
            if digits and ("emd" in stem or "emdb" in stem):
                try:
                    from .loader import _fetch_emdb_contour_level  # noqa: PLC0415

                    level = _fetch_emdb_contour_level(digits.group(0))
                    if level is not None:
                        grid.recommended_level = float(level)
                except Exception:
                    pass

        object_id = viewer.add_volume(grid, name=name or grid.name)
        low, high = grid.value_range()
        recommended = ""
        if grid.recommended_level is not None:
            recommended = f", opened at the deposited level {grid.recommended_level:.4g}"
        self._emit_message(
            f"load_map: {grid.name} {grid.shape[0]}x{grid.shape[1]}x{grid.shape[2]}, "
            f"step {grid.step[0]:.3g}/{grid.step[1]:.3g}/{grid.step[2]:.3g}, "
            f"values {low:.4g} to {high:.4g}{recommended}  [{object_id}]"
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

        name_clean = self._unquote_name(name)
        sel_clean = self._unquote_name(selection)
        level_clean = str(level).strip()

        def _is_number(s: str) -> bool:
            try:
                float(s)
                return True
            except ValueError:
                return False

        def _looks_like_map(s: str) -> bool:
            if not s:
                return False
            s_norm = s.lower().replace("_", "-")
            for oid, entry in viewer._objects.items():
                if getattr(entry.state, "volume", None) is not None:
                    oname = str(getattr(entry, "name", oid)).lower().replace("_", "-")
                    if s_norm in (str(oid).lower().replace("_", "-"), oname):
                        return True
            return False

        if _looks_like_map(name_clean):
            actual_map = name_clean
            actual_level = sel_clean if _is_number(sel_clean) else level_clean
            actual_name = ""
        elif _is_number(sel_clean) and not _looks_like_map(sel_clean):
            actual_name = name_clean
            actual_map = ""
            actual_level = sel_clean
        else:
            actual_name = name_clean
            actual_map = sel_clean
            actual_level = level_clean

        object_id = self._resolve_map_object(viewer, actual_map)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)

        if actual_level.strip():
            try:
                value = float(actual_level)
            except ValueError:
                self._emit_error(f"{style}: level must be a number, not {actual_level!r}")
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
        # A map opens already contoured, so `isosurface map` with no level asked
        # for the level it is already showing -- and got a second identical
        # surface drawn on top of the first. Restyle the existing one instead.
        for index, existing in enumerate(levels):
            try:
                same = abs(float(existing.get("level")) - value) <= abs(value) * 1e-9
            except (TypeError, ValueError):
                continue
            if same:
                levels[index] = dict(
                    existing,
                    style="mesh" if style == "isomesh" else "surface",
                    color=_named_color(color, existing.get("color")),
                )
                viewer.set_volume_levels(levels, object_id=object_id)
                self._emit_message(f"{style}: {grid.name} at {value:.4g}")
                return
        levels.append(
            {
                "level": value,
                "color": _named_color(color),
                "style": "mesh" if style == "isomesh" else "surface",
                "name": actual_name or f"{style}_{len(levels) + 1}",
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
        """Show a map as direct volume rendering (the reference's *solid*).

        PyMOL's `volume` builds a volume object with a colour ramp; here the
        histogram markers already are that ramp, so the command switches the
        map to the `solid` style -- unlit translucent fog composited through
        the markers' colours and opacities. This used to be a registered
        refusal ("not implemented yet"); the style exists now, and a command
        that declines while the panel's button works would be lying about the
        program.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        # PyMOL's signature is `volume new_name, map`; either spelling names
        # the map here, since the fog is a style of the map object itself.
        object_id = self._resolve_map_object(viewer, selection or name)
        if object_id is None:
            return
        viewer.set_volume_mode("solid", object_id=object_id)
        grid = viewer.get_volume(object_id)
        shown = getattr(grid, "name", object_id)
        self._emit_message(
            f"volume: {shown} drawn as translucent fog through the "
            "histogram levels (drag them in `density_panel` to tune it)"
        )

    @command("volume_quality")
    def volume_quality(self, name: str = "", quality: str = "") -> None:
        """Re-contour a map under a surface-quality preset.

        ``volume_quality map, smooth``. The presets wrap the reference
        viewer's rendering options with names: ``coarse`` (a quarter of the
        voxel budget), ``normal`` (the raw contour), ``smooth`` (its
        surface_smoothing -- the marching-cubes staircase and noise glitter
        relax), ``fine`` (its subdivide_surface, then smoothed).
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        wanted = self._unquote_name(quality or name).strip().lower()
        target = name if quality else ""
        if not wanted:
            self._emit_error(
                "Usage: volume_quality [map,] coarse|normal|smooth|fine"
            )
            return
        object_id = self._resolve_map_object(viewer, target)
        if object_id is None:
            return
        if not viewer.set_volume_quality(wanted, object_id=object_id):
            self._emit_error(
                f"volume_quality: no preset called {wanted!r}; "
                "the presets are coarse, normal, smooth and fine"
            )
            return
        grid = viewer.get_volume(object_id)
        shown = getattr(grid, "name", object_id)
        self._emit_message(f"volume_quality: {shown} re-contoured at {wanted}")

    @command("object_panel")
    def object_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the object list window (``object_panel on``).

        The PyMOL-style list of loaded objects with their A/S/H/L/C menus,
        as a window inside the viewport -- closable, draggable, snapped
        top-right until moved, remembered between runs.
        """
        self._toggle_gui_window("objects", action, "object_panel")

    @command("mouse_panel")
    def mouse_panel(self, action: str = "toggle") -> None:
        """Show, hide or toggle the mouse-settings window (``mouse_panel on``).

        The mouse-mode reference block -- bindings, selection level, playback
        -- as its own window, snapped bottom-right until moved.
        """
        self._toggle_gui_window("mouse", action, "mouse_panel")

    def _toggle_gui_window(self, key: str, action: str, name: str) -> None:
        """Shared body for the always-present chrome windows."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        gui = getattr(getattr(viewer, "_renderer", None), "_internal_gui", None)
        win = gui.window(key) if gui is not None else None
        if win is None:
            self._emit_error(f"{name}: this renderer draws no chrome")
            return
        wanted = str(action).strip().lower() or "toggle"
        if wanted in ("off", "hide", "0", "false"):
            win.visible = False
        elif wanted in ("on", "show", "1", "true"):
            win.visible = True
        else:
            win.visible = not win.visible
        if win.visible:
            gui.raise_window(key)
        gui.persist_windows()
        gui.layout(gui._width, gui._height)
        viewer._update_view()

    @command("hide_dust")
    def hide_dust(self, name: str = "", size: str = "") -> None:
        """Hide the small disconnected crumbs of a map contour.

        ``hide_dust [map,] [size]`` -- the reference viewer's Hide Dust. A
        connected piece of the contour survives when the largest extent of
        its bounding box reaches ``size`` (map units). With no size given,
        five voxels: the reference's default of 5 display units scaled by
        the grid step, so it means the same thing on any map.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        target, wanted = name, size
        if not wanted:
            # `hide_dust 4.5` on the only loaded map: the lone argument is
            # the size when it reads as a number.
            try:
                float(name)
            except (TypeError, ValueError):
                pass
            else:
                target, wanted = "", name
        object_id = self._resolve_map_object(viewer, target)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)
        if wanted:
            try:
                threshold = float(wanted)
            except (TypeError, ValueError):
                self._emit_error(f"hide_dust: {wanted!r} is not a size")
                return
        else:
            threshold = 5.0 * float(np.max(np.asarray(grid.step, dtype=float)))
        if not viewer.set_volume_dust(threshold, object_id=object_id):
            self._emit_error("hide_dust: that object has no map")
            return
        shown = getattr(grid, "name", object_id)
        self._emit_message(
            f"hide_dust: {shown} hides pieces smaller than {threshold:.4g}; "
            "`show_dust` brings them back"
        )

    @command("show_dust")
    def show_dust(self, name: str = "") -> None:
        """Show the contour pieces Hide Dust removed (``show_dust [map]``)."""
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        object_id = self._resolve_map_object(viewer, name)
        if object_id is None:
            return
        viewer.set_volume_dust(0.0, object_id=object_id)
        grid = viewer.get_volume(object_id)
        shown = getattr(grid, "name", object_id)
        self._emit_message(f"show_dust: {shown} shows every piece again")

    @command("volume_gaussian")
    def volume_gaussian(self, name: str = "", sdev: str = "") -> None:
        """Smooth a map's data with a Gaussian, as a new map object.

        ``volume_gaussian [map,] [sdev]`` -- the reference viewer's
        ``volume gaussian``. ``sdev`` is the standard deviation in map units;
        with none given, one voxel step. The result loads as ``<name>
        gaussian`` beside the original, contoured at its own default level --
        filtering is analysis, and analysis makes a new object.
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        target, wanted = name, sdev
        if not wanted:
            try:
                float(name)
            except (TypeError, ValueError):
                pass
            else:
                target, wanted = "", name
        object_id = self._resolve_map_object(viewer, target)
        if object_id is None:
            return
        grid = viewer.get_volume(object_id)
        if wanted:
            try:
                width = float(wanted)
            except (TypeError, ValueError):
                self._emit_error(f"volume_gaussian: {wanted!r} is not a width")
                return
        else:
            width = float(np.max(np.asarray(grid.step, dtype=float)))
        try:
            from ..volume import gaussian_filtered

            smoothed = gaussian_filtered(grid, width)
        except ValueError as error:
            self._emit_error(f"volume_gaussian: {error}")
            return
        viewer.add_volume(smoothed, name=smoothed.name)
        self._emit_message(
            f"volume_gaussian: {smoothed.name} added (sdev {width:.4g})"
        )

    # ------------------------------------------------------------------ #
    # Finding the map a command was aimed at
    # ------------------------------------------------------------------ #
    def _resolve_map_object(self, viewer, selection: str):
        """The object id of the map named, or the only one loaded.

        Reports what is available when the answer is ambiguous or absent, rather
        than picking one and leaving the user to wonder which.
        """
        wanted = self._unquote_name(selection).strip()
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
            wanted_low = wanted.lower()
            wanted_norm = wanted_low.replace("_", "-")
            for object_id, name in maps:
                oid_low = str(object_id).lower()
                name_low = str(name).lower()
                if (
                    wanted_low in (oid_low, name_low)
                    or wanted_norm in (oid_low.replace("_", "-"), name_low.replace("_", "-"))
                ):
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
