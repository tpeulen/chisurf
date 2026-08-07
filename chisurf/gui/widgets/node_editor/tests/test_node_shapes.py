"""A node can be a circle, and an untyped port says nothing.

Two rendering claims that only an image would otherwise catch. A circle is the
right shape for a node that *names* a thing and its connections rather than
holding an editor — a page of titled boxes reads as a form where a page of
circles reads as a network — and it is what makes a whole derivation chain fit
without scrolling.
"""

from __future__ import annotations

import pytest

pytest.importorskip("qtpy")

from chisurf.gui.widgets.node_editor.model import NodeModel, PortSpec  # noqa: E402
from chisurf.gui.widgets.node_editor.node_item import NodeGraphicsItem  # noqa: E402


def _model(config: dict | None = None, *, title: str = "artifact") -> NodeModel:
    return NodeModel(
        title=title,
        inputs=[PortSpec(name="from", is_output=False)],
        outputs=[PortSpec(name="to", is_output=True)],
        node_type="artifact",
        config=config or {},
    )


def test_a_box_is_still_the_default(qapp):
    item = NodeGraphicsItem(_model())
    assert not item.is_circle
    assert item.title_height > 0
    assert item.path().boundingRect().width() > item.path().boundingRect().height()


def test_a_circle_is_round_and_has_no_title_bar(qapp):
    item = NodeGraphicsItem(_model({"shape": "circle", "diameter": 40}))
    assert item.is_circle
    rect = item.path().boundingRect()
    assert rect.width() == pytest.approx(40.0)
    assert rect.height() == pytest.approx(40.0)
    # A title *bar* would push the ports and the body below the shape.
    assert item.title_height == 0.0


def test_a_circles_ports_sit_at_its_waist(qapp):
    """Edges then run centre-to-centre, which is what makes a network legible."""
    item = NodeGraphicsItem(_model({"shape": "circle", "diameter": 40}))
    inp, out = item.port_items
    assert (inp.pos().x(), inp.pos().y()) == pytest.approx((0.0, 20.0))
    assert (out.pos().x(), out.pos().y()) == pytest.approx((40.0, 20.0))


def test_the_label_band_is_inside_the_bounding_rect(qapp):
    """The name is painted *below* the circle, so the path bounds are too small.

    Without this the text is clipped at the circle's edge and ``fit_all`` cuts
    the bottom row's labels off the view entirely.
    """
    item = NodeGraphicsItem(_model({"shape": "circle", "diameter": 40}))
    assert item.boundingRect().bottom() > item.path().boundingRect().bottom()
    assert item.boundingRect().width() > 40.0


def test_a_circle_does_not_collapse(qapp):
    """There is no body to fold; collapsing would only strand the edges."""
    item = NodeGraphicsItem(_model({"shape": "circle"}))
    item.set_collapsed(True)
    assert item.collapsed is False


def test_a_box_still_collapses(qapp):
    item = NodeGraphicsItem(_model())
    item.set_collapsed(True)
    assert item.collapsed is True


def test_geometry_can_be_stated_in_the_config(qapp):
    """A whole authored graph can be compact without touching Python."""
    item = NodeGraphicsItem(_model({"width": 210, "min_body_height": 20}))
    assert item.width == pytest.approx(210.0)
    assert item.min_body_height == pytest.approx(20.0)


def test_an_untyped_port_states_no_type(qapp):
    """The default used to be the literal "spectral" — drawn beside every port.

    A name from one graph's domain, rendered as a label on every generic graph
    that stated no type at all.
    """
    assert PortSpec(name="from", is_output=False).port_type == ""

    item = NodeGraphicsItem(_model())
    assert item.port_items[0]._type_label is None


def test_a_typed_port_still_shows_its_type(qapp):
    item = NodeGraphicsItem(
        NodeModel(
            title="n",
            inputs=[PortSpec(name="a", is_output=False, port_type="sF")],
            outputs=[],
        )
    )
    label = item.port_items[0]._type_label
    assert label is not None and label.text() == "sF"


def test_untyped_and_typed_ports_do_not_connect(qapp):
    """Unchanged from when the untyped sentinel was spelled "spectral"."""
    from chisurf.gui.widgets.node_editor.scene import NodeScene

    scene = NodeScene(None)
    untyped = NodeGraphicsItem(_model())
    typed = NodeGraphicsItem(
        NodeModel(
            title="t",
            inputs=[PortSpec(name="a", is_output=False, port_type="sF")],
            outputs=[PortSpec(name="b", is_output=True, port_type="sF")],
        )
    )
    scene.addItem(untyped)
    scene.addItem(typed)
    assert not scene.validate_connection(untyped.port_items[1], typed.port_items[0])
    assert scene.validate_connection(typed.port_items[1], untyped.port_items[0]) is False
