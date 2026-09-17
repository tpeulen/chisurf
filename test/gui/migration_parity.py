"""Before/after screenshot capture for GUI migrations.

Porting a hand-written model widget to AutoForm is a *replacement*, so "the new
panel looks fine" is the wrong question -- the question is whether anything was
lost. This module renders an editor headlessly and writes it as either the
``before`` or the ``after`` half of a pair, so both halves are produced the same
way and are directly comparable.

**Capture the before-half first.** Once the legacy widget is deleted the baseline
is unrecoverable, and a migration without one cannot be reviewed later.

Parity is judged on *control inventory, not pixels*: an AutoForm port
deliberately changes layout (a parameter table replaces stacked labelled rows --
that is the point), so any pixel-similarity threshold is either always red or
tuned so loose it proves nothing. :func:`control_inventory` extracts the
comparable content, and :func:`layout_tripwire` catches the blank-panel and
collapsed-layout failures an eye skims past.

See the migration rule in ``okf/workflows/testing.md``.
"""

from __future__ import annotations

import os
import pathlib
import typing

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: Where pairs are written. Override with ``CHISURF_MIGRATION_DIR``.
DEFAULT_DIR = pathlib.Path(os.environ.get("CHISURF_MIGRATION_DIR", "/tmp/chisurf-migration"))


