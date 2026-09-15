"""The Global View parameter network: what it draws, and what a gesture does.

The graph used to be a ``pyqtgraph.GraphItem`` whose nodes were sized in data
coordinates; it is now painted directly on the shared node-link canvas
(:mod:`chisurf.gui.widgets.graph_canvas`). These tests cover the parts that were
silently wrong before and would be silently wrong again: which way a link arrow
points, whether an edge survives a node being filtered out, and whether the
gestures reach the fitting layer at all.
"""
from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import utils  # noqa: E402

TOPDIR = pathlib.Path(__file__).parent.parent
utils.set_search_paths(TOPDIR)

import chisurf.core.fitting.parameter as fp  # noqa: E402
import chisurf.core.models  # noqa: E402
from chisurf.plugins.core.globalview.api.graph import build_graph  # noqa: E402


def _group(names):
    group = fp.FittingParameterGroup()
    for name in names:
        setattr(group, "_" + name, fp.FittingParameter(value=1.0, name=name))
    group.find_parameters()
    return group


class _Fit:
    def __init__(self, model, name="Fit"):
        self.model = model
        self.name = name
        self.unique_identifier = model.unique_identifier


# ── the builder ──────────────────────────────────────────────────────


def test_a_link_makes_exactly_one_edge():
    """Three fits with a ``tau`` each: one link is one edge, not three.

    The master used to be looked up by *name*, so a follower drew an edge to
    every same-named parameter in the session — with three fits of one model
    that is three arrows out of one link, two of them fiction.
    """
    models = [_group(["tau"]) for _ in range(3)]
    models[1].parameters_all_dict["tau"].link = models[0].parameters_all_dict["tau"]
    fits = [_Fit(m, f"Fit {i}") for i, m in enumerate(models)]

    result = build_graph(fit_list=fits)
    params = {n.node_idx for n in result.nodes if n.node_type == "parameter"}
    links = [e for e in result.edges if e.source in params and e.target in params]
    assert len(links) == 1


def test_the_link_edge_points_from_follower_to_master():
    """Direction is the whole meaning of the arrow, so it is asserted."""
    a, b = _group(["tau"]), _group(["tau"])
    b.parameters_all_dict["tau"].link = a.parameters_all_dict["tau"]
    result = build_graph(fit_list=[_Fit(a, "A"), _Fit(b, "B")])

    by_idx = {n.node_idx: n for n in result.nodes}
    params = {i for i, n in by_idx.items() if n.node_type == "parameter"}
    edge = next(e for e in result.edges if e.source in params and e.target in params)
    assert by_idx[edge.source].is_linked          # follower
    assert not by_idx[edge.target].is_linked      # master


# ── the canvas ───────────────────────────────────────────────────────


@pytest.fixture
def canvas(qapp):
    from chisurf.plugins.core.globalview.gui.graph_canvas import ParameterGraphCanvas

    widget = ParameterGraphCanvas()
    widget.resize(600, 400)
    return widget


def _simple_graph(canvas):
    """One fit with two parameters, the second following the first."""
    from chisurf.plugins.core.globalview.gui import graph_canvas as gcv

    canvas.set_graph(
        positions=[(0.0, 0.0), (-1.0, 1.0), (1.0, 1.0)],
        edges=[(1, 0), (2, 0), (2, 1)],
        names=["Fit A", "tau", "tau"],
        kinds=[gcv.NODE_FIT, gcv.NODE_PARAM_FREE, gcv.NODE_PARAM_LINKED],
    )


def test_the_canvas_separates_ownership_from_links(canvas):
    """Only parameter→parameter edges are links; the rest is scaffolding."""
    _simple_graph(canvas)
    assert canvas._link_edges == [(2, 1)]
    assert sorted(canvas._owner_edges) == [(1, 0), (2, 0)]
    # The fit owns both parameters, so dragging it moves them.
    assert sorted(canvas._owned[0]) == [1, 2]


def test_dropping_a_parameter_on_another_asks_for_a_link(canvas, qapp):
    """The drag gesture reaches the tool as ``linkRequested(follower, master)``."""
    from qtpy import QtCore, QtGui

    _simple_graph(canvas)
    canvas.show()
    qapp.processEvents()

    seen = []
    canvas.linkRequested.connect(lambda a, b: seen.append((a, b)))

    def _press(kind, node, buttons=QtCore.Qt.LeftButton):
        pos = canvas.view.transform().map(canvas._pos[node])
        return QtGui.QMouseEvent(
            kind, QtCore.QPointF(pos), QtCore.Qt.LeftButton, buttons,
            QtCore.Qt.NoModifier,
        )

    canvas.mousePressEvent(_press(QtCore.QEvent.MouseButtonPress, 1))
    canvas.mouseMoveEvent(_press(QtCore.QEvent.MouseMove, 2))
    canvas.mouseReleaseEvent(_press(QtCore.QEvent.MouseButtonRelease, 2, QtCore.Qt.NoButton))

    assert seen == [(1, 2)]


