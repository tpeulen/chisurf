r"""Paint every painter-level control onto one sheet, so a human can look at it.

Why this exists
---------------
The controls in :mod:`chimol.renderer.ui` are tested against a recording
painter, which proves that a control emitted the rectangles it meant to and
nothing about whether the result is *legible*. A slider whose thumb is drawn
one pixel wide, a label that overhangs its column, a checkbox whose tick lands
outside its box, an arrow pointing the wrong way -- every one of those passes a
recording-painter test and is obvious in an image.

This is the image. One PNG, every control, drawn through the same ``QtPainter``
the chrome uses, laid out by the same :class:`~chimol.renderer.ui.layout.Layout`
a host would use.

It is a **development tool, not a test**. There is no golden image to compare
against: the point is that somebody reads it. A pixel threshold over a sheet
this size would be red on every font update and would prove nothing about the
thing being checked, which is the same argument
:mod:`~chisurf.plugins.chimol.test.chrome_baseline` makes about the chrome.

Use
---
    QT_QPA_PLATFORM=offscreen \\
        python -m chisurf.plugins.chimol.test.widget_gallery

writes ``renders/widget_gallery/<page>.png``, one page per family.
"""
from __future__ import annotations

import pathlib
from collections.abc import Callable, Sequence

__all__ = ["OUT_DIR", "PAGE_WIDTH", "ROW_H", "capture", "pages"]

#: Where the sheets land.
OUT_DIR = pathlib.Path(__file__).resolve().parent / "renders" / "widget_gallery"

#: Sheet width. Wide enough that a control given the full row still has room
#: for a caption beside it, which is how most of them are used.
PAGE_WIDTH = 620

#: Height of one control's row, and the gap under it. Deliberately generous:
#: a control drawn tight against its neighbour hides exactly the overhang this
#: sheet exists to reveal.
ROW_H = 22.0
ROW_GAP = 10.0

#: Width given to the control itself; the rest of the row is its caption.
CONTROL_W = 300.0
CAPTION_X = CONTROL_W + 24.0

#: The sheet background. Not black: the chrome is drawn over a lit scene, and
#: a control that relies on the backdrop being dark looks fine on black and
#: disappears in the app.
BACKDROP = (58, 62, 70)


def _rows(module_name: str) -> list[tuple]:
    """Return ``(caption, build)`` or ``(caption, build, height)`` for a module.

    Each ``build`` is a zero-argument callable returning a freshly constructed
    control, so a page can be re-drawn without controls carrying state over
    from a previous sheet.

    The optional third element is the row height. It exists because several
    controls are **not** one row tall -- a list box, a table, a colour picker
    and a menu each own a block -- and drawing them into a single row does not
    merely look cramped, it draws them over the control beneath, which is
    indistinguishable in the image from the overhang bug this sheet is meant
    to catch.

    Parameters
    ----------
    module_name : str
        Bare module name inside ``chimol.renderer.ui``, e.g. ``"buttons"``.

    Returns
    -------
    list
        The rows, or an empty list if the module is not present yet -- the
        gallery is written alongside a port in progress and must not fail
        because a family has not landed.
    """
    builders = _BUILDERS.get(module_name)
    if builders is None:
        return []
    try:
        __import__(f"chisurf.plugins.chimol.chimol.renderer.ui.{module_name}")
    except ImportError:
        return []
    return builders()


