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

from ..mouse_modes import BUTTON_COLUMNS, MODE_NAMES, rows_for
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
    ("|<", "frame 1"),
    ("<", "frame -1"),
    ("\u25a0", "mstop"),
    ("\u25b6", "mplay"),
    (">", "frame +1"),
    (">|", "frame last"),
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
    numbers: list[int] = field(default_factory=list)
    selected: set[int] = field(default_factory=set)


@dataclass
class GuiRow:
    """One line of the panel: a molecule, a group, or the ``all`` header."""

    name: str
    enabled: bool = True
    is_header: bool = False
    is_group: bool = False
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
    """A menu currently on screen."""

    title: str
    target: str
    entries: Sequence[MenuEntry]
    x: float
    y: float
    parent: _OpenMenu | None = None
    item_rects: list[tuple[Rect, MenuEntry]] = field(default_factory=list)
    rect: Rect = Rect(0, 0, 0, 0)


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
    #: Residue numbers every this many columns -- PyMOL's
    #: ``seq_view_label_spacing``, whose default is 5.
    LABEL_SPACING = 5
    #: Height of one sequence line.
    SEQ_ROW_H = 15
    #: Grab width of the splitter, in pixels.
    SPLITTER_W = 6
    #: How narrow and how wide the column may be dragged.
    MIN_COLUMN = 120.0
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
        #: What a click selects, and where the movie is -- both shown there.
        self.selecting = "Residues"
        self.state = (1, 1)
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

    def layout_block(self, width: int, height: int) -> None:
        """Place the mouse-mode block and the movie transport, bottom-right.

        Where PyMOL puts them, and for the same reason: it is reference material
        you glance at without leaving the view, so it belongs in the view.
        """
        char_w = self.FONT_PT * 0.62
        line_h = self.ROW_H
        label_w = 7.4 * char_w
        cell_w = 5 * char_w
        block_w = self.PAD + label_w + 4 * cell_w + self.PAD
        # title, the L/M/R/Wheel heading, six binding rows, selecting, state
        rows = len(rows_for(self.mouse_mode))
        block_h = self.PAD + line_h * (rows + 4) + self.PAD + self.ROW_H + self.PAD

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

    def cycle_mouse_mode(self) -> None:
        """Step to the next mode, as clicking PyMOL's mode line does."""
        names = list(MODE_NAMES)
        if self.mouse_mode in names:
            self.mouse_mode = names[(names.index(self.mouse_mode) + 1) % len(names)]

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
        for menu in reversed(self._menus):
            for rect, entry in menu.item_rects:
                if rect.contains(x, y):
                    return Hit("menu", entry=entry, submenu=entry.is_submenu)
            if menu.rect.contains(x, y):
                return Hit("menu")

        if not self.visible:
            return Hit("")

        if self.docked and self._splitter.contains(x, y):
            return Hit("splitter")

        if self._mode_rect.contains(x, y):
            return Hit("mode")
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

    def wants(self, x: float, y: float) -> bool:
        """Whether the panel would take a click here, rather than the camera.

        The whole reason a mouse press has to be offered to the panel first: a
        click that opens a menu must not also start rotating the molecule.
        """
        return bool(self.hit_test(x, y).kind)

    # ── interaction ──────────────────────────────────────────────────────
    def drag(self, x: float, y: float) -> bool:
        """Continue a splitter drag. Returns whether anything moved."""
        if not self._dragging_splitter:
            return False
        widest = self._width * self.MAX_COLUMN_FRACTION
        self.column_width = min(max(self._width - x, self.MIN_COLUMN), widest)
        self.layout(self._width, self._height)
        return True

    def release(self) -> None:
        """End a splitter drag."""
        self._dragging_splitter = False

    def is_dragging(self) -> bool:
        """Whether the splitter is being dragged."""
        return self._dragging_splitter

    def mouse_move(self, x: float, y: float) -> bool:
        """Track hover. Returns whether a redraw is needed."""
        hit = self.hit_test(x, y)
        changed = hit != self._hover
        self._hover = hit
        # Hovering a submenu opens it, the way a menu behaves everywhere.
        if hit.kind == "menu" and hit.entry is not None and hit.entry.is_submenu:
            self._open_submenu(hit.entry)
            changed = True
        return changed

    def mouse_press(self, x: float, y: float, right: bool = False) -> bool:
        """Handle a press. Returns whether the panel consumed it."""
        hit = self.hit_test(x, y)

        if hit.kind == "menu":
            if hit.entry is None or hit.entry.is_separator:
                return True
            if hit.entry.is_submenu:
                self._open_submenu(hit.entry)
                return True
            if hit.entry.command is None:
                return True          # shown, disabled, and says why
            target = self._menus[-1].target if self._menus else ""
            self._emit(hit.entry.command, target)
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

        if hit.kind == "splitter":
            self._dragging_splitter = True
            return True

        if hit.kind == "mode":
            self.cycle_mouse_mode()
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
            else:
                self._emit("disable {sele}" if row.enabled else "enable {sele}", row.name)
            return True

        if self._menus:
            self.close_menus()
            return True
        return False

    def _emit(self, command: str, target: str) -> None:
        """Run *command* with ``{sele}`` bound to *target*."""
        if self._run_command is None:
            return
        for line in str(command).splitlines():
            line = line.strip()
            if not line or "{text}" in line:
                # A prompted value has no place to be typed in the viewport; the
                # docked panel still offers those entries.
                continue
            try:
                self._run_command(line.replace("{sele}", target))
            except Exception:
                pass

    # ── menus ────────────────────────────────────────────────────────────
    def _open_menu(self, title, target, entries, x, y, parent=None) -> None:
        menu = _OpenMenu(title=title, target=target, entries=list(entries), x=x, y=y,
                         parent=parent)
        self._layout_menu(menu)
        self._menus.append(menu)

    def _open_submenu(self, entry: MenuEntry) -> None:
        if not self._menus:
            return
        # Already open under this parent? Then leave it be.
        for menu in self._menus:
            if menu.title == entry.label:
                return
        parent = self._menus[-1]
        for rect, candidate in parent.item_rects:
            if candidate is entry:
                self._open_menu(entry.label, parent.target, entry.children,
                                parent.rect.x + parent.rect.w - 4, rect.y, parent)
                return

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
        x = min(max(menu.x, 0.0), max(self._width - width, 0.0))
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

            label = ("▾ " if row.is_group else "") + row.name
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
                self._paint_button(painter, QtGui, QtCore, key, brect,
                                   hovered=(self._hover.kind == "button"
                                            and self._hover.row == index
                                            and self._hover.key == key))

    def _paint_block(self, painter, QtGui, QtCore) -> None:
        """Draw the mouse-mode reference, the state, and the transport."""
        rect = self._block
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(*PANEL_BG))
        painter.drawRect(QtCore.QRectF(rect.x, rect.y, rect.w, rect.h))

        char_w = self.FONT_PT * 0.62
        label_w = 7.4 * char_w
        cell_w = 5 * char_w
        left = rect.x + self.PAD
        line = rect.y + self.PAD

        def draw(x, y, text, colour, width=None):
            painter.setPen(QtGui.QColor(*colour))
            painter.drawText(
                QtCore.QRectF(x, y, width or cell_w, self.ROW_H),
                int(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft), text,
            )

        draw(left, line, "Mouse Mode", MODE_TITLE_FG, label_w + cell_w)
        draw(left + label_w + cell_w * 0.6, line,
             MODE_NAMES.get(self.mouse_mode, self.mouse_mode), MODE_TITLE_FG,
             rect.w)
        line += self.ROW_H

        draw(left, line, "Buttons", MODE_HEAD_FG, label_w)
        for index, (_key, heading) in enumerate(BUTTON_COLUMNS):
            draw(left + label_w + index * cell_w, line, heading, MODE_HEAD_FG)
        line += self.ROW_H

        for label, cells in rows_for(self.mouse_mode):
            colour = MODE_HEAD_FG if label == "& Keys" else MODE_KEY_FG
            draw(left, line, label, colour, label_w)
            for index, cell in enumerate(cells):
                if cell:
                    draw(left + label_w + index * cell_w, line, cell, MODE_ACTION_FG)
            line += self.ROW_H

        draw(left, line, "Selecting", SELECT_FG, label_w + cell_w)
        draw(left + label_w + cell_w * 0.6, line, self.selecting, SELECT_MODE_FG, rect.w)
        line += self.ROW_H
        current, total = self.state
        draw(left, line, "State", STATE_FG, label_w)
        draw(left + label_w, line, f"{current} / {total}", MODE_ACTION_FG, cell_w * 3)

        for button_rect, _command in self._movie_rects:
            box = QtCore.QRectF(button_rect.x, button_rect.y,
                                button_rect.w, button_rect.h)
            painter.setBrush(QtGui.QColor(*MOVIE_BG))
            painter.setPen(QtGui.QColor(*BUTTON_EDGE))
            painter.drawRect(box)
            painter.setPen(QtGui.QColor(*MOVIE_FG))
            painter.drawText(box, int(QtCore.Qt.AlignCenter), _glyph_of(_command))

    def _paint_button(self, painter, QtGui, QtCore, key, rect, hovered) -> None:
        box = QtCore.QRectF(rect.x, rect.y + 1, rect.w, rect.h - 2)
        if key == "C":
            gradient = QtGui.QLinearGradient(box.left(), 0.0, box.right(), 0.0)
            for index, stop in enumerate(COLOR_BUTTON_STOPS):
                gradient.setColorAt(index / (len(COLOR_BUTTON_STOPS) - 1),
                                    QtGui.QColor(stop))
            painter.setBrush(QtGui.QBrush(gradient))
        else:
            painter.setBrush(QtGui.QColor(*(HOVER_BG if hovered else BUTTON_BG)))
        painter.setPen(QtGui.QColor(*BUTTON_EDGE))
        painter.drawRect(box)
        painter.setPen(QtGui.QColor(0, 0, 0) if key == "C" else QtGui.QColor(*BUTTON_FG))
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
