"""The Global View's model and surface: what is drawn, and what a gesture does.

No Qt. The window is a Qt-free model drawn by an emtk surface, so what it
claims -- which way a link points, what the factor graph says is shared, which
cells may be typed into -- is asserted here, not looked at.
"""

from __future__ import annotations

import pytest

emtk = pytest.importorskip("emtk")

import chisurf.core.fitting.parameter as fp  # noqa: E402
import chisurf.core.models  # noqa: E402,F401
import chisurf.core.parameter  # noqa: E402,F401
from chisurf.plugins.core.globalview.gui import emtk_view as ev  # noqa: E402
from chisurf.plugins.core.globalview.gui.model import GlobalViewModel  # noqa: E402


def _group(names, fixed=()):
    group = fp.FittingParameterGroup()
    for name in names:
        setattr(group, "_" + name, fp.FittingParameter(value=1.0, name=name, fixed=name in fixed))
    group.find_parameters()
    return group


class _Fit:
    def __init__(self, model, name):
        self.model = model
        self.name = name
        self.unique_identifier = model.unique_identifier


class _Mutator:
    """Applies what the fitting client would, and records it."""

    def __init__(self):
        self.calls = []

    def link(self, follower, master):
        self.calls.append(("link", follower.param, master.param))
        follower.param.link = master.param
        return {"ok": True}

    def unlink(self, row):
        self.calls.append(("unlink", row.param))
        row.param.link = None
        return {"ok": True}

    def set_value(self, row, value):
        self.calls.append(("value", row.param, value))
        row.param.value = value
        return {"ok": True}

    def set_fixed(self, row, fixed):
        row.param.fixed = fixed
        return {"ok": True}


def _session(n=3):
    """*n* fits of ``c + a x²``: ``a`` shared through links, ``c`` held in the last."""
    fits = [
        _Fit(_group(["a", "c"], fixed=("c",) if i == n - 1 else ()), f"dataset {i + 1}")
        for i in range(n)
    ]
    master = fits[0].model.parameters_all_dict["a"]
    for fit in fits[1:]:
        fit.model.parameters_all_dict["a"].link = master
    mutator = _Mutator()
    model = GlobalViewModel(fits=lambda: fits, groups=lambda: [], mutator=mutator)
    return model, fits, mutator


def _param_id(param):
    return f"param:{param.unique_identifier}"


def _edges(model, kind):
    return [(e.source, e.target) for e in model.control.document.edges if e.config["kind"] == kind]


def test_a_link_arrow_runs_from_the_follower_to_its_master():
    model, fits, _ = _session()
    master = fits[0].model.parameters_all_dict["a"]
    links = _edges(model, "link")
    assert len(links) == 2, "one arrow per link, not one per same-named parameter"
    assert all(target == _param_id(master) for _source, target in links)


def test_a_link_drawn_from_a_to_b_makes_a_follow_b():
    """The arrow the user drew is the arrow that stays -- the old host reversed it."""
    model, fits, mutator = _session(2)
    a0 = fits[0].model.parameters_all_dict["c"]
    a1 = fits[1].model.parameters_all_dict["c"]
    fits[1].model.parameters_all_dict["c"].fixed = False
    model.rebuild(force=True)
    model._on_graph_link(_param_id(a1), _param_id(a0))
    assert a1.link is a0 and a0.link is None


def test_breaking_an_arrow_unlinks_its_follower():
    """The old host passed the master, so a broken arrow stayed linked."""
    model, fits, _ = _session(2)
    follower = fits[1].model.parameters_all_dict["a"]
    master = fits[0].model.parameters_all_dict["a"]
    model._on_graph_unlink(_param_id(follower), _param_id(master))
    assert follower.link is None


def test_a_cycle_is_refused_and_said():
    model, fits, _ = _session(2)
    warned = []
    model.warn = lambda title, message: warned.append(message)
    master = fits[0].model.parameters_all_dict["a"]
    follower = fits[1].model.parameters_all_dict["a"]
    model._on_graph_link(_param_id(master), _param_id(follower))
    assert master.link is None and warned and "cycle" in warned[0]