def _widgets_rows() -> list[tuple[str, Callable]]:
    """The nineteen controls that predate the port."""
    from chisurf.plugins.chimol.chimol.renderer.ui import widgets as w

    return [
        ("SliderFloat", lambda: w.SliderFloat("gain", 0.0, 1.0, 0.35)),
        ("ColorEdit4", lambda: w.ColorEdit4("colour", (210, 90, 60, 255))),
        ("Checkbox (on)", lambda: w.Checkbox("depth cue", True)),
        ("Checkbox (off)", lambda: w.Checkbox("outline", False)),
        ("Combo", lambda: w.Combo("style", ["cartoon", "sticks", "surface"], 1)),
        ("Button", lambda: w.Button("Apply")),
        ("ProgressBar", lambda: w.ProgressBar("loading", 0.62)),
        ("TreeNode", lambda: w.TreeNode("chain A", True, ["res 1", "res 2"])),
        ("Separator", lambda: w.Separator("group")),
        ("Toggle", lambda: w.Toggle("shadows", True)),
        ("RadioGroup", lambda: w.RadioGroup("axis", ["x", "y", "z"], 1)),
        ("InputInt", lambda: w.InputInt("frames", 24, 1, 100)),
        ("ListBox", lambda: w.ListBox("chains", ["A", "B", "C", "D"], 1, visible_rows=3), 64.0),
        ("Tabs", lambda: w.Tabs(["Scene", "Maps", "Fit"], 1)),
        ("PlotLines", lambda: w.PlotLines("rmsd", [1.0, 2.4, 1.8, 3.1, 2.2, 2.9]), 48.0),
        ("Histogram", lambda: w.Histogram("counts", [3.0, 7.0, 5.0, 9.0, 4.0]), 48.0),
        ("Tooltip", lambda: w.Tooltip(["distance 4.2 A", "chain A -> B"]), 40.0),
        ("TextInput", lambda: w.TextInput("name", "148L")),
        ("Table", lambda: w.Table(["chain", "atoms"], [["A", "1310"], ["B", "1288"]]), 72.0),
    ]


def _buttons_rows() -> list[tuple]:
    """The Button/Main family.

    The list dot is not here -- it belongs to :mod:`~chimol.renderer.ui.text`
    beside ``BulletText``, so that one dot has one implementation.
    """
    from chisurf.plugins.chimol.chimol.renderer.ui import buttons as b

    rows: list[tuple] = [
        ("SmallButton", lambda: b.SmallButton("SmallButton"), ROW_H, 110.0),
        ("InvisibleButton", lambda: b.InvisibleButton("InvisibleButton")),
        ("RadioButton", lambda: b.RadioButton("per-atom", True)),
    ]
    for name in ("LEFT", "RIGHT", "UP", "DOWN"):
        value = getattr(b, f"DIR_{name}")
        rows.append(
            (f"ArrowButton {name.lower()}", lambda v=value: b.ArrowButton(v), ROW_H, 26.0)
        )
    rows += [
        ("CheckboxFlags all", lambda: b.CheckboxFlags("all", 0b111, 0b111)),
        ("CheckboxFlags mixed", lambda: b.CheckboxFlags("mixed", 0b101, 0b111)),
        ("CheckboxFlags none", lambda: b.CheckboxFlags("none", 0b000, 0b111)),
    ]
    return rows


def _text_rows() -> list[tuple]:
    """The Text family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import text as t

    return [
        ("Text", lambda: t.Text("plain caption")),
        ("TextColored", lambda: t.TextColored((120, 220, 140), "converged")),
        ("TextDisabled", lambda: t.TextDisabled("no map loaded")),
        (
            "TextWrapped",
            lambda: t.TextWrapped(
                "A caption long enough that it has to fold onto several lines."
            ),
            52.0,
        ),
        ("LabelText", lambda: t.LabelText("resolution", "2.10 A")),
        ("Bullet", lambda: t.Bullet()),
        ("BulletText", lambda: t.BulletText("chain A refined")),
        ("SeparatorText", lambda: t.SeparatorText("Density")),
        ("TextLink", lambda: t.TextLink("open in browser")),
        ("Value (float)", lambda: t.Value("rmsd", 1.284)),
        ("Value (bool)", lambda: t.Value("visible", True)),
    ]


def _sliders_rows() -> list[tuple]:
    """The Slider family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import sliders as s

    return [
        ("SliderScalar", lambda: s.SliderScalar("alpha", 0.0, 1.0, 0.4)),
        ("SliderInt", lambda: s.SliderInt("frame", 0, 100, 37)),
        ("SliderInt (log)", lambda: s.SliderInt("atoms", 1, 100000, 500, logarithmic=True)),
        ("SliderAngle", lambda: s.SliderAngle("twist", 0.9)),
        ("SliderFloatN (3)", lambda: s.SliderFloatN("xyz", [0.2, 0.5, 0.8], 0.0, 1.0)),
        ("SliderIntN (2)", lambda: s.SliderIntN("range", [3, 7], 0, 10)),
        # A vertical slider wants a narrow box: given the full row it draws a
        # full-width grab, which reads as a horizontal bar and misrepresents
        # the control even though the geometry is right.
        ("VSliderFloat", lambda: s.VSliderFloat("gain", 0.0, 1.0, 0.65), 96.0, 46.0),
        ("VSliderInt", lambda: s.VSliderInt("step", 0, 10, 3), 96.0, 46.0),
    ]