def test_selecting_keeps_only_the_last_two(canvas):
    """Linking needs two nodes, so the oldest selection is dropped, in order."""
    _simple_graph(canvas)
    seen = []
    canvas.selectionChanged.connect(seen.append)
    canvas._select(1)
    canvas._select(2)
    canvas._select(0)
    assert canvas.selected_nodes_idx == [2, 0]
    assert seen[-1] == [2, 0]


def test_a_resize_refits_the_graph_until_the_user_moves_something(canvas, qapp):
    """The layout is fitted to the panel — but a hand arrangement is kept.

    ``set_graph`` runs before the widget has its real size, so without the
    re-fit the network stays clumped in the corner of whatever panel it lands
    in. Once the user drags a node, re-fitting would throw their work away.
    """
    _simple_graph(canvas)
    canvas.show()
    canvas.resize(1200, 800)
    qapp.processEvents()
    wide = max(p.x() for p in canvas._pos.values())
    assert wide > 600         # the graph grew into the wider panel

    frozen = {k: (v.x(), v.y()) for k, v in canvas._pos.items()}
    canvas._user_moved = True
    canvas.resize(600, 400)
    qapp.processEvents()
    assert {k: (v.x(), v.y()) for k, v in canvas._pos.items()} == frozen

    canvas.refit()            # …until asked for it explicitly
    assert max(p.x() for p in canvas._pos.values()) < wide


# ── the window ───────────────────────────────────────────────────────


@pytest.fixture
def tool(qapp, monkeypatch, tmp_path):
    from qtpy import QtCore

    monkeypatch.setattr(
        QtCore.QSettings, "value", lambda self, *a, **k: None, raising=False
    )
    from chisurf.plugins.core.globalview.gui import GraphWizard

    a, b = _group(["tau", "bg"]), _group(["tau", "bg"])
    b.parameters_all_dict["tau"].link = a.parameters_all_dict["tau"]
    window = GraphWizard(
        fit_list=[_Fit(a, "Decay A"), _Fit(b, "Decay B")], include_fixed=True
    )
    yield window
    window.close()


def test_the_window_is_built_from_dock_panels(tool):
    """Four docks, not a tab strip over a stack of group boxes."""
    from chisurf.gui.widgets.dock_area import DockArea

    assert isinstance(tool.dock_area, DockArea)
    names = {tool.dock_area.tabText(i) for i in range(tool.dock_area.count())}
    assert len(names) == 4
    assert any("Network" in n for n in names)
    assert any("Parameters" in n for n in names)
    assert any("Selection" in n for n in names)
    assert any("View" in n for n in names)


def test_edges_are_reindexed_when_a_node_is_filtered_out(tool):
    """Hiding fixed parameters must not shift an edge onto the wrong node.

    The canvas indexes nodes by position in the arrays it is handed; the graph
    names them by node id. The two diverge the moment ``include_fixed`` drops a
    node, and an un-reindexed edge then joins two unrelated parameters.
    """
    canvas = tool.graph_widget
    names = tool.node_data["names"]
    for a, b in canvas._link_edges:
        assert names[a] == "tau" and names[b] == "tau"

    tool._check_include_fixed.setChecked(False)
    names = tool.node_data["names"]
    for a, b in canvas._link_edges:
        assert names[a] == "tau" and names[b] == "tau"


def test_every_parameter_editor_says_which_fit_it_belongs_to(tool, qapp):
    """Two fits of one model name their parameters identically."""
    from qtpy import QtWidgets

    taus = [i for i, n in enumerate(tool.node_data["names"]) if n == "tau"]
    for i in taus[:2]:
        tool.graph_widget._select(i)
    qapp.processEvents()

    captions = [
        tool.parameter_layout.itemAt(i).widget().text()
        for i in range(tool.parameter_layout.count())
        if isinstance(tool.parameter_layout.itemAt(i).widget(), QtWidgets.QLabel)
    ]
    assert any("Decay A" in c for c in captions)
    assert any("Decay B" in c for c in captions)


def test_the_toolbar_carries_help_and_a_guide(tool):
    """A ``?`` and a **Guide**, from the shipped ``help.md`` / ``guide.json``."""
    assert getattr(tool, "_help_button", None) is not None
    assert getattr(tool, "_guide_button", None) is not None


