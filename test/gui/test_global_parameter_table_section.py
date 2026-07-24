"""Tests for the ``global_parameter_table`` AutoForm section.

Covers registration, enumeration of out-of-fit (registered) parameter groups,
UUID-addressed edit routing, and row-number linking. Uses a fake mutator so no
RPC server is needed.
"""

import pathlib

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.parameter  # noqa: F401  (initialises settings)
import chisurf.core.models  # noqa: F401
import chisurf.core.fitting.parameter as fp
from chisurf.core import parameter_group_registry as reg


def _group(names):
    g = fp.FittingParameterGroup()
    for n in names:
        setattr(g, "_" + n, fp.FittingParameter(value=1.0, name=n))
    g.find_parameters()
    return g


class FakeMutator:
    """Records mutator calls and reports success."""

    def __init__(self):
        self.calls = []

    def set_value(self, row, value):
        self.calls.append(("set_value", row, value))
        row.param.value = value
        return {"ok": True}

    def set_fixed(self, row, fixed):
        self.calls.append(("set_fixed", row, fixed))
        row.param.fixed = fixed
        return {"ok": True}

    def set_bounds(self, row, bounds):
        self.calls.append(("set_bounds", row, bounds))
        return {"ok": True}

    def set_bounds_on(self, row, bounds_on):
        self.calls.append(("set_bounds_on", row, bounds_on))
        return {"ok": True}

    def link(self, src, target):
        self.calls.append(("link", src, target))
        src.param.link = target.param
        return {"ok": True}

    def unlink(self, row):
        self.calls.append(("unlink", row))
        row.param.link = None
        return {"ok": True}


def _clear_registry():
    for owner_id, _label, _g in list(reg.iter_registered_parameter_groups()):
        reg.unregister_parameter_group(owner_id)


def test_registered():
    import chisurf.gui.autoform.sections  # noqa: F401  (populates registry)
    from chisurf.gui.autoform.sections import get_section_factory

    assert get_section_factory("global_parameter_table") is not None


def test_enumerates_registered_group(qapp, qtbot):
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableWidget,
    )

    _clear_registry()
    g = _group(["tau", "amp"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        w = GlobalParameterTableWidget(mutator=FakeMutator())
        qtbot.addWidget(w)
        rows = [w._model.row_at(i) for i in range(w._model.rowCount())]
        group_rows = [r for r in rows if r.owner_label == "Plugin X"]
        assert len(group_rows) == 2
        assert {r.param.name for r in group_rows} == {"tau", "amp"}
        assert all(r.kind == "group" and r.param_uid for r in group_rows)
    finally:
        _clear_registry()


def test_edit_value_routes_by_uid(qapp, qtbot):
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableWidget,
        COL_VALUE,
    )

    _clear_registry()
    g = _group(["tau"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        mut = FakeMutator()
        w = GlobalParameterTableWidget(mutator=mut)
        qtbot.addWidget(w)
        # Find the row for 'tau'.
        r = next(
            i for i in range(w._model.rowCount())
            if w._model.row_at(i).param.name == "tau"
        )
        idx = w._model.index(r, COL_VALUE)
        assert w._model.setData(idx, 4.2, QtCore.Qt.EditRole)
        assert any(c[0] == "set_value" for c in mut.calls)
        row = next(c[1] for c in mut.calls if c[0] == "set_value")
        assert row.kind == "group"
        assert row.param_uid == g.parameters_all_dict["tau"].unique_identifier
    finally:
        _clear_registry()


def test_link_by_row_number(qapp, qtbot):
    from qtpy import QtCore
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableWidget,
        COL_LINK,
    )

    _clear_registry()
    g = _group(["follower", "master"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        mut = FakeMutator()
        w = GlobalParameterTableWidget(mutator=mut)
        qtbot.addWidget(w)
        rows = {w._model.row_at(i).param.name: i for i in range(w._model.rowCount())}
        follower_row = rows["follower"]
        master_row = rows["master"]
        idx = w._model.index(follower_row, COL_LINK)
        # Link the follower to the master's (1-based) row number.
        assert w._model.setData(idx, str(master_row + 1), QtCore.Qt.EditRole)
        assert any(c[0] == "link" for c in mut.calls)
        _, src, target = next(c for c in mut.calls if c[0] == "link")
        assert src.param.name == "follower"
        assert target.param.name == "master"
    finally:
        _clear_registry()