def _drag_rows() -> list[tuple]:
    """The Drag family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import drag as d

    return [
        ("DragFloat", lambda: d.DragFloat("cutoff", 2.5, v_speed=0.1)),
        ("DragInt", lambda: d.DragInt("bins", 64, v_speed=1.0, v_min=1, v_max=512)),
        ("DragFloatN (3)", lambda: d.DragFloatN("origin", [1.0, -2.5, 0.75])),
        ("DragIntN (2)", lambda: d.DragIntN("size", [128, 96])),
        ("DragFloatRange2", lambda: d.DragFloatRange2("contour", 0.8, 3.2)),
        ("DragIntRange2", lambda: d.DragIntRange2("frames", 5, 40)),
    ]


def _inputs_rows() -> list[tuple]:
    """The Input family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import inputs as i

    return [
        ("InputFloat", lambda: i.InputFloat("sigma", 1.25, step=0.1, step_fast=1.0)),
        ("InputDouble", lambda: i.InputDouble("tau", 4.012345)),
        ("InputScalarN (3)", lambda: i.InputScalarN("cell", [90.0, 90.0, 120.0])),
        ("InputTextWithHint", lambda: i.InputTextWithHint("pdb", "e.g. 148L", "")),
        ("  ... once typed", lambda: i.InputTextWithHint("pdb", "e.g. 148L", "2f5n")),
        (
            "InputTextMultiline",
            lambda: i.InputTextMultiline("notes", "chain A ok\nchain B clashes\n", 3),
            84.0,
        ),
    ]


def _combo_rows() -> list[tuple]:
    """The real drop-down, closed and open.

    ``widgets.Combo`` cycles in place on click; this one opens a list. Both
    are photographed so the difference is visible rather than asserted.
    """
    from chisurf.plugins.chimol.chimol.renderer.ui import combo as c

    options = ["cartoon", "sticks", "spheres", "surface", "ribbon", "dots"]

    class _Open:
        """A combo with its list dropped."""

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Open the list and paint frame plus popup."""
            box = c.ComboBox("style", options, 2)
            box.open = True
            box.draw(p, x, y, w, 18.0)

    return [
        ("ComboBox (closed)", lambda: c.ComboBox("style", options, 2)),
        ("ComboBox (no arrow)", lambda: c.ComboBox("style", options, 0, flags=c.COMBO_NO_ARROW_BUTTON)),
        ("ComboBox (open)", _Open, 132.0),
    ]


def _selection_rows() -> list[tuple]:
    """Selectable, CollapsingHeader and the selection model."""
    from chisurf.plugins.chimol.chimol.renderer.ui import selection as s

    return [
        ("Selectable", lambda: s.Selectable("chain A", False)),
        ("Selectable (selected)", lambda: s.Selectable("chain B", True)),
        ("Selectable (disabled)", lambda: s.Selectable("chain C", False, s.SELECTABLE_DISABLED)),
        ("CollapsingHeader", lambda: s.CollapsingHeader("Density", True, children=["level", "step"])),
        ("  ... closable", lambda: s.CollapsingHeader("Maps", False, closable=True)),
        (
            "SelectableList",
            lambda: s.SelectableList(["alpha", "beta", "gamma", "delta"], disabled=[2]),
            84.0,
        ),
    ]


def _color_rows() -> list[tuple]:
    """The Colour family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import color as c

    return [
        ("ColorButton", lambda: c.ColorButton((220, 110, 40, 255), "warm")),
        ("ColorButton (alpha)", lambda: c.ColorButton((60, 160, 240, 110), "half")),
        ("ColorEditRGB", lambda: c.ColorEditRGB("diffuse", (200, 80, 60, 255))),
        ("ColorEditRGBA (HSV)", lambda: c.ColorEditRGBA("tint", (80, 200, 120, 200), mode="HSV")),
        ("ColorPicker3", lambda: c.ColorPicker3((210, 60, 60, 255), "hue"), 150.0),
        ("ColorPicker4", lambda: c.ColorPicker4((60, 120, 220, 180), True, "rgba"), 150.0),
    ]