def test_hiding_fixed_parameters_hides_their_edges_too():
    model, fits, _ = _session()
    held = _param_id(fits[2].model.parameters_all_dict["c"])
    ids = {n.id for n in model.control.document.nodes}
    assert held not in ids
    assert all(held not in edge for edge in _edges(model, "ownership"))
    model.include_fixed = True
    model.relayout()
    assert held in {n.id for n in model.control.document.nodes}


def test_the_factor_graph_resolves_links_into_one_shared_variable():
    model, fits, _ = _session()
    model.representation = "factor graph"
    model.relayout()
    kinds = {n.id: n.config["kind"] for n in model.control.document.nodes}
    master = _param_id(fits[0].model.parameters_all_dict["a"])
    assert kinds[master] == ev.NODE_SHARED
    assert sum(1 for k in kinds.values() if k == ev.NODE_FACTOR) == 3
    # Every likelihood reads the master, never a follower.
    assert sorted(s for s, t in _edges(model, "scope") if t == master) == [
        "owner:0",
        "owner:1",
        "owner:2",
    ]
    assert "1 shared (a)" in model.status and "1 independent block" in model.status


def test_unlinked_datasets_are_independent_blocks():
    model, fits, _ = _session()
    for fit in fits[1:]:
        fit.model.parameters_all_dict["a"].link = None
    model.representation = "factor graph"
    model.relayout()
    assert "0 shared" in model.status and "3 independent blocks" in model.status


def test_the_first_selected_is_the_master_and_link_makes_the_second_follow():
    model, fits, _ = _session(2)
    fits[1].model.parameters_all_dict["a"].link = None
    fits[1].model.parameters_all_dict["c"].fixed = False
    model.rebuild(force=True)
    first = _param_id(fits[0].model.parameters_all_dict["c"])
    second = _param_id(fits[1].model.parameters_all_dict["c"])
    model.selection = [first, second]
    assert [r["role"] for r in model.selection_records()] == ["master", "free"]
    model.link_selected()
    assert fits[1].model.parameters_all_dict["c"].link is fits[0].model.parameters_all_dict["c"]


def test_a_followers_value_cannot_be_typed_and_a_bound_only_while_on():
    model, _fits, _ = _session(2)
    records = {(r["owner"], r["parameter"]): r for r in model.parameter_records()}
    follower = records[("dataset 2", "a")]
    free = records[("dataset 1", "a")]
    assert not model.may_edit_parameter(follower, "value")
    assert model.may_edit_parameter(free, "value")
    assert not model.may_edit_parameter(free, "lo")
    assert model.may_edit_parameter(dict(free, bounded=True), "lo")


def test_the_link_row_column_links_and_unlinks():
    model, fits, mutator = _session(2)
    records = {(r["owner"], r["parameter"]): r for r in model.parameter_records()}
    follower = records[("dataset 2", "a")]
    assert follower["link"] == str(records[("dataset 1", "a")]["row"])
    model.edit_parameter(follower, "link", "")
    assert fits[1].model.parameters_all_dict["a"].link is None
    model.edit_parameter(follower, "link", str(records[("dataset 1", "a")]["row"]))
    assert fits[1].model.parameters_all_dict["a"].link is fits[0].model.parameters_all_dict["a"]


def test_a_value_change_does_not_lay_the_network_out_again():
    model, fits, _ = _session()
    document = model.control.document
    fits[0].model.parameters_all_dict["a"].value = 7.0
    model.fits_changed()
    assert model.control.document is document, "a value moved every node"
    record = next(
        r for r in model.parameter_records() if (r["owner"], r["parameter"]) == ("dataset 1", "a")
    )
    assert record["value"] == 7.0


def test_with_auto_off_the_status_says_the_picture_is_stale():
    model, fits, _ = _session()
    model.auto_refresh = False
    model.fits_changed()
    assert "Refresh" in model.status
    model.auto_refresh = True
    model.auto_refresh_changed()
    assert "Refresh" not in model.status


def test_the_size_setting_scales_every_mark_but_keeps_their_ratio():
    model, _fits, _ = _session()
    owner = next(n for n in model.control.document.nodes if n.id.startswith("owner:"))
    param = next(n for n in model.control.document.nodes if n.id.startswith("param:"))
    before = (model.content.node_shape(owner)[2], model.content.node_shape(param)[2])
    model.node_size = 26.0
    model.apply_node_size()
    after = (model.content.node_shape(owner)[2], model.content.node_shape(param)[2])
    assert after[0] > before[0]
    assert after[0] / after[1] == pytest.approx(before[0] / before[1])