def capture(
    widget: typing.Any,
    name: str,
    phase: str,
    out_dir: pathlib.Path | None = None,
    width: int = 460,
    min_height: int = 600,
    expand_panels: bool = True,
) -> pathlib.Path:
    """Render `widget` offscreen and save it as one half of a migration pair.

    Parameters
    ----------
    widget : typing.Any
        The editor to render. Shown and processed before grabbing so lazily
        built children exist in the image.
    name : str
        Stem identifying the migration, shared by both halves.
    phase : str
        Either ``"before"`` (the legacy widget) or ``"after"`` (its replacement).
    out_dir : pathlib.Path, optional
        Destination directory; :data:`DEFAULT_DIR` when omitted.
    width : int
        Render width. Both halves must use the same value or the comparison is
        confounded by reflow.
    min_height : int
        Floor for the render height, so a short editor is not cropped to nothing.
    expand_panels : bool
        Click open every collapsed panel first, so nothing hides behind a fold.
        The ``bounds`` toggles are left alone -- they hide columns by design.

    Returns
    -------
    pathlib.Path
        The written PNG.

    Raises
    ------
    ValueError
        If `phase` is not ``"before"`` or ``"after"``.
    """
    if phase not in ("before", "after"):
        raise ValueError(f"phase must be 'before' or 'after', got {phase!r}")

    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    if expand_panels:
        # AutoForm's fold headers are ``CollapsibleBox``es, whose header is a
        # QPushButton -- looking only for checkable QToolButtons found none of
        # them, so every panel a spec declares ``collapsed`` stayed shut and its
        # controls were missing from both halves of the pair *and* from the
        # control inventory. That is exactly the loss this module exists to catch.
        try:
            from chisurf.gui.widgets.collapsible_box import CollapsibleBox

            for box in widget.findChildren(CollapsibleBox):
                box.set_expanded(True)
        except Exception:
            pass
        for btn in widget.findChildren(QtWidgets.QToolButton):
            if btn.isCheckable() and not btn.isChecked() and btn.text() != "bounds":
                try:
                    btn.click()
                except Exception:
                    pass
        app.processEvents()

    widget.resize(width, max(widget.sizeHint().height(), min_height))
    widget.show()
    app.processEvents()

    out_dir = pathlib.Path(out_dir or DEFAULT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"{name}.{phase}.png"
    widget.grab().save(str(dest))
    return dest


#: Decoration stripped before comparing control text, so a control that merely
#: changed its rendering is not reported as lost. Includes the rich-text markup
#: legacy widgets used for subscripts (``t<sub>Bg</sub>`` and ``tBg`` are the same
#: control) and the disclosure glyphs AutoForm puts on panel headers.
_STRIP_PREFIXES = ("▶", "▼", "▸", "▾")


def _normalize_control_text(text: str) -> str:
    """Reduce control text to what is comparable across a migration.

    Parameters
    ----------
    text : str
        Raw label or button text.

    Returns
    -------
    str
        Lower-cased text with rich-text tags stripped, HTML entities decoded,
        disclosure glyphs, surrounding punctuation and internal whitespace
        removed.
    """
    import html
    import re

    # Entities are decoded, not just tags stripped: these labels are full of
    # them (``&tau;``, ``&kappa;``, ``&rarr;``), and comparing an escaped label
    # against a rendered one reports every Greek-lettered parameter as lost.
    out = html.unescape(re.sub(r"<[^>]+>", "", text))
    for glyph in _STRIP_PREFIXES:
        out = out.replace(glyph, "")
    out = out.strip().strip(":").strip()
    return re.sub(r"\s+", "", out).lower()


def _table_texts(widget: typing.Any) -> set[str]:
    """Collect the text a table *displays*, headers and cells alike.

    Without this, every port to a `parameter_group_table` reports each parameter
    as lost: the name moved out of a `QLabel` and into a cell, which
    `findChildren` cannot see. A comparison blind to table content is red on
    every migration and therefore worthless.

    Parameters
    ----------
    widget : typing.Any
        A rendered editor, searched for item views.

    Returns
    -------
    set of str
        Normalized header and cell strings across every table in the editor.
    """
    from qtpy import QtCore, QtWidgets

    def _n_columns(model) -> int:
        """Column count, or 1 for a list model (whose ``columnCount`` is private)."""
        try:
            return int(model.columnCount())
        except (TypeError, AttributeError):
            return 1

    found: set[str] = set()
    for view in widget.findChildren(QtWidgets.QAbstractItemView):
        model = view.model()
        if model is None:
            continue
        n_rows, n_cols = int(model.rowCount()), _n_columns(model)
        for orientation, count in (
            (QtCore.Qt.Horizontal, n_cols),
            (QtCore.Qt.Vertical, n_rows),
        ):
            for i in range(count):
                value = model.headerData(i, orientation, QtCore.Qt.DisplayRole)
                if value is not None and str(value).strip():
                    found.add(_normalize_control_text(str(value)))
        for row in range(n_rows):
            for col in range(n_cols):
                value = model.data(model.index(row, col), QtCore.Qt.DisplayRole)
                if value is not None and str(value).strip():
                    found.add(_normalize_control_text(str(value)))
    found.discard("")
    return found


def control_inventory(widget: typing.Any) -> dict:
    """Extract the comparable *content* of a rendered editor.

    What a reviewer needs to diff between the two halves: which controls exist,
    counting a name in a table cell as present. Deliberate layout differences
    (stacked rows becoming a table) therefore do not register, which is the point
    -- a genuinely missing control does.

    Parameters
    ----------
    widget : typing.Any
        A rendered editor.

    Returns
    -------
    dict
        ``controls`` is the union of normalized label, button and table text --
        the field to diff. ``labels`` / ``buttons`` are kept unnormalized for
        eyeballing, and the counts describe the shape of the layout.
    """
    from qtpy import QtWidgets

    labels = sorted(
        {w.text().strip() for w in widget.findChildren(QtWidgets.QLabel) if w.text().strip()}
    )
    buttons = sorted(
        {
            b.text().strip()
            for b in widget.findChildren(QtWidgets.QAbstractButton)
            if b.text().strip()
        }
    )
    controls = {_normalize_control_text(t) for t in labels + buttons}
    controls |= _table_texts(widget)
    controls.discard("")
    return {
        "controls": sorted(controls),
        "labels": labels,
        "buttons": buttons,
        "line_edits": len(widget.findChildren(QtWidgets.QLineEdit)),
        "combos": len(widget.findChildren(QtWidgets.QComboBox)),
        "spin_boxes": len(widget.findChildren(QtWidgets.QAbstractSpinBox)),
        "tables": len(widget.findChildren(QtWidgets.QAbstractItemView)),
    }


def compare_inventories(before: dict, after: dict) -> dict:
    """Diff two :func:`control_inventory` results.

    Parameters
    ----------
    before, after : dict
        Inventories of the legacy widget and its replacement.

    Returns
    -------
    dict
        ``lost`` is the blocker -- normalized controls present before and absent
        after. ``gained`` are additions, which are fine. ``counts`` pairs each
        numeric field as ``(before, after)`` to show how the layout changed.
    """
    return {
        "lost": sorted(set(before["controls"]) - set(after["controls"])),
        "gained": sorted(set(after["controls"]) - set(before["controls"])),
        "counts": {
            k: (before[k], after[k]) for k in ("line_edits", "combos", "spin_boxes", "tables")
        },
    }


def layout_tripwire(widget: typing.Any, min_visible: int = 5) -> list:
    """Report gross layout failures that a screenshot review skims past.

    Not a parity check -- a blank-but-correct panel would pass the inventory
    diff. This catches the editor that rendered to nothing, collapsed to zero
    height, or pushed children outside their parent.

    Parameters
    ----------
    widget : typing.Any
        A rendered editor.
    min_visible : int
        Fewest visible child widgets an editor may have before it is suspect.

    Returns
    -------
    list of str
        Human-readable problems; empty when the layout is sane.
    """
    from qtpy import QtWidgets

    problems = []
    if widget.width() <= 1 or widget.height() <= 1:
        problems.append(f"editor rendered at {widget.width()}x{widget.height()}")

    visible = [
        w
        for w in widget.findChildren(QtWidgets.QWidget)
        if w.isVisible() and w.width() > 0 and w.height() > 0
    ]
    if len(visible) < min_visible:
        problems.append(f"only {len(visible)} visible child widgets")

    rect = widget.rect()
    for w in visible:
        if not w.isWindow() and w.parentWidget() is widget:
            if not rect.intersects(w.geometry()):
                problems.append(f"{type(w).__name__} at {w.geometry()} lies outside the editor")
    return problems
