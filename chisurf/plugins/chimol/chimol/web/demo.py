"""Draw a molecule and chimol's panel into a browser canvas, on its own GPU.

What this proves
----------------
Both halves of a frame, through the whole seam: the **molecule** as sphere
impostors -- ``impostor.wgsl``, analytic ray-sphere intersection, per-fragment
depth, the shared shading prelude and the depth cue -- and the **chrome** as
quads through ``ui.wgsl`` and the baked glyph atlas. Same layout arithmetic,
same :class:`~chimol.renderer.wgpu_backend.WgpuMeshRenderer`, same nineteen
WGSL files, reaching a driver through :mod:`chimol.renderer.gpu.browser`
instead of ``wgpu-py``.

The structure is parsed **in the browser**, by chimol's own PDB reader. That is
worth stating because it was not free: ``io/atoms.py`` took its atom dtype from
the host application and ``io/__init__.py`` imported every reader eagerly, so
asking for the PDB parser pulled in the density-map reader, marching cubes and
scipy. Both are fixed, and the browser is what found them -- Qt was not the only
thing tying the engine to a desktop.

Everything below is the same code the desktop runs. If a frame drawn here
differs from a frame drawn there, the difference is in the backend, which is the
only thing that changed.
"""
from __future__ import annotations

import pathlib
from typing import Optional

__all__ = ["Viewer", "build_molecule", "build_scene_chrome", "draw", "read_demo_payload", "sequence_of"]


#: The molecule the demo draws. T4 lysozyme, the structure this project uses
#: for every protein rendering check, bundled so the page needs no upload and no
#: network beyond its own origin.
DEMO_PDB = "data/148l.pdb"

#: Cached by :func:`read_demo_payload`.
_PAYLOAD = None


def read_demo_payload():
    """Parse the bundled PDB, once.

    Returns
    -------
    StructurePayload
    """
    global _PAYLOAD
    if _PAYLOAD is None:
        from ..io.structure import _parse_pdb_backbone

        path = pathlib.Path(__file__).resolve().parent / DEMO_PDB
        _PAYLOAD = _parse_pdb_backbone(str(path))
    return _PAYLOAD


def sequence_of(payload):
    """Return ``(one-letter codes, residue numbers)`` for the strip.

    Parameters
    ----------
    payload : StructurePayload

    Returns
    -------
    tuple
        The chain's one-letter codes and its residue numbers.

    Notes
    -----
    Read from the structure rather than written out. The demo used to carry a
    43-character string, which is what a viewer showing **164** residues looks
    like when nobody counts: the strip renders happily, scrolls happily, and
    stops a quarter of the way through the protein.
    """
    from ..colors import _AA_THREE_TO_ONE

    names = payload.res_names
    if names is None:
        return "", []
    codes = "".join(
        _AA_THREE_TO_ONE.get(str(name).strip().upper(), "X") for name in names
    )
    numbers = (
        [int(n) for n in payload.res_ids]
        if payload.res_ids is not None
        else list(range(1, len(codes) + 1))
    )
    return codes, numbers


def build_molecule():
    """Read the bundled PDB and return ``(Scene, centre, radius)``.

    Returns
    -------
    tuple
        A :class:`~chimol.renderer.scene.Scene` of sphere impostors, the
        framing centre, and the framing radius.

    Notes
    -----
    Parsed by chimol's **own** PDB reader. ``io/structure.py`` reaches for the
    host application only to read DCD trajectories; the PDB path is
    self-contained, which is what makes a molecule in the browser a matter of
    shipping one file rather than porting the readers.

    Spheres rather than cartoon: ``kind == "points"`` routes to the impostor
    pipeline, which is two triangles and an analytic ray-sphere intersection per
    atom -- so this exercises `impostor.wgsl`, per-fragment depth and the
    shading prelude, without needing the secondary-structure machinery that
    lives in the Qt widget.
    """
    import numpy as np

    from ..renderer.scene import Geometry, Scene, SceneObject
    from ..renderer.view_state import framing_centre, framing_radius

    payload = read_demo_payload()

    coords = np.ascontiguousarray(payload.coords, dtype=np.float32)
    centre = framing_centre(coords)
    # `complete` frames on the bounding sphere rather than PyMOL's default
    # half-extent box, so a demo that nobody is going to re-frame by hand does
    # not clip its own molecule against the top of the canvas.
    radius = framing_radius(coords, complete=True)

    # Coloured along the chain, which is `spectrum count` -- the colouring that
    # makes a fold readable without secondary structure.
    ramp = np.linspace(0.0, 1.0, len(coords), dtype=np.float32)
    colours = np.empty((len(coords), 4), dtype=np.float32)
    colours[:, 0] = np.clip(1.5 - abs(ramp - 1.0) * 3.0, 0.0, 1.0)
    colours[:, 1] = np.clip(1.5 - abs(ramp - 0.5) * 3.0, 0.0, 1.0)
    colours[:, 2] = np.clip(1.5 - abs(ramp - 0.0) * 3.0, 0.0, 1.0)
    colours[:, 3] = 1.0

    radii = payload.atom_radii
    if radii is None:
        radii = np.full(len(coords), 1.6, dtype=np.float32)
    radii = np.ascontiguousarray(radii, dtype=np.float32).reshape(-1, 1)

    # `world_radius` is what says these are Angstroms and not point sizes.
    # Without it the impostor shader reads `radii` as a screen-space sprite
    # size, and 1363 atoms come out as a scatter of two-pixel dots -- which
    # looks like a framing bug and is a units bug.
    geometry = Geometry(
        kind="points", positions=coords, colors=colours, radii=radii,
        meta={"world_radius": True},
    )
    scene = Scene(
        objects=[SceneObject(id="148l", geometry=geometry)],
        center=centre,
        radius=float(radius),
    )
    return scene, centre, float(radius)


