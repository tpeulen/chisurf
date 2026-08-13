"""The dbg window: everything you need to find out what the viewer is doing.

Not a demo, and not a mode
--------------------------
It started as *Help → Demo Mode*, a menu entry that silently toggled a
frame-rate readout: it did not run a demo, it did not say what it had done, and
the other two things anybody wants at the same moment -- run a demo, open every
panel -- were somewhere else. It is a **debugger's window**, so it is called
that, and it stays open: a panel you have to re-open after every action you
take with it is a panel that gets used once.

Tabs, because these are different questions
-------------------------------------------
======== ===============================================================
Frame    What the last frame cost, and the switch that puts it on screen
Panels   Every window the viewer has, and *Open all*
Demos    The shipped scripts
Widgets  The ported controls, **live**, driven inside this window
Shaders  The WGSL the renderer is actually running
======== ===============================================================

The last two are the ones that did not exist. **Widgets** matters because half
of ``renderer/ui`` is reachable only from the panel that happens to use it --
the code editor and the hex view were ported and could not be *tried* without
writing a script -- so it hosts them directly, with their real state, driven by
real presses. **Shaders** matters because the WGSL is the part of the renderer
with no Python to read: when a surface comes out wrong the first question is
what the shader says, and until now the answer was to go and find the file.

Everything is a command
-----------------------
Every row issues one, which is the same thing the user could have typed. That
is what keeps the window from drifting away from what the viewer actually does
-- and it means anything the window can do is reproducible in a script.
"""
from __future__ import annotations

from .internal_gui import GuiWindow
from .ui.painter import ALIGN_CENTER, ALIGN_LEFT, ALIGN_RIGHT, ALIGN_VCENTER
from .ui.style import fit_text

__all__ = ["PANELS", "TABS", "DbgWindow"]

_PAD = 8.0
_ROW = 16.0
_GAP = 6.0
_TAB_H = 20.0

_TEXT = (235, 235, 240)
_DIM = (140, 140, 150)
_HEAD = (255, 208, 96)
_ON = (120, 210, 140)
_ROW_BG = (255, 255, 255, 10)
_ROW_HOT = (255, 255, 255, 26)
_TAB_BG = (255, 255, 255, 12)
_TAB_ON = (255, 255, 255, 34)

#: Every panel the viewer can open, as ``(command, title, note)``.
#:
#: Commands, not window keys: opening a panel is something the command layer
#: already knows how to do -- including creating it the first time and raising
#: it if it exists -- and duplicating that here would be a second way for the
#: same window to appear, which is how two of them end up on screen at once.
PANELS: tuple[tuple[str, str, str], ...] = (
    ("settings_panel on", "Settings", "Every display setting, grouped."),
    ("hierarchy_panel on", "Hierarchy", "Chains, residues and atoms as a tree."),
    ("density_panel on", "Density", "Contour level and rendering for a map."),
    ("history_panel on", "History", "What happened, and what undo takes back."),
    ("mouse_panel on", "Mouse modes", "What each button does."),
    ("object_panel on", "Objects", "The object list, as a window."),
)

#: The tabs, in the order they are drawn.
TABS: tuple[str, ...] = ("Frame", "Panels", "Demos", "Widgets", "Shaders")


