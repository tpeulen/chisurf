from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Any, List, Optional

import numpy as np
from qtpy import QtCore, QtGui, QtWidgets

try:  # PyOpenGL is the GL binding: raw entry points on a plain QOpenGLWidget.
    from OpenGL import GL  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    GL = None

from ..config import _DISPLAY_CONFIG
from .internal_gui import InternalGui
from ..mouse_modes import action_of as mouse_action_of
from ..mouse_modes import click_action_of
from .base import Renderer
from .scene import Geometry, Material, Scene, SceneObject
from .view_state import (
    DEFAULT_FOV,
    distance_for_radius,
    pack_view_state,
    portrait_factor,
    unpack_view_state,
)


# Minimal set of OpenGL enum values used by this renderer. These are
# stable across OpenGL versions, so we can hard-code them and avoid an
# additional PyOpenGL dependency while still driving Qt's GL functions.
GL_TRIANGLES = 0x0004
GL_LINES = 0x0001
logger = logging.getLogger(__name__)

GL_POINTS = 0x0000
GL_LINE_STRIP = 0x0003
GL_POINT_SPRITE = 0x8861

GL_DEPTH_TEST = 0x0B71
GL_CULL_FACE = 0x0B44
GL_BACK = 0x0405
GL_FRONT = 0x0404

GL_COLOR_BUFFER_BIT = 0x00004000
GL_DEPTH_BUFFER_BIT = 0x00000100

GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE_MINUS_SRC_ALPHA = 0x0303

GL_PROGRAM_POINT_SIZE = 0x8642
GL_FLOAT = 0x1406
GL_UNSIGNED_INT = 0x1405


def _invoke_menu(menu: QtWidgets.QMenu, pos: QtCore.QPoint):
    exec_fn = getattr(menu, "exec", None) or getattr(menu, "exec_", None)
    if exec_fn is None:
        raise AttributeError("QMenu.exec/exec_ not available")
    return exec_fn(pos)



def _image_from_rgb(array: np.ndarray) -> QtGui.QImage:
    """Wrap an ``(H, W, 3)`` uint8 array as a QImage that owns its bytes.

    The copy is deliberate: ``QImage`` does not take ownership of a numpy
    buffer, and a texture uploaded from one that has been garbage collected is
    a use-after-free that usually shows up as a black or torn image rather than
    a crash.
    """
    data = np.ascontiguousarray(array, dtype=np.uint8)
    height, width = data.shape[:2]
    image = QtGui.QImage(
        data.tobytes(), width, height, 3 * width, QtGui.QImage.Format_RGB888
    )
    return image.copy()


@dataclass
class _DrawData:
    primitive: int
    positions: np.ndarray
    colors: np.ndarray
    normals: np.ndarray
    render_mode: str
    size: float = 4.0
    width: float = 2.0
    depth_test: bool = True
    glyph: Optional[str] = None
    radii: Optional[np.ndarray] = None
    occlusion: Optional[np.ndarray] = None
    material: Any = None
    two_sided: bool = False
    #: Whether ``radii`` are distances in the model rather than pixel counts.
    #: Sphere impostors (an integrative model's beads) are the case that needs
    #: it: their size has to follow the camera.
    world_radius: bool = False
    #: Triangle indices, when the mesh can be drawn indexed. ``None`` means the
    #: vertices were already expanded into a flat triangle list.
    indices: Optional[np.ndarray] = None

@dataclass
class _LabelData:
    pos: np.ndarray
    text: str
    color: QtGui.QColor
    depth_test: bool = True


def _material_val(mat: Any, key: str, fallback: float) -> float:
    """Read a material parameter from either a Material dataclass or a dict."""
    if isinstance(mat, Material):
        return float(getattr(mat, key, fallback))
    if isinstance(mat, dict):
        return float(mat.get(key, fallback))
    return float(fallback)


@dataclass
class _GpuDrawCall:
    primitive: int
    vertex_count: int
    positions_vbo: QtGui.QOpenGLBuffer
    colors_vbo: QtGui.QOpenGLBuffer
    normals_vbo: QtGui.QOpenGLBuffer
    render_mode: str
    size: float
    width: float
    depth_test: bool
    depth: float = 0.0  # camera-space depth for transparent sorting
    glyph: Optional[str] = None
    radii_vbo: Optional[QtGui.QOpenGLBuffer] = None
    occlusion_vbo: Optional[QtGui.QOpenGLBuffer] = None
    material: Any = None
    two_sided: bool = False
    world_radius: bool = False
    index_vbo: Optional[QtGui.QOpenGLBuffer] = None
    index_count: int = 0

