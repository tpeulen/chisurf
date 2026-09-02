"""The parameter network as a node graph: kinds, edge kinds, and filtering.

No display and no Qt. The old canvas could only be checked by looking at it,
because everything it knew was in the paint method; here the graph is a
document, so what it claims can be asserted.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

cmtk = pytest.importorskip("cmtk")

from chisurf.gui.widgets.node_editor.cmtk_control import GraphControl  # noqa: E402
from chisurf.plugins.core.globalview.gui.cmtk_view import (  # noqa: E402
    EDGE_COLOURS,
    apply_network_style,
    KIND_COLOURS,
    NODE_FIT,
    NODE_GROUP,
    NODE_PARAM_FIXED,
    NODE_PARAM_FREE,
    NODE_PARAM_LINKED,
    GlobalViewContent,
    graph_result_to_document,
)


def _node(index: int, node_type: str, name: str, **overrides) -> SimpleNamespace:
    """Build one ``GraphNode``-shaped record, with the fields the adapter sets."""
    fields = dict(
        node_idx=index, node_type=node_type, name=name, fit_idx=0, value=None,
        fixed=False, is_linked=False, link_name="", link_uid="", fit_name="",
        data_filename="", model="", param_uid="", owner_uid="", owner_id="",
    )
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _result() -> SimpleNamespace:
    """Two fits, four parameters, and one link between them."""
    return SimpleNamespace(
        nodes=[
            _node(0, "fit", "Fit 1", fit_name="decay_a"),
            _node(1, "fit", "Fit 2", fit_name="decay_b"),
            _node(2, "parameter", "tau1", value=2.31),
            _node(3, "parameter", "tau2", value=4.02, fixed=True),
            _node(4, "parameter", "tau1", value=2.31, is_linked=True, link_name="tau1"),
            _node(5, "parameter", "x0", value=0.41),
        ],
        edges=[
            SimpleNamespace(source=0, target=2),
            SimpleNamespace(source=0, target=3),
            SimpleNamespace(source=1, target=4),
            SimpleNamespace(source=1, target=5),
            SimpleNamespace(source=4, target=2),   # follower -> master
            SimpleNamespace(source=0, target=1),   # base
        ],
    )


# ---------------------------------------------------------------------------
# What a node is
# ---------------------------------------------------------------------------


def test_every_node_kind_is_recognised():
    """Fits, groups and the three states a parameter can be in."""
    result = SimpleNamespace(
        nodes=[
            _node(0, "fit", "Fit"),
            _node(1, "group", "Group"),
            _node(2, "parameter", "held", fixed=True),
            _node(3, "parameter", "follows", is_linked=True),
            _node(4, "parameter", "free"),
        ],
        edges=[],
    )
    document = graph_result_to_document(result)
    kinds = [n.config["kind"] for n in document.nodes]
    assert kinds == [NODE_FIT, NODE_GROUP, NODE_PARAM_FIXED,
                     NODE_PARAM_LINKED, NODE_PARAM_FREE]


def test_each_kind_has_a_colour_of_its_own():
    """Five kinds, five colours: two that shared one would be unreadable."""
    assert len(set(KIND_COLOURS.values())) == len(KIND_COLOURS)


def test_a_node_keeps_the_index_it_came_with():
    """Ids are the adapter's ``node_idx``, so a selection resolves back.

    A second mapping from graph node to fit or parameter is a second thing to
    keep in step, and the one that drifts silently selects the wrong parameter.
    """
    document = graph_result_to_document(_result())
    assert [n.id for n in document.nodes] == ["0", "1", "2", "3", "4", "5"]


# ---------------------------------------------------------------------------
# What an edge claims
# ---------------------------------------------------------------------------


def test_the_three_edge_kinds_are_told_apart_by_their_endpoints():
    """Ownership, link and base, recovered from what the two ends *are*.

    The RPC reports only source and target. Deriving the kind from the
    endpoints means it cannot disagree with the graph, which a separately
    transmitted label could.
    """
    document = graph_result_to_document(_result())
    kinds = [e.config["kind"] for e in document.edges]
    assert kinds == ["ownership", "ownership", "ownership", "ownership",
                     "link", "base"]


def test_each_edge_kind_is_drawn_differently():
    """Three claims, three appearances.

    Drawing them alike is not a cosmetic loss: it is a claim the picture makes
    that the model does not.
    """
    assert len({colour for colour, _w, _a in EDGE_COLOURS.values()}) == 3
    content = GlobalViewContent()
    document = graph_result_to_document(_result())
    styles = {content.link_style(e) for e in document.edges}
    assert len(styles) == 3


def test_only_a_link_gets_an_arrowhead():
    """Direction is the information for a link and meaningless for the others.

    Ownership and base edges are symmetric statements about membership; a head
    on them says something untrue.
    """
    assert EDGE_COLOURS["link"][2] is True
    assert EDGE_COLOURS["ownership"][2] is False
    assert EDGE_COLOURS["base"][2] is False


def test_every_node_is_a_disc_and_owners_are_the_larger_ones():
    """Marks, not boxes -- and a network is read outward from its fits."""
    from cmtk import nodes as cmtk_nodes

    content = GlobalViewContent()
    document = graph_result_to_document(_result())
    for node in document.nodes:
        shape, label, radius = content.node_shape(node)
        assert shape == cmtk_nodes.NodeShape.DISC
        assert label == node.title
        assert radius is not None
    fit = next(n for n in document.nodes if n.config["kind"] == NODE_FIT)
    param = next(n for n in document.nodes if n.config["kind"] == NODE_PARAM_FREE)
    assert content.node_shape(fit)[2] > content.node_shape(param)[2]


def test_a_disc_label_is_drawn_once():
    """The disc labels itself, so the title bar must not run as well.

    Both drawing produces the name twice a few pixels apart in two different
    colours, which reads as a font-rendering artefact rather than as two
    draws -- so it survives a look at the screenshot.
    """
    from cmtk.testing import RecordingPainter

    document = graph_result_to_document(_result(), {
        0: (0.0, 0.0), 1: (0.0, 300.0), 2: (260.0, -120.0),
        3: (260.0, 40.0), 4: (260.0, 220.0), 5: (260.0, 360.0),
    })
    control = GraphControl(document, read_only=True, content=GlobalViewContent())
    apply_network_style(control.editor)
    control.set_document(document, fit=False)
    painter = RecordingPainter()
    control.draw(painter, 0, 0, 900, 520)

    assert sum(1 for call in painter.calls if call[0] == "text") == len(document.nodes)


def test_restyling_survives_loading_another_graph():
    """A caller's styling says what kind of graph this is, not which graph.

    Rebuilding the editor context on load dropped it, so the first graph
    looked right and every one after it silently reverted to the defaults.
    """
    document = graph_result_to_document(_result())
    control = GraphControl(document, read_only=True, content=GlobalViewContent())
    apply_network_style(control.editor)
    control.set_document(graph_result_to_document(_result()), fit=False)
    assert control.editor.style.link_routing == "arc"


def test_hiding_fixed_parameters_hides_their_edges_too():
    """A filtered-out node must not leave its edges running to nothing."""
    document = graph_result_to_document(_result(), include_fixed=False)
    assert "tau2" not in [n.title for n in document.nodes]
    for edge in document.edges:
        assert document.node(edge.source) is not None
        assert document.node(edge.target) is not None


def test_a_graph_with_no_layout_does_not_stack_every_node_at_the_origin():
    """A missing layout must be visible, not hidden behind one node.

    Every node at ``(0, 0)`` looks like a graph with one node in it; a column
    looks like what it is -- a layout that did not run.
    """
    document = graph_result_to_document(_result())
    positions = {n.pos for n in document.nodes}
    assert len(positions) == len(document.nodes)


# ---------------------------------------------------------------------------
# Drawing it
# ---------------------------------------------------------------------------


def test_the_network_draws_with_no_display():
    """Six nodes and six edges, through a painter that owns nothing."""
    from cmtk.testing import RecordingPainter

    document = graph_result_to_document(_result(), {
        0: (0.0, 0.0), 1: (0.0, 300.0), 2: (260.0, -120.0),
        3: (260.0, 40.0), 4: (260.0, 220.0), 5: (260.0, 360.0),
    })
    control = GraphControl(document, read_only=True, content=GlobalViewContent())
    control.set_document(document, fit=False)
    painter = RecordingPainter()
    control.draw(painter, 0, 0, 900, 520)
    assert painter.calls


def test_the_network_is_read_only():
    """The graph is a view of live fits, so it must not edit them here.

    A parameter's value is owned by the fitting model. Editing it in the
    network without going through that model's own setter is a second path
    into state that has one, and the two disagree the moment either is used.
    """
    from cmtk.testing import RecordingPainter

    document = graph_result_to_document(_result())
    control = GraphControl(document, read_only=True, content=GlobalViewContent())
    control.set_document(document, fit=False)
    control.draw(RecordingPainter(), 0, 0, 900, 520)

    before = document.node("2").config["value"]
    assert control._apply_interactions() is False
    assert document.node("2").config["value"] == before


def test_no_node_carries_a_port_label():
    """Every node has the same one input and output, so the labels are noise.

    Two rows per node saying "in [param]" and "out [param]" is a fifth of the
    height of a parameter node spent restating what the arrows already say.
    """
    content = GlobalViewContent()
    document = graph_result_to_document(_result())
    node = document.nodes[0]
    assert content.port_label(node, node.inputs[0], False) == ""
    assert content.port_label(node, node.outputs[0], True) == ""


def test_the_size_slider_scales_every_mark_but_keeps_their_ratio():
    """Owners stay larger than parameters at every slider position.

    Setting one absolute radius for every mark would flatten away the
    difference a network is read by.
    """
    content = GlobalViewContent()
    document = graph_result_to_document(_result())
    fit = next(n for n in document.nodes if n.config["kind"] == NODE_FIT)
    param = next(n for n in document.nodes if n.config["kind"] == NODE_PARAM_FREE)

    small = (content.node_shape(fit)[2], content.node_shape(param)[2])
    content.radius_scale = 2.0
    large = (content.node_shape(fit)[2], content.node_shape(param)[2])

    assert large[0] == small[0] * 2.0
    assert large[1] == small[1] * 2.0
    assert large[0] > large[1]


def test_a_fit_cannot_be_linked_to_a_fit():
    """Every mark carries one in and one out pin, so this needs saying.

    Without the check the editor happily wires two fits together -- an edge
    the parameter model has no meaning for, in a panel whose whole job is to
    show what follows what.
    """
    content = GlobalViewContent()
    document = graph_result_to_document(_result())
    fits = [n for n in document.nodes if n.config["kind"] == NODE_FIT]
    params = [n for n in document.nodes if n.config["kind"] != NODE_FIT]

    assert content.accepts_link(fits[0], fits[1]) is False
    assert content.accepts_link(fits[0], params[0]) is False
    assert content.accepts_link(params[0], params[1]) is True


def test_a_drawn_link_is_reported_and_not_drawn():
    """The relation belongs to the fit model, so the panel only reports it.

    Adding the edge here as well would draw a link the model has not accepted,
    and the two would disagree until the next refresh.
    """
    from cmtk.testing import RecordingPainter

    document = graph_result_to_document(_result())
    reported: list = []
    control = GraphControl(document, content=GlobalViewContent(),
                           on_link=lambda s, t: reported.append((s, t)))
    control.set_document(document, fit=False)
    control.draw(RecordingPainter(), 0, 0, 900, 520)

    before = len(document.edges)
    control.editor._link_created = (
        document.pin_id("2", 0, True), document.pin_id("5", 0, False),
    )
    control._apply_interactions()

    assert reported == [("2", "5")], "the host was not told"
    assert len(document.edges) == before, "the panel drew a link the model has not seen"
