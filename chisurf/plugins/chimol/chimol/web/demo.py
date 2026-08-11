"""chimol in a page: the real viewer, on a browser's own WebGPU.

What this is
------------
A host. The viewer is :class:`chimol.renderer.view.MolView` -- the same object
the desktop drives -- with a windowless renderer, and the command layer is
:class:`chimol.cmd.Cmd` -- the same hundred-odd commands. This module supplies
what a page has that a desktop does not: a canvas to draw the built scene into,
DOM events to drive it with, and the handful of application-level calls the
commands make (loading a file, refreshing the object list).

That is the whole design, and it replaced the obvious alternative. This file
used to hold its *own* scene builder (spheres, then a cartoon), its own
trackball and its own command set, because ``MolView`` could not be imported
without Qt. Every representation and every command then existed twice, in two
spellings, with two sets of defaults. ``chimol.host.widget`` removed the reason
for that: the viewer imports without a toolkit, so the browser runs the same
one.

The molecule is parsed **in the browser**, by chimol's own reader, and drawn by
the same nineteen WGSL files the desktop compiles -- reaching a driver through
:mod:`chimol.renderer.gpu.browser` instead of ``wgpu-py``.
"""
from __future__ import annotations

import pathlib

__all__ = ["BrowserHost", "Viewer", "demo_pdb_path"]


#: The structure the page opens with. T4 lysozyme, the structure this project
#: uses for every protein rendering check, bundled so the page needs no upload
#: and no network beyond its own origin.
DEMO_PDB = "data/148l.pdb"


def demo_pdb_path() -> str:
    """Absolute path of the bundled structure, for the opening ``load``."""
    return str(pathlib.Path(__file__).resolve().parent / DEMO_PDB)

class BrowserHost:
    """The host the command layer reaches past the viewer for.

    ``Cmd`` drives a *viewer* -- sixty-seven of its methods -- and reaches the
    surrounding application for exactly thirteen things: loading a file,
    refreshing the docked object list, full-screen, and the rock timer. On the
    desktop that host is ``MolViewPluginWindow``, a Qt main window. Here it is
    this, which is the same role played by a page.

    It is deliberately not a stand-in that swallows everything. An earlier
    version answered every attribute with a no-op, and ``load`` then reported
    success while registering nothing -- the command delegates the actual read
    to the host, and a host that silently accepts it produces a viewer with no
    objects and no error.

    Parameters
    ----------
    viewer : chimol.renderer.view.MolView
        The viewer, built with a windowless renderer.
    """

    def __init__(self, viewer) -> None:
        self.viewer = viewer
        #: Called after anything that changes the object list, so the page can
        #: re-read it into the in-viewport panel.
        self.on_objects_changed = None

    # -- what the commands actually call ----------------------------------
    def _load_structure_from_path(self, path, *, name=None) -> str:
        """Read a structure file and register it as an object.

        Parameters
        ----------
        path : str or pathlib.Path
            A file on the page's filesystem -- which in a browser is Pyodide's
            in-memory one, written by ``fetch``.
        name : str, optional
            Object name; the file's stem otherwise.

        Returns
        -------
        str
            The new object's id.
        """
        import pathlib as _pathlib

        from ..io.structure import _parse_pdb_backbone

        source = _pathlib.Path(str(path))
        payload = _parse_pdb_backbone(str(source))
        if payload is None or payload.coords is None or not len(payload.coords):
            raise ValueError(f"no coordinates in {source.name}")
        label = str(name or source.stem or "molecule")
        # `apply_payload` is the viewer's documented single route from a file
        # in: it is what builds the residues, the CA trace and the secondary
        # structure a cartoon needs. Going in through `set_structure` instead
        # is how a structure arrives as bare points and every feature keyed on
        # atom identity degrades silently.
        entry = self.viewer._create_object(name=label, source_path=str(source))
        self.viewer.set_active_object(entry.object_id)
        self.viewer.apply_payload(payload, object_id=entry.object_id)
        self._refresh_objects_from_viewer()
        return entry.object_id

    def _refresh_objects_from_viewer(self) -> None:
        """Tell the page the object list changed."""
        if self.on_objects_changed is not None:
            self.on_objects_changed()

    def _set_object_visible(self, object_id, visible: bool) -> None:
        """Show or hide an object, then refresh the panel."""
        self.viewer.set_object_visible(object_id, bool(visible))
        self._refresh_objects_from_viewer()

    def _select_object_in_ui(self, object_id) -> None:
        """Make an object current in the page's panel."""
        self._refresh_objects_from_viewer()

    def _update_sequence_view(self) -> None:
        """Rebuild the sequence strip."""
        self._refresh_objects_from_viewer()

    def isFullScreen(self) -> bool:  # noqa: N802 - the Qt name the commands use
        """Whether the page is full screen. It has no window to maximise."""
        return False

    def showFullScreen(self) -> None:  # noqa: N802 - the Qt name
        """Go full screen -- a page cannot, without a user gesture."""

    def showNormal(self) -> None:  # noqa: N802 - the Qt name
        """Leave full screen."""

    def close(self) -> None:
        """Close the window. A page closes itself with the tab."""