def test_a_factor_is_a_square_and_a_parameter_a_disc():
    from emtk import nodes

    model, _fits, _ = _session()
    model.representation = "factor graph"
    model.relayout()
    shapes = {
        n.config["kind"]: model.content.node_shape(n)[0] for n in model.control.document.nodes
    }
    assert shapes[ev.NODE_FACTOR] == nodes.NodeShape.SQUARE
    assert shapes[ev.NODE_SHARED] == nodes.NodeShape.DISC


def test_a_fit_cannot_be_linked_to_anything():
    model, _fits, _ = _session()
    owner = next(n for n in model.control.document.nodes if n.id.startswith("owner:"))
    param = next(n for n in model.control.document.nodes if n.id.startswith("param:"))
    assert not model.content.accepts_link(owner, param)
    assert model.content.accepts_link(param, param)


def test_the_surface_draws_every_declared_control_with_no_display():
    from emtk.testing import RecordingPainter

    from chisurf.plugins.core.globalview.gui.surface import GlobalViewSurface

    model, _fits, _ = _session()
    surface = GlobalViewSurface(model)
    for _ in range(2):
        painter = RecordingPainter()
        surface.draw(painter, 0.0, 0.0, 1100.0, 760.0)
    for name in (
        "load_network",
        "save_network",
        "refresh",
        "auto_refresh",
        "link_selected",
        "unlink_selected",
        "unlink_all",
        "fit_view",
        "show_guide",
        "show_help",
    ):
        assert surface.rect_of(name) is not None, f"{name} was not drawn"
    assert model.status in painter.strings
    for dock in ("Parameters", "View"):
        surface.docks.focus(dock)
    surface.draw(RecordingPainter(), 0.0, 0.0, 1100.0, 760.0)
    for name in (
        "parameter_records",
        "representation",
        "graph_layout",
        "node_size",
        "graph_scale",
        "connect_owners",
        "include_fixed",
        "shade_values",
        "export_parameters",
    ):
        assert surface.rect_of(name) is not None, f"{name} was not drawn"


def test_columns_that_say_nothing_are_not_shown():
    """One fit: no Owner column; no fit groups: no Local; nothing fitted: no Error."""

    def shown(model):
        return [c["key"] for c in model.parameter_columns() if c.get("visible", True)]

    model, _fits, _ = _session(1)
    assert {"owner", "local", "error"}.isdisjoint(shown(model))
    assert {"row", "parameter", "value", "fixed", "lo", "hi", "link"} <= set(shown(model))
    model, _fits, _ = _session(3)
    assert "owner" in shown(model)


def test_a_vector_published_by_population_is_one_expandable_row():
    """``gamma[HF]``, ``gamma[LF]`` are filed under ``gamma``; the table opens it."""
    group = _group(["gamma", "gamma[HF]", "gamma[LF]", "Bg"])
    model = GlobalViewModel(
        fits=lambda: [], groups=lambda: [("ndx", "ndX constants", group)], mutator=_Mutator()
    )
    model.refresh()
    records = {r["parameter"]: r for r in model.parameter_records()}
    parent = records["gamma"]["uid"]
    assert records["gamma[HF]"]["parent"] == parent == records["gamma[LF]"]["parent"]
    assert records["gamma"]["parent"] == "" and records["Bg"]["parent"] == ""
    model.expanded_vectors.add(parent)
    from emtk.pil_painter import PilPainter

    from chisurf.plugins.core.globalview.gui.surface import GlobalViewSurface

    surface = GlobalViewSurface(model)
    surface.docks.focus("Parameters")
    for _ in range(3):
        painter = PilPainter(1100, 760)
        surface.draw(painter, 0.0, 0.0, 1100.0, 760.0)
    import os

    if os.environ.get("CHISURF_TABLE_SHOTS"):
        painter.frame.save(os.path.join(os.environ["CHISURF_TABLE_SHOTS"], "globalview.png"))
