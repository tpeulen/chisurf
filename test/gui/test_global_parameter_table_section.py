"""Tests for the ``global_parameter_table`` AutoForm section.

Covers registration, enumeration of out-of-fit (registered) parameter groups,
UUID-addressed edit routing, and row-number linking. Uses a fake mutator so no
RPC server is needed.
"""

import pathlib

import utils

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.fitting.parameter as fp
import chisurf.core.models  # noqa: F401
import chisurf.core.parameter  # noqa: F401  (initialises settings)
from chisurf.core.registry import parameter_groups as reg


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
        COL_VALUE,
        GlobalParameterTableWidget,
    )

    _clear_registry()
    g = _group(["tau"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        mut = FakeMutator()
        w = GlobalParameterTableWidget(mutator=mut)
        qtbot.addWidget(w)
        # Find the row for 'tau'.
        r = next(i for i in range(w._model.rowCount()) if w._model.row_at(i).param.name == "tau")
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
        COL_LINK,
        GlobalParameterTableWidget,
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


def test_link_row_numbers_survive_sort_and_filter(qapp, qtbot):
    """Row numbers stay source-relative when the table is sorted and filtered.

    The Link column addresses parameters by row number, so the table gained its
    filtering and sorting in a proxy layer *above* the model rather than by
    reordering the model. This pins that: with both active, the displayed row
    numbers and a link written through them must still hit the right parameters.
    """
    from qtpy import QtCore

    from chisurf.gui.autoform.sections.global_parameter_table import (
        COL_LINK,
        COL_OWNER,
        COL_ROW,
        GlobalParameterTableWidget,
    )
    from chisurf.gui.widgets.chitable import ColumnFilter, FilterSpec

    _clear_registry()
    g = _group(["follower", "master", "spectator"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        mut = FakeMutator()
        w = GlobalParameterTableWidget(mutator=mut)
        qtbot.addWidget(w)

        # Sort descending by Parameter name and keep only the plugin's rows.
        w.table_view.sortByColumn(COL_ROW, QtCore.Qt.DescendingOrder)
        w.table.set_filter(
            FilterSpec(columns=(ColumnFilter(column=COL_OWNER, op="contains", value="Plugin X"),))
        )
        assert w.table.visible_row_count() == 3

        proxy = w.table.proxy
        assert proxy is not None
        # Every visible cell's Row number must equal its source row + 1.
        for view_row in range(proxy.rowCount()):
            shown = proxy.data(proxy.index(view_row, COL_ROW), QtCore.Qt.DisplayRole)
            src_row = proxy.mapToSource(proxy.index(view_row, COL_ROW)).row()
            assert int(shown) == src_row + 1

        rows = {w.table_model.row_at(i).param.name: i for i in range(w.table_model.rowCount())}
        idx = w.table_model.index(rows["follower"], COL_LINK)
        assert w.table_model.setData(idx, str(rows["master"] + 1), QtCore.Qt.EditRole)
        _, src, target = next(c for c in mut.calls if c[0] == "link")
        assert src.param.name == "follower"
        assert target.param.name == "master"
    finally:
        _clear_registry()


def test_table_exposes_chitable_accessors(qapp, qtbot):
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableModel,
        GlobalParameterTableWidget,
    )
    from chisurf.gui.widgets.chitable import ChiTableWidget

    _clear_registry()
    g = _group(["tau"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        w = GlobalParameterTableWidget(mutator=FakeMutator())
        qtbot.addWidget(w)
        assert isinstance(w.table, ChiTableWidget)
        assert isinstance(w.table_model, GlobalParameterTableModel)
        # table_model must be the source model, not the filter proxy.
        assert w.table_model is w.table.proxy.sourceModel()
        assert w.table_view is w.table.table_view
    finally:
        _clear_registry()


def test_search_narrows_the_global_table(qapp, qtbot):
    from chisurf.gui.autoform.sections.global_parameter_table import (
        GlobalParameterTableWidget,
    )

    _clear_registry()
    g = _group(["tau", "amplitude"])
    reg.register_parameter_group(g, owner_id="plugin_x", label="Plugin X")
    try:
        w = GlobalParameterTableWidget(mutator=FakeMutator())
        qtbot.addWidget(w)
        total = w.table.total_row_count()
        w.table.set_search_text("amplitude")
        assert w.table.visible_row_count() == 1
        w.table.set_search_text("")
        assert w.table.visible_row_count() == total
    finally:
        _clear_registry()