class QtGLRenderer(QtWidgets.QOpenGLWidget, Renderer):
    """Qt-native OpenGL renderer with lightweight VBO caching.

    The controller pushes :class:`Scene` updates via :meth:`set_scene`; we
    translate them into GPU buffers and render with a single simple shader.
    """

    def __init__(
        self,
        controller,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        Renderer.__init__(self, parent=parent)
        QtWidgets.QOpenGLWidget.__init__(self, parent)
        self._gl = None
        self._controller = controller
        self._scene: Optional[Scene] = None
        self._draw_data: list[_DrawData] = []
        self._gpu_calls: list[_GpuDrawCall] = []
        self._labels: list[_LabelData] = []
        #: Last cursor position of a drag. Only ever *assigned* on press, so it
        #: has to exist before one: a drag whose press went somewhere else --
        #: the in-viewport panel, say -- reaches the move handler with nothing
        #: recorded, and reading it then is an AttributeError, not a no-op.
        self._last_mouse_pos = None
        #: Set while a press has been taken by the panel, so the drag that
        #: follows does not also swing the camera.
        self._gui_grab = False
        #: PyMOL's object panel, drawn in the viewport rather than beside it.
        self._internal_gui = InternalGui()
        #: The last `ray` result, shown *in place of* the live scene until the
        #: view changes. It is drawn inside the paint pass rather than by a
        #: widget laid over the viewport, because a widget over the viewport
        #: also covers the object panel -- and the panel is the only way back.
        self._ray_image: Optional[QtGui.QImage] = None
        self._needs_upload: bool = False
        self._program: Optional[QtGui.QOpenGLShaderProgram] = None
        self._pos_attr = -1
        self._color_attr = -1
        self._normal_attr = -1
        self._mvp_uniform = -1
        self._normal_matrix_uniform = -1
        self._view_matrix_uniform = -1
        self._light_dir_uniform = -1
        self._fill_light_dir_uniform = -1
        self._key_intensity_uniform = -1
        self._fill_intensity_uniform = -1
        self._ambient_uniform = -1
        self._spec_strength_uniform = -1
        self._shininess_uniform = -1
        self._rim_strength_uniform = -1
        self._rim_power_uniform = -1
        self._fog_end_uniform = -1
        self._fog_scale_uniform = -1
        self._fog_color_uniform = -1
        self._glyph_mode_uniform = -1
        self._two_sided_uniform = -1
        self._point_size_uniform = -1
        self._point_scale_uniform = -1
        self._radius_attr = -1
        self._occlusion_attr = -1
        self._background = (0.0, 0.0, 0.0, 1.0)
        #: Backdrop picture: what was requested, the resolved image, its GL
        #: texture, and whether the texture needs rebuilding (a named backdrop
        #: is generated at the widget's own size, so a resize invalidates it).
        self._background_source = None
        self._background_image = None
        self._background_texture = None
        self._background_program = None
        self._background_dirty = False
        self._background_texture_size = (0, 0)

        # Render-to-texture scaffolding. Silhouettes today; occlusion and depth
        # cue reuse the same target rather than each adding their own.
        from .postprocess import PostProcess

        # No copying: `PostProcess` reads the `silhouette` section itself, so a
        # `set silhouette, on` reaches a viewer that is already open. Copying
        # here is what made the configuration a start-up default nothing could
        # change and the renderer's copy a value nothing could see.
        self._post = PostProcess()

        lighting_cfg = (_DISPLAY_CONFIG.get("lighting") or {})
        light_dir = lighting_cfg.get("light_direction", [0.0, 0.0, 1.0])
        self._light_direction = QtGui.QVector3D(
            float(light_dir[0]), float(light_dir[1]), float(light_dir[2])
        )
        self._ambient_strength = float(lighting_cfg.get("ambient_strength", 0.55))
        fill_dir = lighting_cfg.get("fill_light_direction", [-0.4, -0.3, 0.8])
        self._fill_light_direction = QtGui.QVector3D(
            float(fill_dir[0]), float(fill_dir[1]), float(fill_dir[2])
        )
        self._key_intensity = float(lighting_cfg.get("key_light_intensity", 1.0))
        self._fill_intensity = float(lighting_cfg.get("fill_light_intensity", 0.0))
        self._specular_strength = float(lighting_cfg.get("specular_strength", 0.18))
        self._shininess = float(lighting_cfg.get("shininess", 38.0))
        self._rim_strength = float(lighting_cfg.get("rim_strength", 0.18))
        self._rim_power = float(lighting_cfg.get("rim_power", 2.4))
        self._grid_visible = False
        self._grid_size = 20.0
        self._grid_spacing = 1.0
        self._distance = 30.0
        # Camera orientation as a 3x3 world->camera rotation matrix (a PyMOL-style
        # virtual trackball), replacing the old azimuth/elevation turntable so the
        # view can roll and rotate about an arbitrary screen axis like PyMOL.
        self._rot = self._make_rot(20.0, 45.0)
        self._target_radius = 10.0
        #: Aspect the current distance was derived at, so a resize that
        #: does not change the viewport's shape costs nothing.
        self._framed_aspect: float | None = None
        self._near_clip = 0.1
        #: Where framing last put the planes -- what `clip reset` returns to.
        self._framed_near_clip = 0.1
        self._framed_far_clip = 1000.0
        self._far_clip = 1000.0
        self._min_near_clip = 0.01
        self._max_near_clip = 10.0
        self._clip_wheel_scale = 0.85
        #: Fraction of the slab's own thickness one wheel step moves it by.
        #: PyMOL's `0.1 * mouse_wheel_scale`; being a *fraction* is what makes
        #: the gesture feel the same on a peptide and on a ribosome.
        self._slab_wheel_fraction = 0.1
        #: Whether the slab is still the configured default. The first move
        #: fits it around the scene; after that it belongs to the user.
        self._slab_moved = False
        self._grid_draw_data: Optional[_DrawData] = None
        # Vertical field of view in degrees, shared by the projection matrix,
        # the framing rule and the serialised view tuple so that an offscreen
        # raytrace of a saved view frames the scene like the widget does.
        cam_cfg = (_DISPLAY_CONFIG.get("camera") or {})
        self._fov = float(cam_cfg.get("field_of_view", DEFAULT_FOV))
        self._orthoscopic = bool(cam_cfg.get("orthoscopic", False))
        self._drag_selecting = False
        self._drag_start: Optional[QtCore.QPoint] = None
        #: The selection box while it is being dragged, in widget pixels. Drawn
        #: by the overlay painter rather than by a `QRubberBand` child: the box
        #: is scene chrome like the panel and the labels, it has to appear in a
        #: `grab()` of the viewport for a screenshot to show what was selected,
        #: and one painter pass already exists to draw it in.
        self._select_rect: Optional[QtCore.QRect] = None
        self._drag_modifiers = QtCore.Qt.NoModifier
        self._drag_action: Optional[str] = None
        #: The button that started the box, so the release that ends it is the
        #: matching one. Only the left button used to end a box, and `-Box` is
        #: bound to shift-*middle* in every three-button mode -- so that drag
        #: never completed, and `_drag_selecting` stayed set for the rest of the
        #: session, swallowing every later drag into a box that never closed.
        self._drag_button: Optional[QtCore.Qt.MouseButton] = None
        self._press_pos: Optional[QtCore.QPoint] = None
        self._press_mods = QtCore.Qt.NoModifier
        self._press_button: Optional[QtCore.Qt.MouseButton] = None
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        # Without this Qt delivers a move only while a button is down, so every
        # *passive* gesture the in-viewport panel has was dead: no hover
        # highlight on a row or a menu entry, and -- the visible one -- submenus
        # that could only be opened by clicking and were never told the cursor
        # had moved on, so they piled up on top of each other.
        self.setMouseTracking(True)
        self._panning = False
        self._right_dragged = False
        self._pan_offset = np.zeros(3, dtype=float)
        # Camera-space offset applied after the rotation. Zero until `origin`
        # separates the pivot from the centre of the view; see _build_matrices.
        self._view_shift = np.zeros(3, dtype=float)

        camera_cfg = (_DISPLAY_CONFIG.get("camera") or {})
        self._mouse_mode = self._normalize_mouse_mode(
            camera_cfg.get("mouse_mode", "pymol")
        )

    # ------------------------------------------------------------------
    # Mouse rotation mode
    # ------------------------------------------------------------------
    @staticmethod
    def _make_rot(elevation: float, azimuth: float) -> np.ndarray:
        """Build a world->camera rotation matrix ``Rx(elevation) @ Rz(azimuth)``.

        Matches the previous ``QMatrix4x4.rotate(elevation, X); rotate(azimuth, Z)``
        turntable so the default view is unchanged.
        """
        el = math.radians(float(elevation))
        az = math.radians(float(azimuth))
        ce, se = math.cos(el), math.sin(el)
        ca, sa = math.cos(az), math.sin(az)
        rx = np.array([[1.0, 0.0, 0.0], [0.0, ce, -se], [0.0, se, ce]])
        rz = np.array([[ca, -sa, 0.0], [sa, ca, 0.0], [0.0, 0.0, 1.0]])
        return rx @ rz

    @staticmethod
    def _trackball_delta(
        last: tuple[float, float],
        cur: tuple[float, float],
        width: float,
        height: float,
    ) -> np.ndarray:
        """PyMOL virtual-trackball delta rotation (camera-space 3x3).

        Projects the previous and current cursor onto a sphere of radius
        ``0.45*min(W,H)``, takes the rotation carrying one to the other, and damps
        the roll (z) component — see SceneMouse.cpp. Returned matrix left-multiplies
        the current world->camera rotation.
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
        angle = 1.3 * 2.0 * math.asin(min(s, 1.0))  # radians; mouse_scale=1.3
        angle /= 1.0 + abs(axis[2])                  # damp the twist component
        # PyMOL applies rotate(angle, ax, ay, -az); the screen axis lives in
        # camera space, so this delta left-multiplies the view rotation.
        ax, ay, az = axis[0], axis[1], -axis[2]
        c, sn = math.cos(angle), math.sin(angle)
        k = np.array([[0.0, -az, ay], [az, 0.0, -ax], [-ay, ax, 0.0]])
        return np.eye(3) + sn * k + (1.0 - c) * (k @ k)

    @staticmethod
    def _rotation_delta_multiplier(mouse_mode: str) -> float:
        """Return the multiplier applied to left-drag rotation deltas.

        In PyMOL-style rotation the object (protein) appears to follow the
        cursor; in Chimol-style rotation the camera / plane follows the cursor.

        Parameters
        ----------
        mouse_mode : str
            ``"pymol"`` or ``"chimol"``.

        Returns
        -------
        float
            ``-1.0`` for PyMOL-style object rotation, ``1.0`` for
            Chimol-style camera rotation.
        """
        return -1.0 if mouse_mode == "pymol" else 1.0

    @staticmethod
    def _pan_delta_multiplier(mouse_mode: str) -> float:
        """Return the multiplier applied to middle-drag pan deltas.

        In PyMOL-style panning the object (protein) appears to follow the
        cursor; in Chimol-style panning the camera / plane follows the cursor,
        so the object moves opposite to the cursor.

        Parameters
        ----------
        mouse_mode : str
            ``"pymol"`` or ``"chimol"``.

        Returns
        -------
        float
            ``1.0`` for PyMOL-style object panning, ``-1.0`` for
            Chimol-style camera / plane panning.
        """
        return 1.0 if mouse_mode == "pymol" else -1.0

    @staticmethod
    def _normalize_mouse_mode(mode: Any) -> str:
        """Return a valid mouse rotation mode string.

        Parameters
        ----------
        mode : Any
            Candidate mode value (typically ``"pymol"`` or ``"chimol"``).

        Returns
        -------
        str
            ``"pymol"`` or ``"chimol"``. Unrecognised values fall back to
            ``"pymol"``.
        """
        mode_str = str(mode).lower().strip()
        if mode_str == "chimol":
            return "chimol"
        return "pymol"

    def set_mouse_mode(self, mode: str) -> None:
        """Set the left-drag rotation style.

        Parameters
        ----------
        mode : str
            ``"pymol"`` rotates the object in the camera view (follows the
            cursor); ``"chimol"`` rotates the camera / moves the plane.
        """
        self._mouse_mode = self._normalize_mouse_mode(mode)

    def get_mouse_mode(self) -> str:
        """Return the current left-drag rotation style."""
        return self._mouse_mode

    # ------------------------------------------------------------------
    # Renderer interface
    # ------------------------------------------------------------------
    def widget(self) -> QtWidgets.QWidget:
        return self

    def set_scene(self, scene: Optional[Scene]) -> None:
        """Attach a Scene, rebuild VBOs, and request a repaint."""
        self._scene = scene
        # A traced image is a picture of the scene that was; the moment a new
        # one arrives it is a picture of something else. Every command that
        # changes what is drawn comes through here, so this is the one place
        # that has to know.
        self.clear_ray_image()
        self._prepare_draw_data(scene)
        self.update()

    def clear(self) -> None:
        self._scene = None
        self._draw_data = []
        self._release_gpu_calls()
        # Same reason as `set_scene`: an emptied viewport that still shows the
        # last traced frame says the molecule is there when it is not, and this
        # is the path taken when the scene becomes empty rather than different.
        self.clear_ray_image()
        self.update()

    def configure_grid(self, size: float, spacing: float) -> None:
        self._grid_size = float(size)
        self._grid_spacing = max(float(spacing), 0.1)
        self._grid_draw_data = None
        self.update()

    def set_background_color(self, color) -> None:
        """Set the clear colour, from a name, a Qt colour, or any RGB(A) sequence.

        The sequence test has to be by *shape*, not by ``isinstance(tuple, list)``:
        the command layer's colour parser returns a **numpy array**, which is
        neither, so it fell through to ``QColor(ndarray)`` -- which raises, and
        the caller swallowed the exception. `bg_color white` therefore did
        nothing at all and reported success.
        """
        if isinstance(color, str):
            sequence = None
        else:
            try:
                sequence = [float(c) for c in color]
            except (TypeError, ValueError):
                sequence = None

        if sequence is not None and len(sequence) >= 3:
            rgba = (
                tuple(sequence[:4]) if len(sequence) >= 4
                else (*sequence[:3], 1.0)
            )
        else:
            qcolor = QtGui.QColor(color)
            rgba = (
                qcolor.redF(),
                qcolor.greenF(),
                qcolor.blueF(),
                qcolor.alphaF(),
            )
        self._background = rgba
        self.update()

    def get_background_color(self) -> tuple[float, float, float, float]:
        """The clear colour now in force, as RGBA in ``0..1``."""
        return tuple(self._background)

    def set_background_image(self, source) -> None:
        """Put a picture behind the scene, or take it away.

        Transparency is invisible against one flat colour: a surface at alpha
        0.4 over black is merely a darker surface, because there is nothing
        behind it for the eye to catch. Give the background structure and the
        same surface reads as glass immediately.

        Parameters
        ----------
        source : str, QImage, numpy.ndarray or None
            A name from :data:`~chimol.renderer.backdrop.BACKDROPS` (``stars``,
            ``nebula``), a path to an image file, an image already in hand, or
            ``None``/``""``/``"off"`` to go back to the flat colour.

        Raises
        ------
        ValueError
            If a path was given and cannot be read -- a background that silently
            does not appear is indistinguishable from one that is not supported.
        """
        # Recorded only once the source has resolved. Setting it up front left a
        # refused path as the reported background: `bg_image` would name a
        # picture that had never loaded and was not on screen.
        if source is None or (isinstance(source, str) and source.strip().lower()
                              in ("", "off", "none")):
            self._background_source = source
            self._background_image = None
            self._background_dirty = True
            self.update()
            return

        image = None
        if isinstance(source, QtGui.QImage):
            image = source
        elif isinstance(source, np.ndarray):
            image = _image_from_rgb(source)
        elif isinstance(source, str):
            from .backdrop import BACKDROPS

            if source.strip().lower() in BACKDROPS:
                image = None  # generated at paint time, at the widget's size
            else:
                loaded = QtGui.QImage(source)
                if loaded.isNull():
                    raise ValueError(f"cannot read background image: {source}")
                image = loaded

        self._background_source = source
        self._background_image = image
        self._background_dirty = True
        self.update()

    def get_background_image(self):
        """What ``set_background_image`` was last given, or ``None``."""
        return getattr(self, "_background_source", None)

    def set_lighting(self, **values) -> None:
        """Set lighting parameters by name and redraw.

        Names are ChimeraX's -- ``key_light_intensity``, ``fill_light_intensity``,
        ``ambient_light_intensity``, ``silhouette`` and friends -- so a preset is
        just a dict of them and the command layer needs no translation table.
        """
        mapping = {
            "key_light_intensity": "_key_intensity",
            "fill_light_intensity": "_fill_intensity",
            "ambient_light_intensity": "_ambient_strength",
            "specular_strength": "_specular_strength",
            "shininess": "_shininess",
            "rim_strength": "_rim_strength",
            "rim_power": "_rim_power",
        }
        known = set(mapping) | {"silhouette", "silhouette_thickness", "depth_jump"}
        for name, value in values.items():
            if name not in known:
                raise ValueError(
                    f"set_lighting: unknown parameter '{name}'. "
                    f"Use one of: {', '.join(sorted(known))}"
                )
            attribute = mapping.get(name)
            if attribute is not None:
                setattr(self, attribute, float(value))
            elif name == "silhouette":
                self._post.silhouette = bool(value)
            elif name == "silhouette_thickness":
                self._post.silhouette_thickness = float(value)
            elif name == "depth_jump":
                self._post.depth_jump = float(value)
        self.update()

    def lighting_state(self) -> dict:
        """The current lighting parameters, under ChimeraX's names."""
        return {
            "key_light_intensity": float(self._key_intensity),
            "fill_light_intensity": float(self._fill_intensity),
            "ambient_light_intensity": float(self._ambient_strength),
            "specular_strength": float(self._specular_strength),
            "shininess": float(self._shininess),
            "silhouette": bool(self._post.silhouette),
            "silhouette_thickness": float(self._post.silhouette_thickness),
            "depth_jump": float(self._post.depth_jump),
        }

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = bool(visible)
        self._grid_draw_data = None
        self._prepare_draw_data(self._scene)
        self.update()

    def configure_camera(
        self,
        *,
        near_clip: float,
        far_clip: float,
        min_near_clip: float,
        max_near_clip: float,
        clip_wheel_scale: float,
    ) -> None:
        self._min_near_clip = max(float(min_near_clip), 1e-5)
        self._max_near_clip = max(float(max_near_clip), self._min_near_clip * 1.01)
        self._clip_wheel_scale = clip_wheel_scale if 0.0 < clip_wheel_scale < 1.0 else 0.85
        self._near_clip = self._clamp_near_clip(float(near_clip))
        self._framed_near_clip = self._near_clip
        self._framed_far_clip = self._far_clip
        far_val = max(float(far_clip), self._near_clip * 10.0)
        self._far_clip = far_val
        self.update()

    def scene_width(self) -> int:
        """Width left for the 3-D scene once the panel's column is taken.

        The panel is a *column*, not an overlay: drawn on top it would hide the
        molecule it describes, and the part it hides is the part you just moved
        out from under it.
        """
        gui = getattr(self, "_internal_gui", None)
        if gui is None or not (gui.visible and gui.docked):
            return max(self.width(), 1)
        return max(int(self.width() - gui.column_width), 1)

    def scene_height(self) -> int:
        """Height left for the scene once the sequence strip has its band."""
        gui = getattr(self, "_internal_gui", None)
        strip = gui.sequence_height() if gui is not None else 0.0
        return max(int(self.height() - strip), 1)

    def scene_pixel_size(self) -> tuple[int, int]:
        """The scene column in **device** pixels — what a capture of it holds.

        `ray` with no size has to reproduce what is on screen, and what is on
        screen is this rectangle, not the widget: the panel owns a column and
        the sequence viewer a band, and tracing the widget's full size traces a
        wider field than the viewport shows. Measured on a 998x583 widget with
        the panel docked, that put the molecule at 59 % of the image width
        against the viewport's 70 %, and moved it right, because the viewport
        centres the scene in its column while the trace centred it in the
        image. PyMOL has the same rectangle and the same rule -- "default width
        and height are taken from the current viewpoint".

        Device pixels rather than logical ones so a default trace and a
        screenshot of the same window come out the same size on a retina
        display, where they differ by a factor of two.
        """
        ratio = float(getattr(self, "devicePixelRatioF", lambda: 1.0)() or 1.0)
        return (
            max(int(round(self.scene_width() * ratio)), 1),
            max(int(round(self.scene_height() * ratio)), 1),
        )

    #: Below this many pixels the scene column is not a viewport, it is a widget
    #: that has not been laid out yet. Chosen well under any usable window and
    #: well over the 1-pixel floor `scene_width` clamps to.
    _MIN_MEASURABLE_SCENE = 16

    def _aspect(self) -> float:
        """Viewport width over height, for PyMOL's portrait framing correction.

        Square (1.0) until the widget has a viewport worth measuring. A
        never-shown ``MolView`` is 100x30 with a 220-pixel panel column, so
        ``scene_width`` clamps its negative remainder to **1** -- and an aspect
        of 1/30 told the framing correction the window was thirty times taller
        than it is wide, putting the camera thirty times too far away. That is
        not a portrait window; it is no window at all, and the correction has
        nothing to correct for until there is one.
        """
        width = self.scene_width()
        height = self.scene_height()
        if width < self._MIN_MEASURABLE_SCENE or height < self._MIN_MEASURABLE_SCENE:
            return 1.0
        return width / float(height)

    def set_field_of_view(self, fov: float) -> None:
        """Set the vertical field of view in degrees, re-framing the scene.

        Changing the lens keeps the molecule the same size on screen by moving
        the camera, which is how PyMOL behaves and what makes ``field_of_view``
        usable as a perspective control rather than a zoom control.
        """
        new_fov = abs(float(fov))
        if new_fov < 1e-3 or abs(new_fov - self._fov) < 1e-9:
            return
        self._fov = new_fov
        self._distance = max(
            distance_for_radius(
                self._target_radius, new_fov, aspect=self._aspect()
            ),
            5.0,
        )
        self.update()

    def fit_to_radius(self, radius: float) -> None:
        self._target_radius = max(float(radius), 1.0)
        self._framed_aspect = self._aspect()
        self._distance = max(
            distance_for_radius(
                self._target_radius, self._fov, aspect=self._framed_aspect
            ),
            5.0,
        )

        target_near = max(self._target_radius * 0.02, self._min_near_clip)
        self._near_clip = self._clamp_near_clip(target_near)

        max_extent = self._distance + self._target_radius
        far_min = self._near_clip * 10.0
        self._far_clip = max(float(max_extent) * 1.2, far_min)

        # Framing is what defines "not clipped": `clip reset` comes back here,
        # and `zoom` therefore undoes a stray shift-scroll on its own.
        self._framed_near_clip = self._near_clip
        self._framed_far_clip = self._far_clip

        self.update()

    def reset_view(self, distance: float, elevation: float, azimuth: float) -> None:
        self._distance = max(float(distance), 1.0)
        self._rot = self._make_rot(elevation, azimuth)
        self._pan_offset = np.zeros(3, dtype=float)
        self._view_shift = np.zeros(3, dtype=float)
        self.update()

    def look_at(self, target: np.ndarray) -> None:
        """Set the camera to look at the given world-space coordinate.

        Both the pivot and the centre of the view move here, which is what
        ``center`` and ``zoom`` want: PyMOL's framing resets slots 9-11 to
        ``(0, 0, -distance)``. Use :meth:`set_origin` for the other case, where
        only the pivot should move.
        """
        center = np.zeros(3, dtype=float)
        if self._scene is not None:
            try:
                center = np.asarray(self._scene.center, dtype=float)
            except Exception:
                center = np.zeros(3, dtype=float)
        self._pan_offset = np.asarray(target, dtype=float) - center
        self._view_shift = np.zeros(3, dtype=float)
        self.update()

    def set_origin(self, origin: np.ndarray) -> None:
        """Move the point the camera rotates about, without moving the picture.

        This is PyMOL's ``origin``, which always passes ``preserve=1`` to
        ``SceneOriginSet``: the pivot changes and the view translation absorbs the
        difference, so nothing appears to happen until the next rotation. The
        compensation is ``SceneOriginSet``'s, transcribed -- the model-space
        difference rotated into camera space and added to the view offset::

            v0 = origin_new - origin_old        (model space)
            v1 = rotation @ v0                  (camera space)
            shift += v1

        Parameters
        ----------
        origin : numpy.ndarray
            The new pivot, in world (scene) space.
        """
        center = self._scene_center()
        previous = center + self._pan_offset
        wanted = np.asarray(origin, dtype=float).reshape(3)

        self._view_shift = self._view_shift + self._rot @ (wanted - previous)
        self._pan_offset = wanted - center
        self.update()

    def get_origin(self) -> np.ndarray:
        """Return the point the camera rotates about, in world space."""
        return self._scene_center() + self._pan_offset

    def set_distance(self, distance: float) -> None:
        """Set the distance from the target point."""
        self._distance = max(float(distance), 0.1)
        self.update()

    def set_orientation(self, elevation: float, azimuth: float) -> None:
        """Set camera elevation and azimuth."""
        self._rot = self._make_rot(elevation, azimuth)
        self.update()

    def turn(self, axis: str, angle_deg: float) -> None:
        """Rotate the camera about a screen axis (PyMOL ``turn``).

        ``axis`` is ``x``/``y``/``z`` in screen space (x = right, y = up,
        z = toward the viewer). The delta left-multiplies the view rotation, as
        for the trackball.
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
        self._rot = delta @ self._rot
        self.update()

    def move(self, axis: str, dist: float) -> None:
        """Translate the camera along a screen axis (PyMOL ``move``).

        x/y pan in the view plane; z dollies (changes the camera distance).
        """
        ax = str(axis).lower()
        d = float(dist)
        if ax == "x":
            self._pan_offset = self._pan_offset - d * self._rot[0]
        elif ax == "y":
            self._pan_offset = self._pan_offset - d * self._rot[1]
        elif ax == "z":
            self._distance = max(0.1, self._distance - d)
        else:
            return
        self.update()

    def _announce_clipping(self) -> None:
        """Say that the slab moved, and how to put it back.

        Shift+wheel is one stray gesture away from slicing the model open, and a
        cut closed surface does not look cut -- it looks like the transparency
        stopped working, because everything inside it is suddenly unblended and
        at full brightness. Reported as exactly that, more than once. A silent,
        sticky mode change with no way back is the actual defect; saying what
        happened costs one line in the status bar.
        """
        controller = getattr(self, "_controller", None)
        report = getattr(controller, "report_status", None)
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

    def _scene_center(self) -> np.ndarray:
        """Return the current scene center, or the origin when there is none."""
        if self._scene is not None:
            try:
                return np.asarray(self._scene.center, dtype=float)
            except Exception:
                pass
        return np.zeros(3, dtype=float)

    def get_view_state(self) -> list[float]:
        """Return the camera as an 18-float tuple in PyMOL's ``get_view`` layout."""

        return pack_view_state(
            self._rot,
            self._distance,
            self._scene_center() + self._pan_offset,
            self._near_clip,
            self._far_clip,
            self._fov,
            self._orthoscopic,
            shift=self._view_shift,
        )

    def set_view_state(self, view) -> None:
        """Restore an 18-float view tuple; see :mod:`.view_state` for layouts."""

        state = unpack_view_state(view)
        self._distance = max(state.distance, 0.1)
        self._rot = state.rotation
        self._pan_offset = state.target - self._scene_center()
        self._view_shift = np.asarray(state.shift, dtype=float).copy()
        self._near_clip = self._clamp_near_clip(state.near)
        self._far_clip = max(state.far, self._near_clip * 10.0)
        # Assigned rather than routed through set_field_of_view: the tuple
        # already carries the matching distance, which re-framing would discard.
        self._fov = abs(float(state.fov))
        self._orthoscopic = bool(state.orthoscopic)
        self.update()

    def project_to_screen(self, points) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Where scene points land in the widget, in widget pixels.

        Through the **same matrices the frame is drawn with**, because a picker
        that computes its own projection picks where the molecule is not. That
        is not hypothetical: this replaced a hand-rolled camera basis built from
        ``cameraPosition()`` and an ``opts`` dictionary, which are pyqtgraph's
        API and survived here only as a shim -- one whose ``center`` is a
        ``QVector3D`` that the helper reading it fed straight to ``numpy``,
        raising on every click.

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
        pts = np.asarray(points, dtype=float)
        if pts.ndim != 2 or pts.shape[1] != 3 or pts.shape[0] == 0:
            empty = np.zeros(0, dtype=float)
            return empty, empty, np.zeros(0, dtype=bool)

        matrix, _view = self._build_matrices()
        rows = np.asarray(matrix.data(), dtype=float).reshape(4, 4).T  # Qt is column-major
        homogeneous = np.column_stack([pts, np.ones(len(pts))])
        clip = homogeneous @ rows.T
        w = clip[:, 3]
        visible = np.isfinite(w) & (w > 1e-9)
        ndc = np.zeros((len(pts), 2), dtype=float)
        ndc[visible] = clip[visible, :2] / w[visible, None]

        width = max(self.scene_width(), 1)
        height = max(self.scene_height(), 1)
        strip = max(int(self.height()) - height, 0)
        x = (ndc[:, 0] * 0.5 + 0.5) * width
        # GL's y runs up from the bottom of the viewport; the widget's runs down
        # from its top, and the viewport starts under the strip.
        y = strip + (1.0 - (ndc[:, 1] * 0.5 + 0.5)) * height
        return x, y, visible

    # ------------------------------------------------------------------
    # Qt OpenGL overrides
    # ------------------------------------------------------------------
    def initializeGL(self) -> None:
        if GL is None:
            self._notify_gl_failure(
                "PyOpenGL is required for the Qt renderer. Install PyOpenGL first."
            )
            return

        self._gl = GL
        gl = GL
        gl.glEnable(GL_DEPTH_TEST)
        gl.glEnable(GL_CULL_FACE)
        gl.glCullFace(GL_BACK)
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        gl.glEnable(GL_POINT_SPRITE)
        gl.glEnable(GL_BLEND)
        gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self._create_program()

    def resizeGL(self, width: int, height: int) -> None:
        """Follow the widget's new size: the viewport, and the framing with it.

        Parameters
        ----------
        width, height : int
            The widget's new size in logical pixels. The *scene* is narrower
            than ``width`` when the internal panel is docked, which is why
            :meth:`scene_width` is asked rather than the argument used.
        """
        # Reframing first, and outside the GL guard: the camera distance is
        # camera state, not GL state. Behind the guard it would never run
        # without a context, which is exactly where a headless check looks.
        self._reframe_for_aspect()
        gl = self._gl
        if gl is None:
            return
        gl.glViewport(0, 0, self.scene_width(), max(height, 1))

    def _reframe_for_aspect(self) -> None:
        """Re-derive the camera distance when the viewport's shape changes.

        PyMOL's framing correction only applies to a **portrait** viewport, so
        the distance that framed a molecule in a wide window is wrong in a tall
        one and the molecule spills off the sides. Nothing else re-derives it:
        a resize triggers no rebuild, so without this the correction is applied
        once, at whatever shape the window happened to have when the structure
        was framed.

        The distance is **scaled** by the change in the correction rather than
        recomputed from the framed radius, and that is the whole subtlety here:
        the scroll wheel moves ``_distance`` without touching
        ``_target_radius``, so recomputing would snap a hand-zoomed view back to
        wherever the last ``zoom`` left it -- the same class of bug this
        method's neighbours exist to fix.

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

    #: A full-screen quad in clip space: two triangles, no matrices involved.
    _BACKGROUND_VERT = """
        attribute vec2 position;
        varying vec2 v_uv;
        void main() {
            v_uv = position * 0.5 + 0.5;
            gl_Position = vec4(position, 0.0, 1.0);
        }
    """

    _BACKGROUND_FRAG = """
        uniform sampler2D backdrop;
        varying vec2 v_uv;
        void main() {
            // Flipped in v: an image's first row is its top, a texture's is its
            // bottom, and a star field is symmetric enough that getting this
            // wrong is invisible until someone uses a photograph.
            gl_FragColor = texture2D(backdrop, vec2(v_uv.x, 1.0 - v_uv.y));
        }
    """

    def _ensure_background_texture(self, width: int, height: int) -> bool:
        """Build or rebuild the backdrop texture; True when one is ready."""
        source = getattr(self, "_background_source", None)
        if source is None or (isinstance(source, str)
                              and source.strip().lower() in ("", "off", "none")):
            return False

        size = (int(width), int(height))
        if (
            self._background_texture is not None
            and not self._background_dirty
            and self._background_texture_size == size
        ):
            return True

        image = self._background_image
        if image is None and isinstance(source, str):
            from .backdrop import render_backdrop

            array = render_backdrop(source, width, height)
            if array is None:
                return False
            image = _image_from_rgb(array)
        if image is None:
            return False

        try:
            if self._background_texture is not None:
                self._background_texture.destroy()
            texture = QtGui.QOpenGLTexture(image.mirrored(False, True))
            texture.setMinificationFilter(QtGui.QOpenGLTexture.Linear)
            texture.setMagnificationFilter(QtGui.QOpenGLTexture.Linear)
            texture.setWrapMode(QtGui.QOpenGLTexture.ClampToEdge)
        except Exception:
            logger.warning("chimol: could not upload the background image", exc_info=True)
            self._background_texture = None
            return False

        self._background_texture = texture
        self._background_texture_size = size
        self._background_dirty = False
        return True

    def _draw_background(self, gl, width: int, height: int) -> None:
        """Draw the backdrop as a full-screen quad, behind everything.

        Kept on its own tiny program rather than folded into the scene shader:
        the backdrop has no lighting, no normals and no depth, and giving it a
        branch in the shared program would cost every other draw a uniform and
        a test.
        """
        if not self._ensure_background_texture(width, height):
            return
        if self._background_program is None:
            program = QtGui.QOpenGLShaderProgram()
            ok = program.addShaderFromSourceCode(
                QtGui.QOpenGLShader.Vertex, self._BACKGROUND_VERT
            ) and program.addShaderFromSourceCode(
                QtGui.QOpenGLShader.Fragment, self._BACKGROUND_FRAG
            ) and program.link()
            if not ok:
                logger.warning("chimol: background shader failed: %s", program.log())
                self._background_source = None
                return
            self._background_program = program

        program = self._background_program
        program.bind()
        try:
            # One oversized triangle rather than two -- it covers the screen
            # with no seam down the diagonal. Shaped (N, 2): PyQt takes the
            # tuple size from the array, and passing it separately does not
            # match any overload.
            quad = np.array([[-1.0, -1.0], [3.0, -1.0], [-1.0, 3.0]], dtype=np.float32)
            location = program.attributeLocation("position")
            program.enableAttributeArray(location)
            program.setAttributeArray(location, quad)
            self._background_texture.bind(0)
            program.setUniformValue("backdrop", 0)
            gl.glDisable(GL_DEPTH_TEST)
            gl.glDepthMask(False)
            gl.glDrawArrays(GL_TRIANGLES, 0, 3)
            gl.glDepthMask(True)
            gl.glEnable(GL_DEPTH_TEST)
            program.disableAttributeArray(location)
            self._background_texture.release(0)
        finally:
            program.release()
            if self._program is not None:
                self._program.bind()

    def paintGL(self) -> None:
        if GL is None:
            return

        gl = self._gl
        if gl is None:
            return

        # Every frame, not only on resize: dragging the splitter changes how
        # much width the scene has without the widget being resized at all.
        # In *framebuffer* pixels -- `width()` is logical, and on a high-DPI
        # screen the two differ by the device pixel ratio, which would render
        # the scene into a quarter of the window.
        ratio = float(self.devicePixelRatioF())
        # The sequence strip takes a band off the top. GL's origin is the bottom
        # left, so a shorter viewport leaves exactly that band free -- the strip
        # is beside the scene, not over it, which is what `seq_view_overlay off`
        # means in PyMOL.
        strip = self._internal_gui.sequence_height()
        gl.glViewport(
            0, 0,
            max(int(self.scene_width() * ratio), 1),
            max(int((self.height() - strip) * ratio), 1),
        )

        # Effects that read the scene back -- silhouettes now, occlusion and
        # depth cue next -- need it rendered into a texture first. With none of
        # them on, `begin` declines and everything below draws straight to the
        # widget exactly as before, so the scaffolding costs nothing unused.
        ratio = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        buffer_w = max(1, int(self.scene_width() * ratio))
        # The *same* height the viewport above was given -- the sequence strip's
        # band excluded. A full-height buffer renders the molecule centred in a
        # taller frame than the one it is shown in, so switching an effect on
        # visibly shifted the scene; and because `end` blits a quad over the
        # buffer's own extent, a full-height one also painted over the band the
        # strip lives in and took the strip off the screen.
        buffer_h = max(1, int((self.height() - strip) * ratio))
        # A widget that has not been laid out is not a viewport, and the same
        # 1-pixel floor that once told the camera the window was thirty times
        # taller than wide (see `_aspect`) would here build a 1-pixel-wide
        # framebuffer: the scene renders into it, `end` blits a one-pixel column
        # back, and the molecule is *gone*. Below the measurable threshold the
        # effect passes decline and the scene draws straight to the widget,
        # which is the same thing they do when no effect is switched on.
        measurable = (
            buffer_w >= self._MIN_MEASURABLE_SCENE
            and buffer_h >= self._MIN_MEASURABLE_SCENE
        )
        # The depth-linearisation factor needs the near/far ratio, and collapses
        # to 1 under an orthographic projection.
        self._post.near_far_ratio = (
            1.0 if self._orthoscopic
            else float(self._near_clip) / max(float(self._far_clip), 1e-6)
        )
        offscreen = measurable and self._post.begin(buffer_w, buffer_h)

        r, g_col, b, a = self._background
        gl.glClearColor(r, g_col, b, a)
        gl.glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

        # The backdrop goes down first, with depth writes off, so everything
        # else draws over it exactly as it would over the clear colour.
        self._draw_background(gl, buffer_w, buffer_h)

        if self._program is None:
            if offscreen:
                self._post.end(self.defaultFramebufferObject())
            return

        if not self._gpu_calls and self._draw_data:
            self._upload_draw_data()
        elif self._needs_upload:
            self._release_gpu_calls()
            self._upload_draw_data()
            self._needs_upload = False

        if not self._gpu_calls:
            if offscreen:
                self._post.end(self.defaultFramebufferObject())
            # The panel is *not* part of the scene, so an empty scene must not
            # take it with it. Returning here left the view control gone the
            # moment the last object was switched off -- which looks exactly
            # like the control switching itself off, and leaves no way back,
            # because the way back is a button on the thing that vanished.
            self._render_overlay()
            return

        mvp, view = self._build_matrices()
        normal_matrix = QtGui.QMatrix4x4(view)
        normal_matrix.setColumn(3, QtGui.QVector4D(0.0, 0.0, 0.0, 1.0))
        self._program.bind()
        self._program.setUniformValue(self._mvp_uniform, mvp)
        self._program.setUniformValue(self._normal_matrix_uniform, normal_matrix)
        self._program.setUniformValue(self._view_matrix_uniform, view)
        self._program.setUniformValue(self._light_dir_uniform, self._light_direction)
        self._program.setUniformValue(
            self._fill_light_dir_uniform, self._fill_light_direction
        )
        self._program.setUniformValue(
            self._key_intensity_uniform, float(self._key_intensity)
        )
        self._program.setUniformValue(
            self._fill_intensity_uniform, float(self._fill_intensity)
        )
        self._program.setUniformValue(self._ambient_uniform, float(self._ambient_strength))
        self._program.setUniformValue(self._spec_strength_uniform, float(self._specular_strength))
        self._program.setUniformValue(self._shininess_uniform, float(self._shininess))
        self._program.setUniformValue(self._rim_strength_uniform, float(self._rim_strength))
        self._program.setUniformValue(self._rim_power_uniform, float(self._rim_power))
        fog_end, fog_scale = self._fog_planes()
        self._program.setUniformValue(self._fog_end_uniform, float(fog_end))
        self._program.setUniformValue(self._fog_scale_uniform, float(fog_scale))
        fog_color = QtGui.QVector3D(float(r), float(g_col), float(b))
        self._program.setUniformValue(self._fog_color_uniform, fog_color)

        # Render passes: opaque first, then transparent (back-to-front), then overlay
        opaque_calls = [c for c in self._gpu_calls if c.render_mode == "opaque"]
        transparent_calls = [c for c in self._gpu_calls if c.render_mode == "transparent"]
        overlay_calls = [c for c in self._gpu_calls if c.render_mode == "overlay"]

        # Compute camera-space depth for transparent sorting (back-to-front)
        if transparent_calls:
            for call in transparent_calls:
                # Approximate depth from the average of a few positions
                # by reading back VBO data.  For simplicity, use the
                # draw-call's depth stored during upload (centroid z in
                # view space).  If unavailable, fall back to 0.
                depth = getattr(call, "depth", 0.0)
                call.depth = depth
            transparent_calls.sort(key=lambda c: c.depth, reverse=True)

        for call_set, depth_enable, blend_enable in [
            (opaque_calls, True, False),
            (transparent_calls, True, True),
            (overlay_calls, False, False),
        ]:
            if not call_set:
                continue
            if depth_enable:
                gl.glEnable(GL_DEPTH_TEST)
            else:
                gl.glDisable(GL_DEPTH_TEST)
            if blend_enable:
                gl.glEnable(GL_BLEND)
                gl.glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
                # **Stop writing depth.** Transparent geometry has to be tested
                # against the opaque scene but must not occlude itself, and this
                # was never turned off: the first fragment of a transparent
                # surface wrote depth and rejected everything behind it, so an
                # alpha of 0.5 came out as a solid surface that had merely been
                # dimmed. Nothing behind it was ever drawn, which is why it
                # never looked see-through however low the alpha went.
                gl.glDepthMask(False)
            else:
                gl.glDisable(GL_BLEND)
                gl.glDepthMask(True)

            for call in call_set:
                if call.primitive == GL_POINTS and call.glyph == "ring":
                    glyph_mode = 3
                elif call.primitive == GL_POINTS and call.glyph == "selection":
                    glyph_mode = 4
                elif call.primitive == GL_POINTS and call.glyph == "square_outline":
                    glyph_mode = 2
                elif call.glyph == "sphere" and call.primitive == GL_POINTS:
                    glyph_mode = 1
                else:
                    glyph_mode = 0
                self._program.setUniformValue(self._glyph_mode_uniform, glyph_mode)
                self._program.setUniformValue(
                    self._two_sided_uniform, 1 if call.two_sided else 0
                )
                # Two-sided meshes (flat nucleic base plates) must not be
                # back-face culled, or the far cap of each thin plate vanishes
                # and the base looks torn/see-through edge-on.
                if call.two_sided:
                    gl.glDisable(GL_CULL_FACE)
                else:
                    gl.glEnable(GL_CULL_FACE)
                # `gl_PointSize` is in *framebuffer* pixels while a caller asks
                # in logical ones, so on a high-DPI screen a point comes out at
                # half the size it asked for. World-radius points already scale
                # through `_point_scale`, which carries the ratio.
                pixel_size = float(call.size)
                if not call.world_radius:
                    pixel_size *= float(self.devicePixelRatioF())
                self._program.setUniformValue(self._point_size_uniform, pixel_size)
                if self._point_scale_uniform != -1:
                    self._program.setUniformValue(
                        self._point_scale_uniform,
                        self._point_scale() if call.world_radius else 0.0,
                    )

                mat = call.material
                self._program.setUniformValue(self._spec_strength_uniform, _material_val(mat, "specular_strength", self._specular_strength))
                self._program.setUniformValue(self._shininess_uniform, _material_val(mat, "shininess", self._shininess))
                self._program.setUniformValue(self._rim_strength_uniform, _material_val(mat, "rim_strength", self._rim_strength))
                self._program.setUniformValue(self._rim_power_uniform, _material_val(mat, "rim_power", self._rim_power))

                if call.primitive == GL_POINTS:
                    gl.glPointSize(pixel_size)
                    if glyph_mode:
                        gl.glEnable(GL_POINT_SPRITE)
                    else:
                        gl.glDisable(GL_POINT_SPRITE)
                elif call.primitive == GL_LINES:
                    gl.glLineWidth(call.width)
                    gl.glDisable(GL_POINT_SPRITE)
                else:
                    gl.glDisable(GL_POINT_SPRITE)

                call.positions_vbo.bind()
                self._program.enableAttributeArray(self._pos_attr)
                self._program.setAttributeBuffer(
                    self._pos_attr,
                    GL_FLOAT,
                    0,
                    3,
                )
                call.colors_vbo.bind()
                self._program.enableAttributeArray(self._color_attr)
                self._program.setAttributeBuffer(
                    self._color_attr,
                    GL_FLOAT,
                    0,
                    4,
                )

                call.normals_vbo.bind()
                self._program.enableAttributeArray(self._normal_attr)
                self._program.setAttributeBuffer(
                    self._normal_attr,
                    GL_FLOAT,
                    0,
                    3,
                )

                if self._radius_attr != -1:
                    if call.radii_vbo is not None:
                        call.radii_vbo.bind()
                        self._program.enableAttributeArray(self._radius_attr)
                        self._program.setAttributeBuffer(self._radius_attr, GL_FLOAT, 0, 1)
                    else:
                        self._program.disableAttributeArray(self._radius_attr)
                        self._program.setAttributeValue(self._radius_attr, 0.0)

                if self._occlusion_attr != -1:
                    if call.occlusion_vbo is not None:
                        call.occlusion_vbo.bind()
                        self._program.enableAttributeArray(self._occlusion_attr)
                        self._program.setAttributeBuffer(
                            self._occlusion_attr, GL_FLOAT, 0, 1
                        )
                    else:
                        # Geometry with no occlusion baked in is fully exposed,
                        # so it keeps the unattenuated lighting it had before.
                        self._program.disableAttributeArray(self._occlusion_attr)
                        self._program.setAttributeValue(self._occlusion_attr, 0.0)

                # A closed transparent surface is drawn twice: its far wall
                # first, then its near wall. Sorting whole draw calls does
                # nothing for a metaball, which is a *single* call -- the
                # triangles inside it come in whatever order marching cubes
                # emitted, so blending them showed one arbitrary layer and the
                # inside of the blob was never drawn at all. Culling front faces
                # for the first pass and back faces for the second puts them in
                # the right order for free, which is what makes a transparent
                # body read as having an inside.
                two_pass = (
                    blend_enable
                    and call.primitive == GL_TRIANGLES
                    and not call.two_sided
                )
                passes = ((GL_FRONT, GL_BACK) if two_pass else (None,))
                for cull in passes:
                    if cull is not None:
                        gl.glEnable(GL_CULL_FACE)
                        gl.glCullFace(cull)
                    if call.index_vbo is not None:
                        call.index_vbo.bind()
                        gl.glDrawElements(
                            call.primitive, call.index_count, GL_UNSIGNED_INT, None
                        )
                        call.index_vbo.release()
                    else:
                        gl.glDrawArrays(call.primitive, 0, call.vertex_count)
                if two_pass:
                    gl.glCullFace(GL_BACK)

                if call.primitive == GL_POINTS:
                    gl.glPointSize(1.0)
                    gl.glDisable(GL_POINT_SPRITE)

                call.positions_vbo.release()
                call.colors_vbo.release()
                call.normals_vbo.release()
                if call.radii_vbo is not None:
                    call.radii_vbo.release()
                if call.occlusion_vbo is not None:
                    call.occlusion_vbo.release()
                self._program.disableAttributeArray(self._pos_attr)
                self._program.disableAttributeArray(self._color_attr)
                self._program.disableAttributeArray(self._normal_attr)
                if self._radius_attr != -1:
                    self._program.disableAttributeArray(self._radius_attr)
                if self._occlusion_attr != -1:
                    self._program.disableAttributeArray(self._occlusion_attr)

        # Restore global GL state so we don't leak into the next frame
        gl.glEnable(GL_CULL_FACE)
        self._program.setUniformValue(self._two_sided_uniform, 0)
        self._program.setUniformValue(self._spec_strength_uniform, float(self._specular_strength))
        self._program.setUniformValue(self._shininess_uniform, float(self._shininess))
        self._program.setUniformValue(self._rim_strength_uniform, float(self._rim_strength))
        self._program.setUniformValue(self._rim_power_uniform, float(self._rim_power))

        self._program.release()

        # Back to the widget, then the effect passes. `defaultFramebufferObject`,
        # not 0: QOpenGLWidget composites through its own framebuffer, so binding
        # 0 here draws into nothing visible.
        #
        # Before the overlay, not after. `_render_overlay` paints with QPainter,
        # which targets the *widget's* framebuffer rather than the bound one, so
        # running it first put the chrome on screen and then had the composite
        # blit erase it -- the sequence strip disappeared the moment any effect
        # was switched on. The two early-return paths above already had this
        # order; only the one that draws a molecule did not.
        if offscreen:
            self._post.end(self.defaultFramebufferObject())
        self._render_overlay()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _notify_gl_failure(self, message: str) -> None:
        if self._controller is not None:
            handler = getattr(self._controller, "on_renderer_error", None)
            if callable(handler):
                handler(message)
                return
        raise RuntimeError(message)

    def _create_program(self) -> None:
        vert_src = """#version 120
        attribute vec3 position;
        attribute vec4 color;
        attribute vec3 normal;
        attribute float radius;
        attribute float occlusion;
        uniform mat4 mvp;
        uniform mat4 normalMatrix;
        uniform mat4 viewMatrix;
        varying vec4 v_color;
        varying vec3 v_normal;
        varying vec3 v_viewPos;
        varying float v_occ;
        uniform int glyphMode;
        uniform float pointSize;
        // A sphere impostor's radius is a distance in the model, not a number
        // of pixels: a bead has to grow when the camera comes closer, the way
        // a mesh sphere does. `pointScale` is half the viewport height over
        // tan(fov/2), so radius * 2 * pointScale / depth is the sprite's
        // diameter in pixels. Zero leaves the radius a pixel count, which is
        // what every other point glyph means by it.
        uniform float pointScale;
        void main() {
            v_occ = clamp(occlusion, 0.0, 1.0);
            vec4 worldPos = vec4(position, 1.0);
            gl_Position = mvp * worldPos;
            v_color = color;
            v_normal = normalize((normalMatrix * vec4(normal, 0.0)).xyz);
            vec4 viewPos = viewMatrix * worldPos;
            v_viewPos = viewPos.xyz;
            if (glyphMode != 0) {
                if (radius > 0.0) {
                    gl_PointSize = (pointScale > 0.0)
                        ? (2.0 * radius * pointScale / max(-viewPos.z, 1e-3))
                        : radius;
                } else {
                    gl_PointSize = pointSize;
                }
            }
        }
        """

        frag_src = """#version 120
        varying vec4 v_color;
        varying vec3 v_normal;
        varying vec3 v_viewPos;
        varying float v_occ;
        uniform vec3 lightDir;
        uniform float ambientStrength;
        // ChimeraX's model: a key light, a fill light from a second direction,
        // and an ambient term, each with its own intensity. One hard-coded
        // direction cannot express `soft` or `flat`, which are the presets that
        // make a figure look like a ChimeraX figure.
        uniform vec3 fillLightDir;
        uniform float keyIntensity;
        uniform float fillIntensity;
        uniform float specStrength;
        uniform float shininess;
        uniform float rimStrength;
        uniform float rimPower;
        // PyMOL's fog is *linear between two planes*, not exponential in
        // distance: `fog = (g_Fog_end + eye_pos.z) * g_Fog_scale` in its
        // `default.vs`, where the value is a **visibility** (1 = unfogged) and
        // `g_Fog_scale` is 1/(end - start). Expressed that way so the same
        // `fog_start` means the same thing here as it does in the ray tracer
        // and in PyMOL.
        uniform float fogEnd;
        uniform float fogScale;
        uniform vec3 fogColor;
        uniform int glyphMode;
        uniform int twoSided;
        void main() {
            vec3 n = normalize(v_normal);
            if (glyphMode == 1) {
                vec2 coord = gl_PointCoord * 2.0 - 1.0;
                float dist2 = dot(coord, coord);
                if (dist2 > 1.0) {
                    discard;
                }
                float z = sqrt(max(0.0, 1.0 - dist2));
                n = normalize(vec3(coord, z));
            } else if (glyphMode == 3) {
                // A ring: Chimera's selection is a green outline *around* what
                // is selected, not a marker sitting on top of it. Drawn
                // depth-tested and a little wider than the atom, the middle is
                // covered by the molecule and what is left is a halo hugging
                // its silhouette.
                vec2 coord = gl_PointCoord * 2.0 - 1.0;
                float radius = length(coord);
                if (radius > 1.0 || radius < 0.68) {
                    discard;
                }
                gl_FragColor = v_color;
                return;
            } else if (glyphMode == 2) {
                // A hollow square: an outline frames an atom instead of hiding
                // it. Not PyMOL's selection marker -- that one is filled, and
                // is glyphMode 4 below.
                vec2 coord = abs(gl_PointCoord * 2.0 - 1.0);
                float edge = max(coord.x, coord.y);
                if (edge > 1.0 || edge < 0.62) {
                    discard;
                }
                gl_FragColor = v_color;
                return;
            } else if (glyphMode == 4) {
                // PyMOL's selection indicator, in one pass instead of three.
                // `ExecutiveSetupIndicatorPassMultipassImmediate` draws three
                // concentric filled squares per selected atom -- the colour at
                // the full dot width, black at about half of it, white in the
                // middle -- and the ratios here are its own (width, then 4/8,
                // then 2/8 at the default eight-pixel marker). Square, not
                // round: `selection_round_points` is off by default.
                vec2 coord = abs(gl_PointCoord * 2.0 - 1.0);
                float edge = max(coord.x, coord.y);
                if (edge > 1.0) {
                    discard;
                }
                if (edge < 0.25) {
                    gl_FragColor = vec4(1.0, 1.0, 1.0, v_color.a);
                } else if (edge < 0.5) {
                    gl_FragColor = vec4(0.0, 0.0, 0.0, v_color.a);
                } else {
                    gl_FragColor = v_color;
                }
                return;
            }
            vec3 l = normalize(lightDir);
            // Two-sided lighting: a back face is shaded as though it faced the
            // camera. `gl_FrontFacing`, not `dot(n, l)` -- the two are different
            // effects and only this one is PyMOL's `two_sided_lighting`.
            //
            // Flipping toward the *light* lights whatever the light misses,
            // wherever the camera is; measured on a half-transparent surface it
            // made the picture 7.6% *darker*, because a front face lit only by
            // the fill light had its normal flipped away from that fill light.
            // Flipping toward the *viewer* is the textbook formulation and is
            // what makes the inside of a transparent shell visible, which is the
            // whole reason the setting exists.
            if (twoSided == 1 && !gl_FrontFacing) {
                n = -n;
            }
            vec3 viewDir = normalize(-v_viewPos);
            float lambert = max(dot(n, l), 0.0);
            float fillLambert = max(dot(n, normalize(fillLightDir)), 0.0);

            float spec = 0.0;
            if (lambert > 0.0) {
                vec3 reflectDir = reflect(-l, n);
                spec = pow(max(dot(viewDir, reflectDir), 0.0), shininess) * specStrength;
            }

            vec3 baseColor = v_color.rgb;

            // Ambient occlusion is already multiplied into v_color, so the
            // surface term needs nothing further. What has to be damped is every
            // term that does *not* come from the surface colour -- ambient, rim,
            // environment reflection, sun -- because those reach a crevice from
            // directions the crevice cannot see. Leaving them undamped fills the
            // shading back in and the occlusion reads as an overall dimming
            // instead of as shape.
            // Floored, not linear. Occlusion is *already* multiplied into
            // v_color above, so damping these terms by the same factor counts it
            // twice: a deeply occluded fragment got a dark base colour and then
            // near-zero ambient, and went to solid black. On a cartoon that
            // swallowed whole helices -- visible only in a real GL render, which
            // is why it survived. A floor keeps occlusion reading as shape
            // without extinguishing anything.
            float exposure = mix(0.35, 1.0, clamp(1.0 - v_occ, 0.0, 1.0));

            // Fresnel for jelly/bubble look: edges are more opaque and reflective
            float fresnel = pow(clamp(1.0 - dot(n, viewDir), 0.0, 1.0), 2.5);

            // How much of a *surface* this fragment is. A translucent sheet is
            // not a mirror: reflection, rim and specular are surface effects,
            // and a metaball is a stack of many sheets, so adding them at full
            // strength on each one accumulates white until a coloured jelly
            // reads as milk. Opaque fragments (alpha 1) are unaffected.
            float sheet = mix(0.3, 1.0, clamp(v_color.a, 0.0, 1.0));

            // 1. Shading (Diffuse + Ambient)
            // The three lights in the mixing convention: the diffuse terms
            // (key and fill) are blended toward the ambient colour by the
            // ambient weight, so the total is a convex mix that stays in
            // [0, 1] as long as every coefficient does. Both the ambient and
            // the diffuse weight are clamped to that range: ChimeraX's presets
            // carry ambient values above 1 that are calibrated for its
            // *additive* model, and in a mixing formula an ambient above 1
            // makes the diffuse weight negative -- a face facing the light
            // renders *darker* than one turned away. The 0.7 is a stylistic
            // darkener (it makes rim and reflections pop) and is not part of
            // the reported `ambient_light_intensity`.
            float ambientCoeff = clamp(ambientStrength, 0.0, 1.0);
            float litWeight = clamp(
                keyIntensity * lambert + fillIntensity * fillLambert,
                0.0, 1.0
            );
            float ambient = ambientCoeff * 0.7 * exposure;
            float diffuse = (1.0 - ambient) * litWeight;
            vec3 shaded = baseColor * (ambient + diffuse);
            
            // 2. Rim lighting (edge glow)
            float rim = pow(clamp(1.0 - dot(n, viewDir), 0.0, 1.0), rimPower);
            shaded += baseColor * rim * rimStrength * exposure * sheet;
            
            // 3. Procedural Environment Reflection (Fake MatCap)
            vec3 R = reflect(-viewDir, n);
            vec3 skyCol = vec3(0.5, 0.7, 1.0);
            vec3 groundCol = vec3(0.05, 0.05, 0.1);
            vec3 envReflection = mix(groundCol, skyCol, smoothstep(-0.2, 0.4, R.y));
            
            // Add a "sun" highlight
            vec3 sunDir = normalize(vec3(0.5, 1.0, 0.5)); 
            float sun = pow(max(0.0, dot(R, sunDir)), max(10.0, shininess));
            envReflection += vec3(1.5) * sun;
            
            // Blend reflection based on Fresnel
            float reflectMul = clamp(specStrength * (0.1 + 0.6 * fresnel), 0.0, 1.0) * exposure * sheet;
            vec3 finalColor = mix(shaded, envReflection, reflectMul);
            
            // Point-source specular highlight
            finalColor += spec * exposure * sheet * vec3(1.0);
            
            // 4. Depth cue. `v_viewPos.z` is negative in front of the camera,
            // so `fogEnd + z` is how far short of the back plane this fragment
            // is; scaled by 1/(end - start) that is PyMOL's visibility factor.
            // `fogScale <= 0` means the cue is off and everything is unfogged.
            float vis = 1.0;
            if (fogScale > 0.0) {
                vis = clamp((fogEnd + v_viewPos.z) * fogScale, 0.0, 1.0);
            }
            finalColor = mix(fogColor, finalColor, vis);

            // 5. Transparency with Fresnel
            float finalAlpha = v_color.a;
            if (finalAlpha < 0.99) {
                // The edge of a jelly is more opaque than its middle, but the
                // boost has to stay *proportional* to the alpha asked for. The
                // old form added a flat 0.5 at the edges, and a metaball is
                // nearly all edge -- every lump presents its rim to the camera
                // -- so alpha saturated across the whole surface and 0.3 and
                // 0.6 rendered indistinguishably. Scaling the boost by the
                // room left keeps the look and restores the knob.
                float a = finalAlpha;
                finalAlpha = mix(a * 0.55, a + (1.0 - a) * 0.55, fresnel);
            }
            
            // Highlights are opaque -- a glint on wet glass hides what is behind
            // it -- but the amount added has to scale with how much room is
            // left, or a glossy material simply is not transparent: with
            // `specular_strength` at 0.85 this term saturated alpha to 1 over
            // most of the surface, so lowering the alpha changed nothing at all.
            // `spec` and `sun` are radiance terms and are *not* bounded by 1 --
            // they are added to the colour and allowed to blow out. Feeding
            // them into alpha unclamped drove a nominally 0.35-opaque surface
            // to ~0.85, which is why lowering the alpha barely changed what
            // showed through.
            float glint = clamp(spec + sun, 0.0, 1.0) * 0.25 * (1.0 - finalAlpha);
            gl_FragColor = vec4(finalColor, clamp(finalAlpha + glint, 0.0, 1.0));
        }
        """

        program = QtGui.QOpenGLShaderProgram(self.context())
        program.addShaderFromSourceCode(QtGui.QOpenGLShader.Vertex, vert_src)
        program.addShaderFromSourceCode(QtGui.QOpenGLShader.Fragment, frag_src)
        program.link()
        log = program.log()
        if log:
            print("QtGLRenderer shader log:\n", log)
        self._program = program
        self._pos_attr = program.attributeLocation("position")
        self._color_attr = program.attributeLocation("color")
        self._normal_attr = program.attributeLocation("normal")
        self._mvp_uniform = program.uniformLocation("mvp")
        self._normal_matrix_uniform = program.uniformLocation("normalMatrix")
        self._view_matrix_uniform = program.uniformLocation("viewMatrix")
        self._light_dir_uniform = program.uniformLocation("lightDir")
        self._fill_light_dir_uniform = program.uniformLocation("fillLightDir")
        self._key_intensity_uniform = program.uniformLocation("keyIntensity")
        self._fill_intensity_uniform = program.uniformLocation("fillIntensity")
        self._ambient_uniform = program.uniformLocation("ambientStrength")
        self._spec_strength_uniform = program.uniformLocation("specStrength")
        self._shininess_uniform = program.uniformLocation("shininess")
        self._rim_strength_uniform = program.uniformLocation("rimStrength")
        self._rim_power_uniform = program.uniformLocation("rimPower")
        self._fog_end_uniform = program.uniformLocation("fogEnd")
        self._fog_scale_uniform = program.uniformLocation("fogScale")
        self._fog_color_uniform = program.uniformLocation("fogColor")
        self._glyph_mode_uniform = program.uniformLocation("glyphMode")
        self._two_sided_uniform = program.uniformLocation("twoSided")
        self._point_size_uniform = program.uniformLocation("pointSize")
        self._point_scale_uniform = program.uniformLocation("pointScale")
        self._radius_attr = program.attributeLocation("radius")
        self._occlusion_attr = program.attributeLocation("occlusion")

    def _render_overlay(self) -> None:
        """Draw everything that lives in screen space, in one painter pass.

        Labels and the object panel share it because they share a cost: opening
        a QPainter on a QOpenGLWidget flushes the GL pipeline, so doing it twice
        per frame is twice the stall for no reason.
        """
        gui = self._internal_gui
        # Gated on the panel being *visible*, not on it having rows. `scene_width`
        # already gives the column away to a visible panel whether or not
        # anything is loaded, so skipping the paint on an empty object list did
        # not save the space -- it left a black stripe down the right of an empty
        # window, with the mouse-mode block and the splitter missing too.
        if (
            not self._labels
            and not gui.visible
            and not gui.has_menu()
            and self._select_rect is None
            and self._ray_image is None
        ):
            return

        # QPainter draws through the same GL context, so it inherits whatever
        # state the scene pass left behind. Face culling was the one that bit:
        # the panel's filled rectangles vanished while its *text* still drew,
        # which reads as a broken painter rather than as leftover state.
        gl = self._gl
        if gl is not None:
            gl.glDisable(GL_DEPTH_TEST)
            gl.glDisable(GL_CULL_FACE)
            gl.glDepthMask(True)
            gl.glDisable(GL_BLEND)

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        try:
            self.paint_screen_space(painter)
        finally:
            painter.end()

    def paint_screen_space(self, painter) -> None:
        """Everything in screen space, in the order it must be drawn.

        Parameters
        ----------
        painter : QtGui.QPainter
            Open on the widget in normal use, and on a plain ``QImage`` in
            tests -- which is the reason this is split out of
            :meth:`_render_overlay`. The order below is the whole contract and
            a headless renderer cannot read back a GL framebuffer to check it.
        """
        gui = self._internal_gui
        # First, so everything below is chrome drawn *over* the ray result
        # exactly as it is drawn over the live scene.
        self._paint_ray_image(painter)
        if self._labels:
            self._paint_labels(painter)
        self._refresh_gui_state(gui)
        gui.layout(self.width(), self.height())
        gui.paint(painter)
        self._paint_selection_box(painter)

    def show_ray_image(self, image) -> bool:
        """Show a traced image in place of the live scene.

        Parameters
        ----------
        image : QtGui.QImage
            The ray-traced frame.

        Returns
        -------
        bool
            True when the image was accepted.

        Notes
        -----
        This used to be a ``QLabel`` laid over the viewport, and that widget
        covered PyMOL's object panel with it -- the panel is drawn *in* the
        viewport, so anything laid over the scene hides the A/S/H/L/C menus,
        the mouse-mode block and the sequence strip. The panel is the only way
        to switch a representation back on, so it went away exactly when the
        user next needed it, and the click that dismissed the overlay was
        swallowed rather than reaching the button it landed on. The traced
        image belongs *behind* the chrome; only the saved file is chrome-free.
        """
        if image is None or image.isNull():
            return False
        self._ray_image = image
        self.update()
        return True

    def clear_ray_image(self) -> bool:
        """Drop the traced image and go back to the live scene.

        Returns
        -------
        bool
            True when an image was showing.
        """
        if self._ray_image is None:
            return False
        self._ray_image = None
        self.update()
        return True

    def ray_image_rect(self) -> QtCore.QRect:
        """The area a traced image is allowed to occupy.

        Returns
        -------
        QtCore.QRect
            The scene column, in widget pixels.

        Notes
        -----
        The scene *column*, not the widget: the panel's column and the sequence
        strip's band are chrome drawn in this viewport, and an image painted
        across them puts the picture where the chrome goes -- which is the
        fault this replaced, in a different spelling. Exposed rather than
        computed inline so the containment can be asserted exactly; a pixel
        probe cannot, because the panel's background is semi-transparent and
        would darken an out-of-bounds image rather than replace it.
        """
        gui = getattr(self, "_internal_gui", None)
        strip = int(gui.sequence_height()) if gui is not None else 0
        return QtCore.QRect(
            0, strip, self.scene_width(), max(self.height() - strip, 1)
        )

    def _paint_ray_image(self, painter) -> None:
        """Blit the traced image into the scene column, aspect preserved."""
        image = self._ray_image
        if image is None or image.isNull():
            return

        target = self.ray_image_rect()
        if target.width() <= 0 or target.height() <= 0:
            return

        scaled = image.size().scaled(target.size(), QtCore.Qt.KeepAspectRatio)
        where = QtCore.QRect(QtCore.QPoint(0, 0), scaled)
        where.moveCenter(target.center())

        # The letterbox is filled rather than left showing the last GL frame,
        # or a traced image of a different aspect ratio sits in a frame of the
        # live scene it replaced.
        painter.fillRect(target, QtGui.QColor(0, 0, 0))
        painter.drawImage(where, image)

    def _paint_selection_box(self, painter) -> None:
        """Outline the selection box being dragged, PyMOL-style.

        A thin dashed rectangle over the scene, with no fill: the box exists to
        say which atoms it is about to take, and a tinted fill hides them.
        """
        rect = self._select_rect
        if rect is None or rect.isNull():
            return
        pen = QtGui.QPen(QtGui.QColor(255, 255, 255, 220))
        pen.setWidth(1)
        pen.setStyle(QtCore.Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        painter.drawRect(QtCore.QRectF(rect))

    def _refresh_gui_state(self, gui) -> None:
        """Read the movie position into the panel before it is drawn.

        Pulled every frame rather than pushed on change, because there is no one
        place a frame changes: playback advances it on a timer, `frame` and the
        transport set it directly, and a trajectory reload resets it. A slider
        wired to one of those and not the others sits still while the molecule
        moves, which is worse than having no slider.

        A drag in progress wins: the position under the cursor is what the user
        is asking for, and overwriting it from the viewer each frame would drag
        the thumb back out of their hand.
        """
        controller = self._controller
        if controller is None or gui.is_dragging():
            return

        # Re-read the sequence colours as well. Colouring is a *command* --
        # `spectrum`, `color`, `ss` -- and there is no signal for it, so a strip
        # coloured once at load keeps showing the old scheme while the molecule
        # in front of it shows the new one. Reading them back is a cached array
        # copy, which costs nothing beside drawing the molecule itself.
        for row in gui.sequences:
            if not row.object_id:
                continue
            try:
                colours = controller.get_residue_colors(row.object_id)
            except Exception:
                continue
            if colours is None:
                continue
            row.colors = [tuple(float(c) for c in rgba[:3]) for rgba in colours]

        try:
            current = int(controller.get_current_frame()) + 1
            total = max(int(controller.get_total_frames()), 1)
        except Exception:
            return
        if (current, total) != gui.state:
            gui.state = (current, total)

    def _paint_labels(self, painter) -> None:
        """Draw the 3-D labels, projected to the window."""
        painter.save()
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        mvp, _ = self._build_matrices()
        # Scene width: a label is projected through the same matrices the scene
        # is drawn with, so it must be mapped into the same rectangle.
        w = self.scene_width()
        h = self.height()

        for label in self._labels:
            # Project 3D to 2D
            pos4 = QtGui.QVector4D(float(label.pos[0]), float(label.pos[1]), float(label.pos[2]), 1.0)
            clip_pos = mvp * pos4
            if clip_pos.w() <= 0:
                continue
            
            ndc = QtGui.QVector3D(clip_pos.x() / clip_pos.w(), clip_pos.y() / clip_pos.w(), clip_pos.z() / clip_pos.w())
            if ndc.x() < -1 or ndc.x() > 1 or ndc.y() < -1 or ndc.y() > 1 or ndc.z() < -1 or ndc.z() > 1:
                continue
            
            win_x = (ndc.x() + 1.0) * 0.5 * w
            win_y = (1.0 - ndc.y()) * 0.5 * h
            
            painter.setPen(label.color)
            # Draw shadow for readability
            painter.setPen(QtGui.QColor(0, 0, 0, 150))
            painter.drawText(int(win_x) + 1, int(win_y) + 1, label.text)
            painter.setPen(label.color)
            painter.drawText(int(win_x), int(win_y), label.text)

        painter.restore()

    def _point_scale(self) -> float:
        """Pixels per unit of model size at unit camera distance.

        Half the framebuffer height over ``tan(fov / 2)``: the vertex shader
        divides it by the camera-space depth to turn a sphere impostor's world
        radius into a sprite size in pixels. It is in *framebuffer* pixels, so
        a Retina display gets a sprite twice as wide, exactly as a mesh sphere
        covering the same solid angle does.

        This is the *perspective* formula, which is what :meth:`_build_matrices`
        builds unconditionally. Under a parallel projection a sprite must not
        shrink with depth, so whoever makes the ``orthoscopic`` flag reach the
        projection has to make it reach here too.

        Returns
        -------
        float
            The scale factor, always positive.
        """
        ratio = float(self.devicePixelRatioF()) if hasattr(self, "devicePixelRatioF") else 1.0
        height = max(1.0, float(self.height()) * ratio)
        half_fov = math.radians(max(1e-3, float(self._fov)) * 0.5)
        return 0.5 * height / max(math.tan(half_fov), 1e-6)

    def _fog_planes(self) -> tuple[float, float]:
        """Return ``(fog_end, fog_scale)`` for the depth cue, PyMOL's way.

        Transcribed from ``SceneSetFog`` (``layer1/Scene.cpp``)::

            FogStart = (back - front) * fog_start + front
            FogEnd   = fog in (0, 1) ? FogStart + (back - FogStart) / fog : back
            active   = depth_cue and fog != 0

        and the shader then reads a *visibility*, ``(FogEnd - depth) /
        (FogEnd - FogStart)``.

        The planes are the ones fitted **around the scene** -- the camera
        distance either side of the target radius -- not the camera's far plane.
        That distinction is the whole of this feature: the ray tracer was once
        normalised over an unfitted far plane and fogged every pixel of the
        molecule 24-69 %, which reads as a dimmer rather than a depth cue. The
        two renderers now measure the cue over the same span.

        Returns
        -------
        tuple of float
            ``fog_end`` in view units, and ``1 / (end - start)``. A scale of
            ``0`` means the cue is off, which is what the shader tests.
        """
        cfg = _DISPLAY_CONFIG.get("depth_cue", {}) or {}
        # PyMOL's `depth_cue`, `fog` and `fog_start` are global: they govern the
        # viewport, and the tracer follows them unless `ray_trace_fog` overrides.
        # chimol has only ever applied them to the tracer, so the viewport had
        # no depth cue at all -- `fogDensity` was initialised to 0.0 and never
        # assigned from anywhere.
        if not bool(cfg.get("enabled", True)):
            return 0.0, 0.0
        density = float(cfg.get("intensity", 1.0))
        if density == 0.0:
            return 0.0, 0.0

        radius = max(float(self._target_radius), 1e-6)
        front = max(float(self._distance) - radius, 1e-6)
        back = float(self._distance) + radius
        if back <= front:
            return 0.0, 0.0

        start = (back - front) * float(cfg.get("start", 0.45)) + front
        if 0.0 < density < 1.0:
            end = start + (back - start) / density
        else:
            end = back
        if end <= start:
            return 0.0, 0.0
        return end, 1.0 / (end - start)

    def _build_matrices(self) -> tuple[QtGui.QMatrix4x4, QtGui.QMatrix4x4]:
        # The width the *scene* has, not the widget's: the panel takes a column
        # and the viewport was already narrowed to match. Projecting with the
        # full width stretches the same picture into a narrower viewport, which
        # is exactly the squashed molecule that reported this.
        width = max(self.scene_width(), 1)
        height = max(self.scene_height(), 1)
        aspect = width / float(height)
        proj = QtGui.QMatrix4x4()
        proj.perspective(self._fov, aspect, self._near_clip, self._far_clip)

        view = QtGui.QMatrix4x4()
        # The camera-space offset is applied *after* the rotation, which slides the
        # image without moving the pivot -- that separation is what `origin` needs.
        shift = self._view_shift
        view.translate(
            float(shift[0]), float(shift[1]), float(shift[2]) - self._distance
        )
        r = self._rot
        rot_qm = QtGui.QMatrix4x4(
            float(r[0, 0]), float(r[0, 1]), float(r[0, 2]), 0.0,
            float(r[1, 0]), float(r[1, 1]), float(r[1, 2]), 0.0,
            float(r[2, 0]), float(r[2, 1]), float(r[2, 2]), 0.0,
            0.0, 0.0, 0.0, 1.0,
        )
        view = view * rot_qm
        center = np.zeros(3, dtype=float)
        if self._scene is not None:
            try:
                center = np.asarray(self._scene.center, dtype=float)
            except Exception:
                center = np.zeros(3, dtype=float)
        center = center + self._pan_offset
        view.translate(-center[0], -center[1], -center[2])
        return proj * view, view

    def _camera_position(self) -> np.ndarray:
        center = np.zeros(3, dtype=float)
        if self._scene is not None:
            try:
                center = np.asarray(self._scene.center, dtype=float)
            except Exception:
                center = np.zeros(3, dtype=float)
        center = center + self._pan_offset
        # Camera axes in world are the rows of the world->camera rotation; the
        # camera sits distance units along its +Z axis (row 2) from the target,
        # less whatever camera-space offset slides the image (see _build_matrices).
        shift = self._view_shift
        return (
            center
            + self._distance * self._rot[2]
            - float(shift[0]) * self._rot[0]
            - float(shift[1]) * self._rot[1]
            - float(shift[2]) * self._rot[2]
        )

    def _prepare_draw_data(self, scene: Optional[Scene]) -> None:
        """Convert Scene objects into CPU-side arrays ready for VBO upload."""
        self._draw_data = []
        self._labels = []
        if scene is None:
            self._needs_upload = True
            return
        for obj in scene.objects:
            if obj.geometry.kind == "text":
                self._prepare_labels(obj)
                continue
            draw = self._geometry_to_draw_data(obj)
            if draw is not None:
                self._draw_data.append(draw)
        if self._grid_visible:
            grid_draw = self._build_grid_draw_data(scene.radius if scene else self._target_radius)
            if grid_draw is not None:
                self._draw_data.insert(0, grid_draw)
        self._needs_upload = True

    def _prepare_labels(self, obj: SceneObject) -> None:
        geom = obj.geometry
        labels = geom.meta.get("labels", [])
        positions = np.asarray(geom.positions, dtype=float)
        colors = geom.colors
        
        n = min(len(labels), positions.shape[0])
        for i in range(n):
            col = QtGui.QColor(255, 255, 255)
            if colors is not None and i < colors.shape[0]:
                c = colors[i]
                col = QtGui.QColor(int(c[0]*255), int(c[1]*255), int(c[2]*255), int(c[3]*255))
            
            self._labels.append(_LabelData(
                pos=positions[i],
                text=str(labels[i]),
                color=col,
                depth_test=obj.render_mode != "overlay"
            ))

    def _geometry_to_draw_data(self, obj: SceneObject) -> Optional[_DrawData]:
        geom = obj.geometry
        if geom.positions is None:
            return None
        positions = np.asarray(geom.positions, dtype=np.float32)
        if positions.size == 0:
            return None
        normals = None
        # Per-vertex occlusion is indexed like the positions, so it has to be
        # expanded through the same index array or it will not line up with the
        # flattened triangle list and is silently dropped.
        occlusion = None
        if geom.occlusion is not None:
            occlusion = np.asarray(geom.occlusion, dtype=np.float32).reshape(-1)
        indices_out = None
        if geom.indices is not None:
            try:
                idx = np.asarray(geom.indices, dtype=np.int32).reshape(-1)
                # One pass, not four. `idx.max()` was recomputed for the
                # occlusion, the colours and the normals in turn, and on a
                # cartoon this array holds a couple of million entries -- so
                # three quarters of the scans were pure repetition, on the path
                # every single frame of a trajectory goes through.
                vertex_count = int(idx.max()) + 1 if idx.size else 0

                # Draw the mesh indexed whenever every per-vertex attribute is
                # already indexed the same way. Expanding it into a flat
                # triangle list instead -- which is what this did unconditionally
                # -- costs a gather over every attribute *and* multiplies what
                # goes to the GPU: a cartoon's 68k vertices become 402k, and
                # 2.7 MB a frame becomes 16 MB. The expansion path below stays
                # for meshes whose attributes do not line up, where it is the
                # only way to draw them at all.
                aligned = positions.shape[0] == vertex_count
                if aligned and geom.colors is not None:
                    aligned = np.asarray(geom.colors).shape[0] == vertex_count
                if aligned and geom.normals is not None:
                    aligned = np.asarray(geom.normals).shape[0] == vertex_count
                if aligned and occlusion is not None:
                    aligned = occlusion.shape[0] == vertex_count
                if aligned:
                    indices_out = idx.astype(np.uint32, copy=False)
                    colors = (
                        np.asarray(geom.colors, dtype=np.float32)
                        if geom.colors is not None
                        else None
                    )
                    normals = (
                        np.asarray(geom.normals, dtype=np.float32)
                        if geom.normals is not None
                        else None
                    )
                else:
                    if occlusion is not None:
                        occlusion = (
                            occlusion[idx]
                            if occlusion.shape[0] == vertex_count
                            else None
                        )
                    positions = positions[idx]
                    if geom.colors is not None:
                        colors = np.asarray(geom.colors, dtype=np.float32)
                        if colors.shape[0] == vertex_count:
                            colors = colors[idx]
                        else:
                            colors = np.resize(
                                colors, (positions.shape[0], colors.shape[1])
                            )
                    else:
                        colors = None
                    if geom.normals is not None:
                        normals = np.asarray(geom.normals, dtype=np.float32)
                        if normals.shape[0] == vertex_count:
                            normals = normals[idx]
                        else:
                            normals = np.resize(normals, (positions.shape[0], 3))
                    else:
                        normals = None
            except Exception:
                logger.warning(
                    "chimol: could not prepare indexed geometry; drawing it "
                    "unindexed", exc_info=True
                )
                indices_out = None
                colors = None
                normals = None
        else:
            colors = None
            if geom.normals is not None:
                normals = np.asarray(geom.normals, dtype=np.float32)

        if colors is None and geom.colors is not None:
            colors = np.asarray(geom.colors, dtype=np.float32)
            if colors.shape[0] != positions.shape[0]:
                if colors.shape[0] == 1:
                    colors = np.repeat(colors, positions.shape[0], axis=0)
                else:
                    colors = np.resize(colors, (positions.shape[0], colors.shape[1]))
        if colors is None:
            base_color = geom.meta.get("base_color") if geom.meta else None
            if isinstance(base_color, (tuple, list)) and len(base_color) >= 4:
                base = np.array(base_color[:4], dtype=np.float32)
            else:
                base = np.array([1.0, 1.0, 1.0, 1.0], dtype=np.float32)
            colors = np.tile(base, (positions.shape[0], 1))
        colors = colors.astype(np.float32, copy=False)

        if normals is None or normals.shape[0] != positions.shape[0]:
            normals = np.zeros_like(positions, dtype=np.float32)
            normals[:, 2] = 1.0
        else:
            normals = normals.astype(np.float32, copy=False)

        primitive = self._primitive_for_geometry(geom)
        if primitive is None:
            return None
        size = float(geom.meta.get("size", geom.meta.get("radius", 4.0))) if geom.meta else 4.0
        width = float(geom.meta.get("width", 2.0)) if geom.meta else 2.0
        depth_test = obj.render_mode != "overlay"
        glyph = None
        two_sided = False
        world_radius = False
        if geom.meta:
            glyph = geom.meta.get("glyph")
            two_sided = bool(geom.meta.get("two_sided", False))
            world_radius = bool(geom.meta.get("world_radius", False))

        return _DrawData(
            primitive=primitive,
            positions=positions,
            colors=colors,
            normals=normals,
            indices=indices_out,
            render_mode=obj.render_mode,
            width=width,
            depth_test=depth_test,
            glyph=glyph,
            radii=np.asarray(geom.radii, dtype=np.float32) if geom.radii is not None else None,
            occlusion=(
                occlusion
                if occlusion is not None and occlusion.shape[0] == positions.shape[0]
                else None
            ),
            material=obj.material,
            two_sided=two_sided,
            world_radius=world_radius,
        )

    def _primitive_for_geometry(self, geom: Geometry) -> Optional[int]:
        kind = geom.kind.lower()
        if kind == "mesh":
            return GL_TRIANGLES
        if kind == "line":
            mode = (geom.meta or {}).get("mode", "lines")
            if mode == "line_strip":
                return GL_LINE_STRIP
            return GL_LINES
        if kind == "points":
            return GL_POINTS
        return None

    #: How many grid lines to draw across the scene, each way. A *count*, not a
    #: spacing: the spacing has to follow the molecule's size, or the same
    #: setting gives four lines on a peptide and four hundred on a ribosome.
    GRID_LINES_ACROSS = 20

    def _build_grid_draw_data(self, radius: float) -> Optional[_DrawData]:
        half = max(self._grid_size, radius * 1.2)
        # Spacing derived from the extent rather than taken as an absolute.
        # `_grid_spacing` is 1.0 in *scene* units while a protein's radius is a
        # couple of hundred, so a fixed spacing drew ~415 lines each way: an
        # aliased grey sheet that buried the molecule instead of a reference
        # plane behind it.
        spacing = max(
            float(self._grid_spacing),
            2.0 * half / float(max(1, self.GRID_LINES_ACROSS)),
        )
        if spacing <= 0.0:
            return None
        lines = []
        n = int(math.ceil(half / spacing))
        for i in range(-n, n + 1):
            x = i * spacing
            lines.append([[x, -half, 0.0], [x, half, 0.0]])
            lines.append([[-half, x, 0.0], [half, x, 0.0]])
        if not lines:
            return None
        positions = np.asarray(lines, dtype=np.float32).reshape(-1, 3)
        # Faint: it is a reference, not a subject. At full strength a grid drawn
        # across the molecule competes with it for attention.
        color = np.array([0.55, 0.55, 0.55, 0.5], dtype=np.float32)
        colors = np.tile(color, (positions.shape[0], 1))
        normals = np.zeros_like(positions, dtype=np.float32)
        normals[:, 2] = 1.0
        return _DrawData(
            primitive=GL_LINES,
            positions=positions,
            colors=colors,
            normals=normals,
            render_mode="overlay",
            width=1.0,
            depth_test=False,
        )

    def _upload_draw_data(self) -> None:
        """Upload cached draw data into VBOs (idempotent until scene changes)."""
        if self._gl is None or self._program is None:
            return
        self._release_gpu_calls()
        gl = self._gl
        for draw in self._draw_data:
            vbo_pos = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
            vbo_pos.create()
            vbo_pos.bind()
            vbo_pos.allocate(draw.positions.tobytes(), draw.positions.nbytes)
            vbo_pos.release()

            vbo_col = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
            vbo_col.create()
            vbo_col.bind()
            vbo_col.allocate(draw.colors.tobytes(), draw.colors.nbytes)
            vbo_col.release()

            vbo_norm = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
            vbo_norm.create()
            vbo_norm.bind()
            vbo_norm.allocate(draw.normals.tobytes(), draw.normals.nbytes)
            vbo_norm.release()

            centroid_z = float(np.mean(draw.positions[:, 2])) if draw.render_mode == "transparent" and draw.positions.shape[0] > 0 else 0.0

            gpu_call = _GpuDrawCall(
                primitive=draw.primitive,
                vertex_count=draw.positions.shape[0],
                positions_vbo=vbo_pos,
                colors_vbo=vbo_col,
                normals_vbo=vbo_norm,
                render_mode=draw.render_mode,
                size=draw.size,
                width=draw.width,
                depth_test=draw.depth_test,
                depth=centroid_z,
                glyph=draw.glyph,
                material=draw.material,
                two_sided=draw.two_sided,
                world_radius=draw.world_radius,
            )
            self._gpu_calls.append(gpu_call)

            if draw.indices is not None and draw.indices.size:
                vbo_idx = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.IndexBuffer)
                vbo_idx.create()
                vbo_idx.bind()
                vbo_idx.allocate(draw.indices.tobytes(), draw.indices.nbytes)
                vbo_idx.release()
                gpu_call.index_vbo = vbo_idx
                gpu_call.index_count = int(draw.indices.size)

            if draw.radii is not None and draw.radii.size == draw.positions.shape[0]:
                vbo_rad = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
                vbo_rad.create()
                vbo_rad.bind()
                vbo_rad.allocate(draw.radii.tobytes(), draw.radii.nbytes)
                vbo_rad.release()
                gpu_call.radii_vbo = vbo_rad

            if (
                draw.occlusion is not None
                and draw.occlusion.size == draw.positions.shape[0]
            ):
                vbo_occ = QtGui.QOpenGLBuffer(QtGui.QOpenGLBuffer.VertexBuffer)
                vbo_occ.create()
                vbo_occ.bind()
                vbo_occ.allocate(draw.occlusion.tobytes(), draw.occlusion.nbytes)
                vbo_occ.release()
                gpu_call.occlusion_vbo = vbo_occ

        self._needs_upload = False

    def _release_gpu_calls(self) -> None:
        for call in self._gpu_calls:
            if call.positions_vbo.isCreated():
                call.positions_vbo.destroy()
            if call.colors_vbo.isCreated():
                call.colors_vbo.destroy()
            if call.normals_vbo.isCreated():
                call.normals_vbo.destroy()
            if call.radii_vbo is not None and call.radii_vbo.isCreated():
                call.radii_vbo.destroy()
            if call.occlusion_vbo is not None and call.occlusion_vbo.isCreated():
                call.occlusion_vbo.destroy()
            if call.index_vbo is not None and call.index_vbo.isCreated():
                call.index_vbo.destroy()
        self._gpu_calls = []

    # ------------------------------------------------------------------
    # Input handling (basic orbit controls)
    # ------------------------------------------------------------------
    def _gui_pos(self, event) -> tuple[float, float]:
        """The event position in widget pixels, for the in-viewport panel."""
        pos = event.pos()
        return float(pos.x()), float(pos.y())

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        # The panel is drawn over the scene, so it is offered the press first.
        # Otherwise a click meant for a menu also starts rotating the molecule,
        # and the model spins away under the menu that just opened.
        x, y = self._gui_pos(event)
        if self._internal_gui.mouse_press(
            x,
            y,
            right=event.button() == QtCore.Qt.RightButton,
            modifiers=event.modifiers(),
            double=event.type() == QtCore.QEvent.MouseButtonDblClick,
        ):
            self._gui_grab = True
            self._last_mouse_pos = event.pos()
            self.update()
            event.accept()
            return

        # Past the panel, so this press is aimed at the scene -- and the scene
        # is about to move under a still frame of where it used to be. The
        # press is *not* consumed: dismissing a picture is not what the user
        # asked for by clicking, and swallowing the click is what made the
        # first click after `ray` do nothing.
        self.clear_ray_image()

        if event.button() == QtCore.Qt.RightButton:
            # The right button carries a box too -- `-Box` is shift-right in the
            # two-button modes -- so the table is asked before the press is
            # deferred, or that cell of the block on screen names a gesture the
            # widget never starts.
            if self._start_box_drag(event, event.modifiers()):
                return
            # Defer: a right *drag* dollies (see mouseMoveEvent); a right *click*
            # opens the context menu on release.
            self._last_mouse_pos = event.pos()
            self._right_dragged = False
            event.accept()
            return

        if event.button() in (QtCore.Qt.LeftButton, QtCore.Qt.MiddleButton):
            mods = event.modifiers()
            # Which action this button carries comes from the same table the
            # block on screen draws, so what the panel promises and what the
            # mouse does cannot drift apart. PyMOL binds the box select to
            # shift-left (`+Box`) and the residue select to ctrl-shift-left
            # (`Sele`); both drag a rubber band here.
            #
            # The **middle** button comes through here too. It used to be caught
            # above and turned straight into a pan, so its three modified cells
            # -- `-Box` on shift, `PkAt` on ctrl, `Orig` on ctrl-shift -- were
            # unreachable: the block on screen promised a subtract-box that
            # panned the camera instead. Plain middle is `Move`, which still
            # pans, and it now says so through the table rather than beside it.
            action = mouse_action_of(
                self._internal_gui.mouse_mode, event.button(), mods
            )
            if action == "move":
                self._panning = True
                self._last_mouse_pos = event.pos()
                event.accept()
                return
            if self._start_box_drag(event, mods):
                return
            # A non-box press is a candidate click (or the start of a drag --
            # left drags rotate via the trackball in mouseMoveEvent). PyMOL
            # decides on release: a press that never dragged fires the
            # `single_*` cell, so the click action (e.g. `+/-`) and the drag
            # action (e.g. `rota`) can differ. Record the press and let the
            # release handler tell them apart.
            self._press_pos = event.pos()
            self._press_mods = mods
            self._press_button = event.button()
            self._last_mouse_pos = event.pos()
            event.accept()
            return

        self._last_mouse_pos = event.pos()
        super().mousePressEvent(event)

    #: The mode-table actions that drag a selection box. `box` is Maestro's
    #: plain-left cell, and it was the one action of the four the press did not
    #: recognise -- the block drew `Box` and the drag rotated the camera.
    _BOX_ACTIONS = ("+box", "-box", "sele", "box")

    def _start_box_drag(self, event, modifiers) -> bool:
        """Begin a selection box if this press is bound to one.

        Returns whether the press was taken. Shared by every button, because
        which button carries a box is the mode table's business, not the
        handler's: `+Box` is shift-left, `-Box` is shift-middle in the
        three-button modes and shift-right in the two-button ones.
        """
        try:
            action = mouse_action_of(
                self._internal_gui.mouse_mode, event.button(), modifiers
            )
        except Exception:
            return False
        if action not in self._BOX_ACTIONS:
            return False
        self._drag_selecting = True
        self._drag_start = event.pos()
        self._drag_modifiers = modifiers
        self._drag_action = action
        self._drag_button = event.button()
        self._select_rect = QtCore.QRect(self._drag_start, QtCore.QSize(0, 0))
        self.update()
        event.accept()
        return True

    def _end_box_drag(self, event) -> None:
        """Apply the dragged box and clear it, whatever it ended up enclosing."""
        rect = self._select_rect or QtCore.QRect()
        self._select_rect = None
        self._drag_selecting = False
        self._drag_start = None
        self._drag_button = None
        self.update()
        if self._controller is None:
            self._drag_action = None
            return
        if rect.width() > 2 and rect.height() > 2:
            self._controller.handle_rect_selection(
                rect, self._drag_modifiers, self._drag_action
            )
        elif self._drag_action is not None:
            # A box that was never dragged is a **click**, and it has to act
            # like one: ctrl-shift-left is `Sele`, so the press claims it as a
            # rubber band, and a plain ctrl-shift *click* -- which is how anyone
            # coming from PyMOL selects a residue -- then fell through a
            # zero-size rectangle and did nothing at all. Each box action
            # degenerates to the same operation on the atom under the cursor.
            self._controller.handle_mouse_click(event, self._drag_action)
        self._drag_action = None

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        # Hover feedback, and the same precedence as the press: while the
        # cursor is over the panel it must not be dragging the camera.
        x, y = self._gui_pos(event)
        if self._gui_grab:
            if self._internal_gui.is_dragging() and self._internal_gui.drag(x, y):
                self.update()
            event.accept()
            return
        if not event.buttons():
            if self._internal_gui.mouse_move(x, y):
                self.update()
            if self._internal_gui.wants(x, y):
                event.accept()
                return
        elif self._internal_gui.has_menu():
            event.accept()
            return


        if self._drag_selecting and self._drag_start is not None:
            self._select_rect = QtCore.QRect(
                self._drag_start, event.pos()
            ).normalized()
            self.update()
            event.accept()
            return

        # The *press* decided which gesture this is, from the mode table, so the
        # drag follows that decision rather than re-deriving one from the button.
        # Keyed on the button instead, `Move` on ctrl-left rotated -- the table
        # said pan, the middle-button branch was the only pan, and the left
        # button fell through to the trackball.
        if self._panning and self._last_mouse_pos is not None:
            delta = event.pos() - self._last_mouse_pos
            self._pan_from_delta(delta.x(), delta.y())
            self._last_mouse_pos = event.pos()
            event.accept()
            return

        # Right drag = dolly (PyMOL cButModeTransZ): vertical motion moves the
        # camera in/out proportional to the current distance. A right *click*
        # (no drag) still opens the context menu, handled on release.
        if (event.buttons() & QtCore.Qt.RightButton) and self._last_mouse_pos is not None:
            delta = event.pos() - self._last_mouse_pos
            factor = (delta.y() / 400.0) * max(5.0, self._distance)
            self._distance = max(0.1, self._distance + factor)
            self._right_dragged = True
            self._last_mouse_pos = event.pos()
            self.update()
            event.accept()
            return

        if event.buttons() & QtCore.Qt.LeftButton and self._last_mouse_pos is not None:
            # PyMOL virtual trackball: rotate about a screen-space axis so the
            # object follows the cursor and the view can roll.
            last = (float(self._last_mouse_pos.x()), float(self._last_mouse_pos.y()))
            cur = (float(event.pos().x()), float(event.pos().y()))
            delta_rot = self._trackball_delta(last, cur, self.scene_width(), self.height())
            rot = delta_rot @ self._rot
            # Re-orthonormalise to prevent numerical drift over many drags.
            u, _, vt = np.linalg.svd(rot)
            self._rot = u @ vt
            self._last_mouse_pos = event.pos()
            self.update()
        super().mouseMoveEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        mods = event.modifiers()
        # Whichever axis carries it. **macOS turns shift+scroll into a
        # horizontal scroll** before the application ever sees it, so a shifted
        # wheel arrives with `angleDelta().y() == 0` and the whole delta in
        # `x()`. Reading only `y` is why shift+wheel did nothing on a Mac while
        # a synthetic event in a test -- which sets `y` -- worked perfectly.
        angle = event.angleDelta()
        raw = angle.y() if angle.y() else angle.x()
        delta_steps = int(raw / 120.0)
        if raw and delta_steps == 0:
            # A trackpad sends many small deltas rather than 120-unit notches;
            # truncating them to zero makes the gesture do nothing at all.
            delta_steps = 1 if raw > 0 else -1

        pos = event.position() if hasattr(event, "position") else event.posF()
        gui = self._internal_gui

        # Over an open menu, the wheel scrolls the menu -- PyMOL's `CPopUp`
        # takes the scroll buttons and translates the pop-up. A menu longer
        # than the window is the ordinary case for the Action menu on a small
        # viewport, and zooming the molecule underneath it is never what was
        # meant.
        if gui.has_menu():
            if delta_steps and gui.scroll_menu(pos.x(), pos.y(), delta_steps):
                self.update()
            event.accept()
            return

        # Over the sequence, the wheel scrolls it. Zooming the molecule because
        # the cursor happened to be on the strip is never what was meant.
        if not (gui.sequence_visible and gui.sequence_strip_contains(pos.x(), pos.y())):
            # About to move the camera, so the still frame stops being true.
            self.clear_ray_image()
        if gui.sequence_visible and gui.sequence_strip_contains(pos.x(), pos.y()):
            if delta_steps and gui.scroll_sequence(-delta_steps * 5):
                self.update()
            event.accept()
            return
        # PyMOL's wheel column, transcribed: `Shft` is `MovS` and `CtSh` is
        # `MovZ`, both of which move the **whole slab** -- `SceneClipMode::
        # Proportional` shifts front *and* back by `(front - back) * movement`
        # (`layer1/Scene.cpp`) -- while `Ctrl` is `MvSZ`, the same move with the
        # camera following it.
        #
        # What stood here moved the *near plane alone*, multiplicatively, and
        # clamped it to `max_near_clip` = 5 scene units. On a molecule ~200
        # units across the near plane therefore never reached the geometry
        # whatever you did, which is why shift-wheel appeared to do nothing at
        # all. Moving the slab by a fraction of its own thickness is
        # scale-free, so one wheel step is one step whatever the molecule.
        if delta_steps != 0 and (mods & (QtCore.Qt.ShiftModifier | QtCore.Qt.ControlModifier)):
            self._fit_slab_to_scene()
            thickness = max(float(self._far_clip) - float(self._near_clip), 1e-6)
            shift = thickness * self._slab_wheel_fraction * float(delta_steps)
            near = float(self._near_clip) + shift
            far = float(self._far_clip) + shift
            # The slab may travel, but it must not turn inside out or cross the
            # camera: a near plane at or behind zero makes the projection
            # singular and the scene vanishes rather than clips.
            if near > self._min_near_clip and far > near:
                self._near_clip, self._far_clip = near, far
                if mods & QtCore.Qt.ControlModifier:
                    # `MvSZ`: the camera goes with it, so the slab stays put
                    # against the molecule and the view dollies instead.
                    self._distance = max(float(self._distance) + shift, 0.1)
                self._announce_clipping()
                self.update()
            event.accept()
            return

        delta = delta_steps
        if delta != 0:
            self._distance = max(self._distance * (1.0 - 0.1 * delta), 2.0)
            self.update()
        super().wheelEvent(event)

    def _fit_slab_to_scene(self) -> None:
        """Put the slab around the molecule, once, before it is first moved.

        The clipping planes come from the configuration -- 0.03 and 2000 scene
        units -- and nothing re-derived them from what is actually on screen. So
        the near plane sat about 1500 units in *front* of a molecule 400 units
        deep, and the first several wheel clicks moved a slab through empty
        space: the gesture worked and the picture did not change, which is
        indistinguishable from the gesture doing nothing.

        PyMOL fits front and back around the scene (`SceneClipSet` after a
        zoom), so a click is a click on a peptide and on a ribosome alike. This
        does the same, and only while the slab is still the configured default:
        once it has been moved, it is the user's and must stay where they put
        it.
        """
        if self._slab_moved:
            return
        self._slab_moved = True
        radius = max(float(self._target_radius), 1e-3)
        distance = float(self._distance)
        near = distance - radius
        far = distance + radius
        if near > self._min_near_clip and far > near:
            self._near_clip, self._far_clip = near, far
            # This *is* the framing, so it becomes the baseline "not clipped"
            # position: scroll one step out and back and the status line has to
            # say `Clipping: off` again, which it can only do if the reference
            # moved with the slab.
            self._framed_near_clip = near
            self._framed_far_clip = far

    def _clamp_near_clip(self, value: float) -> float:
        val = max(float(value), self._min_near_clip)
        val = min(val, self._max_near_clip)
        return val

    def _pan_from_delta(self, dx: float, dy: float) -> None:
        """Slide the scene by a cursor delta, one pixel of scene per pixel of mouse.

        PyMOL's `cButModeTransXY` translates by `delta * vScale`, where
        `SceneGetScreenVertexScale` is `depth * 2 tan(fov/2) / Height` — the
        **same** scale on both axes, and by construction the number of scene
        units one pixel covers at the origin's depth. The point of it is that
        the molecule stays under the cursor.

        This multiplied the horizontal scale by the aspect ratio on top of that,
        which is the aspect counted twice: a perspective frustum is already
        `height * aspect` wide, so per *pixel* the two axes are equal. On the
        1278x631 viewport that reported this, horizontal panning ran 1.7x the
        cursor and the molecule slid out from under it.

        The height is the **scene column's**, not the widget's, because that is
        the height the projection matrix is built with; the sequence strip's
        band is not part of it.
        """
        height = max(self.scene_height(), 1)
        fov = math.radians(float(self._fov))
        half_tan = math.tan(fov / 2.0)
        if half_tan <= 0:
            return
        scale = 2.0 * self._distance * half_tan / height

        right = self._camera_right_vector()
        up = self._camera_up_vector()

        # Panning direction depends on the mouse mode: PyMOL moves the object
        # with the cursor; Chimol moves the camera / plane with the cursor.
        mult = self._pan_delta_multiplier(self._mouse_mode)
        shift = (mult * -dx * scale) * right + (mult * dy * scale) * up
        self._pan_offset += shift
        self.update()

    def _camera_forward_vector(self) -> np.ndarray:
        # Camera looks down its -Z axis; row 2 of the world->camera rotation is
        # the camera +Z in world, so forward = -row2.
        return -np.asarray(self._rot[2], dtype=float)

    def _camera_right_vector(self) -> np.ndarray:
        return np.asarray(self._rot[0], dtype=float)

    def _camera_up_vector(self) -> np.ndarray:
        return np.asarray(self._rot[1], dtype=float)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        # There is **one** of these now. The class used to define it twice and
        # Python keeps the last, so the earlier one -- which is where the middle
        # button ended its pan -- never ran: `_panning` was set on every middle
        # press and cleared on none, so after one middle-drag the molecule
        # followed the cursor for the rest of the session. Merged rather than
        # commented, because a note saying "the code above is dead" leaves the
        # dead code there to be edited by the next person.
        if self._panning:
            # Any button can start a pan -- plain middle is `Move`, and so is
            # ctrl-left -- so the release ends it whichever one it was.
            self._panning = False
            event.accept()
            return

        if self._gui_grab:
            # The press belonged to the panel, so the release does too:
            # otherwise letting go over the scene picks whatever is under it.
            self._gui_grab = False
            self._internal_gui.release()
            event.accept()
            return

        if self._drag_selecting and event.button() == self._drag_button:
            self._end_box_drag(event)
            event.accept()
            return

        if event.button() == QtCore.Qt.RightButton:
            if not getattr(self, "_right_dragged", False):
                menu = QtWidgets.QMenu(self)
                reset_act = menu.addAction("Reset view")
                action = menu.exec_(event.globalPos())
                if action is reset_act and self._controller is not None:
                    try:
                        self._controller.reset_view()
                    except Exception:
                        pass
            self._right_dragged = False
            event.accept()
            return

        # A left *click* (press and release without a meaningful drag) fires
        # the `single_*` cell of the mode table, which may be a different
        # action than the drag. In the viewing modes the click is `+/-` -- the
        # clicked residue toggles in/out of the selection -- while a real drag
        # is `rota` and must not touch the selection.
        if self._press_pos is not None and self._controller is not None:
            delta = event.pos() - self._press_pos
            was_drag = abs(delta.x()) > 4 or abs(delta.y()) > 4
            if not was_drag and not self._drag_selecting:
                # PyMOL has a separate row for clicks, so a press that never
                # dragged can mean something other than the drag it would have
                # been -- plain left drags (`Rota`) but clicks (`+/-`). Where
                # that row says nothing, the modified cell the press resolved
                # still applies: ctrl-middle is `PkAt` whether or not it moved.
                try:
                    click = click_action_of(
                        self._internal_gui.mouse_mode,
                        self._press_button,
                        self._press_mods,
                    )
                except Exception:
                    click = "none"
                if click in ("none", ""):
                    try:
                        click = mouse_action_of(
                            self._internal_gui.mouse_mode,
                            self._press_button,
                            self._press_mods,
                        )
                    except Exception:
                        click = "none"
                if click in ("+/-", "sele", "pkat", "+box", "-box", "orig"):
                    self._controller.handle_mouse_click(event, click)
            self._press_pos = None
            self._press_mods = QtCore.Qt.NoModifier
            self._press_button = None
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[name-defined]
        handled = False
        if self._controller is not None:
            try:
                handled = bool(self._controller.handle_key_event(event))
            except Exception:
                handled = False
        if handled:
            return
        super().keyPressEvent(event)
