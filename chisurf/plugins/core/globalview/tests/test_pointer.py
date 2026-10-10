"""Global View: the pointer on the drawn network -- select, multi-select, link, unlink, refuse a cycle.

Nodes are pressed where the node editor drew them; the toolbar buttons are pressed at the rectangles the surface
reports. The mutator records what the fitting client would receive, so a link is asserted where it lands: on the
parameter the user sees follow another.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("emtk")
from emtk import nodes  # noqa: E402
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.core.globalview.gui import app as gvapp  # noqa: E402

SIZE = (1200, 800)
CTRL = 0x04000000


def _session(n=3):
    spec = importlib.util.spec_from_file_location("_gv_test_model", Path(__file__).parent / "test_model.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._session(n)


def _frames(app, n=3):
    for _ in range(n):
        app.draw(RecordingPainter(), 0, 0, *SIZE)


def _make():
    model, fits, mutator = _session(3)
    app = gvapp.make_app(model=model, remember_layout=False)
    _frames(app)
    return app, model, fits, mutator


def _node_id(fit, name):
    return f"param:{fit.model.parameters_all_dict[name].unique_identifier}"


def _node(model, node_id):
    control = model.control
    return control.editor._nodes[control.document.node_number(node_id)]


def _centre(model, node_id):
    """A point on the node's mark that no connector claims: the rim just below its centre.

    A disc is its own connector, so its input and output pins sit left and right of the centre and the pointer
    catches a pin within ``pin_hover_radius`` of them; a press straight below the centre is on the node.
    """
    x0, y0, x1, y1 = _node(model, node_id).rect
    return (x0 + x1) / 2, (y0 + y1) / 2 + 0.4 * (y1 - y0)


def _pin(model, node_id, kind):
    """Where the node's input or output connector was drawn last frame."""
    editor = model.control.editor
    for pin_id in _node(model, node_id).pins:
        if editor._pins[pin_id].kind == kind:
            return editor._pins[pin_id].pos
    raise AssertionError(f"{node_id} has no {kind} pin")


def _click_at(app, x, y, modifiers=0):
    app.pointer_move(x, y)
    _frames(app, 1)
    app.press(x, y, modifiers=modifiers)
    _frames(app, 1)
    app.release()
    _frames(app, 2)


def _click_node(app, model, node_id, modifiers=0):
    _click_at(app, *_centre(model, node_id), modifiers=modifiers)


def _press_button(app, action):
    x, y, w, h = app.rect_of(action)
    _click_at(app, x + w / 2, y + h / 2)


def _selected_ids(model):
    return list(model.selection)


def test_clicking_a_node_selects_it_and_clicking_another_replaces_the_selection():
    app, model, fits, _ = _make()
    first, second = _node_id(fits[0], "c"), _node_id(fits[1], "c")
    _click_node(app, model, first)
    assert _selected_ids(model) == [first]
    assert nodes.is_node_selected(model.control.editor, model.control.document.node_number(first))
    _click_node(app, model, second)
    assert _selected_ids(model) == [second]
    # an empty corner of the network clears the selection
    x, y, w, h = app.network_box
    _click_at(app, x + w - 6, y + 6)
    assert _selected_ids(model) == []


def test_ctrl_click_adds_to_the_selection_in_click_order():
    app, model, fits, _ = _make()
    first, second = _node_id(fits[1], "c"), _node_id(fits[0], "c")
    _click_node(app, model, first)
    _click_node(app, model, second, modifiers=CTRL)
    assert _selected_ids(model) == [first, second]


def test_link_button_makes_the_second_selection_follow_the_first_and_unlink_releases_it():
    app, model, fits, mutator = _make()
    master_fit, follower_fit = fits[0], fits[1]
    master = master_fit.model.parameters_all_dict["c"]
    follower = follower_fit.model.parameters_all_dict["c"]
    assert follower.link is None
    _click_node(app, model, _node_id(master_fit, "c"))
    _click_node(app, model, _node_id(follower_fit, "c"), modifiers=CTRL)
    _press_button(app, "link_selected")
    assert mutator.calls[-1][0] == "link" and follower.link is master and master.link is None
    link_edges = [e for e in model.control.document.edges if e.config["kind"] == "link"]
    assert any(e.source == _node_id(follower_fit, "c") and e.target == _node_id(master_fit, "c") for e in link_edges)
    # unlink: select the follower and press Unlink
    _click_node(app, model, _node_id(follower_fit, "c"))
    _press_button(app, "unlink_selected")
    assert follower.link is None


def test_link_with_one_selected_parameter_says_what_is_missing():
    app, model, fits, mutator = _make()
    _click_node(app, model, _node_id(fits[0], "c"))
    _press_button(app, "link_selected")
    assert mutator.calls == []
    assert model.status == "Select two parameters first -- the first one is the master."


def _drag(app, start, end, steps=8):
    app.pointer_move(*start)
    _frames(app, 1)
    app.press(*start)
    _frames(app, 1)
    for step in range(1, steps + 1):
        app.pointer_move(
            start[0] + (end[0] - start[0]) * step / steps, start[1] + (end[1] - start[1]) * step / steps, 1
        )
        _frames(app, 1)
    app.release()
    _frames(app, 3)


def test_dragging_a_connector_onto_another_links_them_and_a_cycle_is_refused():
    app, model, fits, mutator = _make()
    source_id, target_id = _node_id(fits[1], "c"), _node_id(fits[0], "c")
    follower = fits[1].model.parameters_all_dict["c"]
    master = fits[0].model.parameters_all_dict["c"]
    _drag(app, _pin(model, source_id, "output"), _pin(model, target_id, "input"))
    assert follower.link is master, "a link drawn from A to B makes A follow B"
    assert mutator.calls[-1][0] == "link"
    # drawing the reverse arrow would close a cycle: refused, and said in a message
    _drag(app, _pin(model, target_id, "output"), _pin(model, source_id, "input"))
    assert master.link is None
    assert app.message is not None and "cycle" in app.message[1]
    assert app.message_window.open


def test_dragging_a_connector_to_empty_space_links_nothing():
    app, model, fits, mutator = _make()
    start = _pin(model, _node_id(fits[1], "c"), "output")
    x, y, w, h = app.network_box
    _drag(app, start, (x + w - 8, y + 8))
    assert mutator.calls == []


def test_pressing_the_middle_of_a_mark_selects_the_node():
    app, model, fits, _ = _make()
    node_id = _node_id(fits[0], "c")
    x0, y0, x1, y1 = _node(model, node_id).rect
    _click_at(app, (x0 + x1) / 2, (y0 + y1) / 2)
    assert _selected_ids(model) == [node_id]
