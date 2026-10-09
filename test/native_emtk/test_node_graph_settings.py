"""The node-graph plot settings: what the reader returns and what it writes.

Everything here runs with no Qt and no window: the reader, the style it
writes, and the two places that consume it -- :class:`GraphControl`, whose
every graph starts from the settings, and Global View's ``apply_network_style``,
which must *keep* them rather than redefine the grid it just inherited.
"""

from __future__ import annotations

import pytest

from emtk import nodes as emtk_nodes

from chisurf.emtk.node_editor.control import GraphControl
from chisurf.emtk.node_editor.document import GraphDocument
from chisurf.emtk.node_editor.style_settings import (
    NODE_GRAPH_DEFAULTS,
    apply_node_graph_settings,
    node_graph_settings,
)


@pytest.fixture
def plot_store(monkeypatch):
    """A clean ``gui.plot`` the reader can be pointed at, and returned."""
    from chisurf.core import settings as css

    store = {"gui": {"plot": {}}}
    monkeypatch.setattr(css, "cs_settings", store, raising=False)
    return store["gui"]["plot"]


def test_the_reader_fills_every_default(plot_store):
    """An empty section reads as the shipped defaults, typed."""
    settings = node_graph_settings()
    assert settings == NODE_GRAPH_DEFAULTS
    assert isinstance(settings["grid_line_width"], float)
    assert isinstance(settings["grid_opacity"], float)
    assert isinstance(settings["grid_spacing"], float)
    assert isinstance(settings["node_size"], float)
    assert isinstance(settings["show_grid"], bool)


def test_the_reader_honours_stored_values_and_coerces_them(plot_store):
    """A stored value wins; one of the wrong type falls back, not crashes."""
    plot_store["node_graph"] = {
        "grid_line_width": "1.25",  # a string a hand-edited yaml can hold
        "grid_spacing": 40,
        "grid_opacity": "not a number",
    }
    settings = node_graph_settings()
    assert settings["grid_line_width"] == 1.25
    assert settings["grid_spacing"] == 40.0
    assert settings["grid_opacity"] == NODE_GRAPH_DEFAULTS["grid_opacity"]
    assert settings["show_grid"] is True


def test_apply_writes_the_whole_grid_onto_a_style(plot_store):
    """Width, spacing, both line opacities, and the on/off flag."""
    plot_store["node_graph"] = {"grid_line_width": 1.25, "grid_opacity": 0.5, "grid_spacing": 40.0}
    style = emtk_nodes.Style()
    apply_node_graph_settings(style)
    assert style.grid_line_width == 1.25
    assert style.grid_spacing == 40.0
    minor = style.colors[emtk_nodes.Col.GRID_LINE]
    primary = style.colors[emtk_nodes.Col.GRID_LINE_PRIMARY]
    assert minor == (255, 255, 255, 128)
    # The primary lines read stronger, never above full opacity.
    assert primary == (255, 255, 255, 217)
    assert style.flags & emtk_nodes.StyleFlags.GRID_LINES

    plot_store["node_graph"]["show_grid"] = False
    apply_node_graph_settings(style)
    assert not style.flags & emtk_nodes.StyleFlags.GRID_LINES


def test_every_graph_starts_from_the_settings(plot_store):
    """A fresh GraphControl inherits the panel's grid, not emtk's defaults."""
    plot_store["node_graph"] = {"grid_line_width": 1.25, "grid_opacity": 0.5}
    control = GraphControl(document=GraphDocument())
    style = control.editor.style
    assert style.grid_line_width == 1.25
    assert style.colors[emtk_nodes.Col.GRID_LINE] == (255, 255, 255, 128)


def test_globalview_keeps_the_settings_grid_it_inherits(plot_store):
    """``apply_network_style`` adds its diagram look without redefining the grid.

    It once painted the grid itself, which made the panel's numbers true of
    every graph but this one. The background stays its own -- darker than
    emtk's -- because that is a claim about *this* graph.
    """
    from chisurf.plugins.core.globalview.gui.emtk_view import apply_network_style

    plot_store["node_graph"] = {"grid_line_width": 1.25, "grid_opacity": 0.5}
    control = GraphControl(document=GraphDocument())
    apply_network_style(control.editor)
    style = control.editor.style
    assert style.grid_line_width == 1.25
    assert style.colors[emtk_nodes.Col.GRID_LINE] == (255, 255, 255, 128)
    assert style.colors[emtk_nodes.Col.GRID_BACKGROUND] == (24, 26, 31, 255)
    assert style.link_routing == emtk_nodes.LinkRouting.ARC
    assert not style.flags & emtk_nodes.StyleFlags.NODE_OUTLINE
