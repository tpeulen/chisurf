from __future__ import annotations

import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from ..io.export import unscale_coordinates, write_structure
from .base import BaseCmd
from .registry import command
from .selection_types import Selection

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from qtpy import QtCore

    from chisurf.gui.progress import ChiSurfProgress

#: Cache for :func:`ray_render_thread_class`.
_RAY_RENDER_THREAD = None


def ray_render_thread_class():
    """Return the background ray-tracing thread class, building it on first call.

    Why a factory rather than a ``class`` statement
    -----------------------------------------------
    The class derives from ``QThread`` and declares ``Signal`` attributes, so
    Qt has to be present *when the class body runs* -- and a class body at
    module scope runs on import. That made the whole command set require a
    window system in order to parse ``color`` or write a PDB, because
    :mod:`chimol.cmd` imports this module for the rest of what is in it.

    Deferring the class body to first use is the only way to keep both: the
    thread is still a real ``QThread`` where one exists, and the module still
    imports where one does not. The class is built once and cached.

    Returns
    -------
    type
        A ``QThread`` subclass whose ``finished`` signal carries an
        ``(H, W, 3)`` uint8 image and whose ``error`` signal carries a message.
    """
    global _RAY_RENDER_THREAD
    if _RAY_RENDER_THREAD is not None:
        return _RAY_RENDER_THREAD

    from qtpy import QtCore

    class RayRenderThread(QtCore.QThread):
        """Background thread for Chimol ray-tracing.

        Runs a render callable that returns an (H, W, 3) uint8 image and emits
        the result (or an error message) back to the GUI thread.
        """

        finished = QtCore.Signal(object)
        error = QtCore.Signal(str)

        def __init__(
            self,
            render_func: Callable[[], np.ndarray],
            parent=None,
        ) -> None:
            super().__init__(parent)
            self._render_func = render_func

        def run(self) -> None:
            """Render, and emit either the image or the failure."""
            try:
                image = self._render_func()
                self.finished.emit(image)
            except Exception as exc:
                self.error.emit(str(exc))

    _RAY_RENDER_THREAD = RayRenderThread
    return _RAY_RENDER_THREAD