def build_scene_chrome(width: int, height: int, payload=None):
    """Lay the panel out and return it as chrome vertices.

    Parameters
    ----------
    width, height : int
        Canvas size, in device pixels.
    payload : StructurePayload, optional
        The structure whose sequence the strip shows. Read from the file when
        omitted.

    Returns
    -------
    numpy.ndarray
        ``(n, 12)`` float32 for ``ui.wgsl``.
    """
    if payload is None:
        payload = read_demo_payload()
    from ..renderer.internal_gui import GuiRow, InternalGui, SequenceRow
    from ..renderer.ui.quad_painter import QuadPainter

    gui = InternalGui()
    gui.visible = True
    gui.set_rows(
        [
            GuiRow(name="all", is_header=True),
            GuiRow(name="148l"),
            GuiRow(name="sugars", enabled=False),
        ]
    )
    gui.sequence_visible = True
    codes, numbers = sequence_of(payload)
    gui.set_sequences(
        [SequenceRow(name="148l", codes=codes, numbers=numbers)]
    )
    gui.state = (12, 40)
    gui.layout(int(width), int(height))
    gui.layout_block(int(width), int(height))

    painter = QuadPainter()
    gui.paint(painter)
    return painter.vertices()


def draw(canvas, background: Optional[tuple] = None) -> int:
    """Render one frame of chimol's chrome into *canvas*.

    Parameters
    ----------
    canvas : object
        A JavaScript ``HTMLCanvasElement``.
    background : tuple, optional
        Clear colour, linear RGB in ``[0, 1]``.

    Returns
    -------
    int
        The number of quads drawn, so the page can report something specific
        rather than "it worked".
    """
    import numpy as np

    from ..renderer.gpu import api, browser
    from ..renderer.pack import pack_scene
    from ..renderer.view_state import distance_for_radius, pack_view_state
    from ..renderer.wgpu_backend import WgpuMeshRenderer

    api.use_backend(browser)

    width = int(canvas.width)
    height = int(canvas.height)
    adapter = browser.request_adapter_sync()
    device = adapter.request_device_sync()
    fmt = browser.configure_canvas(canvas, device)

    renderer = WgpuMeshRenderer(width, height, format=fmt, device=device)
    scene, centre, radius = build_molecule()
    packed = pack_scene(scene)
    chrome = build_scene_chrome(width, height, read_demo_payload())

    # Framed on the molecule, and the near/far planes fitted around it -- the
    # depth cue is measured over that span, so a far plane widened "for safety"
    # spreads the cue over empty space and dims the whole molecule instead of
    # separating its front from its back.
    distance = distance_for_radius(radius, aspect=width / max(height, 1))
    view = pack_view_state(
        rotation=np.eye(3, dtype=np.float32),
        distance=distance,
        target=centre,
        near=max(distance - radius, 0.1),
        far=distance + radius,
    )

    context = canvas.getContext("webgpu")
    target = context.getCurrentTexture().createView()
    renderer.render_into(
        target,
        packed,
        view,
        background=background or (0.16, 0.16, 0.16),
        target_radius=radius,
        viewport=_scene_viewport(width, height),
        chrome=chrome,
    )
    return int(len(chrome) // 6)


def _scene_viewport(width: int, height: int):
    """Return the part of the canvas the molecule gets.

    The panel is a **column** beside the scene, not an overlay on it: drawing
    the molecule under the panel and then covering it wastes the pixels and
    puts the centre of the view behind the object list.
    """
    from ..renderer.internal_gui import InternalGui

    column = InternalGui().minimum_column_width()
    return (0.0, 0.0, max(float(width) - column, 1.0), float(height))
class Viewer:
    """One interactive viewer: a scene, a camera, a panel, and a canvas.

    Holds the state a browser frame needs between events. The desktop keeps this
    in the Qt widget, which is exactly the part a browser does not have -- so the
    only thing that is new here is *where the state lives*, not what it is: the
    same trackball, the same dolly, the same ``InternalGui`` that decides whether
    a click landed on a button or on the molecule.

    Parameters
    ----------
    canvas : object
        A JavaScript ``HTMLCanvasElement``.
    """

    def __init__(self, canvas) -> None:
        import numpy as np

        from ..renderer.gpu import api, browser
        from ..renderer.internal_gui import GuiRow, InternalGui, SequenceRow
        from ..renderer.pack import pack_scene
        from ..renderer.view_state import distance_for_radius
        from ..renderer.wgpu_backend import WgpuMeshRenderer

        api.use_backend(browser)

        self.canvas = canvas
        self.width = int(canvas.width)
        self.height = int(canvas.height)

        adapter = browser.request_adapter_sync()
        self.device = adapter.request_device_sync()
        self.format = browser.configure_canvas(canvas, self.device)
        self.renderer = WgpuMeshRenderer(
            self.width, self.height, format=self.format, device=self.device
        )

        scene, centre, radius = build_molecule()
        self.packed = pack_scene(scene)
        self.target = np.asarray(centre, dtype=np.float64)
        self.radius = radius
        self.rotation = np.eye(3, dtype=np.float64)
        self.distance = distance_for_radius(
            radius, aspect=self.width / max(self.height, 1)
        )

        payload = read_demo_payload()
        gui = InternalGui()
        gui.visible = True
        gui.set_rows(
            [
                GuiRow(name="all", is_header=True),
                GuiRow(name="148l"),
                GuiRow(name="sugars", enabled=False),
            ]
        )
        gui.sequence_visible = True
        codes, numbers = sequence_of(payload)
        gui.set_sequences([SequenceRow(name="148l", codes=codes, numbers=numbers)])
        gui.state = (12, 40)
        self.gui = gui
        self._drag = None

    # -- geometry ----------------------------------------------------------

    def scene_width(self) -> int:
        """Width of the part of the canvas the molecule gets."""
        return int(max(self.width - self.gui.column_width, 1))

    def scene_height(self) -> int:
        """Height of the part of the canvas the molecule gets."""
        return int(max(self.height - self.gui.sequence_height(), 1))

    # -- events ------------------------------------------------------------

    def press(self, x: float, y: float, button: int, modifiers: int) -> bool:
        """Handle a press. Returns whether the frame needs redrawing."""
        if self.gui.mouse_press(x, y, right=(button == 2), modifiers=modifiers):
            return True
        self._drag = (x, y, button)
        return False

    def move(self, x: float, y: float) -> bool:
        """Handle a move, dragging the camera or hovering the panel."""
        if self._drag is None:
            return bool(self.gui.mouse_move(x, y))

        import numpy as np

        from ..renderer.camera_state import trackball_delta

        last_x, last_y, button = self._drag
        self._drag = (x, y, button)
        if button == 0:
            delta = trackball_delta(
                (last_x, last_y), (x, y), self.scene_width(), self.scene_height()
            )
            self.rotation = delta @ self.rotation
        else:
            # Middle or right drags pan, at one pixel of scene per pixel of
            # cursor -- the same scale on both axes, or the molecule slides out
            # from under the pointer.
            import math

            half_tan = math.tan(math.radians(30.0) / 2.0)
            scale = 2.0 * self.distance * half_tan / max(self.scene_height(), 1)
            right = self.rotation[0]
            up = self.rotation[1]
            self.target = self.target + (-(x - last_x) * scale) * right + (
                (y - last_y) * scale
            ) * up
        return True

    def release(self) -> bool:
        """Handle a release."""
        self._drag = None
        self.gui.release()
        return False

    def wheel(self, steps: float) -> bool:
        """Dolly the camera. Multiplicative, so one step feels the same at any scale."""
        self.distance = float(min(max(self.distance * (1.1 ** steps), 1e-3), 1e9))
        return True

    # -- drawing -----------------------------------------------------------

    def draw(self) -> int:
        """Render one frame. Returns the quad count of the chrome."""
        from ..renderer.ui.quad_painter import QuadPainter
        from ..renderer.view_state import pack_view_state

        self.gui.layout(self.width, self.height)
        painter = QuadPainter()
        self.gui.paint(painter)
        chrome = painter.vertices()

        view = pack_view_state(
            rotation=self.rotation,
            distance=self.distance,
            target=self.target,
            near=max(self.distance - self.radius, 0.1),
            far=self.distance + self.radius,
        )
        context = self.canvas.getContext("webgpu")
        self.renderer.render_into(
            context.getCurrentTexture().createView(),
            self.packed,
            view,
            background=(0.16, 0.16, 0.16),
            target_radius=self.radius,
            viewport=(0.0, 0.0, float(self.scene_width()), float(self.height)),
            chrome=chrome,
        )
        return int(len(chrome) // 6)
