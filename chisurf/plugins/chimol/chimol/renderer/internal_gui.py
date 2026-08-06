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

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from qtpy import QtCore

from ..mouse_modes import BUTTON_COLUMNS, DEFAULT_RING, MODE_NAMES, next_mode, rows_for
from ..object_menus import OBJECT_MENUS, MenuEntry

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
COLOR_BUTTON_STOPS = ("#ff0000", "#ffff00", "#00ff00", "#00ffff", "#0000ff")


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
    FONT_PT = 10
    MENU_ITEM_H = 18
    MENU_PAD = 6
    #: Gap between a submenu and the parent it hangs off, on either side.
    CHILD_GAP = 3
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
    #: How narrow and how wide the column may be dragged.
    #: The transport needs a hit target per button, whatever else is in the
    #: column: below this the buttons stop being clickable rather than merely
    #: looking cramped.
    MIN_BUTTON_W = 14.0
    MAX_COLUMN_FRACTION = 0.6

    def __init__(self, run_command: Callable[[str], None] | None = None) -> None:
        self.visible = True
        #: Docked into a column of its own, PyMOL-style, rather than floating
        #: over the scene.
        self.docked = True
        self.rows: list[GuiRow] = []
        self._run_command = run_command
        self._row_rects: list[Rect] = []
        self._button_rects: list[dict[str, Rect]] = []
        self._panel = Rect(0, 0, 0, 0)
        self._hover = Hit("")
        self._menus: list[_OpenMenu] = []
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
        self.column_width = 220.0   # PyMOL's `internal_gui_width`
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

    # ── model ────────────────────────────────────────────────────────────
    def set_run_command(self, run_command: Callable[[str], None] | None) -> None:
        """Set the sink every click is turned into a command for."""
        self._run_command = run_command

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

        self.layout_block(width, height)
        self.layout_sequence(width, height)

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

        char_w = self.FONT_PT * 0.62
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
        char_w = self.FONT_PT * 0.62
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
        char_w = self.FONT_PT * 0.62
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
        char_w = self.FONT_PT * 0.62
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
        char_w = self.FONT_PT * 0.62
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
        char_w = self.FONT_PT * 0.62
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

        if not self.visible:
            return Hit("")

        if self.sequence_visible and self._seq_track.contains(x, y):
            return Hit("scrollbar")

        if self.sequence_visible and self._seq_strip.contains(x, y):
            found = self.sequence_index_at(x, y)
            if found is not None:
                return Hit("residue", row=found[0], key=str(found[1]))
            return Hit("sequence")

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
                if rect.contains(x, y):
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
            # Off the menus entirely. The branch the cursor wandered into is
            # done with, but the menu the button opened stays: it is dismissed
            # by a click, as PyMOL's is, not by the cursor drifting over the
            # scene on the way to it.
            return self._collapse_to(1)
        if entry is not None and entry.is_submenu:
            child = self._menus[depth + 1] if len(self._menus) > depth + 1 else None
            if child is not None and child.owner is entry:
                return self._collapse_to(depth + 2)   # its own children, though
            self._collapse_to(depth + 1)
            self._open_submenu(entry)
            return True
        return self._collapse_to(depth + 1)

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
        hit = self.hit_test(x, y)

        try:
            ctrl = bool(
                modifiers is not None and (modifiers & QtCore.Qt.ControlModifier)
            )
            shift = bool(
                modifiers is not None and (modifiers & QtCore.Qt.ShiftModifier)
            )
        except Exception:
            ctrl = False
            shift = False

        if hit.kind == "menu":
            if hit.entry is None or hit.entry.is_separator:
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
                if self.on_prompt_command is not None:
                    try:
                        self.on_prompt_command(
                            line.replace("{text}", placeholder), placeholder
                        )
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
        char_w = self.FONT_PT * 0.62
        col_w = max(
            [len(menu.title) * char_w]
            + [len(e.label) * char_w + (18 if e.is_submenu else 0) for e in menu.entries]
        ) + 2 * self.MENU_PAD + 12

        title_h = self.MENU_ITEM_H
        available = max(self._height - 2 * self.MENU_PAD - title_h, self.MENU_ITEM_H)
        clickable = [e for e in menu.entries if not e.is_separator]
        per_column = max(int(available // self.MENU_ITEM_H), 1)
        columns = max(1, -(-len(clickable) // per_column))    # ceil

        # Separators only cost height while the menu still fits in one column;
        # once it wraps, they would push the columns out of alignment.
        wrapped = columns > 1
        if not wrapped:
            height = title_h + 2 * self.MENU_PAD + sum(
                5 if e.is_separator else self.MENU_ITEM_H for e in menu.entries
            )
        else:
            height = title_h + 2 * self.MENU_PAD + per_column * self.MENU_ITEM_H

        width = col_w * columns
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
        column, iy = 0, y + self.MENU_PAD + title_h
        placed = 0
        for entry in menu.entries:
            if entry.is_separator:
                if not wrapped:
                    iy += 5
                continue
            if wrapped and placed and placed % per_column == 0:
                column += 1
                iy = y + self.MENU_PAD + title_h
            menu.item_rects.append(
                (Rect(x + column * col_w, iy, col_w, self.MENU_ITEM_H), entry)
            )
            iy += self.MENU_ITEM_H
            placed += 1

    # ── drawing ──────────────────────────────────────────────────────────
    def paint(self, painter) -> None:
        """Draw the panel and any open menu with *painter*."""
        from qtpy import QtCore, QtGui

        if not self.visible and not self._menus:
            return

        font = QtGui.QFont("Menlo")
        font.setStyleHint(QtGui.QFont.Monospace)
        font.setPointSize(self.FONT_PT)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)

        if self.sequence_visible and self.sequences:
            self._paint_sequence(painter, QtGui, QtCore)
        if self.visible and self.docked:
            # One continuous column, not two floating boxes with the scene
            # showing between them: the gap reads as a hole in the panel.
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(*PANEL_BG))
            painter.drawRect(QtCore.QRectF(
                self._width - self.column_width, 0.0,
                self.column_width, float(self._height),
            ))
        if self.visible and self.rows:
            self._paint_panel(painter, QtGui, QtCore, metrics)
        if self.visible:
            self._paint_block(painter, QtGui, QtCore)
        if self.visible and self.docked:
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(*SPLITTER_FG))
            painter.drawRect(QtCore.QRectF(
                self._splitter.x + self.SPLITTER_W / 2 - 1, 0.0, 2.0, self._height
            ))
        for menu in self._menus:
            self._paint_menu(painter, QtGui, QtCore, menu)

    def _paint_panel(self, painter, QtGui, QtCore, metrics) -> None:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*PANEL_BG))
        painter.drawRect(
            QtCore.QRectF(self._panel.x, self._panel.y, self._panel.w, self._panel.h)
        )

        for index, row in enumerate(self.rows):
            rect = self._row_rects[index]
            if row.is_header:
                painter.setBrush(QtGui.QColor(*HEADER_BG))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(QtCore.QRectF(rect.x, rect.y, rect.w, rect.h))

            label = row.name
            if row.is_group:
                label = ("▾ " if row.group_open else "▸ ") + label
            if row.detail:
                label = f"{label} {row.detail}"
            colour = (
                HEADER_FG if row.is_header
                else (ENABLED_FG if row.enabled else DISABLED_FG)
            )
            painter.setPen(QtGui.QColor(*colour))
            painter.drawText(
                QtCore.QRectF(
                    rect.x + self.PAD + row.indent * 10, rect.y,
                    self._name_width, rect.h,
                ),
                int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft),
                label,
            )

            for key, brect in self._button_rects[index].items():
                self._paint_button(
                    painter, QtGui, QtCore, key, brect,
                    hovered=(self._hover.kind == "button"
                             and self._hover.row == index
                             and self._hover.key == key),
                    enabled=row.enabled or row.is_header,
                )

    def _paint_sequence(self, painter, QtGui, QtCore) -> None:
        """Draw the sequence strip: numbers, names, residues, selection.

        One-letter codes with a number every fifth column, which is PyMOL's
        default (``seq_view_format 0``, ``seq_view_label_mode 2``,
        ``seq_view_label_spacing 5``).
        """
        strip = self._seq_strip
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*SEQ_BG))
        painter.drawRect(QtCore.QRectF(strip.x, strip.y, strip.w, strip.h))

        char_w = self.FONT_PT * 0.62
        visible = max(int((strip.w - self._seq_origin) / char_w), 1)

        # The number line, above the rows it labels.
        first = self.sequences[0] if self.sequences else None
        if first is not None:
            painter.setPen(QtGui.QColor(*SEQ_NUMBER_FG))
            for column in range(self._seq_scroll, min(self._seq_scroll + visible,
                                                      len(first.codes))):
                if column % self.LABEL_SPACING:
                    continue
                number = (
                    first.numbers[column] if column < len(first.numbers) else column + 1
                )
                painter.drawText(
                    QtCore.QRectF(
                        self._seq_origin + (column - self._seq_scroll) * char_w,
                        self.PAD, char_w * 6, self.SEQ_ROW_H,
                    ),
                    int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft), str(number),
                )

        for index, row in enumerate(self.sequences):
            rect = self._seq_rows[index]
            painter.setPen(QtGui.QColor(*SEQ_NAME_FG))
            painter.drawText(
                QtCore.QRectF(self.PAD, rect.y, self._seq_origin - self.PAD, rect.h),
                int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft), row.name,
            )
            for column in range(self._seq_scroll,
                                min(self._seq_scroll + visible, len(row.codes))):
                x = self._seq_origin + (column - self._seq_scroll) * char_w
                cell = QtCore.QRectF(x, rect.y, char_w, rect.h)
                if column in row.selected:
                    painter.setPen(QtCore.Qt.NoPen)
                    painter.setBrush(QtGui.QColor(*SEQ_SELECTED_BG))
                    painter.drawRect(cell)
                    painter.setPen(QtGui.QColor(*SEQ_SELECTED_FG))
                else:
                    painter.setPen(QtGui.QColor(*_residue_color(row, column)))
                painter.drawText(cell, int(QtCore.Qt.AlignCenter), row.codes[column])

        track, thumb = self._seq_track, self._seq_thumb
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*SEQ_TRACK_BG))
        painter.drawRect(QtCore.QRectF(track.x, track.y, track.w, track.h))
        painter.setBrush(QtGui.QColor(*SEQ_THUMB_BG))
        painter.drawRect(QtCore.QRectF(thumb.x, thumb.y, thumb.w, thumb.h))

    def _paint_block(self, painter, QtGui, QtCore) -> None:
        """Draw the mouse-mode reference, the state, and the transport."""
        rect = self._block
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*PANEL_BG))
        painter.drawRect(QtCore.QRectF(rect.x, rect.y, rect.w, rect.h))

        char_w = self.FONT_PT * 0.62
        label_w = 10.0 * char_w
        cell_w = 5 * char_w
        left = rect.x + self.PAD
        line = rect.y + self.PAD

        gutter = char_w          # between a right-aligned label and its values

        def draw(x, y, text, colour, width=None, right=False):
            painter.setPen(QtGui.QColor(*colour))
            align = QtCore.Qt.AlignRight if right else QtCore.Qt.AlignLeft
            box = QtCore.QRectF(x, y, width or cell_w, self.BLOCK_ROW_H)
            if right:
                # Shrink from the right so the text ends a gutter short of the
                # column beside it; right-aligning into the full width puts the
                # last glyph hard against the first value ("ButtonsL").
                box.setWidth(box.width() - gutter)
            painter.drawText(box, int(QtCore.Qt.AlignVCenter | align), text)

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
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*SEQ_TRACK_BG))
        painter.drawRect(QtCore.QRectF(track.x, track.y, track.w, track.h))
        painter.setBrush(QtGui.QColor(*MOVIE_FG))
        painter.drawRect(QtCore.QRectF(thumb.x, thumb.y, thumb.w, thumb.h))

        for button_rect, _command in self._movie_rects:
            box = QtCore.QRectF(button_rect.x, button_rect.y,
                                button_rect.w, button_rect.h)
            painter.setBrush(QtGui.QColor(*MOVIE_BG))
            painter.setPen(QtGui.QColor(*BUTTON_EDGE))
            painter.drawRect(box)
            painter.setPen(QtGui.QColor(*MOVIE_FG))
            painter.drawText(box, int(QtCore.Qt.AlignCenter), _glyph_of(_command))

    def _paint_button(self, painter, QtGui, QtCore, key, rect, hovered,
                      enabled=True) -> None:
        """Draw one A/S/H/L/C box.

        A switched-off object keeps its boxes -- they are how it gets switched
        back on -- but they are drawn dim, so the row says at a glance which
        state it is in rather than only in the colour of its name.
        """
        box = QtCore.QRectF(rect.x, rect.y + 1, rect.w, rect.h - 2)
        if key == "C":
            gradient = QtGui.QLinearGradient(box.left(), 0.0, box.right(), 0.0)
            for index, stop in enumerate(COLOR_BUTTON_STOPS):
                colour = QtGui.QColor(stop)
                if not enabled:
                    grey = colour.value() // 3 + 60
                    colour = QtGui.QColor(grey, grey, grey)
                gradient.setColorAt(index / (len(COLOR_BUTTON_STOPS) - 1), colour)
            painter.setBrush(QtGui.QBrush(gradient))
        elif not enabled:
            painter.setBrush(QtGui.QColor(*BUTTON_OFF_BG))
        else:
            painter.setBrush(QtGui.QColor(*(HOVER_BG if hovered else BUTTON_BG)))
        painter.setPen(QtGui.QColor(*BUTTON_EDGE))
        painter.drawRect(box)
        if key == "C":
            painter.setPen(QtGui.QColor(0, 0, 0) if enabled else QtGui.QColor(70, 70, 70))
        else:
            painter.setPen(QtGui.QColor(*(BUTTON_FG if enabled else BUTTON_OFF_FG)))
        painter.drawText(box, int(QtCore.Qt.AlignCenter), key)

    def _paint_menu(self, painter, QtGui, QtCore, menu: _OpenMenu) -> None:
        rect = QtCore.QRectF(menu.rect.x, menu.rect.y, menu.rect.w, menu.rect.h)
        painter.setBrush(QtGui.QColor(*MENU_BG))
        painter.setPen(QtGui.QColor(*MENU_EDGE))
        painter.drawRect(rect)

        painter.setPen(QtGui.QColor(*MENU_FG))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            QtCore.QRectF(menu.rect.x + self.MENU_PAD, menu.rect.y + self.MENU_PAD,
                          menu.rect.w, self.MENU_ITEM_H),
            int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft), menu.title,
        )
        font.setBold(False)
        painter.setFont(font)

        for item_rect, entry in menu.item_rects:
            hovered = (self._hover.kind == "menu" and self._hover.entry is entry)
            if hovered and entry.command is not None or (hovered and entry.is_submenu):
                painter.setBrush(QtGui.QColor(*MENU_SEL_BG))
                painter.setPen(QtCore.Qt.NoPen)
                painter.drawRect(
                    QtCore.QRectF(item_rect.x + 1, item_rect.y,
                                  item_rect.w - 2, item_rect.h)
                )
            enabled = entry.is_submenu or entry.command is not None
            painter.setPen(QtGui.QColor(*(MENU_FG if enabled else MENU_DISABLED_FG)))
            painter.drawText(
                QtCore.QRectF(item_rect.x + self.MENU_PAD, item_rect.y,
                              item_rect.w - 2 * self.MENU_PAD, item_rect.h),
                int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft),
                entry.label,
            )
            if entry.is_submenu:
                painter.drawText(
                    QtCore.QRectF(item_rect.x, item_rect.y,
                                  item_rect.w - self.MENU_PAD, item_rect.h),
                    int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignRight), "▸",
                )


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
