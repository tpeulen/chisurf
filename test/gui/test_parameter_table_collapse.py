"""The emtk parameter table drops whole column tiers for width, in its declared order.

The editor declares each column's priority as ``collapse_order`` on its column spec
(``PARAMETER_COLUMNS``): the prior first, then the bounds (Lo, Hi, Bounds), then the
error, then Fixed; the name and the value never (order 0). emtk's data table applies
them. The renderer draws one lifetime fit (one linked parameter) across a width sweep;
the sequence of column sets it passes through must be the tiers the declarations give,
narrowing and widening.
"""

from __future__ import annotations

import types

import numpy as np
import pytest

SWEEP = list(range(900, 100, -20))
#: Column keys under the names the assertions use; the prior has a tier of its own and is not
#: drawn for these parameters, so it is left out of the stages.
_EMTK_KEY = {"label": "name", "lo": "bounds_lo", "hi": "bounds_hi"}


def _declared_stages() -> list:
    """The column sets ``PARAMETER_COLUMNS`` gives as each ``collapse_order`` tier drops, widest first."""
    from chisurf.emtk.model_editor import PARAMETER_COLUMNS

    columns = [
        (_EMTK_KEY.get(c["key"], c["key"]), c.get("collapse_order", 0))
        for c in PARAMETER_COLUMNS
        if c["key"] != "prior"
    ]
    tiers = sorted({order for _key, order in columns if order})
    return [tuple(k for k, order in columns if not order or order > dropped) for dropped in [0, *tiers]]


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
    """The emtk table, narrowed to name + value and widened again.

    It walks the declared tiers: bounds, error, Fixed go; then Fixed, error, bounds come back.
    """
    stages = _declared_stages()
    assert stages[0][:2] == ("name", "value") and stages[-1] == ("name", "value")
    assert len(stages) == 4  # bounds, error, Fixed: three tiers below the full table
    widths = SWEEP + SWEEP[::-1]
    seen = _emtk_columns(params, widths)
    assert _stages(seen) == stages + stages[-2::-1], seen


def test_the_emtk_column_declarations_carry_the_priorities():
    """The prior (emtk only) 1, bounds 2, error 3, fixed 4; name and value never.

    The prior goes first, on its own: tied with the bounds, it made the bounds drop at a dock
    width (474 px) where there is room for them.
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


def test_at_the_shell_dock_width_the_table_shows_the_bounds(params):
    """460 px is a third of the emtk shell: the table still shows Lo / Hi / Bounds there."""
    ((name, seen),) = (("emtk", _emtk_columns(params, [460])),)
    assert "bounds_lo" in seen[0] and "bounds_on" in seen[0], (name, seen)