def test_every_guide_step_points_at_a_real_widget(tool):
    """A step whose target does not resolve is shown centred, teaching nothing.

    The shared seam test only checks the two target kinds that must name a view
    spec; these steps address dock tabs and toolbar actions, which only a live
    window can resolve.
    """
    import pathlib as _pathlib

    from chisurf.gui.widgets.tools.guided_tour import GuidedTour, load_tour
    from chisurf.plugins.core.globalview.gui import tool as tool_module

    guide = _pathlib.Path(tool_module.__file__).parent / "guide.json"
    steps = load_tour(guide)
    assert steps, "the plugin must ship a guided tour"

    tour = GuidedTour(tool, steps)
    unresolved = [s.title for s in steps if tour.resolve_target(s.target) is None]
    assert not unresolved, unresolved


# ── refreshing ───────────────────────────────────────────────────────


def test_a_value_change_does_not_relayout_the_network(tool, monkeypatch):
    """A running fit emits an event per iteration; none of them move a node.

    The layout algorithm is the expensive part, so it must only run when the
    network's *shape* changed — a parameter appearing, disappearing, or becoming
    fixed/linked/free. Without this the tool re-laid-out the whole graph
    hundreds of times during one fit.
    """
    calls = []
    original = tool.get_node_positions
    monkeypatch.setattr(
        tool, "get_node_positions",
        lambda *a, **k: (calls.append(1), original(*a, **k))[1],
    )

    tool.recompute_graph(force=False)
    assert calls == []                       # nothing changed: nothing laid out

    tool.recompute_graph(force=True)
    assert len(calls) == 1                   # the user asked: always redraw

    # A structural change — a new link — does redraw on its own. Made on the
    # parameters directly, so nothing but the shape of the graph differs.
    calls.clear()
    tool.fit_list[1].model.parameters_all_dict["bg"].link = (
        tool.fit_list[0].model.parameters_all_dict["bg"]
    )
    tool.recompute_graph(force=False)
    assert len(calls) == 1


def test_change_events_are_coalesced_rather_than_answered_one_by_one(tool):
    """Twenty events in a row schedule one wake-up, not twenty rebuilds."""
    rebuilds = []
    tool._refresh_timer.timeout.connect(lambda: rebuilds.append(1))
    for _ in range(20):
        tool._on_change_event()
    assert tool._refresh_timer.isActive()
    assert rebuilds == []                    # nothing has run yet


def test_with_auto_off_the_status_bar_says_the_picture_is_stale(tool):
    """Turning the automatic refresh off must not silently show old data."""
    tool._check_auto.setChecked(False)
    tool._on_change_event()
    assert tool._stale
    assert not tool._refresh_timer.isActive()
    assert "Refresh" in tool.statusBar().currentMessage()


def test_a_layout_is_not_remembered_before_the_window_has_a_size(tool, monkeypatch):
    """``layoutChanged`` fires mid-construction, when every split reads 48/48.

    Persisting that would beat the authored default on the next launch, and the
    tool would come up half controls forever without anyone dragging anything.
    """
    saved = []
    monkeypatch.setattr(
        type(tool._dock_settings()), "setValue",
        lambda self, key, value: saved.append(key), raising=False,
    )
    tool._layout_ready = False
    tool._save_dock_layout()
    assert saved == []


# ── connect base ─────────────────────────────────────────────────────


def test_connect_base_joins_plugin_groups_to_the_fits():
    """Not just fits: a registered group is an owner and joins the same web.

    It used to connect ``node_type == "fit"`` only, which left a plugin's
    working model floating apart from the fits it exists to be linked against —
    the one relation the option is for.
    """
    from chisurf.core.registry.parameter_groups import (
        register_parameter_group,
        unregister_parameter_group,
    )

    plugin = _group(["E"])
    register_parameter_group(plugin, owner_id="test_owner", label="Plugin")
    try:
        result = build_graph(
            fit_list=[_Fit(_group(["tau"]), "A"), _Fit(_group(["tau"]), "B")],
            connect_owners=True,
            group_list=[("test_owner", "Plugin", plugin)],
        )
        owners = {n.node_idx for n in result.nodes if n.node_type in ("fit", "group")}
        group_idx = next(n.node_idx for n in result.nodes if n.node_type == "group")
        owner_edges = [
            e for e in result.edges if e.source in owners and e.target in owners
        ]
        # 3 owners fully connected = 3 edges, and the group is in two of them.
        assert len(owner_edges) == 3
        assert sum(
            1 for e in owner_edges if group_idx in (e.source, e.target)
        ) == 2
    finally:
        unregister_parameter_group("test_owner")