class DbgWindow:
    """The dbg window's contents, as a viewport panel.

    Parameters
    ----------
    run_command : callable
        ``(str) -> None``. Every row issues one, which is what
        :class:`~.internal_gui.InternalGui` already holds and what the menu bar
        uses. Taking the callable rather than the viewer keeps this panel
        testable without a renderer, and keeps it honest: there is nothing it
        can do that the user could not have typed.
    stats : chimol.renderer.frame_stats.FrameStats, optional
        Read by the Frame tab. Optional so the window works before a frame has
        been drawn, which is exactly when somebody opens it to find out why.
    """

    KEY = "dbg"

    def __init__(self, run_command, stats=None) -> None:
        self.run_command = run_command
        self.stats = stats
        self.tab = 0
        #: Row rectangles from the last draw, as ``(y0, y1, command)``. The
        #: press handler needs to know what was drawn where, and drawing is
        #: the only thing that knows -- the lists are generated, so their
        #: geometry is not a constant anyone could write down.
        self._rows: list[tuple[float, float, str]] = []
        self._tab_rects: list[tuple[float, float, int]] = []
        self._hover = -1.0
        #: The hosted controls. Built on first use, then kept: they hold real
        #: state -- a cursor, a selection, an undo stack -- and rebuilding them
        #: per frame would make them impossible to actually try.
        self._widgets: dict[str, object] = {}
        self._widget_box: tuple[float, float, float, float] = (0, 0, 0, 0)
        self._active_widget = "text_editor"

    # -- the frame ------------------------------------------------------ #
    def window(self, **kwargs) -> GuiWindow:
        """A :class:`GuiWindow` wired to this panel.

        Not ``transient``: it is a workbench, and every action taken in it --
        opening a panel, running a demo -- is one you want to take again
        without re-opening the window that offers it.
        """
        options = dict(
            key=self.KEY, title="dbg", x=60.0, y=90.0, w=520.0, h=440.0,
            transient=False, resizable=True,
        )
        options.update(kwargs)
        # `on_key=self`: pressing in the body focuses this panel, and the
        # chrome's key route then hands it every keystroke -- which is what
        # makes the hosted editors typable.
        return GuiWindow(
            body=self.draw, on_press=self.press, on_key=self, **options,
        )

    # -- data ----------------------------------------------------------- #
    @staticmethod
    def _demos() -> tuple[tuple[str, str, str], ...]:
        """The shipped demos, or nothing if the catalogue cannot be read."""
        try:
            from ..app.demo_catalog import DEMOS  # noqa: PLC0415

            return tuple(DEMOS)
        except Exception:  # noqa: BLE001 - a panel is not worth a frame
            return ()

    @staticmethod
    def shaders() -> tuple[str, ...]:
        """The WGSL files the renderer draws with, by name.

        Read from the directory rather than listed here: a shader added and
        not listed is one nobody can look at, and the directory is the only
        thing that knows what is really there.
        """
        import pathlib  # noqa: PLC0415

        folder = pathlib.Path(__file__).resolve().parent / "wgsl"
        try:
            return tuple(sorted(one.name for one in folder.glob("*.wgsl")))
        except OSError:
            return ()

    def _nerd_is_on(self) -> bool:
        """Whether nerd mode is currently switched on."""
        try:
            from ..config import _DISPLAY_CONFIG  # noqa: PLC0415

            return bool((_DISPLAY_CONFIG.get("layout") or {}).get("nerd", False))
        except Exception:  # noqa: BLE001
            return False

    # -- drawing -------------------------------------------------------- #
    def draw(self, p, rect) -> None:
        """Paint the tab strip and whichever tab is open."""
        self._rows = []
        self._tab_rects = []
        x = rect.x + _PAD
        width = rect.w - 2 * _PAD
        y = self._tabs(p, x, rect.y + 4.0, width)

        body = (
            self._frame_tab, self._panels_tab, self._demos_tab,
            self._widgets_tab, self._shaders_tab,
        )[min(self.tab, len(TABS) - 1)]
        body(p, x, y, width, rect)

    def _tabs(self, p, x: float, y: float, width: float) -> float:
        """The tab strip; returns the top of the body."""
        each = width / len(TABS)
        for index, title in enumerate(TABS):
            left = x + index * each
            on = index == self.tab
            p.fill_rect(left, y, each - 2.0, _TAB_H, _TAB_ON if on else _TAB_BG)
            p.text(left, y, each - 2.0, _TAB_H, ALIGN_CENTER, title,
                   _HEAD if on else _DIM)
            self._tab_rects.append((left, left + each - 2.0, index))
        self._tab_top = y
        return y + _TAB_H + _GAP

    # -- the tabs ------------------------------------------------------- #
    def _frame_tab(self, p, x: float, y: float, width: float, rect) -> None:
        """The switch, and the numbers it puts on screen."""
        on = self._nerd_is_on()
        y = self._section(p, x, y, width, "Nerd mode")
        y = self._toggle(p, x, y, width, "Frame rate, CPU, GPU, quads, pipelines", on)
        p.text(x + _PAD, y, width - _PAD, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
               "drawn into the backdrop, top-left", _DIM)
        y += _ROW + _GAP

        y = self._section(p, x, y, width, "Last frame")
        stats = self.stats
        lines = stats.lines() if stats is not None else ()
        if not lines:
            p.text(x + _PAD, y, width - _PAD, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                   "no frame drawn yet", _DIM)
            return
        for line in lines:
            p.text(x + _PAD, y, width - _PAD, _ROW,
                   ALIGN_VCENTER | ALIGN_LEFT, fit_text(p, line, width - _PAD), _TEXT)
            y += _ROW

    def _panels_tab(self, p, x: float, y: float, width: float, rect) -> None:
        """Every window the viewer has."""
        y = self._section(p, x, y, width, "Panels")
        y = self._row(p, x, y, width, "panels_all", "Open all", "every panel at once")
        y = self._row(p, x, y, width, "panels_all off", "Close all", "and put them away")
        for command, title, note in PANELS:
            y = self._row(p, x, y, width, command, title, note)

    def _demos_tab(self, p, x: float, y: float, width: float, rect) -> None:
        """The shipped scripts."""
        y = self._section(p, x, y, width, "Demos")
        for key, title, note in self._demos():
            y = self._row(p, x, y, width, f"demo {key}", title, note)

    def _widgets_tab(self, p, x: float, y: float, width: float, rect) -> None:
        """The ported controls, live, driven inside this window.

        Hosted rather than screenshotted: a control that can be looked at but
        not *used* tells you nothing about whether its keys work, and these two
        -- the code editor and the hex view -- have no other way in.
        """
        y = self._section(p, x, y, width, "Widgets")
        for name, label in (("text_editor", "Text editor"),
                            ("memory_editor", "Hex editor")):
            hot = name == self._active_widget
            p.fill_rect(x, y, width, _ROW, _ROW_HOT if hot else _ROW_BG)
            p.text(x + _PAD, y, width * 0.5, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                   label, _TEXT if hot else _DIM)
            p.text(x, y, width - _PAD, _ROW, ALIGN_VCENTER | ALIGN_RIGHT,
                   "shown" if hot else "show", _ON if hot else _DIM)
            self._rows.append((y, y + _ROW, f"__widget__ {name}"))
            y += _ROW
        y += _GAP

        control = self._widget(self._active_widget)
        if control is None:
            p.text(x + _PAD, y, width - _PAD, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                   "control unavailable", _DIM)
            return
        height = max(rect.y + rect.h - y - _PAD, _ROW * 4)
        self._widget_box = (x, y, width, height)
        control.draw(p, x, y, width, height)

    def _shaders_tab(self, p, x: float, y: float, width: float, rect) -> None:
        """The WGSL the renderer is running, opened in the code editor."""
        y = self._section(p, x, y, width, "Shaders")
        names = self.shaders()
        if not names:
            p.text(x + _PAD, y, width - _PAD, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
                   "no wgsl found", _DIM)
            return
        for name in names:
            y = self._row(p, x, y, width, f"__shader__ {name}", name,
                          "open in the editor")

    # -- pieces --------------------------------------------------------- #
    def _section(self, p, x: float, y: float, width: float, title: str) -> float:
        """A heading, and the rule under it."""
        p.text(x, y, width, _ROW, ALIGN_VCENTER | ALIGN_LEFT, title, _HEAD)
        p.fill_rect(x, y + _ROW - 1.0, width, 1.0, (255, 255, 255, 30))
        return y + _ROW + 2.0

    def _toggle(self, p, x: float, y: float, width: float, label: str, on: bool) -> float:
        """A checkbox row: a box, a label, and the word for its state."""
        hot = y <= self._hover < y + _ROW
        p.fill_rect(x, y, width, _ROW, _ROW_HOT if hot else _ROW_BG)
        box = _ROW - 6.0
        p.stroke_rect(x + 3.0, y + 3.0, box, box, _DIM, _ON if on else None)
        # The state word gets its own column and the label the rest, measured
        # rather than guessed: drawn over each other, the label ran into the
        # word and both stopped being readable.
        state = "on" if on else "off"
        left = x + box + 10.0
        room = width - (left - x) - (p.text_width(state) + _PAD)
        p.text(left, y, room, _ROW, ALIGN_VCENTER | ALIGN_LEFT,
               fit_text(p, label, room), _TEXT)
        p.text(x, y, width - 4.0, _ROW, ALIGN_VCENTER | ALIGN_RIGHT,
               state, _ON if on else _DIM)
        self._rows.append((y, y + _ROW, f"nerd_mode {'off' if on else 'on'}"))
        return y + _ROW

    def _row(
        self, p, x: float, y: float, width: float, command: str, title: str, note: str
    ) -> float:
        """One actionable row: what it is called, and what it does."""
        hot = y <= self._hover < y + _ROW
        p.fill_rect(x, y, width, _ROW, _ROW_HOT if hot else _ROW_BG)
        # Two columns, split where the *longest title* needs it rather than at
        # a fixed fraction: the titles are generated from the catalogues, so a
        # fraction that fits today is one a new demo breaks. The note is
        # truncated to what is left, and dropped when that is nothing -- half a
        # word of explanation is worse than none.
        title_w = min(p.text_width(title) + _PAD * 2, width * 0.6)
        p.text(x + _PAD, y, title_w, _ROW,
               ALIGN_VCENTER | ALIGN_LEFT, fit_text(p, title, title_w), _TEXT)
        room = width - title_w - _PAD
        if room > p.text_width("...."):
            p.text(x + title_w, y, room, _ROW,
                   ALIGN_VCENTER | ALIGN_RIGHT, fit_text(p, note, room), _DIM)
        self._rows.append((y, y + _ROW, command))
        return y + _ROW

    # -- the hosted controls -------------------------------------------- #
    def _widget(self, name: str):
        """Return the hosted control called *name*, building it once."""
        if name in self._widgets:
            return self._widgets[name]
        try:
            if name == "text_editor":
                from .ui import text_editor as te  # noqa: PLC0415

                control = te.TextEditor(
                    "# the code editor, live in the dbg window\\n"
                    "# open a shader from the Shaders tab to read the WGSL\\n"
                    "fetch 148L\\n"
                    "show cartoon\\n",
                    te.Language.chimol(),
                )
            elif name == "memory_editor":
                from .ui import memory_editor as me  # noqa: PLC0415

                control = me.MemoryEditor(
                    me.BufferSource(bytes(range(256)) * 4, "scratch"),
                    columns=16, read_only=False,
                )
            else:
                return None
        except Exception:  # noqa: BLE001 - a dead widget is not the window
            return None
        self._widgets[name] = control
        return control

    def open_shader(self, name: str) -> None:
        """Load a shader into the hosted code editor and show it.

        In *this* window rather than a new one: the question -- what does the
        shader actually say -- is asked while looking at the frame it drew, and
        a second window would be one more thing to place.
        """
        import pathlib  # noqa: PLC0415

        editor = self._widget("text_editor")
        if editor is None:
            return
        path = pathlib.Path(__file__).resolve().parent / "wgsl" / name
        try:
            editor.set_text(path.read_text(errors="replace"))
        except OSError as problem:
            editor.set_text(f"// {name}: {problem}")
        try:
            from .ui import text_editor as te  # noqa: PLC0415

            editor.set_language(te.Language.glsl())
        except Exception:  # noqa: BLE001
            pass
        self._active_widget = "text_editor"
        self.tab = TABS.index("Widgets")

    # -- input ---------------------------------------------------------- #
    def press(self, x: float, y: float, rect) -> bool:
        """Switch tab, run a row, or hand the press to a hosted control."""
        for left, right, index in self._tab_rects:
            if left <= x < right and self._tab_top <= y < self._tab_top + _TAB_H:
                self.tab = index
                return True

        for top, bottom, command in self._rows:
            if top <= y < bottom:
                self._act(command)
                return True

        box_x, box_y, box_w, box_h = self._widget_box
        if (
            TABS[self.tab] == "Widgets"
            and box_x <= x < box_x + box_w
            and box_y <= y < box_y + box_h
        ):
            control = self._widget(self._active_widget)
            press = getattr(control, "press", None)
            if callable(press):
                press(x, y, box_x, box_y, box_w, box_h)
            return True
        return bool(rect.contains(x, y))

    def key(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Hand a keystroke to the hosted control, if one is showing.

        This is what makes *try the widget* mean something: a text editor you
        cannot type into has not been tried.
        """
        if TABS[self.tab] != "Widgets":
            return False
        control = self._widget(self._active_widget)
        handler = getattr(control, "key", None)
        return bool(callable(handler) and handler(key, text, modifiers))

    def hover(self, y: float) -> None:
        """Remember where the pointer is, so the row under it lights up."""
        self._hover = float(y)

    def _act(self, command: str) -> None:
        """Run a row: an internal action, or a real command."""
        if command.startswith("__widget__ "):
            self._active_widget = command.split(" ", 1)[1]
            return
        if command.startswith("__shader__ "):
            self.open_shader(command.split(" ", 1)[1])
            return
        if callable(self.run_command):
            self.run_command(command)