class Viewer:
    """One interactive viewer in a page: the real viewer, on a canvas.

    The state a browser frame needs between events is the same state a desktop
    frame needs, and it lives in the same object -- ``MolView``. What differs is
    only where the pixels go and where the events come from.

    That is the point, and it is what this class was rewritten to be. It used to
    hold its own scene builder, its own trackball and its own command set, which
    meant every representation, every command and every default existed twice.
    ``MolView`` imports without a toolkit now (see ``chimol.host.widget``), so
    the browser runs **the** viewer and **the** command layer, with a windowless
    renderer whose scene this draws.

    Parameters
    ----------
    canvas : object
        A JavaScript ``HTMLCanvasElement``.
    """

    def __init__(self, canvas) -> None:
        import numpy as np

        from ..cmd import Cmd
        from ..renderer.gpu import api, browser
        from ..renderer.headless import SceneSink
        from ..renderer.internal_gui import InternalGui
        from ..renderer.view import MolView
        from ..renderer.wgpu_backend import WgpuMeshRenderer

        api.use_backend(browser)

        self.canvas = canvas
        # Device pixels for the surface, CSS pixels for the layout -- the same
        # split the desktop has between `_physical_size()` and a mouse event.
        # Laying the panel out in device pixels makes it half-size on a 2x
        # display *and* hit-test in coordinates the events do not use.
        self.width = int(canvas.width)
        self.height = int(canvas.height)
        try:
            self.dpr = float(canvas.width) / float(canvas.clientWidth)
        except Exception:
            self.dpr = 1.0
        if not (self.dpr > 0.0):
            self.dpr = 1.0
        self.logical_width = int(self.width / self.dpr)
        self.logical_height = int(self.height / self.dpr)

        adapter = browser.request_adapter_sync()
        self.device = adapter.request_device_sync()
        self.format = browser.configure_canvas(canvas, self.device)
        self.renderer = WgpuMeshRenderer(
            self.width, self.height, format=self.format, device=self.device
        )

        # The viewer, with the windowless renderer: it builds scenes and
        # rasterises nothing, and this class rasterises what it built.
        self.view = MolView(renderer_factory=SceneSink)
        self.sink = self.view._renderer
        self.sink.resize(self.logical_width, self.logical_height)

        self.host = BrowserHost(self.view)
        self.cmd = Cmd(self.host)
        self.host.on_objects_changed = self._sync_panel

        self.gui = InternalGui()
        self.gui.visible = True
        self.gui.sequence_visible = True
        self.gui.set_run_command(self.cmd.do)
        self.gui.command_line.completions = self._completions
        self.cmd.set_message_callback(self.gui.command_line.append_message)
        self.cmd.set_error_callback(self.gui.command_line.append_error)
        self.gui.on_select = self._on_select

        self._drag = None
        self._np = np

        # The bundled structure, through the same command a user would type.
        self.cmd.do(f"load {demo_pdb_path()}")
        self.cmd.do("as cartoon")
        self.gui.command_line.append(
            "chimol in the browser -- type 'help' for the commands", "message"
        )

    # -- the panel ----------------------------------------------------------

    def _completions(self, line: str, cursor: int):
        """Complete a command name or an argument, as the console does."""
        from ..cmd import completion

        head = line[:cursor].lstrip()
        parts = [p for p in head.replace(",", " ").split() if p]
        if not parts or (len(parts) == 1 and not head.endswith((" ", ","))):
            prefix = (parts[0] if parts else "").lower()
            return [n for n in completion.command_names(self.cmd)
                    if n.startswith(prefix)]
        prefix = "" if head.endswith((" ", ",")) else parts[-1].lower()
        pool = completion.argument_pool(parts[0], self.cmd)
        return [item for item in pool if item.lower().startswith(prefix)]

    def _sync_panel(self) -> None:
        """Mirror the viewer's objects and sequences into the in-viewport panel.

        The same job ``molview_main_window.sync_internal_gui`` does on the
        desktop, and for the same reason: the panel is a *view* of the object
        list, so it is fed from the list rather than kept in step by hand.
        """
        from ..renderer.internal_gui import GuiRow, SequenceRow

        rows = [GuiRow(name="all", is_header=True)]
        sequences = []
        for entry in self.view.list_objects():
            name = str(entry.get("name") or entry.get("id"))
            rows.append(GuiRow(name=name, enabled=bool(entry.get("visible", True))))
            codes, numbers, colours = self._sequence_of(entry.get("id"))
            if codes:
                sequences.append(
                    SequenceRow(name=name, codes=codes, numbers=numbers,
                                colors=colours, object_id=str(entry.get("id")))
                )
        rows.append(GuiRow(name="sele", is_selection=True))
        self.gui.set_rows(rows)
        self.gui.set_sequences(sequences)

    def _sequence_of(self, object_id):
        """One-letter codes, residue numbers and colours for an object.

        From the viewer's own accessors, which is what the desktop's
        ``_sync_internal_sequences`` reads too -- deriving the sequence here
        from the payload instead is how the strip ends up disagreeing with the
        molecule about what a residue is coloured.
        """
        try:
            codes, _names = self.view.get_sequence_arrays(object_id)
            numbers = self.view.get_residue_numbers(object_id)
            colours = self.view.get_residue_colors(object_id)
        except Exception:  # noqa: BLE001 - an object with no sequence
            return "", [], []
        if codes is None or not len(codes):
            return "", [], []
        return (
            "".join(str(c) for c in codes),
            [int(n) for n in (numbers if numbers is not None else [])],
            [tuple(float(c) for c in rgba[:3])
             for rgba in (colours if colours is not None else [])],
        )

    def _on_select(self, name: str, indices, additive: bool) -> None:
        """Turn a sequence-strip selection into the viewer's own selection."""
        columns = [int(i) for i in (indices or [])]
        object_id = None
        for entry in self.view.list_objects():
            if str(entry.get("name")) == str(name):
                object_id = entry.get("id")
                break
        if object_id is None:
            return
        self.view.set_selected_residues(columns, object_id=object_id)

    # -- geometry ----------------------------------------------------------

    def scene_width(self) -> int:
        """Width of the part of the canvas the molecule gets, in CSS pixels."""
        return int(max(self.logical_width - self.gui.column_width, 1))

    def scene_height(self) -> int:
        """Height of the part of the canvas the molecule gets, in CSS pixels."""
        return int(max(self.logical_height - self.gui.sequence_height(), 1))

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

        last_x, last_y, button = self._drag
        self._drag = (x, y, button)
        if button == 0:
            # The shared trackball, from `camera_state`: a viewer whose drags
            # turn the molecule by a different amount is a different viewer,
            # and no screenshot comparison catches it.
            self.sink.orbit((last_x, last_y), (x, y))
        else:
            self.sink.pan(x - last_x, y - last_y)
        return True

    def release(self) -> bool:
        """Handle a release."""
        self._drag = None
        self.gui.release()
        return False

    def wheel(self, steps: float) -> bool:
        """Dolly the camera. Multiplicative, so one step feels the same at any scale."""
        self.sink.dolly(1.1 ** float(steps))
        return True

    def key(
        self,
        name: str,
        text: str = "",
        ctrl: bool = False,
        shift: bool = False,
        alt: bool = False,
        meta: bool = False,
    ) -> bool:
        """Handle a ``keydown``. Returns whether the key was consumed.

        Parameters
        ----------
        name : str
            ``KeyboardEvent.key`` -- the browser's name for the key.
        text : str
            The character it produced, empty for a key that produces none.
        ctrl, shift, alt, meta : bool
            ``KeyboardEvent.ctrlKey`` and friends.

        Notes
        -----
        The answer is what the page uses to decide whether to call
        ``preventDefault``. It must be honest: swallowing every key would take
        the browser's own shortcuts -- reload, find, the developer console --
        away from a page that is not a text editor.
        """
        from ..host.keys import key_from_dom, modifiers_from_dom

        return bool(
            self.gui.key_press(
                key_from_dom(name),
                str(text or ""),
                modifiers_from_dom(bool(ctrl), bool(shift), bool(alt), bool(meta)),
            )
        )

    def prompt_state(self) -> str:
        """Return the prompt as one plain string: focus, the line, the log.

        For the page and for a test driving it. Everything else about the
        command line is Python objects, and a proxy of a list of dataclasses is
        not something a browser test can read -- so the one thing that crosses
        the boundary is a string.
        """
        line = self.gui.command_line
        parts = [f"focused={int(line.focused)}", f"line={line.text}"]
        parts += [f"{entry.kind}: {entry.text}" for entry in line.log[-8:]]
        return "\n".join(parts)

    # -- drawing -----------------------------------------------------------

    def draw(self) -> int:
        """Render one frame. Returns the quad count of the chrome."""
        from ..renderer.pack import pack_scene
        from ..renderer.ui.quad_painter import QuadPainter

        self.gui.layout(self.logical_width, self.logical_height)
        self.gui.layout_block(self.logical_width, self.logical_height)
        painter = QuadPainter(scale=self.dpr)
        self.gui.paint(painter)
        chrome = painter.vertices()

        scene = getattr(self.sink, "scene", None)
        packed = pack_scene(scene) if scene is not None else None
        context = self.canvas.getContext("webgpu")
        if packed is not None:
            self.renderer.render_into(
                context.getCurrentTexture().createView(),
                packed,
                self.sink.get_view_state(),
                background=self.sink.get_background_color()[:3],
                target_radius=getattr(self.sink, "_target_radius", None),
                viewport=(0.0, 0.0, float(self.scene_width() * self.dpr),
                          float(self.height)),
                chrome=chrome,
            )
        return int(len(chrome) // 6)