class ExportMixin(BaseCmd):
    """Image and data export commands."""



    @command("save")
    def save(self, filename: str = "", sel: Selection = "") -> None:
        """Write a structure or image (PyMOL ``save filename [, selection]``).

        The format follows the extension: ``.pdb``/``.ent``/``.pqr`` write PDB,
        ``.cif``/``.mmcif`` write mmCIF, ``.png`` saves the viewport, and anything
        unrecognised writes PDB -- which is PyMOL's own rule rather than an
        error, since a mistyped extension should still leave a usable file.

        What is written is the structure **as the viewer holds it**: coordinates
        as currently transformed, atoms as currently present. Re-exporting the
        source file instead would silently discard whatever the user did.
        """
        if not filename:
            self._emit_error("Usage: save <filename> [, selection]")
            return

        path = Path(str(filename)).expanduser()
        if path.suffix.lower() == ".png":
            self.png(str(path))
            return
        if path.suffix.lower() in (".stl", ".wrl", ".vrml", ".glb", ".gltf"):
            self._save_scene_mesh(path)
            return
        # A session, not a structure: `save figure.pse` is how a PyMOL user
        # saves their work, so the extension has to route there.
        if self.names_a_session(path):
            self.session_save(str(path))
            return

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        # Which object to write: the one the selection resolved against, not
        # whichever happens to be active. `save out.pdb, sugars` must write
        # `sugars`; reading the active object's arrays while masking with another
        # object's selection is a length mismatch when the two differ in size and,
        # worse, silently writes the wrong atoms when they do not.
        mask = None
        state = None
        selection = str(sel).strip()
        if selection:
            try:
                object_id, _, mask = self._resolve_selection_to_atom_mask(
                    viewer, selection
                )
            except Exception as exc:
                self._emit_error(f"save: {exc}")
                return
            if mask is None or not np.asarray(mask, dtype=bool).any():
                self._emit_error(f"save: selection '{selection}' matched no atoms")
                return
            entry = getattr(viewer, "_objects", {}).get(object_id)
            state = getattr(entry, "state", None)

        if state is not None:
            atoms = getattr(state, "atoms", None)
            coords = getattr(state, "all_atom_coords", None)
            centre = getattr(state, "raw_center", None)
        else:
            atoms = getattr(viewer, "_atoms", None)
            coords = getattr(viewer, "_all_atom_coords", None)
            centre = getattr(viewer, "_raw_center", None)

        if atoms is None or coords is None:
            self._emit_error(
                "save: that object has no atoms to write "
                "(load a structure first)"
            )
            return

        xyz = unscale_coordinates(
            coords,
            float(getattr(viewer, "_scale_factor", 1.0) or 1.0),
            centre,
        )

        try:
            fmt, written = write_structure(
                path, atoms, xyz, mask=mask,
                title=str(getattr(window, "windowTitle", lambda: "")() or ""),
            )
        except Exception as exc:
            self._emit_error(f"save: could not write {path}: {exc}")
            return

        self._emit_message(f"Wrote {written} atoms as {fmt.upper()}: {path}")

    def _save_scene_mesh(self, path: Path) -> None:
        """Write the drawn scene as a 3-D model file, routed by extension.

        ``.glb``/``.gltf`` write binary glTF -- the format PowerPoint's
        Insert ▸ 3D Models takes; ``.stl`` writes triangles for printing and
        CAD; ``.wrl``/``.vrml`` write VRML 2.0 with per-vertex colours.
        Spheres and sticks -- analytic on screen -- are tessellated back into
        triangles; lines, labels and the translucent map fog are skipped.
        """
        from ..io.mesh_export import (  # noqa: PLC0415
            scene_mesh_objects,
            write_glb,
            write_stl,
            write_wrl,
        )

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return
        scene = getattr(viewer, "_scene", None)
        objects = scene_mesh_objects(scene) if scene is not None else []
        if not objects:
            self._emit_error(
                "save: the scene has no triangles to export -- load and show "
                "something first"
            )
            return
        suffix = path.suffix.lower()
        try:
            if suffix in (".glb", ".gltf"):
                count = write_glb(path, objects)
                note = " (binary glTF; PowerPoint: Insert ▸ 3D Models)"
            elif suffix == ".stl":
                count = write_stl(path, objects)
                note = " (no colours; STL carries geometry only)"
            else:
                count = write_wrl(path, objects)
                note = ""
        except (OSError, ValueError) as error:
            self._emit_error(f"save: {error}")
            return
        self._emit_message(
            f"save: wrote {path} -- {len(objects)} object(s), "
            f"{count:,} triangles{note}"
        )

    @command("png")
    def png(
        self,
        filename: str = "",
        width: int = 0,
        height: int = 0,
        dpi: int = 0,
        ray: bool = False,
    ) -> None:
        """Save the current live OpenGL viewport as a PNG file."""
        if not filename:
            self._emit_error("Usage: png filename [, width [, height [, dpi [, ray]]]]")
            return

        width = int(width) if width and int(width) > 0 else None
        height = int(height) if height and int(height) > 0 else None

        if ray:
            self.ray(str(width or 0), str(height or 0))

        path = Path(filename).expanduser()
        if path.suffix.lower() != ".png":
            path = path.with_suffix(".png")

        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        try:
            ok = bool(viewer.save_png(path, width=width, height=height))
        except AttributeError:
            ok = self._save_png_from_renderer(viewer, path, width=width, height=height)
        except Exception as exc:
            self._emit_error(f"Failed to write PNG {path}: {exc}")
            return

        if ok:
            self._emit_message(f"Wrote PNG: {path}")
        else:
            self._emit_error(f"Failed to write PNG {path}")

    @staticmethod
    def _scene_pixel_size(viewer) -> tuple[int, int]:
        """The size of the rectangle the viewport draws the scene into.

        Asks the GL widget, which is the only thing that knows how much of
        itself the panel and the sequence strip have taken. Falls back to the
        widget's own size, and then to 800x600, so a viewer without a real
        widget -- the mock the tests use, a headless session -- still traces
        something rather than refusing.
        """
        default = (800, 600)
        renderer = getattr(viewer, "_renderer", None)
        widget = None
        if renderer is not None and hasattr(renderer, "widget"):
            try:
                widget = renderer.widget()
            except Exception:
                widget = None
        if widget is None:
            return default
        sizer = getattr(widget, "scene_pixel_size", None)
        if callable(sizer):
            try:
                width, height = sizer()
                if width > 0 and height > 0:
                    return int(width), int(height)
            except Exception:
                pass
        try:
            if widget.width() > 0 and widget.height() > 0:
                return int(widget.width()), int(widget.height())
        except Exception:
            pass
        return default

    @command("ray")
    def ray(self, *tokens: str) -> None:
        """Ray-trace the current scene.

        PyMOL syntax: ray [width, [height]] or ray filename, width, height
        Default output: chimol_ray_YYYYMMDD_HHMMSS.png
        """
        window, viewer = self._require_window_and_viewer()
        if viewer is None:
            return

        args = list(tokens)
        default_w, default_h = 800, 600
        width = default_w
        height = default_h

        # Rejoin with commas so the filename-vs-size detection below keeps the
        # structure the central tokenizer already split on.
        joined = ", ".join(args).strip()
        output_path: str | None = None

        if joined:
            if "," in joined:
                parts = [p.strip() for p in joined.split(",")]

                def _number(text: str) -> int | None:
                    """*text* as an int, or ``None`` when it is not a number."""
                    try:
                        return int(float(text))
                    except (ValueError, TypeError):
                        return None

                # A leading *number* is a width, not a filename. PyMOL spells
                # this `ray 200, 150`, and reading the first field as a name
                # unconditionally turned that into a file called `200.png`
                # traced at the default size -- so the one form users actually
                # type both ignored the size it was given and littered the
                # working directory.
                first = _number(parts[0]) if parts[0] else None
                if parts[0] and first is None:
                    output_path = parts[0]
                    rest = parts[1:]
                else:
                    rest = parts
                nums = [n for n in (_number(p) for p in rest) if n is not None]
            else:
                nums = []
                for tok in joined.split():
                    try:
                        nums.append(int(float(tok)))
                    except (ValueError, TypeError):
                        continue
        else:
            nums = []

        # What the viewport actually shows, which is the scene *column* and not
        # the widget -- the panel has a column of its own and the sequence
        # viewer a band. PyMOL: "default width and height are taken from the
        # current viewpoint. If one is specified but not the other, then the
        # missing value is scaled so as to preserve the current aspect ratio."
        scene_w, scene_h = self._scene_pixel_size(viewer)

        explicit_size = False
        if len(nums) >= 2 and nums[0] > 0 and nums[1] > 0:
            width, height = nums[0], nums[1]
            explicit_size = True
        elif len(nums) >= 1 and nums[0] > 0:
            width = nums[0]
            # The current aspect, not a fixed 4:3. A hard-coded 0.75 traces a
            # different field from the one on screen for every window that is
            # not 4:3, which is most of them.
            height = max(1, int(round(width * scene_h / max(scene_w, 1))))
            explicit_size = True

        if not explicit_size:
            width, height = scene_w, scene_h

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if output_path:
            out_path = Path(output_path).expanduser()
        else:
            out_path = Path(tempfile.gettempdir()) / f"chimol_ray_{timestamp}.png"
        if out_path.suffix.lower() != ".png":
            out_path = out_path.with_suffix(".png")

        grab_current = None
        if callable(grab_current):
            try:
                image = grab_current(width=width, height=height)
            except Exception:
                image = None
            if image is not None:
                try:
                    parent = out_path.parent
                    parent.mkdir(parents=True, exist_ok=True)
                    if image.save(str(out_path), "PNG"):
                        show_overlay = getattr(viewer, "show_ray_overlay", None)
                        if callable(show_overlay):
                            show_overlay(image)
                        self._emit_message(
                            f"ray: wrote {out_path} ({width}x{height})"
                        )
                        return
                except Exception as exc:
                    self._emit_error(f"ray: failed to save image: {exc}")
                    return

        view_state_func = getattr(viewer, "get_ray_view_state", None)
        if not callable(view_state_func):
            self._emit_message("ray: viewer does not support ray tracing")
            return

        from ..config import _DISPLAY_CONFIG
        from ..renderer.raytracer import (
            TRACEABLE_KINDS,
            Sphere,
            _camera_from_view_state,
            render_scene,
            trace,
            traceable_geometry_counts,
        )

        try:
            view = view_state_func()
        except Exception as exc:
            self._emit_error(f"ray: failed to read the camera: {exc}")
            return
        camera = _camera_from_view_state(view)

        # The scene is what the viewport draws -- cartoon, sticks, surface,
        # spheres, wireframe -- and the tracer takes all of it. This decision
        # used to be made from the *sphere* count instead, so a cartoon-only
        # display (the default) counted zero and `ray` refused with a message
        # about a limitation the tracer no longer had. Ask the scene.
        scene = None
        scene_func = getattr(viewer, "get_current_scene", None)
        if callable(scene_func):
            try:
                scene = scene_func()
            except Exception:
                scene = None
        counts = traceable_geometry_counts(scene)
        dropped = {k: v for k, v in counts.items() if k not in TRACEABLE_KINDS}
        use_scene_path = any(k in TRACEABLE_KINDS for k in counts)

        # Where the depth cue starts and ends. `render_scene` derives these from
        # the scene's own bounds; the sphere fallback below has to say it here.
        fog_front: float | None = None
        fog_back: float | None = None

        spheres: list = []
        if not use_scene_path:
            if scene is not None:
                # A viewer that produced a scene has told us everything it draws.
                # Falling through to the atoms here gave a second opinion that
                # disagreed: after `hide everything` the scene was empty and the
                # viewport blank, while `get_atom_sphere_data(visible_only=True)`
                # still offered the 32 ligand atoms -- and `ray` drew them.
                if dropped:
                    kinds = ", ".join(sorted(dropped))
                    self._emit_error(
                        f"ray: the only thing shown is {kinds} geometry, which the "
                        "ray tracer does not draw. Use 'png' to capture it as "
                        "displayed."
                    )
                else:
                    self._emit_message("ray: nothing is shown; nothing to trace")
                return

            sphere_data = getattr(viewer, "get_atom_sphere_data", None)
            if not callable(sphere_data):
                self._emit_message("ray: viewer does not support ray tracing")
                return
            try:
                # What is *drawn*, not every atom: `ray` used to trace the whole
                # molecule in every state, so `hide everything` and
                # `show spheres, resn NAG` gave the identical picture.
                positions, colors_rgb, radii = sphere_data(visible_only=True)
            except TypeError:
                positions, colors_rgb, radii = sphere_data()
            except Exception as exc:
                self._emit_error(f"ray: failed to extract scene data: {exc}")
                return

            if positions.shape[0] == 0:
                # Distinguish "nothing is shown" from "what is shown cannot be
                # traced": only the second is a limitation of the tracer, and the
                # user can act on either.
                if dropped:
                    kinds = ", ".join(sorted(dropped))
                    self._emit_error(
                        f"ray: the only thing shown is {kinds} geometry, which the "
                        "ray tracer does not draw. Use 'png' to capture it as "
                        "displayed."
                    )
                else:
                    self._emit_message("ray: nothing is shown; nothing to trace")
                return

            for i in range(positions.shape[0]):
                spheres.append(Sphere(
                    center=positions[i],
                    radius=float(radii[i]) if i < len(radii) else 1.0,
                    color=np.clip(colors_rgb[i], 0.0, 1.0),
                ))

            try:
                along = (positions - camera.origin) @ camera.forward
                fog_front = float(np.nanmin(along - radii))
                fog_back = float(np.nanmax(along + radii))
            except Exception:
                fog_front = fog_back = None

        # A gap that is shown beats a gap that is hidden: labels are rasterised
        # glyphs and the tracer has no glyph, so say they are missing from the
        # image rather than let the user hunt for them in it.
        if dropped:
            kinds = ", ".join(f"{n} {k}" for k, n in sorted(dropped.items()))
            self._emit_message(f"ray: not traced and absent from the image: {kinds}")


        ray_cfg = _DISPLAY_CONFIG.get("ray", {})
        light_cfg = _DISPLAY_CONFIG.get("lighting", {})

        # Legacy single light direction (fallback)
        legacy_light_dir = np.asarray(
            light_cfg.get("light_direction", [0.0, 0.0, 1.0]),
            dtype=float,
        )
        # New multi-light from ray config
        light_dirs = ray_cfg.get("light_directions", [[0.0, 0.0, 1.0]])
        light_dirs_arr = np.asarray(light_dirs, dtype=float)
        if light_dirs_arr.ndim == 1:
            light_dirs_arr = light_dirs_arr.reshape(1, 3)

        ambient = float(ray_cfg.get("ambient", 0.14))
        diffuse = float(ray_cfg.get("diffuse", 0.45))
        specular = float(ray_cfg.get("specular", 0.25))
        shininess = float(ray_cfg.get("shininess", 40.0))
        direct_specular = float(ray_cfg.get("direct_specular", 0.30))
        direct_specular_power = float(ray_cfg.get("direct_specular_power", 55.0))
        reflect_power = float(ray_cfg.get("reflect_power", 1.0))
        direct = float(ray_cfg.get("direct", 0.45))
        direct_power = float(ray_cfg.get("power", 1.0))
        legacy_lighting = float(ray_cfg.get("legacy_lighting", 0.0))
        ssaa_val = int(ray_cfg.get("antialias", 2))
        gamma = float(ray_cfg.get("gamma", 2.2))
        shadow_enabled = bool(ray_cfg.get("shadow", True))
        shadow_fudge = float(ray_cfg.get("shadow_fudge", 0.001))
        shadow_decay_factor = float(ray_cfg.get("shadow_decay_factor", 0.2))
        shadow_decay_range = float(ray_cfg.get("shadow_decay_range", 1.8))
        # The same three the viewport reads: PyMOL's depth cue is global, so
        # a traced image and the screen must not be able to disagree about it.
        cue_cfg = _DISPLAY_CONFIG.get("depth_cue", {}) or {}
        depth_cue = bool(cue_cfg.get("enabled", True))
        fog_start = float(cue_cfg.get("start", 0.45))
        fog_intensity = float(cue_cfg.get("intensity", 1.0))
        color_blend = bool(ray_cfg.get("color_blend", True))
        color_blend_red = float(ray_cfg.get("color_blend_red", 0.17))
        color_blend_green = float(ray_cfg.get("color_blend_green", 0.25))
        color_blend_blue = float(ray_cfg.get("color_blend_blue", 0.14))

        # The *live* background, not the configured one. `bg_color` writes to
        # the renderer and `ray` read the configuration, so the two disagreed
        # from the moment anyone set a background: `bg_color white; ray` traced
        # onto black. The configuration is the fallback for a viewer that has no
        # renderer yet, which is the only case it is right for.
        # Asked for rather than assumed: `ray` is written against any viewer
        # that can describe its scene, and one that cannot say what its
        # background is falls back to the configured value.
        reader = getattr(viewer, "get_background_color", None)
        live_background = reader() if callable(reader) else None
        bg_rgb = self._parse_background(
            live_background
            if live_background is not None
            else _DISPLAY_CONFIG.get("background", "k")
        )

        # PyMOL's own two settings for how thick a traced line comes out; see
        # `line_radius_for_camera`.
        line_width = float(_DISPLAY_CONFIG.get("line_width", 1.0))
        line_radius = float(ray_cfg.get("line_radius", 0.0))

        progress = np.zeros(1, dtype=np.int64)
        cancel = np.zeros(1, dtype=np.int64)
        total_rows = height * max(1, ssaa_val)

        # The first render of a session compiles the tracer's shader, which is a
        # fraction of a second rather than the ~30 s the numba build cost -- but
        # it is still the largest part of a small render, and with nothing said
        # it reads as "ray is slow". The note is cheap; say it once.
        from ..renderer import compute

        if not compute.shader_compiled("raytrace.wgsl"):
            self._emit_message(
                "ray: compiling the tracer -- once per session, well under a second"
            )

        if use_scene_path:
            shown = ", ".join(f"{n} {k}" for k, n in sorted(counts.items()) if k in TRACEABLE_KINDS)
            self._emit_message(
                f"ray: rendering the current scene ({shown}) at {width}x{height} ..."
            )

            def _render_scene() -> np.ndarray:
                return render_scene(
                    scene=scene,
                    camera=camera,
                    light_directions=light_dirs_arr,
                    width=width,
                    height=height,
                    background=bg_rgb,
                    ambient=ambient,
                    diffuse=diffuse,
                    specular=specular,
                    shininess=shininess,
                    ssaa=ssaa_val,
                    direct_specular=direct_specular,
                    direct_specular_power=direct_specular_power,
                    reflect_power=reflect_power,
                    direct=direct,
                    direct_power=direct_power,
                    legacy_lighting=legacy_lighting,
                    shadow=shadow_enabled,
                    shadow_fudge=shadow_fudge,
                    shadow_decay_factor=shadow_decay_factor,
                    shadow_decay_range=shadow_decay_range,
                    gamma=gamma,
                    depth_cue=depth_cue,
                    fog_start=fog_start,
                    fog_intensity=fog_intensity,
                    color_blend=color_blend,
                    color_blend_red=color_blend_red,
                    color_blend_green=color_blend_green,
                    color_blend_blue=color_blend_blue,
                    line_width=line_width,
                    line_radius=line_radius,
                    progress=progress,
                    cancel=cancel,
                )

            render_func = _render_scene
        else:
            self._emit_message(f"ray: tracing {len(spheres)} spheres at {width}x{height} ...")

            def _render_trace() -> np.ndarray:
                return trace(
                    spheres=spheres,
                    camera=camera,
                    light_directions=light_dirs_arr,
                    width=width,
                    height=height,
                    background=bg_rgb,
                    ambient=ambient,
                    diffuse=diffuse,
                    specular=specular,
                    shininess=shininess,
                    ssaa=ssaa_val,
                    direct_specular=direct_specular,
                    direct_specular_power=direct_specular_power,
                    reflect_power=reflect_power,
                    direct=direct,
                    direct_power=direct_power,
                    legacy_lighting=legacy_lighting,
                    shadow=shadow_enabled,
                    shadow_fudge=shadow_fudge,
                    shadow_decay_factor=shadow_decay_factor,
                    shadow_decay_range=shadow_decay_range,
                    gamma=gamma,
                    depth_cue=depth_cue,
                    fog_start=fog_start,
                    fog_intensity=fog_intensity,
                    fog_front=fog_front,
                    fog_back=fog_back,
                    color_blend=color_blend,
                    color_blend_red=color_blend_red,
                    color_blend_green=color_blend_green,
                    color_blend_blue=color_blend_blue,
                    progress=progress,
                    cancel=cancel,
                )

            render_func = _render_trace

        self._render_ray_async(
            render_func=render_func,
            progress=progress,
            cancel=cancel,
            total_rows=total_rows,
            out_path=out_path,
            width=width,
            height=height,
            viewer=viewer,
            window=window,
        )

    def _render_ray_async(
        self,
        render_func: Callable[[], np.ndarray],
        progress: np.ndarray,
        cancel: np.ndarray,
        total_rows: int,
        out_path: Path,
        width: int,
        height: int,
        viewer: object,
        window: object | None,
    ) -> None:
        """Run *render_func* in a background thread and report progress.

        The progress display goes wherever :class:`ChiSurfProgress` puts it (a
        host panel's bar, or a standalone dialog) while the application event
        loop stays alive. It shows a bar, an ETA and a Cancel button. When no
        real GUI window is available (e.g. tests), rendering falls back to the
        synchronous path.

        ``ChiSurfProgress`` is a *facade*, not a ``QProgressDialog``: it speaks
        ``set_value``/``set_text``/``was_canceled`` and takes its title and its
        cancel callback in the constructor. This code called the Qt spelling of
        all of that, so `ray` raised ``'ChiSurfProgress' object has no attribute
        'setMinimumSize'`` before a single ray was cast -- every time it ran with
        a window, which is every time a user runs it.
        """
        # Imported here, not at module scope: this method is the only one in
        # the file that needs a window system, and the rest of the file writes
        # PDB and mmCIF.
        from qtpy import QtCore, QtWidgets

        from chisurf.gui.progress import ChiSurfProgress

        parent = window if isinstance(window, QtWidgets.QWidget) else None
        if parent is None:
            # Headless / test context: run synchronously without a dialog.
            started = time.time()
            try:
                image = render_func()
            except Exception as exc:
                self._emit_error(f"ray: {exc}")
                return
            self._finish_ray(
                image, out_path, width, height, viewer, window, started
            )
            return

        def _cancel_render() -> None:
            self._on_ray_cancel(cancel, dialog)

        dialog = ChiSurfProgress(
            parent,
            "Ray tracing...",
            total_rows,
            title="Rendering",
            cancel=_cancel_render,
        )

        start_time = time.time()
        timer = QtCore.QTimer(parent)
        timer.timeout.connect(
            lambda: self._update_ray_progress(
                dialog, progress, cancel, total_rows, start_time,
            )
        )
        timer.start(100)

        thread = ray_render_thread_class()(render_func, parent=parent)
        thread.finished.connect(
            lambda image: self._on_ray_finished(
                image, cancel, out_path, width, height, viewer, window, dialog, timer, thread,
                start_time,
            )
        )
        thread.error.connect(
            lambda msg: self._on_ray_error(msg, dialog, timer, thread)
        )
        thread.start()

    def _update_ray_progress(
        self,
        dialog: ChiSurfProgress,
        progress: np.ndarray,
        cancel: np.ndarray,
        total_rows: int,
        start_time: float,
    ) -> None:
        """Poll the shared progress counter and update the dialog + ETA.

        When the render thread reports real progress (NumPy path), we use it
        directly.  When it does not (Numba path — atomic-free to keep the
        hot loop fast), we fall back to a time-based estimate so the user
        still sees a moving bar and an ETA.
        """
        try:
            current = int(progress[0])
        except Exception:
            current = 0

        elapsed = time.time() - start_time
        if cancel[0] != 0:
            text = "Cancelling..."
        elif current > 0:
            current = min(current, total_rows)
            dialog.set_value(current)
            fraction = current / total_rows if total_rows > 0 else 0.0
            if fraction > 0.02:
                eta = elapsed / fraction - elapsed
                text = (
                    f"Ray tracing... {int(fraction * 100)}%  "
                    f"ETA: {max(0, int(eta))}s  (elapsed: {int(elapsed)}s)"
                )
            else:
                text = f"Ray tracing... {int(fraction * 100)}%  (elapsed: {int(elapsed)}s)"
        else:
            # Time-based estimate: assume ~150k SSAA-rows per second on a
            # modest machine; clamp to 99% so we never claim completion.
            est_total = max(1, total_rows) / 150_000.0
            fraction = min(0.99, elapsed / est_total) if est_total > 0 else 0
            dialog.set_value(int(fraction * total_rows))
            text = f"Ray tracing...  (elapsed: {int(elapsed)}s)"
        dialog.set_text(text)

    def _on_ray_cancel(
        self,
        cancel: np.ndarray,
        dialog: ChiSurfProgress,
    ) -> None:
        """Signal the background thread to stop rendering."""
        cancel[0] = 1
        dialog.set_text("Cancelling...")

    def _finish_ray(
        self,
        image: object,
        out_path: Path,
        width: int,
        height: int,
        viewer: object,
        window: object | None,
        started: float | None = None,
    ) -> None:
        """Save the ray-traced image, show the overlay and emit a message.

        The elapsed time is part of the message because `ray` is the one command
        whose cost varies by orders of magnitude with the scene, and a report of
        "slow" that carries no number cannot be acted on -- it took a session of
        measuring to establish that a render this tool called slow was under a
        second, and the machine was loaded. Saying it costs one string.
        """
        try:
            if image is None:
                self._emit_error("ray: render returned no image")
                return
            from PIL import Image
            img = Image.fromarray(image)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(out_path), "PNG")
            show_overlay = getattr(viewer, "show_ray_overlay", None)
            if callable(show_overlay):
                # The array itself, not a QImage. Building a QImage here made
                # *displaying* a traced frame depend on a toolkit that tracing
                # does not need: on the Qt-free host `ray` wrote the PNG,
                # reported success and showed nothing. The renderer accepts
                # either and converts if its own paint path wants one.
                try:
                    show_overlay(np.ascontiguousarray(image))
                except Exception:  # noqa: BLE001 - the file is already written
                    pass
            took = "" if started is None else f" in {time.time() - started:.1f}s"
            self._emit_message(
                f"ray: wrote {out_path} ({width}x{height}){took}"
            )
        except Exception as exc:
            self._emit_error(f"ray: failed to save image: {exc}")
        finally:
            try:
                if window is not None:
                    window._update_sequence_view()
            except Exception:
                pass

    def _on_ray_finished(
        self,
        image: object,
        cancel: np.ndarray,
        out_path: Path,
        width: int,
        height: int,
        viewer: object,
        window: object | None,
        dialog: ChiSurfProgress,
        timer: QtCore.QTimer,
        thread: "QtCore.QThread",
        started: float,
    ) -> None:
        """Take the progress display down and save what the thread rendered.

        ``dialog`` is a :class:`ChiSurfProgress`, which owns and releases its own
        backend in ``close()`` -- it is not a ``QObject``, so it has no
        ``deleteLater`` to call here.
        """
        timer.stop()
        dialog.close()
        if cancel[0] != 0:
            self._emit_message("ray: cancelled")
        else:
            self._finish_ray(
                image, out_path, width, height, viewer, window, started
            )
        thread.deleteLater()
        timer.deleteLater()

    def _on_ray_error(
        self,
        msg: str,
        dialog: ChiSurfProgress,
        timer: QtCore.QTimer,
        thread: "QtCore.QThread",
    ) -> None:
        """Report a render that raised, and take the progress display down."""
        timer.stop()
        dialog.close()
        self._emit_error(f"ray: {msg}")
        thread.deleteLater()
        timer.deleteLater()

    def _parse_background(self, spec) -> tuple:
        if isinstance(spec, str):
            spec = spec.strip().lower()
            if spec in ("k", "black"):
                return (0, 0, 0)
            if spec in ("w", "white"):
                return (255, 255, 255)
        try:
            items = np.asarray(spec, dtype=float).flatten()
            # RGBA as well as RGB: the renderer keeps an alpha, and taking only
            # a three-long sequence sent every live background to the fallback.
            if len(items) in (3, 4):
                return tuple(int(max(0, min(255, x * 255))) for x in items[:3])
        except Exception:
            pass
        return (0, 0, 0)

    def _save_png_from_renderer(
        self,
        viewer,
        path: Path,
        *,
        width: int | None,
        height: int | None,
    ) -> bool:
        renderer = getattr(viewer, "_renderer", None)
        if renderer is None:
            return False
        widget = renderer.widget() if hasattr(renderer, "widget") else renderer
        grab = getattr(widget, "grabFramebuffer", None)
        if not callable(grab):
            return False
        if width or height:
            self._emit_message(
                "png: width/height currently use the live viewport; offscreen sizing is not implemented"
            )
        # A saved image is a picture of the *scene*. The in-viewport windows are
        # tools laid over it, not part of the molecule, so they come out for the
        # grab and go straight back -- PyMOL's own output carries no GUI either.
        with self._windows_hidden(renderer):
            image = grab()
        parent = path.parent
        parent.mkdir(parents=True, exist_ok=True)
        return bool(image.save(str(path), "PNG"))

    @contextmanager
    def _windows_hidden(self, renderer):
        """Draw a frame without the in-viewport windows, then restore them."""
        gui = getattr(renderer, "_internal_gui", None)
        if gui is None or not getattr(gui, "draw_windows", False):
            yield
            return
        gui.draw_windows = False
        try:
            update = getattr(renderer, "update", None)
            repaint = getattr(renderer, "repaint", None)
            # `repaint` rather than `update`: the grab happens inside this block
            # and an `update` only *schedules* a paint, so the windows would
            # still be in the buffer that gets saved.
            (repaint or update or (lambda: None))()
            yield
        finally:
            gui.draw_windows = True
            update = getattr(renderer, "update", None)
            if callable(update):
                update()

    def _parse_optional_int(self, parts: list[str], index: int) -> int | None:
        if index >= len(parts):
            return None
        text = parts[index].strip()
        if not text:
            return None
        if "=" in text:
            _, text = text.split("=", 1)
            text = text.strip()
        try:
            value = int(float(text))
        except Exception:
            return None
        return value if value > 0 else None

    def _parse_optional_bool(self, parts: list[str], index: int) -> bool:
        if index >= len(parts):
            return False
        text = parts[index].strip().lower()
        if "=" in text:
            _, text = text.split("=", 1)
            text = text.strip().lower()
        return text in ("1", "true", "yes", "on")
