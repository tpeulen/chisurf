"""Camera, viewport and scene bookkeeping, shared by every non-GL backend.

Why this is its own module
--------------------------
A renderer is two things: something that holds a camera and a scene, and
something that turns them into pixels. Only the second half is backend-specific,
and this port has now paid three times for treating a shared quantity as
something each backend re-derives -- the depth-cue planes, the light rig, and the
shading model itself. The camera is the one that would hurt most: two backends
that frame a scene differently cannot be compared at all, and the comparison is
the only way this port is being verified.

So :class:`CameraState` holds it once. :class:`~.headless.SceneSink` is this and
nothing else; the WebGPU widget is this plus a surface to draw on. Both therefore
answer ``get_view_state()`` with the same eighteen floats for the same commands,
which is what makes a headless replay reproduce a windowed frame.

The camera is PyMOL's 18-float view tuple throughout (:mod:`.view_state`).
"""
from __future__ import annotations

import math
from typing import Optional

import numpy as np

from .scene import Scene
from .view_state import (
    distance_for_radius,
    pack_view_state,
    portrait_factor,
    unpack_view_state,
)


def trackball_delta(
    last: tuple[float, float],
    cur: tuple[float, float],
    width: float,
    height: float,
    *,
    mouse_scale: float = 1.3,
) -> np.ndarray:
    """PyMOL's virtual-trackball delta rotation, as a camera-space 3x3.

    Projects the previous and current cursor onto a sphere of radius
    ``0.45 * min(W, H)``, takes the rotation carrying one to the other, and damps
    the roll component -- see ``SceneMouse.cpp``. The result **left-multiplies**
    the current world-to-camera rotation.

    Shared rather than reimplemented per backend: two viewers whose drags turn
    the molecule by different amounts are two different programs, and the
    difference is the kind a screenshot comparison never catches because every
    frame is individually correct.

    Parameters
    ----------
    last, cur : tuple of float
        Cursor positions in widget pixels, Qt's top-left origin.
    width, height : float
        Viewport size in the same pixels.
    mouse_scale : float, optional
        PyMOL's ``mouse_scale``.

    Returns
    -------
    numpy.ndarray
        A ``(3, 3)`` rotation.
    """
    scale = 0.45 * min(float(width), float(height))
    if scale <= 0.0:
        return np.eye(3)
    cx, cy = width / 2.0, height / 2.0

    def _sphere(px: float, py: float) -> np.ndarray:
        # Screen vector from centre; y is flipped (Qt top-left origin).
        vx = px - cx
        vy = cy - py
        r2 = vx * vx + vy * vy
        vz = math.sqrt(scale * scale - r2) if r2 < scale * scale else 0.0
        v = np.array([vx, vy, vz], dtype=float)
        n = np.linalg.norm(v)
        return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])

    n1 = _sphere(*last)
    n2 = _sphere(*cur)
    axis = np.cross(n1, n2)
    s = float(np.linalg.norm(axis))
    if s <= 1e-9:
        return np.eye(3)
    axis /= s
    angle = float(mouse_scale) * 2.0 * math.asin(min(s, 1.0))
    angle /= 1.0 + abs(axis[2])  # damp the twist component
    # PyMOL applies rotate(angle, ax, ay, -az); the screen axis lives in camera
    # space, so this delta left-multiplies the view rotation.
    ax, ay, az = axis[0], axis[1], -axis[2]
    c, sn = math.cos(angle), math.sin(angle)
    k = np.array([[0.0, -az, ay], [az, 0.0, -ax], [-ay, ax, 0.0]])
    return np.eye(3) + sn * k + (1.0 - c) * (k @ k)

#: Viewport reported when nothing has been requested. Chosen well above the
#: 16-pixel floor that a real widget can clamp to when it has never been laid
#: out, because framing maths divides by it and a degenerate viewport silently
#: produces a scene nothing can be judged from.
DEFAULT_VIEWPORT: tuple[int, int] = (1280, 860)


def _silhouette_config() -> dict:
    """The ``silhouette`` display-config section, or an empty one."""
    from ..config import _DISPLAY_CONFIG

    section = _DISPLAY_CONFIG.get("silhouette")
    if not isinstance(section, dict):
        # Created rather than returned empty: `set_lighting` writes into it, and
        # a fresh dict per call would accept the setting and drop it.
        section = {}
        _DISPLAY_CONFIG["silhouette"] = section
    return section