def _menus_rows() -> list[tuple]:
    """Menus and popups."""
    from chisurf.plugins.chimol.chimol.renderer.ui import menus as m

    def _file_menu() -> m.Menu:
        return m.Menu(
            "File",
            [
                m.MenuItem("Open...", "Ctrl+O"),
                m.MenuItem("Save", "Ctrl+S"),
                m.MenuItem("Autosave", checked=True, checkable=True),
                m.MenuItem("Export", enabled=False),
            ],
        )

    class _OpenBarMenu:
        """A bar title with its panel dropped, which is the common case.

        Drawn ``horizontal`` so the panel opens *downwards*. A submenu opens
        to the right instead, and at this sheet's width that puts the panel
        over the caption column -- which photographs as a bug and is not one.
        """

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Open the menu and paint title plus panel."""
            menu = _file_menu()
            menu.horizontal = True
            menu.open = True
            menu.draw(p, x, y, 90.0, 18.0)

    class _OpenPopup:
        """A popup anchored near the top-left of its viewport.

        A popup is *placed inside a viewport*, not into a row box, and a
        closed one draws nothing -- so it has to be opened somewhere before
        there is anything to photograph.
        """

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Open at a point and paint into the row as the viewport."""
            popup = m.Popup([m.MenuItem("Copy", "Ctrl+C"), m.MenuItem("Paste")], "Selection")
            popup.open_at((x + 8.0, y + 4.0))
            popup.draw(p, x, y, w, h)

    return [
        ("MenuItem", lambda: m.MenuItem("Fetch...", "Ctrl+F")),
        ("MenuItem (checked)", lambda: m.MenuItem("Depth cue", checked=True, checkable=True)),
        ("MenuItem (disabled)", lambda: m.MenuItem("Undo", "Ctrl+Z", enabled=False)),
        ("MenuBar", lambda: m.MenuBar([_file_menu(), m.Menu("Edit"), m.Menu("Display")])),
        ("Menu (open, from a bar)", _OpenBarMenu, 116.0),
        ("Popup (open)", _OpenPopup, 96.0),
    ]


def _tabs_rows() -> list[tuple]:
    """The TabBar family."""
    from chisurf.plugins.chimol.chimol.renderer.ui import tabs as t

    return [
        ("TabBar (measured)", lambda: t.TabBar(["Scene", "A much longer tab", "Fit"], index=1)),
        (
            "TabBar (closable)",
            lambda: t.TabBar(
                [
                    t.TabItem("148L", closable=True),
                    t.TabItem("2f5n", closable=True, modified=True),
                    t.TabItem("locked", disabled=True),
                ],
            ),
        ),
        (
            "TabBar (shrunk)",
            lambda: t.TabBar(
                ["Structures", "Densities", "Trajectories", "Measurements", "Fitting"],
            ),
        ),
        (
            "TabBar (scroll policy)",
            lambda: t.TabBar(
                ["Structures", "Densities", "Trajectories", "Measurements", "Fitting"],
                flags=t.TAB_BAR_FITTING_POLICY_SCROLL,
                index=4,
            ),
        ),
    ]


