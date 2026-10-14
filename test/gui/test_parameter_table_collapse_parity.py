"""The emtk parameter table drops columns for width in the order the Qt one does.

The Qt ``ParameterGroupTableWidget`` hides whole column tiers when its viewport
is too narrow (``_ContentSizedTable.RESPONSIVE_TIERS``): the bounds (Lo, Hi,
Bounds) first, then the error, then Fixed; the name and the value never. The
emtk editor declares the same priorities as ``collapse_order`` on its column
spec and emtk's data table applies them. Both renderers draw one lifetime fit
(one linked parameter) across a width sweep; the sequence of column sets each
passes through must be the same, narrowing and widening.
"""

from __future__ import annotations

import os
import types

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

#: The column sets the Qt table passes through as it narrows.
STAGES = [
    ("name", "value", "fixed", "bounds_lo", "bounds_hi", "bounds_on", "error"),
    ("name", "value", "fixed", "error"),
    ("name", "value", "fixed"),
    ("name", "value"),
]
SWEEP = list(range(900, 100, -20))
#: emtk column keys under the Qt column ids; the prior goes with the bounds and is not in Qt.
_EMTK_KEY = {"label": "name", "lo": "bounds_lo", "hi": "bounds_hi"}


@pytest.fixture(scope="module")
def params():
    from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

    t = np.arange(1024) * 0.032
    irf = 1e4 * np.exp(-0.5 * ((t - 2) / 0.1) ** 2)
    decay = np.convolve(irf, 0.5 * np.exp(-t / 1.0) + 0.5 * np.exp(-t / 4.0))[:1024] * 0.01 + 5
    fit = build_lifetime_fit(decay, bin_width=0.032, irf=irf, n_components=2)
    by_name = {p.name: p for p in fit.model.parameters_all}
    chosen = [by_name[n] for n in ("a0", "t0", "a1", "t1", "background", "timeshift")]
    by_name["a1"].link = by_name["a0"]
    for p, e in zip(chosen, (0.01, 0.023, 0.01, 0.15, 0.4, 0.002)):
        p.error_estimate = e
    return chosen


def _stages(sets: list) -> list:
    """The distinct column sets in the order they were seen."""
    out: list = []
    for s in sets:
        if not out or out[-1] != s:
            out.append(s)
    return out


def _qt_columns(params, widths) -> list:
    from qtpy import QtWidgets

    from chisurf.gui.autoform.sections.parameter_table import (
        COLUMN_IDS,
        ParameterGroupTableWidget,
    )

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget = ParameterGroupTableWidget(params, remote=False)
    widget.show()
    seen = []
    try:
        for w in widths:
            widget.resize(w, 260)
            app.processEvents()
            view = widget.table_view
            seen.append(tuple(c for i, c in enumerate(COLUMN_IDS) if not view.isColumnHidden(i)))
    finally:
        widget.close()
        widget.deleteLater()
        app.processEvents()
    return seen


def _emtk_columns(params, widths) -> list:
    from emtk import im
    from emtk.app import ImApp
    from emtk.testing import Driver

    from chisurf.emtk.model_editor import ModelEditor

    def entry(p):
        lo, hi = p.bounds
        return {
            "uid": p.name,
            "name": p.name,
            "label": p.name,
            "value": p.value,
            "fixed": p.fixed,
            "lo": lo,
            "hi": hi,
            "bounds_on": p.bounds_on,
            "error_estimate": p.error_estimate,
            "is_linked": bool(p.is_linked),
            "linked_to": p.link.name if p.is_linked else "",
        }

    editor = ModelEditor(types.SimpleNamespace(busy=False))
    editor.set_editor(
        "fit",
        {"sections": [{"type": "parameters", "key": "g", "rows": [entry(p) for p in params]}]},
    )
    seen = []
    for w in widths:

        def gui(w=w):
            im.begin("editor", (0, 0, w, 260))
            editor.draw()
            im.end()

        Driver(ImApp(gui), size=(w, 260)).frame(2)
        table = next(iter(editor.form.tables.values())).control
        keys = [_EMTK_KEY.get(c.key, c.key) for c in table.visible_columns()]
        seen.append(tuple(k for k in keys if k != "prior"))
    return seen


def test_both_tables_drop_bounds_then_error_then_fixed_and_restore_in_reverse(params):
    """One table per renderer, narrowed to name + value and widened again.

    Each walks the same stages in the same order: bounds, error, Fixed go; then
    Fixed, error, bounds come back.
    """
    widths = SWEEP + SWEEP[::-1]
    for name, seen in (
        ("qt", _qt_columns(params, widths)),
        ("emtk", _emtk_columns(params, widths)),
    ):
        assert _stages(seen) == STAGES + STAGES[-2::-1], (name, seen)


def test_the_emtk_column_declarations_carry_the_qt_priorities():
    """The prior (emtk only) 1, bounds 2, error 3, fixed 4; name and value never.

    The prior goes first, on its own: tied with the bounds, the emtk-only column made the
    bounds drop at a width where the Qt table still shows them (474 px, the Qt left dock).
    """
    from chisurf.emtk.model_editor import PARAMETER_COLUMNS, _paired
    from chisurf.emtk.model_sections import GLOBAL_COLUMNS

    order = {c["key"]: c.get("collapse_order", 0) for c in PARAMETER_COLUMNS}
    assert order == {
        "label": 0,
        "value": 0,
        "fixed": 4,
        "lo": 2,
        "hi": 2,
        "bounds_on": 2,
        "error": 3,
        "prior": 1,
    }
    entries = [
        {"uid": f"p{i}", "name": f"p{i}", "value": 1.0, "lo": 0.0, "hi": 2.0} for i in range(4)
    ]
    _rows, columns = _paired(entries, 2, {"key": "lifetimes"})
    paired = {c["key"]: c.get("collapse_order", 0) for c in columns}
    assert paired["index"] == paired["value0"] == paired["value1"] == 0
    assert paired["lo1"] == paired["bounds_on0"] == 2
    assert paired["error1"] == 3 and paired["fixed0"] == 4
    glob = {c["key"]: c.get("collapse_order", 0) for c in GLOBAL_COLUMNS}
    assert glob["lo"] == glob["hi"] == glob["bounds_on"] == 1
    assert glob["error"] == 2 and glob["link_row"] == glob["row"] == 3 and glob["fixed"] == 4
    assert glob["owner"] == glob["label"] == glob["value"] == 0


def test_at_the_qt_docks_width_both_tables_show_the_bounds(params):
    """474 px is the Qt window's left dock at 1440 x 900 (and a third of the emtk shell):
    both tables still show Lo / Hi / Bounds there (final shell parity pass, 2026-10-14)."""
    for name, seen in (("qt", _qt_columns(params, [474])), ("emtk", _emtk_columns(params, [460]))):
        assert "bounds_lo" in seen[0] and "bounds_on" in seen[0], (name, seen)
