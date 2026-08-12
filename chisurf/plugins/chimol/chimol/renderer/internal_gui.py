"""PyMOL's object panel, drawn inside the viewport instead of beside it.

PyMOL puts its object list *in* the 3-D window: the names and their A/S/H/L/C
menus sit over the scene in the top-right corner, and the sequence runs along
the top. That is not decoration. A panel docked next to the view is a second
widget with its own font, its own metrics and its own idea of how much room it
needs, and it drifts out of step with the thing it is describing -- which is why
the spacing of five buttons became a question at all.

Drawn here, the panel is part of the picture: it scales with the view, it costs
no layout negotiation, and a screenshot of the viewport contains it.

The geometry is deliberately separate from the drawing. Layout and hit-testing
are plain arithmetic over rectangles and can be tested without a GL context or a
window; only :meth:`InternalGui.paint` needs a painter. Every click is turned
into a **command string** rather than a direct call, so the panel drives the
viewer through exactly the path a typed command takes, and nothing can be done
here that could not be scripted.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from ..mouse_modes import BUTTON_COLUMNS, DEFAULT_RING, MODE_NAMES, next_mode, rows_for
from ..object_menus import OBJECT_MENUS, MenuEntry, quote_selection_name
from .ui.command_line import HINT, PROMPT, CommandLine
from .ui.text_field import TextField
from .ui.progress import ProgressOverlay
from .ui.painter import (
    ALIGN_CENTER,
    ALIGN_LEFT,
    ALIGN_RIGHT,
    ALIGN_VCENTER,
)

from ..host.events import CONTROL_MODIFIER, SHIFT_MODIFIER

_CHAR_WIDTH: float | None = None

#: The point size the glyph atlas was baked at, and therefore the size at which
#: :func:`char_width` returns the atlas' own advance. Everything else is a
#: multiple of it.
BASE_FONT_PT: float = 8.0


def char_width(font_pt: int) -> float:
    """Advance width of one character of the chrome font, in pixels.

    Parameters
    ----------
    font_pt : int
        Point size, i.e. ``InternalGui.FONT_PT``.

    Returns
    -------
    float

    Notes
    -----
    Read from the baked glyph atlas, because that is what actually draws the
    text. It used to be ``font_pt * 0.62``, a guess that is **22 % narrow**:
    Menlo at 10 pt advances 8.5 px and the layout budgeted 6.2. Every box in
    the panel is sized in multiples of this, so the whole chrome was laid out
    into boxes too small for their own contents -- ``assign sec. structure``
    was given 130 px and needs 177, and because a menu is clamped against the
    right edge of the window the overflow ran *off-screen* rather than merely
    overlapping. The truncated mouse-mode block (``Mouse Mode 3-Button
    Viewin…``) and the cramped sequence strip are the same constant.

    The baked advance is what the font *is*; ``font_pt`` scales it, so the one
    knob that makes the chrome smaller (``InternalGui.FONT_PT``) reaches all
    fourteen call sites without any of them knowing about it.

    Cached: the atlas is read on every layout pass and is immutable.
    """
    global _CHAR_WIDTH
    if _CHAR_WIDTH is None:
        from .ui.font import load_atlas

        _CHAR_WIDTH = load_atlas().advance()
    return _CHAR_WIDTH * (float(font_pt) / BASE_FONT_PT)

# PyMOL's palette, read off its internal GUI.
PANEL_BG = (0, 0, 0, 190)
HEADER_BG = (128, 128, 128, 220)
HEADER_FG = (0, 0, 0)
ENABLED_FG = (0, 224, 0)
DISABLED_FG = (112, 112, 112)
BUTTON_BG = (157, 157, 255)
BUTTON_FG = (16, 16, 96)
BUTTON_EDGE = (32, 32, 96)
HOVER_BG = (192, 192, 255)
#: The same boxes on a switched-off object: still there, visibly inactive.
BUTTON_OFF_BG = (78, 78, 116)
BUTTON_OFF_FG = (150, 150, 170)
MENU_BG = (58, 58, 58, 244)
MENU_FG = (240, 240, 240)
MENU_DISABLED_FG = (144, 144, 144)
MENU_SEL_BG = (74, 74, 138)
MENU_EDGE = (144, 144, 144)
SPLITTER_FG = (96, 96, 96, 230)
SEQ_BG = (0, 0, 0, 210)
SEQ_FG = (224, 224, 224)
SEQ_NAME_FG = (0, 224, 0)
SEQ_NUMBER_FG = (144, 144, 144)
SEQ_SELECTED_BG = (255, 96, 176)
SEQ_SELECTED_FG = (0, 0, 0)
SEQ_TRACK_BG = (64, 64, 64, 230)
SEQ_THUMB_BG = (128, 128, 128, 240)

# The bottom-right block's palette, read off PyMOL's own.
MODE_TITLE_FG = (0, 224, 0)
MODE_HEAD_FG = (240, 128, 128)
MODE_KEY_FG = (128, 128, 255)
MODE_ACTION_FG = (224, 224, 224)
SELECT_FG = (0, 224, 0)
SELECT_MODE_FG = (0, 224, 224)
STATE_FG = (0, 224, 0)
MOVIE_FG = (240, 128, 128)
MOVIE_BG = (48, 48, 48, 230)

# The in-viewport command line. Green for what the user typed and for the
# prompt itself, PyMOL's colour for its own internal feedback; red for a
# refusal, because a command that did nothing has to say so where the eye
# already is rather than in a console behind the window.
CMD_BG = (0, 0, 0, 190)
CMD_PROMPT_FG = (0, 224, 0)
CMD_TEXT_FG = (240, 240, 240)
CMD_HINT_FG = (128, 128, 128)
CMD_ECHO_FG = (0, 224, 0)
CMD_MESSAGE_FG = (208, 208, 208)
CMD_ERROR_FG = (240, 128, 128)
CMD_CARET_FG = (0, 224, 0)

#: The movie transport, left to right: glyph and the command it runs.
MOVIE_BUTTONS: tuple[tuple[str, str], ...] = (
    ("|\u25c0", "frame 1"),
    ("\u25c0", "frame -1"),
    ("\u25a0", "mstop"),
    ("\u25b6", "mplay"),
    ("\u25b6\u25b6", "frame +1"),
    ("\u25b6|", "frame last"),
    # PyMOL's three at the right of the transport, which were missing: the
    # sequence, rocking, and full screen.
    ("S", "set seq_view, toggle"),
    ("\u25bc", "rock"),
    ("F", "full_screen"),
)

#: The C button's rainbow, left to right.
#:
#: RGB triples rather than the ``"#ff0000"`` strings they were: parsing a hex
#: colour was the last thing in the panel that needed ``QColor``, and the
#: values are identical either way.
COLOR_BUTTON_STOPS = (
    (255, 0, 0),
    (255, 255, 0),
    (0, 255, 0),
    (0, 255, 255),
    (0, 0, 255),
)


def _grey_of(colour: tuple[int, int, int]) -> tuple[int, int, int]:
    """Return the dimmed grey a disabled ``C`` button shows instead of *colour*.

    Parameters
    ----------
    colour : tuple of int
        An RGB triple, 0-255.

    Returns
    -------
    tuple of int
        A neutral grey of the same lightness band.

    Notes
    -----
    ``QColor.value()`` is HSV *value*, which is simply the largest of the three
    components -- so the original ``value() // 3 + 60`` is reproduced exactly
    without a toolkit. Every rainbow stop is fully saturated, so this is 145
    for all five of them: the disabled button is a flat grey, which is the
    point.
    """
    grey = max(colour[:3]) // 3 + 60
    return grey, grey, grey


@dataclass
class SequenceRow:
    """One object's sequence, as the strip shows it.

    Attributes
    ----------
    name : str
        Object name, drawn at the left as PyMOL's ``seq_view_label_mode 0`` does.
    codes : str
        One-letter residue codes -- PyMOL's ``seq_view_format 0``, its default.
    numbers : list of int
        Residue numbers, labelled every ``LABEL_SPACING`` as PyMOL labels them.
    selected : set of int
        Indices currently selected, highlighted the way PyMOL highlights them.
    """

    name: str
    codes: str
    #: The object this row belongs to, so its colours can be re-read without
    #: going back through the window that built the row.
    object_id: str = ""
    numbers: list[int] = field(default_factory=list)
    selected: set[int] = field(default_factory=set)
    #: Per-residue RGB, as the structure is coloured. A sequence in one colour
    #: is a different picture from the molecule it indexes: colouring by chain
    #: or by spectrum means nothing if the strip does not show it.
    colors: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class WizardRow:
    """One line of the wizard panel, in PyMOL's own shape.

    PyMOL's `Wizard.get_panel` returns `[code, label, action]` per row, where
    the code is 1 for the banner, 2 for a button whose action is a command, and
    3 for a pop-up whose action names a menu the wizard supplies. That is the
    whole vocabulary, and it is enough for every wizard it ships -- so it is
    the vocabulary here, with the codes spelled out.

    Attributes
    ----------
    kind : {"title", "button", "menu"}
        What the row is.
    label : str
        What it says. A pop-up row carries its current value in the label, as
        PyMOL's do (`Mutate to LYS`, `Hydrogens: auto`), because there is
        nowhere else to show it.
    action : str
        A command for a button; a menu **tag** for a pop-up, resolved by
        whoever supplied the panel.
    """

    kind: str
    label: str
    action: str = ""


@dataclass
class GuiRow:
    """One line of the panel: a molecule, a group, or the ``all`` header."""

    name: str
    enabled: bool = True
    is_header: bool = False
    is_group: bool = False
    #: Whether a group row is expanded. Drawn as the disclosure marker, and it
    #: is what a click on the name toggles -- a group has no visibility of its
    #: own to switch, so the click has to mean something else than it does on a
    #: molecule.
    group_open: bool = True
    #: PyMOL's ``sele`` pseudo-object: always present, pinned to the bottom of
    #: the list, and not backed by a real molecule.
    is_selection: bool = False
    indent: int = 0
    detail: str = ""


@dataclass(frozen=True)
class Rect:
    """An axis-aligned rectangle in widget pixels."""

    x: float
    y: float
    w: float
    h: float

    def contains(self, px: float, py: float) -> bool:
        """Whether ``(px, py)`` lies inside."""
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h


@dataclass(frozen=True)
class Hit:
    """What sits under the cursor."""

    kind: str            # "name" | "button" | "menu" | "" (nothing)
    row: int = -1
    key: str = ""        # button key, for kind == "button"
    entry: MenuEntry | None = None
    submenu: bool = False


@dataclass
class _OpenMenu:
    """A menu currently on screen.

    Attributes
    ----------
    owner : MenuEntry or None
        The parent's entry this menu hangs off. Held by identity rather than by
        label: two submenus at different depths share a label -- ``by element``
        opens a menu whose one entry is also ``by element`` -- and matching on
        the text kept the wrong one open.
    affinity : int
        Which side of its parent the menu was placed on: ``+1`` right, ``-1``
        left. PyMOL's ``PlacementAffinity``, and inherited for the same reason:
        once a chain has flipped left against the window edge, its own children
        keep going left rather than zig-zagging back across the parent.
    """

    title: str
    target: str
    entries: Sequence[MenuEntry]
    x: float
    y: float
    parent: _OpenMenu | None = None
    item_rects: list[tuple[Rect, MenuEntry]] = field(default_factory=list)
    rect: Rect = Rect(0, 0, 0, 0)
    owner: MenuEntry | None = None
    affinity: int = 1
    #: Pixels the content is shifted up when the menu is taller than the
    #: window, and how far it may go. PyMOL scrolls a long pop-up rather than
    #: wrapping it into columns, because the column break lands wherever the
    #: window height happens to put it and takes the grouping with it.
    scroll: float = 0.0
    max_scroll: float = 0.0
    #: Height of one screenful of entries, set by the layout. A menu too tall
    #: for the window is read a **page** at a time -- the arrows in its title
    #: row turn the page -- because a wheel is not available to every hand and
    #: a menu whose remainder can only be reached by scrolling is a menu whose
    #: remainder most people never see.
    page_px: float = 0.0


class InternalGui:
    """The object panel, laid out and drawn in the viewport.

    Parameters
    ----------
    run_command : callable, optional
        Receives a command string. Everything the panel does goes through it.
    """

    ROW_H = 17
    BUTTON_W = 17
    PAD = 6
    MARGIN = 8
    FONT_PT = 8
    MENU_ITEM_H = 18
    MENU_PAD = 6
    #: The gap a separator leaves between two groups of entries.
    SEPARATOR_H = 5
    #: Gap between a submenu and the parent it hangs off, on either side.
    CHILD_GAP = 3
    #: How far one wheel notch scrolls a menu too tall for the window. PyMOL's
    #: `CPopUp::release` translates the block by ten pixels a notch; a row is
    #: the better unit, because ten pixels is not a multiple of the row height
    #: and every notch then slices the rows at both edges in half.
    MENU_SCROLL_PX = float(MENU_ITEM_H)
    #: Residue numbers every this many columns -- PyMOL's
    #: ``seq_view_label_spacing``, whose default is 5.
    LABEL_SPACING = 5
    #: Height of one sequence line.
    SEQ_ROW_H = 15
    #: Height of the scrollbar under the strip.
    SEQ_BAR_H = 9
    #: Line height inside the mouse-mode block. Tighter than a panel row: it is
    #: a dense reference table, and PyMOL sets it close enough that the whole
    #: matrix reads as one thing rather than eight loose lines.
    BLOCK_ROW_H = 14
    #: Grab width of the splitter, in pixels.
    SPLITTER_W = 6
    #: Height of one row of the command line and of its feedback log.
    CMD_ROW_H = 16
    #: How narrow and how wide the column may be dragged.
    #: The transport needs a hit target per button, whatever else is in the
    #: column: below this the buttons stop being clickable rather than merely
    #: looking cramped.
    MIN_BUTTON_W = 14.0
    MAX_COLUMN_FRACTION = 0.6

    #: Every length the chrome is laid out with, at scale 1.0. `set_ui_scale`
    #: multiplies each of them onto the instance, so the whole panel -- text,
    #: rows, menus, title bars -- changes size together. Scaling the font alone
    #: leaves 17-pixel rows around 11-pixel text, which is not smaller chrome,
    #: only emptier chrome.
    SCALED_LENGTHS = (
        "ROW_H", "BUTTON_W", "PAD", "MARGIN", "FONT_PT", "MENU_ITEM_H",
        "MENU_PAD", "SEPARATOR_H", "CHILD_GAP", "MENU_SCROLL_PX", "SEQ_ROW_H",
        "SEQ_BAR_H", "MOUSE_LINE_H", "MENUBAR_H", "TOOLBAR_H",
        "WINDOW_TITLE_H", "WINDOW_MIN_W", "WINDOW_MIN_H", "WINDOW_GRIP",
    )

    #: How big the chrome is drawn, as a multiple of the sizes above. Smaller
    #: than one by default: the chrome is read at a glance and then looked
    #: past, and every pixel it takes is a pixel of the molecule it covers.
    DEFAULT_UI_SCALE = 0.85

    def set_ui_scale(self, scale: float) -> float:
        """Scale the whole chrome -- text and the boxes around it.

        Parameters
        ----------
        scale : float
            Multiplier on the class' own lengths. Clamped to a range that
            stays legible at one end and leaves room for the scene at the
            other.

        Returns
        -------
        float
            The scale actually applied.
        """
        scale = min(max(float(scale), 0.5), 2.0)
        if scale == getattr(self, "ui_scale", None):
            return scale
        self.ui_scale = scale
        cls = type(self)
        for name in self.SCALED_LENGTHS:
            base = getattr(cls, name, None)
            if base is None:
                continue
            # `MENU_SCROLL_PX` is a float and `ROW_H` an int; keeping each
            # one's own type matters, because a fractional row height puts
            # every row below the first on a half pixel. `FONT_PT` is the
            # exception and stays fractional: it is what `char_width` divides
            # by, so rounding it there would budget boxes for text of a size
            # nothing draws.
            value = base * scale
            keep_int = isinstance(base, int) and name != "FONT_PT"
            setattr(self, name, int(round(value)) if keep_int else float(value))
        self._menus = []
        return scale

    def __init__(self, run_command: Callable[[str], None] | None = None) -> None:
        self.visible = True
        #: Set before anything is laid out, so a panel that is never told a
        #: scale is still smaller than the baked one rather than being the one
        #: place the default does not apply.
        self.ui_scale = 1.0
        self.set_ui_scale(self.DEFAULT_UI_SCALE)
        #: Docked into a column of its own, PyMOL-style, rather than floating
        #: over the scene.
        self.docked = True
        self.rows: list[GuiRow] = []
        #: The wizard panel, PyMOL's `get_panel()`: rows drawn under the object
        #: list while a wizard is running, and nothing at all when none is.
        self.wizard_rows: list[WizardRow] = []
        #: PyMOL's `get_prompt()`: the line in the top-left of the viewport
        #: telling you what the wizard is waiting for. It is the whole of the
        #: instruction, and a wizard without one is a panel of buttons whose
        #: order nobody can guess.
        self.wizard_prompt: list[str] = []
        #: Resolves a pop-up row's tag into menu entries, supplied with the
        #: panel by whoever is running the wizard.
        self.wizard_menu: Callable[[str], Sequence[MenuEntry]] | None = None
        self._wizard_rect = Rect(0, 0, 0, 0)
        self._wizard_row_rects: list[tuple[Rect, WizardRow]] = []
        self._run_command = run_command
        self._row_rects: list[Rect] = []
        self._button_rects: list[dict[str, Rect]] = []
        self._eye_rects: list[Rect] = []
        #: The hover tooltip: ``(x, y, text)`` while something explains itself.
        self._tooltip: tuple[float, float, str] | None = None
        self._panel = Rect(0, 0, 0, 0)
        self._hover = Hit("")
        self._menus: list[_OpenMenu] = []
        #: Modal progress reporting. Public, because everything that takes long
        #: enough to notice drives it -- a load, a trace, a surface -- and none
        #: of those live in this class.
        self.progress = ProgressOverlay()
        #: Whether the developer instruments are drawn -- the chrome-size
        #: slider and the frame-rate readout. A figure does not want either.
        self.debug_overlays = False
        #: Frames per second, pushed by the renderer. 0 means "not measured",
        #: which is what a still frame and a headless host both are.
        self.fps = 0.0
        self._width = 0
        self._height = 0
        #: Widest name seen, so the panel does not change width every frame.
        self._name_width = 90.0
        #: The mouse mode the bottom-right block describes.
        self.mouse_mode = "three_button_viewing"
        #: Which ring the mode line cycles within.
        self.mouse_ring = DEFAULT_RING
        #: What a click selects, and where the movie is -- both shown there.
        self.selecting = "Residues"
        self.state = (1, 1)
        #: Frames advanced per playback step, and the window a trajectory is
        #: averaged over. PyMOL has neither: a long trajectory is watched at
        #: whatever rate it was written, and a noisy one jitters. Both are
        #: shown in the block and clicking cycles them.
        self.stride = 1
        self.average = 0
        self._stride_rect = Rect(0, 0, 0, 0)
        self._timeline_track = Rect(0, 0, 0, 0)
        self._timeline_thumb = Rect(0, 0, 0, 0)
        self._dragging_timeline = False
        #: Called with a 1-based frame when the timeline is dragged.
        self.on_frame_change: Callable[[int], None] | None = None
        self._average_rect = Rect(0, 0, 0, 0)
        #: Called with ``(stride, average)`` when either is clicked.
        self.on_playback_change: Callable[[int, int], None] | None = None
        #: Called with ``(line, placeholder)`` for a menu entry that needs a
        #: typed value. The host puts the line in its command box with the
        #: placeholder selected; there is nowhere in the viewport to type.
        self.on_prompt_command: Callable[[str, str], None] | None = None
        self._mode_rect = Rect(0, 0, 0, 0)
        #: Width of the column the panel and the block live in. The scene is
        #: rendered to the *left* of it, as PyMOL does, rather than under it:
        #: an overlay hides the molecule it is describing, and the part it hides
        #: is the part you just moved out of the way.
        #: PyMOL's `internal_gui_width`, as a *starting* value: `layout` raises
        #: it to `minimum_column_width()` when the contents need more, which at
        #: this font is 267.
        self.column_width = 220.0
        self._splitter = Rect(0, 0, 0, 0)
        self._dragging_splitter = False
        #: PyMOL's `seq_view`, off by default there and here.
        self.sequence_visible = False
        self.sequences: list[SequenceRow] = []
        self._seq_strip = Rect(0, 0, 0, 0)
        self._seq_rows: list[Rect] = []
        self._seq_origin = 0.0
        self._seq_scroll = 0
        self._seq_drag: tuple[int, int] | None = None
        #: The residue a shift-click extends from -- PyMOL's ``Seeker`` keeps
        #: the previous drag gesture alive for a shift continuation.
        self._seq_anchor: int | None = None
        #: Whether the press that started the drag carried a modifier, so the
        #: drag merges instead of replacing.
        self._seq_drag_additive = False
        self._seq_track = Rect(0, 0, 0, 0)
        self._seq_thumb = Rect(0, 0, 0, 0)
        self._dragging_thumb = False
        self._dragging_timeline = False
        #: Called with ``(object name, indices, additive)`` when the strip
        #: selects. Kept separate from `run_command`: a selection is not a
        #: command string, and round-tripping one through the parser would lose
        #: the indices.
        self.on_select: Callable[[str, list[int], bool], None] | None = None
        self._movie_rects: list[tuple[Rect, str]] = []
        self._block = Rect(0, 0, 0, 0)
        #: PyMOL's *internal* prompt: the command line drawn in the viewport,
        #: bottom-left of the scene. The docked console is the external one, and
        #: both drive the same command layer -- which is what lets a browser,
        #: where there is no console to dock, still be typed at.
        self.command_line = CommandLine(run_command)
        self._cmd_rect = Rect(0, 0, 0, 0)
        self._cmd_log_rect = Rect(0, 0, 0, 0)

    # ── model ────────────────────────────────────────────────────────────
    def set_run_command(self, run_command: Callable[[str], None] | None) -> None:
        """Set the sink every click is turned into a command for.

        The in-viewport prompt gets the same sink: a line typed there and a
        button pressed here are the same command, and giving them separate
        routes is how the two stop agreeing about what a click means.
        """
        self._run_command = run_command
        self.command_line.set_run(run_command)

    def set_rows(self, rows: Sequence[GuiRow]) -> None:
        """Replace the panel's contents."""
        self.rows = list(rows)
        self.close_menus()

    def has_menu(self) -> bool:
        """Whether a menu is currently open."""
        return bool(self._menus)

    def close_menus(self) -> None:
        """Dismiss any open menu."""
        self._menus = []

    # ── layout ───────────────────────────────────────────────────────────
    def layout(self, width: int, height: int, name_width: float | None = None) -> None:
        """Place the rows for a viewport of *width* x *height*.

        Anchored top-right, as PyMOL's is. Rows are laid out downward from the
        top margin; the panel is exactly as wide as it needs to be, because a
        fixed width either truncates a long name or wastes the view.
        """
        self._width, self._height = int(width), int(height)
        if name_width is not None:
            self._name_width = float(name_width)

        if self.docked:
            # The column must be at least as wide as the things inside it. It
            # starts at PyMOL's `internal_gui_width` of 220, and only the
            # *splitter drag* used to consult `minimum_column_width` -- so until
            # someone dragged it, the mouse-mode block was laid out wider than
            # the column that positions it and ran off the right edge of the
            # window (`Mouse Mode 3-Button Viewin...`).
            #
            # Not capped to the window. On a viewport narrower than the panel's
            # own minimum the two cannot both be satisfied, and the minimum
            # wins: a panel that overhangs a 200 px window is still readable,
            # where one truncated to fit it is the defect this whole clamp
            # exists to prevent.
            self.column_width = max(self.column_width, self.minimum_column_width())

        column = self.column_width if self.docked else 0.0
        self._splitter = Rect(
            width - column - self.SPLITTER_W / 2, 0.0, self.SPLITTER_W, float(height)
        ) if self.docked else Rect(0, 0, 0, 0)

        buttons_w = self.BUTTON_W * len(OBJECT_MENUS)
        panel_w = self.PAD + self._name_width + self.PAD + buttons_w + self.PAD
        if self.docked:
            panel_w = max(panel_w, column)
        panel_h = self.ROW_H * len(self.rows) + 2 * self.PAD if self.rows else 0
        if self.docked:
            self._panel = Rect(width - column, 0.0, column, panel_h)
        else:
            self._panel = Rect(
                width - self.MARGIN - panel_w, self.MARGIN, panel_w, panel_h
            )

        self._row_rects = []
        self._button_rects = []
        y = self._panel.y + self.PAD
        for row in self.rows:
            self._row_rects.append(Rect(self._panel.x, y, panel_w, self.ROW_H))
            bx = self._panel.x + panel_w - self.PAD - buttons_w
            keys: dict[str, Rect] = {}
            for index, (key, _title, _entries) in enumerate(OBJECT_MENUS):
                keys[key] = Rect(
                    bx + index * self.BUTTON_W, y, self.BUTTON_W, self.ROW_H
                )
            self._button_rects.append(keys)
            y += self.ROW_H

        self.layout_wizard(width, height)
        self.layout_block(width, height)
        self.layout_sequence(width, height)
        self.layout_command(width, height)

    def layout_command(self, width: int, height: int) -> None:
        """Place the command line along the bottom of the scene.

        An *overlay*, not a band the scene gives up. The prompt is one row of a
        viewport that is usually a thousand pixels tall, and taking that row
        away from the molecule would change the camera's aspect every time the
        prompt was shown -- so it is drawn over the scene, as PyMOL's is, and
        the renderer needs to know nothing about it.

        Left of the panel column, because the column is where the object list
        already is and a prompt underneath it would be reading the two as one
        block.
        """
        self._width, self._height = int(width), int(height)
        line = self.command_line
        if not line.visible:
            self._cmd_rect = Rect(0, 0, 0, 0)
            self._cmd_log_rect = Rect(0, 0, 0, 0)
            return

        scene_w = max(float(width) - (self.column_width if self.docked else 0.0), 1.0)
        rows = len(line.visible_log())
        bottom = float(height) - self.MARGIN
        self._cmd_rect = Rect(
            0.0, bottom - self.CMD_ROW_H, scene_w, float(self.CMD_ROW_H)
        )
        self._cmd_log_rect = Rect(
            0.0, self._cmd_rect.y - rows * self.CMD_ROW_H,
            scene_w, float(rows * self.CMD_ROW_H),
        )

    def command_rect(self) -> Rect:
        """Where the prompt sits, for a host that wants to place a caret."""
        return self._cmd_rect

    # ── the command line ─────────────────────────────────────────────────
    def focus_command(self, focused: bool = True) -> None:
        """Give the prompt the keyboard, or take it away.

        Closing any open menu with it: a menu and a text cursor both claim the
        next keystroke, and the one that is drawn on top is not necessarily the
        one that would get it.
        """
        if focused:
            self.close_menus()
        self.command_line.set_focus(focused)

    def _cmd_cursor_at(self, x: float) -> int:
        """Character index under *x* on the prompt line.

        The chrome font is monospaced -- it is Menlo, and the whole panel's
        layout arithmetic already assumes a single advance width -- so this is
        division rather than a walk over glyph metrics.
        """
        advance = char_width(self.FONT_PT)
        origin = self._cmd_rect.x + self.MARGIN + advance * (len(PROMPT) + 1)
        return max(0, min(
            int(round((float(x) - origin) / max(advance, 1e-6))),
            len(self.command_line.text),
        ))

    def key_press(self, key: int, text: str = "", modifiers: int = 0) -> bool:
        """Offer a key to the chrome. Returns whether it was consumed.

        Every host calls this before its own shortcuts, and the answer decides
        whether they run. Three things can take a key: an open menu takes
        Escape, a focused prompt takes everything, and an unfocused prompt takes
        Return -- which is how it gets focus without the mouse, and the only
        gesture a browser page can offer that costs nothing else.

        Parameters
        ----------
        key : int
            One of :mod:`chimol.host.keys`' constants, ``0`` for a key that only
            produces text.
        text : str
            The character produced, if any.
        modifiers : int
            A mask of :mod:`chimol.host.events`' ``*_MODIFIER`` values.
        """
        from ..host.keys import KEY_ENTER, KEY_ESCAPE, KEY_RETURN

        if key == KEY_ESCAPE and self._menus:
            self.close_menus()
            return True
        if self.command_line.focused:
            return self.command_line.key(key, text, modifiers)
        if key in (KEY_RETURN, KEY_ENTER) and self.command_line.visible:
            self.focus_command(True)
            return True
        return False

    def layout_wizard(self, width: int, height: int) -> None:
        """Place the wizard panel directly under the object list.

        Where PyMOL puts it: the wizard is a *block* in the internal GUI
        column, below the object list and above the mouse-mode block, so the
        thing you are being asked to do sits next to the objects you would do
        it to.
        """
        self._wizard_row_rects = []
        if not self.wizard_rows:
            self._wizard_rect = Rect(0, 0, 0, 0)
            return
        column = self.column_width if self.docked else max(
            self._panel.w, 160.0
        )
        top = self._panel.y + self._panel.h + self.PAD
        panel_h = self.PAD + self.ROW_H * len(self.wizard_rows) + self.PAD
        x = width - column if self.docked else self._panel.x
        self._wizard_rect = Rect(x, top, column, panel_h)

        y = top + self.PAD
        for row in self.wizard_rows:
            self._wizard_row_rects.append((Rect(x, y, column, self.ROW_H), row))
            y += self.ROW_H

    def set_sequences(self, rows: Sequence[SequenceRow]) -> None:
        """Replace the sequences the strip shows."""
        self.sequences = list(rows)

    def sequence_height(self) -> float:
        """Height the strip takes from the top of the scene.

        Zero when there is nothing to show. PyMOL's ``seq_view_overlay`` is off
        by default, meaning the sequence gets a band of its own rather than
        covering the molecule -- so this is height the scene does not get, and
        the renderer has to know it.
        """
        if not (self.sequence_visible and self.sequences):
            return 0.0
        return self.SEQ_ROW_H * (len(self.sequences) + 1) + self.SEQ_BAR_H + 2 * self.PAD

    def layout_sequence(self, width: int, height: int) -> None:
        """Place the strip across the top of the scene, left of the column."""
        strip_h = self.sequence_height()
        scene_w = width - (self.column_width if self.docked else 0.0)
        self._seq_strip = Rect(0.0, 0.0, max(scene_w, 1.0), strip_h)
        self._seq_rows = []
        if not strip_h:
            return

        char_w = char_width(self.FONT_PT)
        name_w = max(
            [len(row.name) for row in self.sequences] + [4]
        ) * char_w + self.PAD
        self._seq_origin = self.PAD + name_w
        y = self.PAD + self.SEQ_ROW_H          # below the number line
        for _row in self.sequences:
            self._seq_rows.append(
                Rect(self._seq_origin, y, self._seq_strip.w - self._seq_origin,
                     self.SEQ_ROW_H)
            )
            y += self.SEQ_ROW_H

        # The scrollbar, under the rows. Without it a long sequence simply ends
        # at the edge of the window with nothing to say there is more of it.
        track_w = self._seq_strip.w - self._seq_origin - self.PAD
        self._seq_track = Rect(self._seq_origin, y + 2, max(track_w, 1.0), self.SEQ_BAR_H)
        longest = max((len(row.codes) for row in self.sequences), default=0)
        visible = self.visible_columns()
        if longest > visible > 0:
            span = track_w * visible / float(longest)
            offset = track_w * self._seq_scroll / float(longest)
            self._seq_thumb = Rect(
                self._seq_track.x + offset, self._seq_track.y,
                max(span, 12.0), self.SEQ_BAR_H,
            )
        else:
            self._seq_thumb = Rect(self._seq_track.x, self._seq_track.y,
                                   self._seq_track.w, self.SEQ_BAR_H)

    def sequence_strip_contains(self, x: float, y: float) -> bool:
        """Whether ``(x, y)`` is over the sequence strip."""
        return bool(self.sequence_visible and self._seq_strip.contains(x, y))

    def clear_selection(self) -> None:
        """Drop every selected residue and tell whoever is listening.

        Clicking empty space clears the selection, as it does in PyMOL: a
        selection you cannot see the edges of is one you cannot get rid of.
        """
        changed = any(row.selected for row in self.sequences)
        for row in self.sequences:
            row.selected = set()
        if changed and self.on_select is not None:
            for row in self.sequences:
                try:
                    self.on_select(row.name, [], False)
                except Exception:
                    pass

    def visible_columns(self) -> int:
        """How many residues fit across the strip."""
        char_w = char_width(self.FONT_PT)
        return max(int((self._seq_strip.w - self._seq_origin - self.PAD) / char_w), 1)

    def max_scroll(self) -> int:
        """Return the furthest the sequence can be scrolled."""
        longest = max((len(row.codes) for row in self.sequences), default=0)
        return max(longest - self.visible_columns(), 0)

    def scroll_sequence(self, columns: int) -> bool:
        """Scroll by *columns*; returns whether anything moved."""
        before = self._seq_scroll
        self._seq_scroll = min(max(self._seq_scroll + int(columns), 0), self.max_scroll())
        if self._seq_scroll != before:
            self.layout_sequence(self._width, self._height)
        return self._seq_scroll != before

    def sequence_index_at(self, x: float, y: float) -> tuple[int, int] | None:
        """Return ``(row, residue index)`` under the cursor, or ``None``."""
        char_w = char_width(self.FONT_PT)
        for index, rect in enumerate(self._seq_rows):
            if not rect.contains(x, y):
                continue
            column = int((x - rect.x) / char_w) + self._seq_scroll
            row = self.sequences[index]
            if 0 <= column < len(row.codes):
                return index, column
            return None
        return None

    def _seek_to(self, x: float) -> None:
        """Jump the movie to the frame under the cursor."""
        track = self._timeline_track
        if track.w <= 0:
            return
        _current, total = self.state
        span = max(int(total), 1)
        fraction = min(max((x - track.x) / track.w, 0.0), 1.0)
        frame = int(round(fraction * (span - 1))) + 1
        if frame != self.state[0]:
            self.state = (frame, span)
            self.layout_block(self._width, self._height)
            if self.on_frame_change is not None:
                try:
                    self.on_frame_change(frame)
                except Exception:
                    pass

    def _scroll_to(self, x: float) -> None:
        """Put the thumb under the cursor and scroll to match."""
        track = self._seq_track
        if track.w <= 0:
            return
        fraction = min(max((x - track.x) / track.w, 0.0), 1.0)
        target = int(round(fraction * self.max_scroll()))
        if target != self._seq_scroll:
            self._seq_scroll = target
            self.layout_sequence(self._width, self._height)

    def _toggle_residue(self, row_index: int, column: int) -> None:
        """Flip one residue in and out of the selection.

        PyMOL's ``Seeker`` toggles on a click: a selected column is deselected,
        an unselected one selected. The whole selected set is emitted, because
        whoever mirrors the strip into the 3-D view replaces, not merges.
        """
        row = self.sequences[row_index]
        if column in row.selected:
            row.selected.discard(column)
        else:
            row.selected.add(column)
        if self.on_select is not None:
            try:
                self.on_select(row.name, sorted(row.selected), False)
            except Exception:
                pass

    def _select_range(self, row_index: int, start: int, end: int, additive: bool) -> None:
        """Select the residues between *start* and *end* on one row."""
        row = self.sequences[row_index]
        lo, hi = (start, end) if start <= end else (end, start)
        chosen = set(range(lo, hi + 1))
        row.selected = (row.selected | chosen) if additive else chosen
        if self.on_select is not None:
            try:
                self.on_select(row.name, sorted(row.selected), additive)
            except Exception:
                pass

    @property
    def movie_panel_visible(self) -> bool:
        """Whether there is a movie to scrub, and therefore a panel for it.

        PyMOL's own rule, from ``MovieGetPanelHeight`` (``layer1/Movie.cpp``):
        the panel has zero height unless a movie is defined or the scene has
        more than one frame. In chimol ``mset`` sets the frame count, so the two
        conditions collapse into one.

        Without it a single-state PDB -- the ordinary case -- got a full-width
        scrubber and a nine-button transport for a timeline of one, which is the
        loudest thing in the panel and controls nothing.
        """
        return int(self.state[1]) > 1

    def layout_block(self, width: int, height: int) -> None:
        """Place the mouse-mode block and the movie transport, bottom-right.

        Where PyMOL puts them, and for the same reason: it is reference material
        you glance at without leaving the view, so it belongs in the view.
        """
        char_w = char_width(self.FONT_PT)
        line_h = self.BLOCK_ROW_H
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        block_w = self.PAD + label_w + 4 * cell_w + self.PAD
        # title, the L/M/R/Wheel heading, six binding rows, selecting, state
        rows = len(rows_for(self.mouse_mode))
        movie = self.movie_panel_visible
        block_h = self.PAD + line_h * (rows + 5) + self.PAD
        if movie:
            block_h += self.SEQ_BAR_H + 4 + self.ROW_H + self.PAD

        if self.docked:
            block_w = max(block_w, self.column_width)
            self._block = Rect(
                width - self.column_width, height - block_h, block_w, block_h
            )
        else:
            self._block = Rect(
                width - self.MARGIN - block_w,
                height - self.MARGIN - block_h,
                block_w,
                block_h,
            )
        self._mode_rect = Rect(
            self._block.x + self.PAD, self._block.y + self.PAD, block_w, line_h
        )

        # Stride and average share the line under the state.
        stride_y = self._block.y + self.PAD + line_h * (rows + 4)
        char_w = char_width(self.FONT_PT)
        split = self.PAD + 10.0 * char_w + 5 * char_w      # label column + one cell
        self._stride_rect = Rect(self._block.x, stride_y, split, line_h)
        self._average_rect = Rect(
            self._block.x + split, stride_y, block_w - split, line_h
        )

        self._movie_rects = []
        if not movie:
            # Nothing to play: no track, no thumb, no buttons -- and an empty
            # rect fails `contains`, so the hit tests fall through by themselves.
            self._timeline_track = Rect(0, 0, 0, 0)
            self._timeline_thumb = Rect(0, 0, 0, 0)
            return

        # The timeline runs the width of the block, above the transport: the
        # state counter says *where* you are, and this is how you get somewhere
        # else without stepping frame by frame.
        self._timeline_track = Rect(
            self._block.x + self.PAD,
            self._block.y + block_h - self.PAD - self.ROW_H - self.SEQ_BAR_H - 4,
            block_w - 2 * self.PAD,
            self.SEQ_BAR_H,
        )
        current, total = self.state
        span = max(int(total), 1)
        fraction = (max(int(current), 1) - 1) / max(span - 1, 1)
        thumb_w = max(self._timeline_track.w / span, 10.0)
        self._timeline_thumb = Rect(
            self._timeline_track.x + fraction * (self._timeline_track.w - thumb_w),
            self._timeline_track.y, thumb_w, self.SEQ_BAR_H,
        )

        # The transport sits on the block's last line, spread across its width.
        self._movie_rects = []
        count = len(MOVIE_BUTTONS)
        button_w = min(28.0, (block_w - 2 * self.PAD) / count - 2)
        gap = ((block_w - 2 * self.PAD) - button_w * count) / max(count - 1, 1)
        bx = self._block.x + self.PAD
        by = self._block.y + block_h - self.PAD - self.ROW_H
        for glyph, command in MOVIE_BUTTONS:
            self._movie_rects.append((Rect(bx, by, button_w, self.ROW_H), command))
            bx += button_w + gap

    @property
    def block_rect(self) -> Rect:
        """Where the mouse-mode block currently sits."""
        return self._block

    def minimum_column_width(self) -> float:
        """Return the narrowest the column can be and still show what it holds.

        Measured from the contents rather than fixed: the object rows need the
        widest name plus five boxes, the mouse-mode block needs its label column
        and four action columns, and the transport needs a clickable target for
        each of its nine buttons. A constant floor either cuts one of them off
        or stops the splitter well before it needs to.
        """
        char_w = char_width(self.FONT_PT)
        rows_w = (
            self.PAD + self._name_width + self.PAD
            + self.BUTTON_W * len(OBJECT_MENUS) + self.PAD
        )
        block_w = self.PAD + 10.0 * char_w + 4 * (5 * char_w) + self.PAD
        transport_w = 2 * self.PAD + self.MIN_BUTTON_W * len(MOVIE_BUTTONS)
        return max(rows_w, block_w, transport_w)

    def cycle_mouse_mode(self) -> None:
        """Step to the next mode in the ring, as PyMOL's mode line does.

        Within the ring, not through all ten modes: a viewing ring steps
        viewing -> editing -> viewing and never lands on lights or maestro
        unless the ring is changed, which is the point of having one.
        """
        self.mouse_mode = next_mode(self.mouse_mode, self.mouse_ring)

    @property
    def panel_rect(self) -> Rect:
        """Where the panel currently sits."""
        return self._panel

    # ── hit testing ──────────────────────────────────────────────────────
    def hit_test(self, x: float, y: float) -> Hit:
        """Return what is under ``(x, y)``, menus first.

        Menus are tested before the panel and the panel before the scene, which
        is simply front-to-back: an open menu is drawn over everything, so it
        must also receive the click that lands on it.
        """
        depth, entry = self._menu_at(x, y)
        if depth is not None:
            if entry is None:
                return Hit("menu")
            return Hit("menu", entry=entry, submenu=entry.is_submenu)

        # Before the panel's own visibility gate: the prompt is drawn when the
        # panel is hidden, and a control that draws and cannot be clicked is
        # worse than one that is not drawn at all.
        if self.command_line.visible and self._cmd_rect.contains(x, y):
            return Hit("command")

        if not self.visible:
            return Hit("")

        if self.sequence_visible and self._seq_track.contains(x, y):
            return Hit("scrollbar")

        if self.sequence_visible and self._seq_strip.contains(x, y):
            found = self.sequence_index_at(x, y)
            if found is not None:
                return Hit("residue", row=found[0], key=str(found[1]))
            return Hit("sequence")

        for index, (rect, row) in enumerate(self._wizard_row_rects):
            if rect.contains(x, y):
                # A title row takes the click and does nothing, so a stray
                # press on the wizard's banner does not fall through to the
                # scene and start rotating the molecule behind it.
                return Hit("wizard", row=index, key=row.kind)
        if self._wizard_rect.contains(x, y):
            return Hit("wizard")

        if self.docked and self._splitter.contains(x, y):
            return Hit("splitter")

        if self._mode_rect.contains(x, y):
            return Hit("mode")
        if self._timeline_track.contains(x, y):
            return Hit("timeline")
        if self._stride_rect.contains(x, y):
            return Hit("stride")
        if self._average_rect.contains(x, y):
            return Hit("average")
        for rect, command in self._movie_rects:
            if rect.contains(x, y):
                return Hit("movie", key=command)
        if self._block.contains(x, y):
            return Hit("block")     # reference text: takes the click, does nothing

        for index, rect in enumerate(self._row_rects):
            if not rect.contains(x, y):
                continue
            for key, brect in self._button_rects[index].items():
                if brect.contains(x, y):
                    return Hit("button", row=index, key=key)
            return Hit("name", row=index)
        return Hit("")

    def _menu_at(self, x: float, y: float) -> tuple[int | None, MenuEntry | None]:
        """Return ``(depth, entry)`` for the deepest open menu under the cursor.

        Deepest first, because a child is drawn over its parent and, on a window
        too narrow to hold the chain, may still be sitting on top of it.
        ``entry`` is ``None`` when the cursor is on the menu but not on a row --
        the title, the padding, or the gap a separator leaves.
        """
        for depth in range(len(self._menus) - 1, -1, -1):
            menu = self._menus[depth]
            for rect, entry in menu.item_rects:
                # A scrolled-out row keeps its rectangle -- it is the same list
                # the painter walks -- so the visibility test has to be here as
                # well, or a menu would take clicks through its own title.
                if rect.contains(x, y) and self._menu_row_visible(menu, rect):
                    return depth, entry
            if menu.rect.contains(x, y):
                return depth, None
        return None, None

    def wants(self, x: float, y: float) -> bool:
        """Whether the panel would take a click here, rather than the camera.

        The whole reason a mouse press has to be offered to the panel first: a
        click that opens a menu must not also start rotating the molecule.
        """
        return bool(self.hit_test(x, y).kind)

    # ── interaction ──────────────────────────────────────────────────────
    def drag(self, x: float, y: float) -> bool:
        """Continue a splitter drag. Returns whether anything moved."""
        if self._dragging_timeline:
            self._seek_to(x)
            return True

        if self._dragging_thumb:
            self._scroll_to(x)
            return True

        if self._seq_drag is not None:
            found = self.sequence_index_at(x, y)
            if found is not None and found[0] == self._seq_drag[0]:
                self._select_range(self._seq_drag[0], self._seq_drag[1], found[1],
                                   additive=self._seq_drag_additive)
                return True
            return False

        if not self._dragging_splitter:
            return False
        # The upper bound has to clear the lower one on a narrow window, or the
        # clamp inverts and the column snaps to the *widest* it may be.
        floor = self.minimum_column_width()
        widest = max(self._width * self.MAX_COLUMN_FRACTION, floor)
        self.column_width = min(max(self._width - x, floor), widest)
        self.layout(self._width, self._height)
        return True

    def release(self) -> None:
        """End whichever drag the panel had started."""
        self._dragging_splitter = False
        self._seq_drag = None
        self._seq_drag_additive = False
        self._dragging_thumb = False
        self._dragging_timeline = False

    def is_dragging(self) -> bool:
        """Whether a drag the panel owns is in progress."""
        return (
            self._dragging_splitter
            or self._seq_drag is not None
            or self._dragging_thumb
            or self._dragging_timeline
        )

    def mouse_move(self, x: float, y: float) -> bool:
        """Track hover, opening and collapsing submenus. Returns whether to redraw."""
        hit = self.hit_test(x, y)
        changed = hit != self._hover
        self._hover = hit
        if self._menus:
            changed = self._track_menu_hover(x, y) or changed
        return changed

    def _track_menu_hover(self, x: float, y: float) -> bool:
        """Open the submenu under the cursor and close the branch it left.

        A submenu opening on hover is only half of the behaviour; PyMOL's
        ``PopUp`` drag also *frees the child* the moment the cursor moves to
        another row of the parent, and walks back up when the cursor re-enters
        it. Without that half, every submenu passed over stayed on screen and
        the menu became a pile of overlapping boxes.

        Returns whether anything opened or closed.
        """
        depth, entry = self._menu_at(x, y)
        if depth is None:
            # Off the menus -- but not off the *gap between* them. A submenu
            # opens beside its parent with `CHILD_GAP` of nothing in between, so
            # the straight line from the parent's row to the child's first item
            # crosses pixels that belong to neither menu. Collapsing on those
            # closed the child under the cursor on its way there, which made
            # every submenu unreachable by the obvious gesture.
            #
            # So the branch still collapses when the cursor genuinely leaves --
            # into the scene, into the object list -- and tolerates the seam.
            if self._within_menu_reach(x, y):
                return False
            return self._collapse_to(1)
        if entry is not None and entry.is_submenu:
            child = self._menus[depth + 1] if len(self._menus) > depth + 1 else None
            if child is not None and child.owner is entry:
                return self._collapse_to(depth + 2)   # its own children, though
            self._collapse_to(depth + 1)
            self._open_submenu(entry)
            return True
        return self._collapse_to(depth + 1)

    def _within_menu_reach(self, x: float, y: float) -> bool:
        """Whether ``(x, y)`` is inside the open menus' bounds, plus the seam.

        Parameters
        ----------
        x, y : float
            Cursor position, in logical pixels.

        Returns
        -------
        bool
            ``True`` for a point between two open menus -- the ``CHILD_GAP``
            seam a diagonal move across has to survive -- and ``False`` for one
            genuinely outside them.
        """
        if not self._menus:
            return False
        pad = float(self.CHILD_GAP) + 1.0
        left = min(menu.rect.x for menu in self._menus) - pad
        right = max(menu.rect.x + menu.rect.w for menu in self._menus) + pad
        top = min(menu.rect.y for menu in self._menus) - pad
        bottom = max(menu.rect.y + menu.rect.h for menu in self._menus) + pad
        return left <= x <= right and top <= y <= bottom

    def _collapse_to(self, depth: int) -> bool:
        """Close every menu deeper than *depth*. Returns whether any was open."""
        if len(self._menus) <= depth:
            return False
        del self._menus[depth:]
        return True

    def mouse_press(
        self,
        x: float,
        y: float,
        right: bool = False,
        modifiers=None,
        double: bool = False,
    ) -> bool:
        """Handle a press. Returns whether the panel consumed it."""
        # The progress overlay is modal and takes every press, including the
        # ones that miss its Cancel button. Letting one through would reach the
        # menu behind the scrim and start a second load on top of the first,
        # which is the failure this widget exists to prevent.
        if self.progress.active:
            return self.progress.handle_press(x, y)
        hit = self.hit_test(x, y)

        try:
            ctrl = bool(modifiers is not None and (modifiers & CONTROL_MODIFIER))
            shift = bool(modifiers is not None and (modifiers & SHIFT_MODIFIER))
        except Exception:
            ctrl = False
            shift = False

        if hit.kind == "command":
            self.close_menus()
            self.focus_command(True)
            self.command_line.cursor = self._cmd_cursor_at(x)
            return True
        if self.command_line.focused:
            # A press anywhere else takes focus away, so the next ``r`` rotates
            # the representation instead of appearing in a prompt the user has
            # stopped looking at.
            self.focus_command(False)

        if hit.kind == "menu":
            if hit.entry is None or hit.entry.is_separator:
                # The title row's arrows are the page control. Everything else
                # in the frame is deliberately inert -- a press on a menu's own
                # padding must not close it.
                for menu in reversed(self._menus):
                    if menu.max_scroll <= 0.0:
                        continue
                    button = self._menu_page_button(menu)
                    if button.contains(x, y):
                        # The left half goes back, the right half forward.
                        self.page_menu(-1 if x < button.x + button.w * 0.5 else 1,
                                       depth=self._menus.index(menu))
                        break
                return True
            if hit.entry.is_submenu:
                self._open_submenu(hit.entry)
                return True
            if hit.entry.command is None:
                return True          # shown, disabled, and says why
            target = self._menus[-1].target if self._menus else ""
            self._emit(hit.entry.command, target, prompt=hit.entry.prompt)
            self.close_menus()
            return True

        if hit.kind == "button":
            row = self.rows[hit.row]
            self.close_menus()
            for key, title, entries in OBJECT_MENUS:
                if key == hit.key:
                    rect = self._button_rects[hit.row][key]
                    self._open_menu(f"{title}:", row.name, entries, rect.x, rect.y + rect.h)
                    break
            return True

        if hit.kind == "wizard":
            self.close_menus()
            if hit.row < 0 or hit.row >= len(self._wizard_row_rects):
                return True                        # the panel's own background
            rect, row = self._wizard_row_rects[hit.row]
            if row.kind == "button":
                self._emit(row.action, "")
            elif row.kind == "menu":
                entries = ()
                if self.wizard_menu is not None:
                    try:
                        entries = self.wizard_menu(row.action) or ()
                    except Exception:
                        entries = ()
                if entries:
                    self._open_menu(
                        row.label, "", entries, rect.x, rect.y + rect.h
                    )
            return True

        if hit.kind == "scrollbar":
            self._dragging_thumb = True
            self._scroll_to(x)
            return True

        if hit.kind == "residue":
            row_index, column = hit.row, int(hit.key)
            self._seq_drag = (row_index, column)
            self._seq_drag_additive = bool(ctrl or shift)
            prev_anchor = self._seq_anchor
            self._seq_anchor = column
            if shift and prev_anchor is not None:
                # PyMOL's Seeker: shift continues the previous drag gesture,
                # extending the range from where it left off -- additively.
                self._select_range(row_index, prev_anchor, column, additive=True)
            else:
                # PyMOL's Seeker: a click toggles the residue (ctrl does the
                # same and additionally centres the view).
                self._toggle_residue(row_index, column)
            return True

        if hit.kind == "sequence":
            # PyMOL's Seeker clears the selection on a double-click on blank
            # sequence area.
            if double:
                self.clear_selection()
            return True

        if hit.kind == "splitter":
            self._dragging_splitter = True
            return True

        if hit.kind == "mode":
            self.cycle_mouse_mode()
            return True

        if hit.kind == "timeline":
            self._dragging_timeline = True
            self._seek_to(x)
            return True

        if hit.kind in ("stride", "average"):
            # Right-click steps back, so a value overshot is one click away
            # rather than a full trip round the cycle.
            step = -1 if right else 1
            if hit.kind == "stride":
                self.stride = max(1, self.stride + step)
            else:
                self.average = max(0, self.average + step)
            if self.on_playback_change is not None:
                try:
                    self.on_playback_change(self.stride, self.average)
                except Exception:
                    pass
            return True

        if hit.kind == "movie":
            self.close_menus()
            self._emit(hit.key, "")
            return True

        if hit.kind == "block":
            return True

        if hit.kind == "name":
            row = self.rows[hit.row]
            self.close_menus()
            if right:
                # PyMOL's right-click on a name is its action menu.
                _key, title, entries = OBJECT_MENUS[0]
                self._open_menu(f"{title}:", row.name, entries, x, y)
            elif row.is_group:
                # A group is a container row, so its name is the disclosure
                # control -- the same click the docked panel's marker takes.
                # Enabling or disabling it would be meaningless: a group has no
                # visibility apart from its members'.
                self._emit("group {sele}, toggle", row.name)
            elif row.is_selection:
                # PyMOL's `sele` row has no on/off: a selection is either there
                # or not, and the name click just makes it current. There is no
                # object to toggle.
                pass
            else:
                self._emit("disable {sele}" if row.enabled else "enable {sele}", row.name)
            return True

        if self._menus:
            self.close_menus()
            return True
        return False

    def _emit(self, command: str, target: str, prompt=None) -> None:
        """Run *command* with ``{sele}`` bound to *target*.

        An entry needing a typed value is written into the **command line**
        instead of being run, with the placeholder selected so the next
        keystroke replaces it. Skipping it -- which is what happened before, on
        the grounds that "a prompted value has no place to be typed in the
        viewport" -- made a menu entry that did nothing at all when clicked, and
        the viewport panel is now the primary one. The command line sits
        directly beneath it, which is where PyMOL would have you type anyway.

        Parameters
        ----------
        command : str
            Template, with ``{sele}`` for the target and ``{text}`` for a value.
        target : str
            Object, group or selection the menu was opened on.
        prompt : tuple of str, optional
            ``(title, question)`` from the menu entry; the question names the
            placeholder, so ``Group name:`` becomes ``<group name>``.
        """
        if self._run_command is None:
            return
        for line in str(command).splitlines():
            line = line.strip()
            if not line:
                continue
            line = line.replace("{sele}", target)
            if "{text}" in line:
                question = str((prompt or ("", "value"))[-1]).strip().rstrip(":")
                placeholder = f"<{question.lower() or 'value'}>"
                filled = line.replace("{text}", placeholder)
                # Into the viewport's own prompt first, with the caret on the
                # placeholder. That is the one that exists everywhere: the host
                # console is a desktop widget, and in a browser the entry would
                # otherwise be clickable and inert.
                if self.command_line.visible:
                    self.focus_command(True)
                    self.command_line.set_text(
                        filled, cursor=filled.find(placeholder)
                    )
                if self.on_prompt_command is not None:
                    try:
                        self.on_prompt_command(filled, placeholder)
                    except Exception:
                        pass
                continue
            try:
                self._run_command(line)
            except Exception:
                pass

    # ── menus ────────────────────────────────────────────────────────────
    def _open_menu(self, title, target, entries, x, y, parent=None,
                   owner=None) -> None:
        menu = _OpenMenu(title=title, target=target, entries=list(entries), x=x, y=y,
                         parent=parent, owner=owner,
                         affinity=parent.affinity if parent is not None else 1)
        self._layout_menu(menu)
        self._menus.append(menu)

    def _open_submenu(self, entry: MenuEntry) -> None:
        """Open *entry*'s children beside the row they hang off."""
        if self._menus and self._menus[-1].owner is entry:
            return                       # already open, and on the right row
        for depth in range(len(self._menus) - 1, -1, -1):
            parent = self._menus[depth]
            for rect, candidate in parent.item_rects:
                if candidate is not entry:
                    continue
                del self._menus[depth + 1:]
                # Beside the row, with the child's first *entry* on it rather
                # than the child's title -- PyMOL's `target_y` correction. The
                # x here is a starting point only; `_layout_menu` decides the
                # side, because it is the only place the width is known.
                self._open_menu(
                    entry.label, parent.target, entry.children,
                    parent.rect.x + parent.rect.w + self.CHILD_GAP,
                    rect.y - self.MENU_PAD - self.MENU_ITEM_H,
                    parent, owner=entry,
                )
                return

    def _place_child(
        self, parent: Rect, width: float, affinity: int
    ) -> tuple[float, int]:
        """Return ``(x, affinity)`` for a submenu *width* wide beside *parent*.

        PyMOL's ``PopPlaceChild``: try the preferred side, and if the menu had
        to be shoved back on screen to fit there, flip to the other side and try
        again. That flip is the whole point -- the panel is docked against the
        right edge, so a submenu opened to the right never fits, and clamping it
        into the window instead of flipping is what drew it *on top of its own
        parent*.
        """
        sides = {
            1: parent.x + parent.w + self.CHILD_GAP,
            -1: parent.x - width - self.CHILD_GAP,
        }
        limit = max(self._width - width, 0.0)
        preferred = 1 if affinity >= 0 else -1
        for side in (preferred, -preferred):
            if 0.0 <= sides[side] <= limit:
                return sides[side], side
        # Neither side fits: take the one with more room and clamp into it, so
        # what is lost is at the window edge rather than over the parent.
        side = -1 if parent.x >= self._width - (parent.x + parent.w) else 1
        return min(max(sides[side], 0.0), limit), side

    def _layout_menu(self, menu: _OpenMenu) -> None:
        """Size a menu from its entries and keep every item on screen.

        PyMOL's Action menu is two dozen entries long, which is taller than a
        viewport that is sharing its height with a sequence strip and a console.
        A menu that runs off the bottom is worse than a small font: the entries
        are simply unreachable, and nothing says they are there. So it wraps
        into columns, the way a long menu does everywhere, and the item
        rectangles stay the single source of truth for both drawing and hit
        testing -- they cannot disagree about where an entry is.
        """
        char_w = char_width(self.FONT_PT)
        title_h = self.MENU_ITEM_H
        content = title_h + 2 * self.MENU_PAD + sum(
            self.SEPARATOR_H if e.is_separator else self.MENU_ITEM_H
            for e in menu.entries
        )
        height = min(content, float(self._height))
        # A paged menu's title carries "2/3" and the arrows beside it, and both
        # are in the title *row*: without the allowance the page number is
        # drawn underneath the arrows on any menu whose entries are short.
        paged = content > height
        width = max(
            [len(menu.title) * char_w + (10 * char_w if paged else 0.0)]
            + [len(e.label) * char_w + (18 if e.is_submenu else 0) for e in menu.entries]
        ) + 2 * self.MENU_PAD + 12
        if height < content:
            # A whole number of rows, so the bottom one is not sliced through
            # the middle of its text -- which reads as a rendering fault rather
            # than as "there is more below".
            rows = max(int((height - title_h - 2 * self.MENU_PAD) // self.MENU_ITEM_H), 1)
            height = title_h + 2 * self.MENU_PAD + rows * self.MENU_ITEM_H
        menu.max_scroll = max(content - height, 0.0)
        menu.page_px = max(height - title_h - 2 * self.MENU_PAD, self.MENU_ITEM_H)
        menu.scroll = min(max(menu.scroll, 0.0), menu.max_scroll)

        if menu.parent is None:
            x = min(max(menu.x, 0.0), max(self._width - width, 0.0))
        else:
            # A submenu is placed *beside* its parent, never clamped into it.
            x, menu.affinity = self._place_child(
                menu.parent.rect, width, menu.affinity
            )
        y = min(max(menu.y, 0.0), max(self._height - height, 0.0))
        menu.rect = Rect(x, y, width, height)

        menu.item_rects = []
        iy = y + self.MENU_PAD + title_h - menu.scroll
        for entry in menu.entries:
            if entry.is_separator:
                iy += self.SEPARATOR_H
                continue
            menu.item_rects.append((Rect(x, iy, width, self.MENU_ITEM_H), entry))
            iy += self.MENU_ITEM_H

    @staticmethod
    def menu_pages(menu: _OpenMenu) -> tuple[int, int]:
        """Which page of a too-tall menu is showing, and how many there are.

        Returns
        -------
        tuple of int
            ``(page, pages)``, one-based. ``(1, 1)`` when it all fits.
        """
        if menu.max_scroll <= 0.0 or menu.page_px <= 0.0:
            return (1, 1)
        pages = int(menu.max_scroll // menu.page_px) + 2 \
            if menu.max_scroll % menu.page_px else int(menu.max_scroll // menu.page_px) + 1
        page = int(round(menu.scroll / menu.page_px)) + 1
        return (min(page, pages), pages)

    def page_menu(self, delta: int, depth: int | None = None) -> bool:
        """Turn a too-tall menu's page. Returns whether anything moved.

        Parameters
        ----------
        delta : int
            ``+1`` forward, ``-1`` back.
        depth : int, optional
            Which open menu; the innermost by default.
        """
        if not self._menus:
            return False
        menu = self._menus[depth if depth is not None else -1]
        if menu.max_scroll <= 0.0:
            return False
        wanted = min(max(menu.scroll + delta * menu.page_px, 0.0), menu.max_scroll)
        wanted = self._snap_scroll(menu, wanted)
        if wanted == menu.scroll:
            return False
        menu.scroll = wanted
        # Children hang off a row that has just moved, so they cannot stay.
        del self._menus[self._menus.index(menu) + 1:]
        self._layout_menu(menu)
        return True

    def _menu_page_button(self, menu: _OpenMenu) -> Rect:
        """The arrows in a menu's title row, as a press target."""
        rect = menu.rect
        width = 4.0 * char_width(self.FONT_PT) + self.MENU_PAD
        return Rect(rect.x + rect.w - width, rect.y + self.MENU_PAD,
                    width, self.MENU_ITEM_H)

    def _snap_scroll(self, menu: _OpenMenu, wanted: float) -> float:
        """Round a scroll offset to the nearest row boundary.

        So the first visible row starts flush with the top of the list instead
        of being sliced through its text. The separators are why a fixed step
        cannot do this on its own: they are five pixels, not a row, so the
        entries below one are off the row grid.
        """
        offsets = [0.0]
        y = 0.0
        for entry in menu.entries:
            y += self.SEPARATOR_H if entry.is_separator else self.MENU_ITEM_H
            if y <= menu.max_scroll:
                offsets.append(y)
        offsets.append(menu.max_scroll)
        return min(offsets, key=lambda candidate: abs(candidate - wanted))

    def _menu_row_visible(self, menu: _OpenMenu, rect: Rect) -> bool:
        """Whether a row is inside the menu's window rather than scrolled out."""
        top = menu.rect.y + self.MENU_PAD + self.MENU_ITEM_H
        return rect.y >= top - 1 and rect.y + rect.h <= menu.rect.y + menu.rect.h + 1

    def scroll_menu(self, x: float, y: float, steps: int) -> bool:
        """Scroll the menu under the cursor by *steps* notches. Returns if it moved.

        PyMOL's ``CPopUp::release`` translates the whole pop-up by ten pixels a
        notch rather than wrapping a long menu into columns, and that is the
        behaviour: a wrapped menu loses its **grouping**, which is most of what
        a menu's order is saying. chimol's Action menu wrapped on any short
        window and the two columns then read as one list broken in an arbitrary
        place, with the separators dropped to keep the columns aligned.
        """
        depth, _entry = self._menu_at(x, y)
        if depth is None:
            return False
        menu = self._menus[depth]
        if menu.max_scroll <= 0.0:
            return False
        before = menu.scroll
        wanted = min(
            max(menu.scroll - steps * self.MENU_SCROLL_PX, 0.0), menu.max_scroll
        )
        menu.scroll = self._snap_scroll(menu, wanted)
        if menu.scroll == before:
            return False
        # The children hang off rows that have just moved, so they are stale.
        del self._menus[depth + 1:]
        self._layout_menu(menu)
        return True

    # ── drawing ──────────────────────────────────────────────────────────
    def paint(self, p) -> None:
        """Draw the panel and any open menu.

        Parameters
        ----------
        p : chimol.renderer.ui.painter.Painter
            The surface to draw on. Six operations, each carrying its own
            colour -- see :mod:`chimol.renderer.ui.painter` for why this is not
            a ``QPainter`` with the names changed.
        """
        if not self.visible and not self._menus:
            # The prompt is not part of the panel: PyMOL's `internal_prompt` and
            # `internal_gui` are separate settings, and hiding the object list
            # to see the molecule is not a reason to lose the only way of typing
            # at it -- which in a browser is the *only* way.
            if self.info_visible:
                self._paint_info(p)
            if self.command_line.visible:
                self._paint_command(p)
                self._paint_windows(p)
            self._paint_menubar(p)
            self._paint_toolbar(p)
            return

        if self.info_visible:
            self._paint_info(p)
        if self.sequence_visible and self.sequences:
            self._paint_sequence(p)
        if self.visible and self.docked:
            # One continuous column, not two floating boxes with the scene
            # showing between them: the gap reads as a hole in the panel.
            column = self.effective_column_width()
            p.fill_rect(
                self._width - column, 0.0, column, float(self._height), PANEL_BG,
            )
        if self.docked and self.visible and self.rows:
            # Docked, the panel and block are part of the column; windowed,
            # their windows draw them in the window pass, correctly stacked
            # under whatever floats above.
            self._paint_panel(p)
        if self.visible and self.wizard_rows:
            self._paint_wizard(p)
        if self.docked and self.visible:
            self._paint_block(p)
        if self.wizard_prompt:
            self._paint_prompt(p)
        if self.command_line.visible:
            self._paint_command(p)
        self._paint_windows(p)
        self._paint_menubar(p)
        self._paint_toolbar(p)
        if self.visible and self.docked:
            p.fill_rect(
                self._splitter.x + self.SPLITTER_W / 2 - 1, 0.0,
                2.0, self._height, SPLITTER_FG,
            )
        self._paint_status(p)
        for menu in self._menus:
            self._paint_menu(p, menu)
        self._paint_tooltip(p)
        # Last, and after the tooltip: it is modal, so nothing may draw over
        # it. A tooltip surfacing above a scrim would say the chrome beneath is
        # live, which is exactly what the scrim is there to deny.
        self.progress.paint(p, self._width, self._height, self.ui_scale)

    def _paint_tooltip(self, p) -> None:
        """The hover tooltip, beside the cursor, above everything else."""
        if self._tooltip is None:
            return
        x, y, text = self._tooltip
        lines = _wrap_lines(str(text), 46)
        char_w = char_width(self.FONT_PT)
        width = max(len(line) for line in lines) * char_w + 2 * self.PAD
        height = len(lines) * self.CMD_ROW_H + 2.0
        # Beside the cursor, flipped to stay on screen.
        bx = min(x + 14.0, float(self._width) - width - 2.0)
        by = min(y + 18.0, float(self._height) - height - 2.0)
        p.fill_rect(bx, by, width, height, MOVIE_BG)
        p.stroke_rect(bx, by, width, height, WINDOW_BORDER)
        for index, line in enumerate(lines):
            p.text(bx + self.PAD, by + 1.0 + index * self.CMD_ROW_H,
                   width - 2 * self.PAD, float(self.CMD_ROW_H),
                   ALIGN_VCENTER | ALIGN_LEFT, line, MODE_ACTION_FG)

    def _paint_status(self, p) -> None:
        """The own status line, bottom-right of the viewport.

        Replaces the toolkit's status bar: drawn by the chrome, so it exists
        in the browser too, and it is a display setting (`show_status`) like
        every other piece of the chrome rather than a strip the toolkit owns.
        """
        height = float(self.CMD_ROW_H)
        y = float(self._height) - height - 2.0
        char_w = char_width(self.FONT_PT)

        # The chrome-size slider and the frame-rate readout are **developer
        # instruments**, so both are behind `debug`. They were shown to
        # everyone, and a permanent slider plus a permanent number in the
        # corner of a figure is chrome that earns its space only while someone
        # is measuring. Off, the status band is just the status band.
        if not self.debug_overlays:
            # An *empty* rect, not None. `Rect(0, 0, 0, 0).contains(...)` is
            # False, which is what "not there" means everywhere else in this
            # class -- and it is what `hit_test` and the drag handler already
            # assume, both of which dereference these without a guard. Using
            # None here made every click raise AttributeError the moment the
            # instruments were switched off, which is the default.
            self._ui_scale_rect = Rect(0, 0, 0, 0)
            self._ui_scale_groove = Rect(0, 0, 0, 0)
            self._paint_status_text(p, y, height, float(self._width) - 2.0)
            return

        # Frame rate, immediately left of the size slider: the two are read
        # together -- the question is always "what does this cost", and the
        # slider is the thing most likely to change the answer.
        fps_w = 0.0
        if self.fps > 0.0:
            fps_label = f"{self.fps:.0f} fps"
            fps_w = char_w * (len(fps_label) + 1) + self.PAD
        char_w = char_width(self.FONT_PT)
        # The number gets its own column and the groove gets the rest. Drawn on
        # top of each other, the thumb crossed the digits and both became hard
        # to read -- and the one thing a slider owes is a legible value.
        label = f"{self.ui_scale:.2f}"
        label_w = char_w * (len(label) + 1)
        groove_w = max(char_w * 10.0, 54.0)
        total_w = groove_w + label_w + 2 * self.PAD
        box_x = float(self._width) - total_w - 2.0
        self._ui_scale_rect = Rect(box_x, y, total_w, height)

        p.fill_rect(box_x, y, total_w, height, PANEL_BG)
        groove_x = box_x + self.PAD
        low, high = self.UI_SCALE_MIN, self.UI_SCALE_MAX
        fraction = (float(self.ui_scale) - low) / max(high - low, 1e-6)
        fraction = min(max(fraction, 0.0), 1.0)
        mid = y + height * 0.5
        p.fill_rect(groove_x, mid - 1.0, groove_w, 2.0, WINDOW_DIM_FG)
        p.fill_rect(groove_x, mid - 1.0, groove_w * fraction, 2.0, MODE_TITLE_FG)
        thumb = groove_x + fraction * max(groove_w - 5.0, 0.0)
        p.fill_rect(thumb, y + 3.0, 5.0, height - 6.0,
                    MODE_TITLE_FG if self._dragging_ui_scale else ENABLED_FG)
        editing = self.focused_field is self.ui_scale_field
        p.text(groove_x + groove_w + self.PAD, y, label_w, height,
               ALIGN_VCENTER | ALIGN_RIGHT,
               (self.ui_scale_field.text + "|") if editing else label,
               MODE_TITLE_FG if editing else WINDOW_DIM_FG)
        #: The groove alone, which is what a drag maps onto.
        self._ui_scale_groove = Rect(groove_x, y, groove_w, height)

        self._paint_status_text(p, y, height, box_x - fps_w)

    def _paint_status_text(self, p, y: float, height: float, right: float) -> None:
        """The status message, right-aligned against *right*.

        Split out because the band's right edge depends on what else is in it:
        the size slider and the frame counter are debug-only, so with them off
        the message may use the full width.

        This used to end at ``x = track_x - width``, and ``track_x`` is a name
        from a *different* method -- the info panel's scrollbar. Any code that
        set a status message would have raised ``NameError`` from inside the
        paint pass. Nothing sets one today, which is the only reason it was
        never seen.
        """
        if not (self.status_visible and self.status_text):
            return
        text = str(self.status_text)
        width = char_width(self.FONT_PT) * len(text) + 2 * self.PAD
        x = max(right - width - 4.0, 0.0)
        p.fill_rect(x, y, width, height, PANEL_BG)
        p.text(x + self.PAD, y, width - 2 * self.PAD, height,
               ALIGN_VCENTER | ALIGN_RIGHT, text, WINDOW_DIM_FG)

    def _paint_panel(self, p) -> None:
        """Draw the object list: one row per molecule, group or selection."""
        p.fill_rect(self._panel.x, self._panel.y, self._panel.w, self._panel.h,
                    PANEL_BG)

        for index, row in enumerate(self.rows):
            rect = self._row_rects[index]
            if row.is_header:
                p.fill_rect(rect.x, rect.y, rect.w, rect.h, HEADER_BG)

            label = row.name
            if row.is_group:
                label = ("▾ " if row.group_open else "▸ ") + label
            if row.detail:
                label = f"{label} {row.detail}"
            colour = (
                HEADER_FG if row.is_header
                else (ENABLED_FG if row.enabled else DISABLED_FG)
            )
            p.text(
                rect.x + self.PAD + row.indent * 10, rect.y,
                self._name_width, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, label, colour,
            )

            for key, brect in self._button_rects[index].items():
                self._paint_button(
                    p, key, brect,
                    hovered=(self._hover.kind == "button"
                             and self._hover.row == index
                             and self._hover.key == key),
                    enabled=row.enabled or row.is_header,
                )

    def _paint_wizard(self, p) -> None:
        """Draw the wizard panel, PyMOL's three row kinds and nothing else.

        A banner, pop-ups that carry their current value in the label, and
        buttons. PyMOL draws a pop-up and a button the same way and tells them
        apart by what happens on the click; here a pop-up keeps the menu
        marker, because a row that opens a menu and a row that acts are worth
        distinguishing before the click rather than after it.
        """
        rect = self._wizard_rect
        p.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL_BG)

        for row_rect, row in self._wizard_row_rects:
            hovered = (
                self._hover.kind == "wizard"
                and 0 <= self._hover.row < len(self._wizard_row_rects)
                and self._wizard_row_rects[self._hover.row][1] is row
            )
            if row.kind == "title":
                p.fill_rect(row_rect.x, row_rect.y, row_rect.w, row_rect.h,
                            HEADER_BG)
                colour = HEADER_FG
            else:
                if hovered:
                    p.fill_rect(row_rect.x + 1, row_rect.y,
                                row_rect.w - 2, row_rect.h, MENU_SEL_BG)
                colour = MENU_FG
            p.text(
                row_rect.x + self.PAD, row_rect.y,
                row_rect.w - 2 * self.PAD, row_rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, row.label, colour,
            )
            if row.kind == "menu":
                p.text(
                    row_rect.x, row_rect.y,
                    row_rect.w - self.PAD, row_rect.h,
                    ALIGN_VCENTER | ALIGN_RIGHT, "▾", colour,
                )

    def _paint_prompt(self, p) -> None:
        """Draw the wizard's instruction, top-left of the scene, as PyMOL does.

        Not in the panel: the prompt says what to do *in the view* -- "pick a
        residue" -- and putting it in the corner where the panel is means
        looking away from the molecule to read it.
        """
        if not self.wizard_prompt:
            return
        # Below the sequence strip, not over it. The strip owns a band at the
        # top of the window and the scene starts under it; a prompt at the
        # window's own top edge lands on the residue numbers.
        y = self.sequence_height() + self.MARGIN
        for line in self.wizard_prompt:
            p.text(
                self.MARGIN, y, self._width * 0.6, self.ROW_H,
                ALIGN_VCENTER | ALIGN_LEFT, str(line), MODE_TITLE_FG,
            )
            y += self.ROW_H

    def _paint_command(self, p) -> None:
        """Draw the feedback log and the prompt across the bottom of the scene.

        The caret is a filled rectangle rather than a glyph. A ``|`` sits inside
        a cell and reads as a character of the command; a block between two
        cells reads as a position, which is what it is -- and it needs nothing
        baked into the atlas.
        """
        line = self.command_line
        rect = self._cmd_rect
        if rect.w <= 0.0:
            return

        log = line.visible_log()
        if log:
            box = self._cmd_log_rect
            p.fill_rect(box.x, box.y, box.w, box.h, CMD_BG)
            for index, entry in enumerate(log):
                colour = {
                    "echo": CMD_ECHO_FG,
                    "error": CMD_ERROR_FG,
                }.get(entry.kind, CMD_MESSAGE_FG)
                p.text(
                    box.x + self.MARGIN, box.y + index * self.CMD_ROW_H,
                    box.w - 2 * self.MARGIN, float(self.CMD_ROW_H),
                    ALIGN_VCENTER | ALIGN_LEFT, entry.text, colour,
                )

        p.fill_rect(rect.x, rect.y, rect.w, rect.h, CMD_BG)
        if not line.focused:
            p.text(
                rect.x + self.MARGIN, rect.y, rect.w - 2 * self.MARGIN, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, HINT, CMD_HINT_FG,
            )
            return

        x = rect.x + self.MARGIN
        p.text(x, rect.y, p.text_width(PROMPT), rect.h,
               ALIGN_VCENTER | ALIGN_LEFT, PROMPT, CMD_PROMPT_FG)
        text_x = x + p.text_width(PROMPT + " ")
        p.text(
            text_x, rect.y, max(rect.w - text_x - self.MARGIN, 1.0), rect.h,
            ALIGN_VCENTER | ALIGN_LEFT, line.text, CMD_TEXT_FG,
        )
        caret = text_x + p.text_width(line.text[: line.cursor])
        p.fill_rect(caret, rect.y + 2.0, 1.5, rect.h - 4.0, CMD_CARET_FG)

    def _paint_sequence(self, p) -> None:
        """Draw the sequence strip: numbers, names, residues, selection.

        One-letter codes with a number every fifth column, which is PyMOL's
        default (``seq_view_format 0``, ``seq_view_label_mode 2``,
        ``seq_view_label_spacing 5``).
        """
        strip = self._seq_strip
        p.fill_rect(strip.x, strip.y, strip.w, strip.h, SEQ_BG)

        char_w = char_width(self.FONT_PT)
        visible = max(int((strip.w - self._seq_origin) / char_w), 1)

        # The number line, above the rows it labels.
        first = self.sequences[0] if self.sequences else None
        if first is not None:
            for column in range(self._seq_scroll, min(self._seq_scroll + visible,
                                                      len(first.codes))):
                if column % self.LABEL_SPACING:
                    continue
                number = (
                    first.numbers[column] if column < len(first.numbers) else column + 1
                )
                p.text(
                    self._seq_origin + (column - self._seq_scroll) * char_w,
                    self.PAD, char_w * 6, self.SEQ_ROW_H,
                    ALIGN_VCENTER | ALIGN_LEFT, str(number), SEQ_NUMBER_FG,
                )

        for index, row in enumerate(self.sequences):
            rect = self._seq_rows[index]
            p.text(
                self.PAD, rect.y, self._seq_origin - self.PAD, rect.h,
                ALIGN_VCENTER | ALIGN_LEFT, row.name, SEQ_NAME_FG,
            )
            for column in range(self._seq_scroll,
                                min(self._seq_scroll + visible, len(row.codes))):
                x = self._seq_origin + (column - self._seq_scroll) * char_w
                if column in row.selected:
                    p.fill_rect(x, rect.y, char_w, rect.h, SEQ_SELECTED_BG)
                    colour = SEQ_SELECTED_FG
                else:
                    colour = _residue_color(row, column)
                p.text(x, rect.y, char_w, rect.h,
                       ALIGN_CENTER, row.codes[column], colour)

        track, thumb = self._seq_track, self._seq_thumb
        p.fill_rect(track.x, track.y, track.w, track.h, SEQ_TRACK_BG)
        p.fill_rect(thumb.x, thumb.y, thumb.w, thumb.h, SEQ_THUMB_BG)

    def _paint_block(self, p) -> None:
        """Draw the mouse-mode reference, the state, and the transport."""
        rect = self._block
        p.fill_rect(rect.x, rect.y, rect.w, rect.h, PANEL_BG)

        char_w = char_width(self.FONT_PT)
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        left = rect.x + self.PAD
        line = rect.y + self.PAD

        gutter = char_w          # between a right-aligned label and its values

        def draw(x, y, text, colour, width=None, right=False):
            box_w = width or cell_w
            if right:
                # Shrink from the right so the text ends a gutter short of the
                # column beside it; right-aligning into the full width puts the
                # last glyph hard against the first value ("ButtonsL").
                box_w -= gutter
            p.text(
                x, y, box_w, self.BLOCK_ROW_H,
                ALIGN_VCENTER | (ALIGN_RIGHT if right else ALIGN_LEFT),
                text, colour,
            )

        draw(left, line, "Mouse Mode", MODE_TITLE_FG, label_w + cell_w, right=True)
        draw(left + label_w + cell_w, line,
             MODE_NAMES.get(self.mouse_mode, self.mouse_mode), MODE_TITLE_FG,
             rect.w)
        line += self.BLOCK_ROW_H

        draw(left, line, "Buttons", MODE_HEAD_FG, label_w, right=True)
        for index, (_key, heading) in enumerate(BUTTON_COLUMNS):
            draw(left + label_w + index * cell_w, line, heading, MODE_HEAD_FG)
        line += self.BLOCK_ROW_H

        for label, cells in rows_for(self.mouse_mode):
            colour = MODE_HEAD_FG if label == "& Keys" else MODE_KEY_FG
            draw(left, line, label, colour, label_w, right=True)
            for index, cell in enumerate(cells):
                if cell:
                    draw(left + label_w + index * cell_w, line, cell, MODE_ACTION_FG)
            line += self.BLOCK_ROW_H

        draw(left, line, "Selecting", SELECT_FG, label_w, right=True)
        draw(left + label_w, line, self.selecting, SELECT_MODE_FG, rect.w)
        line += self.BLOCK_ROW_H
        current, total = self.state
        draw(left, line, "State", STATE_FG, label_w, right=True)
        draw(left + label_w, line, f"{current} / {total}", MODE_ACTION_FG, cell_w * 3)
        line += self.BLOCK_ROW_H

        # Stride and averaging: PyMOL has neither, and a long or noisy
        # trajectory needs both -- one to watch it end to end without waiting,
        # the other to see the motion rather than the jitter.
        draw(left, line, "Stride", STATE_FG, label_w, right=True)
        draw(left + label_w, line, f"x{self.stride}", MODE_ACTION_FG, cell_w)
        draw(left + label_w + cell_w, line, "Avg", STATE_FG, cell_w)
        draw(left + label_w + cell_w * 2, line,
             "off" if self.average <= 1 else str(self.average),
             MODE_ACTION_FG, cell_w * 2)

        if not self.movie_panel_visible:
            return

        track, thumb = self._timeline_track, self._timeline_thumb
        p.fill_rect(track.x, track.y, track.w, track.h, SEQ_TRACK_BG)
        p.fill_rect(thumb.x, thumb.y, thumb.w, thumb.h, MOVIE_FG)

        for button_rect, _command in self._movie_rects:
            p.stroke_rect(button_rect.x, button_rect.y,
                          button_rect.w, button_rect.h,
                          BUTTON_EDGE, fill=MOVIE_BG)
            p.text(button_rect.x, button_rect.y, button_rect.w, button_rect.h,
                   ALIGN_CENTER, _glyph_of(_command), MOVIE_FG)

    def _paint_button(self, p, key, rect, hovered, enabled=True) -> None:
        """Draw one A/S/H/L/C box.

        A switched-off object keeps its boxes -- they are how it gets switched
        back on -- but they are drawn dim, so the row says at a glance which
        state it is in rather than only in the colour of its name.
        """
        x, y = rect.x, rect.y + 1
        w, h = rect.w, rect.h - 2
        if key == "C":
            stops = [
                _grey_of(stop) if not enabled else stop
                for stop in COLOR_BUTTON_STOPS
            ]
            p.gradient_rect(x, y, w, h, stops, edge=BUTTON_EDGE)
        elif not enabled:
            p.stroke_rect(x, y, w, h, BUTTON_EDGE, fill=BUTTON_OFF_BG)
        else:
            p.stroke_rect(x, y, w, h, BUTTON_EDGE,
                          fill=(HOVER_BG if hovered else BUTTON_BG))
        if key == "C":
            colour = (0, 0, 0) if enabled else (70, 70, 70)
        else:
            colour = BUTTON_FG if enabled else BUTTON_OFF_FG
        p.text(x, y, w, h, ALIGN_CENTER, key, colour)

    def _paint_menu(self, p, menu: _OpenMenu) -> None:
        """Draw one open menu, its title row, and its scroll marks."""
        rect = menu.rect
        p.stroke_rect(rect.x, rect.y, rect.w, rect.h, MENU_EDGE, fill=MENU_BG)

        page, pages = self.menu_pages(menu)
        title = menu.title if pages == 1 else f"{menu.title}  {page}/{pages}"
        room = rect.w - (self._menu_page_button(menu).w if pages > 1 else 0.0)
        p.text(
            rect.x + self.MENU_PAD, rect.y + self.MENU_PAD,
            max(room - self.MENU_PAD, 1.0), self.MENU_ITEM_H,
            ALIGN_VCENTER | ALIGN_LEFT, title, MENU_FG, bold=True,
        )

        # Say which way there is more, when the menu is taller than the window.
        # In the *title* row, not at the edges of the list: an arrow on the last
        # row would sit on top of that row's own text and its submenu marker.
        # PyMOL draws nothing at all and simply scrolls, which leaves a menu
        # that is silently cut off at the window edge -- the complaint that the
        # column-wrapping this replaces was trying to answer.
        if menu.max_scroll > 0.0:
            # `▴`/`▾`, not `◂`/`▸`: the baked atlas has the vertical pair (the
            # scroll marks these replace used them) and only one of the
            # horizontal one -- `▸` is the submenu marker. A glyph the atlas
            # does not have draws as nothing, so the "back" arrow was simply
            # absent on every page but the first.
            marks = ("▴" if menu.scroll > 0.0 else " ") + " " + (
                "▾" if menu.scroll < menu.max_scroll else " "
            )
            button = self._menu_page_button(menu)
            p.fill_rect(button.x, button.y, button.w, button.h, MENU_SEL_BG)
            p.text(
                rect.x, rect.y + self.MENU_PAD,
                rect.w - self.MENU_PAD, self.MENU_ITEM_H,
                ALIGN_VCENTER | ALIGN_RIGHT, marks, MENU_FG,
            )

        # Below the title, so a scrolled row cannot be drawn over it.
        p.push_clip(
            rect.x,
            rect.y + self.MENU_PAD + self.MENU_ITEM_H,
            rect.w,
            max(rect.h - self.MENU_PAD - self.MENU_ITEM_H, 0.0),
        )
        try:
            for item_rect, entry in menu.item_rects:
                hovered = (self._hover.kind == "menu" and self._hover.entry is entry)
                if hovered and (entry.command is not None or entry.is_submenu):
                    p.fill_rect(item_rect.x + 1, item_rect.y,
                                item_rect.w - 2, item_rect.h, MENU_SEL_BG)
                enabled = entry.is_submenu or entry.command is not None
                colour = MENU_FG if enabled else MENU_DISABLED_FG
                p.text(
                    item_rect.x + self.MENU_PAD, item_rect.y,
                    item_rect.w - 2 * self.MENU_PAD, item_rect.h,
                    ALIGN_VCENTER | ALIGN_LEFT, entry.label, colour,
                )
                if entry.is_submenu:
                    p.text(
                        item_rect.x, item_rect.y,
                        item_rect.w - self.MENU_PAD, item_rect.h,
                        ALIGN_VCENTER | ALIGN_RIGHT, "▸", colour,
                    )
        finally:
            p.pop_clip()


def _glyph_of(command: str) -> str:
    """Return the transport glyph bound to *command*."""
    for glyph, bound in MOVIE_BUTTONS:
        if bound == command:
            return glyph
    return "?"


def _residue_color(row: SequenceRow, index: int) -> tuple[int, int, int]:
    """Return the colour a residue is drawn in, from the structure's own.

    A sequence in one flat colour is a different picture from the molecule it
    indexes: colouring by chain or by spectrum says nothing if the strip does
    not show the same thing.
    """
    if index < len(row.colors):
        red, green, blue = row.colors[index][:3]
        return (
            int(max(0.0, min(1.0, red)) * 255),
            int(max(0.0, min(1.0, green)) * 255),
            int(max(0.0, min(1.0, blue)) * 255),
        )
    return SEQ_FG