def _tables_rows() -> list[tuple]:
    """The Tables subsystem."""
    from chisurf.plugins.chimol.chimol.renderer.ui import tables as tb

    rows = [
        ["A", 1310, "protein", 2.10],
        ["B", 1288, "protein", 2.14],
        ["C", 96, "dna", 2.30],
        ["W", 412, "water", 1.98],
    ]
    return [
        (
            "DataTable (stretch)",
            lambda: tb.DataTable(["chain", "atoms", "kind", "res"], rows),
            96.0,
        ),
        (
            "DataTable (fixed+stretch)",
            lambda: tb.DataTable(
                [
                    tb.Column("chain", tb.WIDTH_FIXED, 54.0),
                    tb.Column("atoms", tb.WIDTH_FIXED, 54.0),
                    tb.Column("kind", tb.WIDTH_STRETCH, 1.0),
                    tb.Column("res", tb.WIDTH_STRETCH, 2.0),
                ],
                rows,
                sizing=tb.SIZING_FIXED_FIT,
            ),
            96.0,
        ),
        (
            "DataTable (frozen row)",
            lambda: tb.DataTable(
                ["chain", "atoms", "kind", "res"], rows * 3, freeze_rows=1
            ),
            110.0,
        ),
    ]


def _dragdrop_rows() -> list[tuple]:
    """Drag-and-drop and the delayed tooltip.

    These are the one family whose members do not all share the plain
    ``draw(p, x, y, w, h)`` surface -- a drag preview follows the cursor and
    so takes the context, and a delayed tooltip only paints once its delay has
    elapsed. Each is wrapped in a shim that puts it into the state worth
    photographing, which is also the honest picture: an idle source and a
    dragging one look different, and that difference is the widget.
    """
    from chisurf.plugins.chimol.chimol.renderer.ui import dragdrop as dd

    class _Dragging:
        """A source mid-drag, drawing its preview under the cursor."""

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Begin a drag and paint the preview."""
            source = dd.DragDropSource("obj:148L", "object", "148L", "148L")
            context = dd.DragDropContext()
            context.begin(source)
            context.move(x + 40.0, y + 2.0)
            source.draw_preview(p, context)

    class _Hovered:
        """A target with a compatible drag over it, showing its highlight."""

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Place the target, hover it, and paint the accept rectangle."""
            target = dd.DragDropTarget("scene", "object")
            source = dd.DragDropSource("obj:148L", "object", "148L", "148L")
            context = dd.DragDropContext()
            context.begin(source)
            target.place(x, y, w, h)
            context.move(x + w * 0.5, y + h * 0.5)
            context.hover(target)
            target.draw(p, x, y, w, h)

    class _Tip:
        """A tooltip whose delay has elapsed with the cursor held still."""

        def draw(self, p, x: float, y: float, w: float, h: float) -> None:
            """Dwell past the delay, then paint."""
            tip = dd.DelayedTooltip(["chain A", "1310 atoms"], delay=0.1)
            tip.hover(x, y, 0.0)
            tip.hover(x, y, 5.0)
            tip.draw_at(p, x, y)

    return [
        ("DragDropSource (dragging)", _Dragging, 40.0),
        ("DragDropTarget (hovered)", _Hovered, 34.0),
        ("DelayedTooltip (shown)", _Tip, 48.0),
    ]