class CameraState:
    """The state a renderer holds, with no opinion about how it is drawn.

    Attributes
    ----------
    scene : Scene or None
        The most recent scene handed to :meth:`set_scene`.
    """

    def init_camera_state(self, size: tuple[int, int] = DEFAULT_VIEWPORT) -> None:
        """Initialise the camera and viewport.

        A method rather than ``__init__`` because the Qt subclass must run
        ``QWidget.__init__`` first and multiple inheritance through a Qt base is
        the kind of thing that fails at C++ level with no Python traceback.
        """
        self._width, self._height = int(size[0]), int(size[1])
        self.scene: Optional[Scene] = None
        self.internal_gui = None
        self._fov = 20.0
        self._background = (0.0, 0.0, 0.0, 1.0)
        self._grid_visible = False
        self._grid = (0.0, 0.0)
        self._origin = np.zeros(3, dtype=float)
        self._target = np.zeros(3, dtype=float)
        self._distance = 100.0
        self._target_radius = 10.0
        self._rotation = np.eye(3, dtype=float)
        self._near_clip = 10.0
        self._far_clip = 1000.0
        # Where framing last put the planes -- what `clip reset` returns to, and
        # what `clipping_is_default` is measured against.
        self._framed_near_clip = self._near_clip
        self._framed_far_clip = self._far_clip
        self._min_near_clip = 0.01
        self._max_near_clip = 10.0
        #: Fraction of the slab's own thickness one wheel notch moves it by.
        #: PyMOL's `0.1 * mouse_wheel_scale`; being a *fraction* is what makes
        #: the gesture feel the same on a peptide and on a ribosome.
        self._clip_wheel_scale = 0.85
        self._slab_wheel_fraction = 0.1
        #: Whether the slab is still the configured default. The first move
        #: fits it around the scene; after that it belongs to the user.
        self._slab_moved = False
        #: The aspect the current distance was derived at, so a resize that does
        #: not change the viewport's shape costs nothing.
        self._framed_aspect: Optional[float] = None
        self._orthoscopic = False
        # Three floats, not two: the view tuple carries an x/y/z shift.
        self._shift = np.zeros(3, dtype=float)
        self._lighting_overrides: dict = {}
        self.update_count = 0

    # -- what the viewer hands us -------------------------------------------

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Store ``scene``."""
        self.scene = scene

    def clear(self) -> None:
        """Drop the stored scene."""
        self.scene = None

    def set_background_color(self, color) -> None:
        """Store the clear colour as RGBA, from a name or any RGB(A) sequence.

        Resolved here rather than at draw time, because ``get_background_color``
        and the ray tracer read it too, and a stored ``"k"`` means each of them
        needs its own parser. The sequence test is by *shape*: the command
        layer's colour parser returns a numpy array, which is neither a tuple
        nor a list, and an isinstance check against those two fell through to
        black -- ``bg_color white`` then did nothing and reported success.
        """
        from ..colors import as_rgba

        rgba = as_rgba(color)
        self._background = tuple(float(c) for c in rgba) if rgba else (0.0, 0.0, 0.0, 1.0)

    def get_background_color(self) -> tuple:
        """The clear colour as RGBA in ``0..1``."""
        return tuple(self._background)

    def configure_grid(self, size: float, spacing: float) -> None:
        """Store the ground-grid dimensions."""
        self._grid = (float(size), float(spacing))

    def set_grid_visible(self, visible: bool) -> None:
        """Store ground-grid visibility."""
        self._grid_visible = bool(visible)

    def set_lighting(self, **values) -> None:
        """Set lighting parameters by name.

        Names are ChimeraX's -- ``key_light_intensity``,
        ``ambient_light_intensity``, ``silhouette`` and friends -- so a preset
        is just a dict of them and the command layer needs no translation table.

        The three silhouette values are written to the **display config**, not
        held here: that is the store ``set silhouette, on`` writes and the one
        both renderers read. Keeping a private copy is precisely how a setting
        ends up accepted and inert -- the renderer's copy moves the picture, the
        configuration is a start-up default nothing can change, and the two
        disagree with no way to tell which is in force.

        Raises
        ------
        ValueError
            On an unknown name. Silently ignoring one turns a typo into a
            setting that appears to work.
        """
        from .lighting import CHIMERAX_NAMES

        silhouette_keys = {"silhouette", "silhouette_thickness", "depth_jump"}
        known = set(CHIMERAX_NAMES) | silhouette_keys
        unknown = set(values) - known
        if unknown:
            raise ValueError(
                f"set_lighting: unknown parameter '{sorted(unknown)[0]}'. "
                f"Use one of: {', '.join(sorted(known))}"
            )
        section = _silhouette_config()
        for name, value in values.items():
            if name == "silhouette":
                section["enabled"] = bool(value)
            elif name == "silhouette_thickness":
                section["thickness"] = float(value)
            elif name == "depth_jump":
                section["depth_jump"] = float(value)
            else:
                self._lighting_overrides[name] = float(value)
        self.update()

    def lighting_state(self) -> dict:
        """The current lighting parameters, under ChimeraX's names.

        A *method*, matching the OpenGL backend: the viewer calls
        ``renderer.lighting_state()``, and an attribute of the same name would
        be returned uncalled and read as a dict of nothing.
        """
        from .lighting import CHIMERAX_NAMES, resolve_light_rig

        rig = resolve_light_rig()
        state = {
            name: float(getattr(rig, field))
            for name, field in CHIMERAX_NAMES.items()
        }
        state.update({k: float(v) for k, v in self._lighting_overrides.items()
                      if k in CHIMERAX_NAMES})
        silhouette = _silhouette_config()
        state.update({
            "silhouette": bool(silhouette.get("enabled", False)),
            "silhouette_thickness": float(silhouette.get("thickness", 1.0)),
            "depth_jump": float(silhouette.get("depth_jump", 0.03)),
        })
        return state

    def configure_camera(
        self,
        *,
        near_clip: float,
        far_clip: float,
        min_near_clip: float,
        max_near_clip: float,
        clip_wheel_scale: float,
    ) -> None:
        """Set the clipping planes and the limits a gesture may move them within."""
        self._min_near_clip = max(float(min_near_clip), 1e-5)
        self._max_near_clip = max(float(max_near_clip), self._min_near_clip * 1.01)
        self._clip_wheel_scale = (
            clip_wheel_scale if 0.0 < clip_wheel_scale < 1.0 else 0.85
        )
        self._near_clip = self._clamp_near_clip(float(near_clip))
        self._framed_near_clip = self._near_clip
        self._framed_far_clip = self._far_clip
        self._far_clip = max(float(far_clip), self._near_clip * 10.0)
        self.update()

    # -- clipping ------------------------------------------------------------

    def _clamp_near_clip(self, value: float) -> float:
        """Keep the near plane inside the range a gesture may reach."""
        return float(min(max(float(value), self._min_near_clip), self._max_near_clip))

    def clipping_is_default(self) -> bool:
        """Whether the near plane still sits where framing put it."""
        return abs(self._near_clip - self._framed_near_clip) < 1e-9

    def reset_clipping(self) -> None:
        """Put the clip planes back where framing left them.

        A slab cut into a closed surface opens it, and what you then see is the
        *inside*: everything within renders unblended at full brightness, which
        reads as broken transparency rather than as a cut. Since the gesture is
        one stray shift-scroll away, there has to be a way back that does not
        require knowing what happened.
        """
        self._near_clip = self._clamp_near_clip(self._framed_near_clip)
        self._far_clip = self._framed_far_clip
        self.update()

    def adjust_clip(self, mode: str, dist: float) -> None:
        """Move the near/far clip planes (PyMOL ``clip``)."""
        m = str(mode).lower()
        if m in ("reset", "off", "none"):
            self.reset_clipping()
            return
        d = float(dist)
        if m in ("near", "front"):
            self._near_clip = self._clamp_near_clip(self._near_clip + d)
        elif m in ("far", "back"):
            self._far_clip = max(self._far_clip + d, self._near_clip * 10.0)
        elif m == "slab":
            mid = 0.5 * (self._near_clip + self._far_clip)
            half = max(0.5 * abs(d), self._near_clip)
            self._near_clip = self._clamp_near_clip(mid - half)
            self._far_clip = max(mid + half, self._near_clip * 10.0)
        elif m == "move":
            self._near_clip = self._clamp_near_clip(self._near_clip + d)
            self._far_clip = max(self._far_clip + d, self._near_clip * 10.0)
        else:
            return
        self.update()

    def move_slab(self, steps: int, dolly: bool = False) -> bool:
        """Slide the whole clipping slab by ``steps`` wheel notches.

        By a **fraction of the slab's own thickness**, which is scale-free: one
        wheel step is one step whether the molecule is a peptide or a ribosome.

        Not through :meth:`adjust_clip`, and that is the point: ``adjust_clip``
        clamps the near plane into the range a *typed* ``clip near`` may reach,
        and a clamp makes the gesture asymmetric -- scroll out and back and the
        plane does not return, so the status line can never say "off" again.
        Here the only guard is that the slab must not turn inside out or cross
        the camera, because a near plane at or behind zero makes the projection
        singular and the scene vanishes rather than clips.

        Parameters
        ----------
        steps : int
            Wheel notches; negative moves the slab toward the camera.
        dolly : bool
            Move the camera with it (PyMOL's ``MvSZ``), so the slab stays put
            against the molecule and the view dollies instead.

        Returns
        -------
        bool
            Whether the slab moved. It refuses rather than clamping.
        """
        if not steps:
            return False
        self.fit_slab_to_scene()
        thickness = max(float(self._far_clip) - float(self._near_clip), 1e-6)
        shift = thickness * self._slab_wheel_fraction * float(steps)
        near = float(self._near_clip) + shift
        far = float(self._far_clip) + shift
        if not (near > self._min_near_clip and far > near):
            return False
        self._near_clip, self._far_clip = near, far
        if dolly:
            self._distance = max(float(self._distance) + shift, 0.1)
        return True

    def announce_clipping(self) -> None:
        """Say that the slab moved, and how to put it back.

        Shift+wheel is one stray gesture away from slicing the model open, and a
        cut closed surface does not look cut -- it looks like the transparency
        stopped working, because everything inside it is suddenly unblended and
        at full brightness. Reported as exactly that, more than once. A silent,
        sticky mode change with no way back is the actual defect; saying what
        happened costs one line in the status bar.
        """
        report = getattr(getattr(self, "_controller", None), "report_status", None)
        if not callable(report):
            return
        try:
            if self.clipping_is_default():
                report("Clipping: off")
            else:
                report(
                    f"Clipping: near plane at {self._near_clip:.3g} "
                    "\N{EM DASH} shift+wheel to adjust, 'clip reset' to restore"
                )
        except Exception:
            pass

    # -- viewport ------------------------------------------------------------

    def width(self) -> int:
        """Viewport width in pixels."""
        return self._width

    def height(self) -> int:
        """Viewport height in pixels."""
        return self._height

    def scene_width(self) -> int:
        """Width of the 3-D column. No panel is reserved, so the full width."""
        return self._width

    def scene_height(self) -> int:
        """Height of the 3-D column. No strip is reserved, so the full height."""
        return self._height

    def resize(self, width: int, height: int) -> None:
        """Set the reported viewport, and re-frame if its shape changed."""
        self._width, self._height = int(width), int(height)
        self.reframe_for_aspect()

    #: Below this many pixels the scene column is not a viewport, it is a widget
    #: that has not been laid out yet. Chosen well under any usable window and
    #: well over the 1-pixel floor `scene_width` clamps to.
    _MIN_MEASURABLE_SCENE = 16

    def _aspect(self) -> float:
        """Viewport width over height, for PyMOL's portrait framing correction.

        A widget that has never been laid out reports a size Qt has not
        computed yet -- and with a docked panel the remainder can go negative,
        which `scene_width` clamps to **1**. An aspect of 1/30 then tells the
        framing correction the window is thirty times taller than it is wide and
        puts the camera thirty times too far away. That is not a portrait
        window; it is no window at all, and the correction has nothing to
        correct for until there is one.
        """
        width, height = self.scene_width(), self.scene_height()
        if width < self._MIN_MEASURABLE_SCENE or height < self._MIN_MEASURABLE_SCENE:
            return 1.0
        return width / float(height)

    def reframe_for_aspect(self) -> None:
        """Re-derive the camera distance when the viewport's shape changes.

        PyMOL's framing correction only applies to a **portrait** viewport, so
        the distance that framed a molecule in a wide window is wrong in a tall
        one and the molecule spills off the sides. Nothing else re-derives it: a
        resize triggers no rebuild, so without this the correction is applied
        once, at whatever shape the window happened to have when the structure
        was framed.

        The distance is **scaled** by the change in the correction rather than
        recomputed from the framed radius, and that is the whole subtlety: the
        scroll wheel moves ``_distance`` without touching ``_target_radius``, so
        recomputing would snap a hand-zoomed view back to wherever the last
        ``zoom`` left it.

        Only the distance is touched. The near and far clips carry a user's
        ``clip`` adjustments, and a window resize is not a request to discard
        them.
        """
        aspect = self._aspect()
        previous = getattr(self, "_framed_aspect", None)
        if aspect == previous:
            return
        self._framed_aspect = aspect
        if previous is None:
            return
        ratio = portrait_factor(aspect) / portrait_factor(previous)
        if ratio != 1.0:
            self._distance = max(self._distance * ratio, 5.0)

    # -- camera --------------------------------------------------------------

    def fit_to_radius(self, radius: float) -> None:
        """Pull the camera back far enough to frame ``radius``."""
        self._target_radius = max(float(radius), 1.0)
        self._framed_aspect = self._aspect()
        self._distance = max(
            distance_for_radius(
                self._target_radius, self._fov, aspect=self._framed_aspect
            ),
            5.0,
        )
        # The slab, and it is deliberately generous at both ends. It was
        # `radius * 0.02` to `(distance + radius) * 1.2`, which cuts close on a
        # molecule the camera is near and leaves little room behind it -- so
        # rotating a structure clipped its front and back before it had turned
        # far. A slab is a tool for looking *into* something; the default should
        # be to show the whole object and let `clip` narrow it deliberately.
        self._near_clip = self._clamp_near_clip(
            max(self._target_radius * 0.01, self._min_near_clip)
        )
        max_extent = self._distance + self._target_radius
        self._far_clip = max(float(max_extent) * 2.2, self._near_clip * 10.0)

        # Framing is what *defines* "not clipped": `clip reset` comes back here,
        # and so a stray shift-scroll is undone by `zoom` on its own -- which
        # matters more than the command, because someone whose view has gone
        # strange reaches for zoom long before they suspect the clip planes.
        self._framed_near_clip = self._near_clip
        self._framed_far_clip = self._far_clip
        # The slab is the configured default again, so the next wheel gesture
        # may re-fit it around the scene.
        self._slab_moved = False

    def fit_slab_to_scene(self) -> None:
        """Put the slab around the molecule, once, before it is first moved.

        The clipping planes come from the configuration, and nothing re-derives
        them from what is actually on screen -- so the near plane can sit far in
        *front* of the molecule and the first several wheel clicks move a slab
        through empty space: the gesture works and the picture does not change,
        which is indistinguishable from the gesture doing nothing.

        PyMOL fits front and back around the scene (``SceneClipSet`` after a
        zoom), so a click is a click on a peptide and on a ribosome alike. Only
        while the slab is still the configured default: once it has been moved
        it is the user's, and must stay where they put it.
        """
        if getattr(self, "_slab_moved", False):
            return
        self._slab_moved = True
        radius = max(float(self._target_radius), 1e-3)
        near, far = float(self._distance) - radius, float(self._distance) + radius
        if near > self._min_near_clip and far > near:
            self._near_clip, self._far_clip = near, far
            # This *is* the framing, so it becomes the baseline "not clipped"
            # position: scroll one step out and back and the status line has to
            # say `Clipping: off` again, which it can only do if the reference
            # moved with the slab.
            self._framed_near_clip = near
            self._framed_far_clip = far

    def reset_view(self, distance: float, elevation: float, azimuth: float) -> None:
        """Place the camera on a spherical coordinate."""
        self._distance = float(distance)
        el, az = np.radians(float(elevation)), np.radians(float(azimuth))
        ce, se, ca, sa = np.cos(el), np.sin(el), np.cos(az), np.sin(az)
        self._rotation = np.array(
            [[ca, 0.0, -sa], [-se * sa, ce, -se * ca], [ce * sa, se, ce * ca]],
            dtype=float,
        )

    def set_distance(self, distance: float) -> None:
        """Set the camera-to-target distance."""
        self._distance = max(float(distance), 0.1)
        self.update()

    def set_field_of_view(self, fov: float) -> None:
        """Change the lens, keeping the molecule the same size on screen.

        The camera moves to compensate, which is how PyMOL behaves and what
        makes ``field_of_view`` a perspective control rather than a zoom one.
        """
        new_fov = abs(float(fov))
        if new_fov < 1e-3 or abs(new_fov - self._fov) < 1e-9:
            return
        self._fov = new_fov
        self._distance = max(
            distance_for_radius(self._target_radius, new_fov, aspect=self._aspect()),
            5.0,
        )
        self.update()

    def set_orientation(self, elevation: float, azimuth: float) -> None:
        """Point the camera from a spherical coordinate, keeping the distance."""
        distance = self._distance
        self.reset_view(distance, elevation, azimuth)
        self._distance = distance
        self.update()

    def turn(self, axis: str, angle_deg: float) -> None:
        """Rotate the camera about a **screen** axis (PyMOL ``turn``).

        ``x`` is right, ``y`` up, ``z`` toward the viewer. The delta
        left-multiplies the view rotation, as the trackball's does.
        """
        vec = {
            "x": (1.0, 0.0, 0.0),
            "y": (0.0, 1.0, 0.0),
            "z": (0.0, 0.0, 1.0),
        }.get(str(axis).lower())
        if vec is None:
            return
        a = math.radians(float(angle_deg))
        kx, ky, kz = vec
        k = np.array([[0.0, -kz, ky], [kz, 0.0, -kx], [-ky, kx, 0.0]])
        delta = np.eye(3) + math.sin(a) * k + (1.0 - math.cos(a)) * (k @ k)
        self._rotation = delta @ self._rotation
        self.update()

    def move(self, axis: str, dist: float) -> None:
        """Translate along a screen axis (PyMOL ``move``).

        x/y pan in the view plane; z dollies.
        """
        ax = str(axis).lower()
        d = float(dist)
        if ax == "x":
            self._target = self._target - d * self._rotation[0]
        elif ax == "y":
            self._target = self._target - d * self._rotation[1]
        elif ax == "z":
            self._distance = max(0.1, self._distance - d)
        else:
            return
        self.update()

    def look_at(self, target: np.ndarray) -> None:
        """Aim the camera at ``target``."""
        self._target = np.asarray(target, dtype=float).reshape(3).copy()

    def set_origin(self, origin: np.ndarray) -> None:
        """Move the point the camera rotates about, without moving the picture.

        This is PyMOL's ``origin``, which always passes ``preserve=1`` to
        ``SceneOriginSet``: the pivot changes and the view translation absorbs
        the difference, so nothing appears to happen until the next rotation,
        which then pivots about the chosen point. The compensation is
        ``SceneOriginSet``'s, transcribed -- the model-space difference rotated
        into camera space and added to the view offset::

            v0 = origin_new - origin_old        (model space)
            v1 = rotation @ v0                  (camera space)
            shift += v1

        Storing the new pivot and nothing else is what an ``origin`` that does
        nothing looks like: the camera keeps orbiting the old point, and the
        setting reads as unimplemented rather than as inert.
        """
        wanted = np.asarray(origin, dtype=float).reshape(3).copy()
        delta = wanted - self._target
        self._target = wanted
        self._shift = self._shift + self._rotation @ delta
        self._origin = wanted
        self.update()

    def get_origin(self) -> np.ndarray:
        """Return the rotation origin."""
        return self._origin.copy()

    def get_view_state(self) -> list[float]:
        """Return the camera as an 18-float tuple in PyMOL's ``get_view`` layout."""
        return pack_view_state(
            self._rotation,
            self._distance,
            self._target,
            self._near_clip,
            self._far_clip,
            self._fov,
            self._orthoscopic,
            shift=self._shift,
        )

    def set_view_state(self, view) -> None:
        """Restore an 18-float view tuple; see :mod:`.view_state` for layouts."""
        state = unpack_view_state(view)
        self._rotation = np.asarray(state.rotation, dtype=float).reshape(3, 3).copy()
        self._distance = max(float(state.distance), 0.1)
        self._target = np.asarray(state.target, dtype=float).reshape(3).copy()
        self._shift = np.asarray(state.shift, dtype=float).copy()
        self._near_clip = float(state.near)
        # Stored as given. The Qt/GL backend widens the far plane to protect its
        # depth buffer's precision; doing the same here would make
        # `set_view_state(get_view_state())` return a different camera than it
        # was handed -- and a view tuple that does not survive a round trip
        # cannot be used to reproduce a frame, which is the one job it has.
        self._far_clip = float(state.far)
        self._fov = float(state.fov)
        self._orthoscopic = bool(state.orthoscopic)

    def lighting_parameters(self) -> dict:
        """Only the overrides the viewer has set, under ChimeraX's names."""
        return dict(self._lighting_overrides)

    # -- projection ----------------------------------------------------------

    def scene_origin_y(self) -> int:
        """Where the 3-D column starts, measured down from the widget's top.

        The sequence strip's band. Exposed because both the projection and the
        render viewport need it and they must not disagree by a pixel: they are
        what decides whether a click lands on the atom under the cursor.
        """
        return max(self.height() - self.scene_height(), 0)

    def project_to_screen(self, points) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Where scene points land in the widget, in widget pixels.

        Through the **same matrices the frame is drawn with**, because a picker
        that computes its own projection picks where the molecule is not.

        Two things the maths has to respect and a from-scratch version keeps
        getting wrong: the viewport is the **scene column**, not the widget (the
        panel takes a column on the right), and it sits below the **sequence
        strip**, so a y measured from the widget's top is off by the strip's
        height.

        Parameters
        ----------
        points : array_like
            ``(n, 3)`` positions in scene space -- what the geometry carries.

        Returns
        -------
        tuple of numpy.ndarray
            ``(x, y, visible)``: widget pixel coordinates with the origin at the
            top left, and a boolean saying which points are in front of the
            camera. Points behind it carry meaningless coordinates.
        """
        from .wgpu_backend import perspective, view_matrix

        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
            empty = np.zeros(0, dtype=float)
            return empty, empty, np.zeros(0, dtype=bool)

        width = max(self.scene_width(), 1)
        height = max(self.scene_height(), 1)
        view = view_matrix(self._rotation, self._target, self._distance, self._shift)
        proj = perspective(
            self._fov, width / height, max(self._near_clip, 1e-3), max(self._far_clip, 1e-2)
        )
        mvp = np.asarray(proj @ view, dtype=float)

        homogeneous = np.column_stack([pts, np.ones(len(pts))])
        clip = homogeneous @ mvp.T
        w = clip[:, 3]
        visible = np.isfinite(w) & (w > 1e-9)
        ndc = np.zeros((len(pts), 2), dtype=float)
        ndc[visible] = clip[visible, :2] / w[visible, None]

        x = (ndc[:, 0] * 0.5 + 0.5) * width
        # Clip space is y-up and the widget's y runs down from its top; the
        # viewport starts under the strip.
        y = self.scene_origin_y() + (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * height
        return x, y, visible

    # -- gestures ------------------------------------------------------------

    def camera_axes(self) -> tuple[np.ndarray, np.ndarray]:
        """The camera's right and up axes in world space.

        The world-to-camera rotation keeps them in its *rows*, so they are read
        out rather than computed.
        """
        r = np.asarray(self._rotation, dtype=float)
        return r[0].copy(), r[1].copy()

    def orbit(self, last: tuple[float, float], cur: tuple[float, float]) -> None:
        """Turn the camera by a cursor drag, through PyMOL's trackball."""
        delta = trackball_delta(last, cur, self.scene_width(), self.scene_height())
        self._rotation = delta @ self._rotation

    def pan(self, dx: float, dy: float) -> None:
        """Slide the scene by a cursor delta, one pixel of scene per pixel of mouse.

        PyMOL's ``SceneGetScreenVertexScale`` is ``depth * 2 tan(fov/2) /
        Height`` -- the **same** scale on both axes, which is what keeps the
        molecule under the cursor. Multiplying the horizontal scale by the aspect
        ratio counts the aspect twice, because a perspective frustum is already
        ``height * aspect`` wide; that bug made horizontal panning run 1.7x the
        cursor on a 1278x631 viewport.
        """
        height = max(self.scene_height(), 1)
        half_tan = math.tan(math.radians(float(self._fov)) / 2.0)
        if half_tan <= 0.0:
            return
        scale = 2.0 * self._distance * half_tan / height
        right, up = self.camera_axes()
        self._target = self._target + (-dx * scale) * right + (dy * scale) * up

    def dolly(self, factor: float) -> None:
        """Move the camera along its own axis by a multiplicative ``factor``.

        Multiplicative, not additive: one wheel step has to feel the same on a
        peptide and on a ribosome, and only a ratio does.
        """
        self._distance = float(np.clip(self._distance * float(factor), 1e-3, 1e9))