def _layout_rows() -> list[tuple]:
    """A worked layout, since ``Layout`` itself draws nothing.

    The cursor is arithmetic: it has no ``draw``. Photographing it therefore
    means photographing *controls it placed*, which is also the only way to
    see the thing worth seeing -- that a row, a ``same_line`` and an indent
    put controls where a reader expects them.
    """
    from chisurf.plugins.chimol.chimol.renderer.ui import layout as lay
    from chisurf.plugins.chimol.chimol.renderer.ui import widgets as w

    class _Demo:
        """Draws a small panel through :class:`Layout`."""

        def draw(self, p, x: float, y: float, width: float, height: float) -> None:
            """Lay out five controls with the cursor and paint them."""
            cursor = lay.Layout(p, x, y, width, height)
            w.Separator("Group").draw(p, *cursor.row())
            w.Checkbox("cull", True).draw(p, *cursor.row(width=90.0))
            cursor.same_line()
            w.Checkbox("fog", False).draw(p, *cursor.row(width=90.0))
            cursor.indent()
            w.SliderFloat("density", 0.0, 1.0, 0.4).draw(p, *cursor.row())
            cursor.unindent()
            w.Button("Apply").draw(p, *cursor.row(width=80.0))

    return [("Layout: rows, same_line, indent", _Demo, 108.0)]


#: One entry per control module. A family that has not landed is simply
#: absent from the sheet rather than an import error.
_BUILDERS: dict[str, Callable[[], list[tuple]]] = {
    "widgets": _widgets_rows,
    "text": _text_rows,
    "buttons": _buttons_rows,
    "sliders": _sliders_rows,
    "drag": _drag_rows,
    "inputs": _inputs_rows,
    "combo": _combo_rows,
    "color": _color_rows,
    "selection": _selection_rows,
    "menus": _menus_rows,
    "tabs": _tabs_rows,
    "tables": _tables_rows,
    "dragdrop": _dragdrop_rows,
    "layout": _layout_rows,
}


def pages() -> list[str]:
    """Names of the families the gallery can currently draw.

    Returns
    -------
    list of str
        Module names, in the order the sheets are written.
    """
    return [name for name in _BUILDERS if _rows(name)]


def capture(page: str, out_dir: pathlib.Path = OUT_DIR) -> pathlib.Path:
    """Draw one family's sheet and write it as a PNG.

    Parameters
    ----------
    page : str
        A module name from :func:`pages`.
    out_dir : pathlib.Path, optional
        Directory for the PNG; created if absent.

    Returns
    -------
    pathlib.Path
        The file written.
    """
    from qtpy import QtGui

    from chisurf.plugins.chimol.chimol.renderer.ui import painter as painter_mod
    from chisurf.plugins.chimol.chimol.renderer.ui.qt_painter import QtPainter

    rows = [
        (
            row[0],
            row[1],
            row[2] if len(row) > 2 else ROW_H,
            row[3] if len(row) > 3 else CONTROL_W,
        )
        for row in _rows(page)
    ]
    height = int(sum(row[2] + ROW_GAP for row in rows) + 2 * ROW_GAP)
    image = QtGui.QImage(PAGE_WIDTH, height, QtGui.QImage.Format_ARGB32_Premultiplied)
    image.fill(QtGui.QColor(*BACKDROP))

    qp = QtGui.QPainter(image)
    try:
        p = QtPainter(qp, font_pt=10)
        y = ROW_GAP
        for caption, build, row_h, row_w in rows:
            build().draw(p, ROW_GAP, y, row_w, row_h)
            p.text(
                CAPTION_X,
                y,
                PAGE_WIDTH - CAPTION_X - ROW_GAP,
                row_h,
                painter_mod.ALIGN_LEFT | painter_mod.ALIGN_VCENTER,
                caption,
                (170, 175, 185),
            )
            y += row_h + ROW_GAP
    finally:
        qp.end()

    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{page}.png"
    image.save(str(path))
    return path


def main(argv: Sequence[str] | None = None) -> int:
    """Write a sheet for every family the gallery can draw.

    Parameters
    ----------
    argv : sequence of str, optional
        Family names to draw. When omitted the command line is read, and
        when that is empty too, every family is drawn.

    Returns
    -------
    int
        Process exit status.
    """
    import sys

    from qtpy import QtWidgets

    if argv is None:
        argv = sys.argv[1:]
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    wanted = list(argv) if argv else pages()
    for page in wanted:
        print(capture(page))
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
