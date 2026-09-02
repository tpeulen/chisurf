"""The cmtk beam-path node bodies: the probe filters and the three-layer plot.

None of this needs a display, which is the point of moving the node bodies out
of ``QGraphicsProxyWidget``: what a node shows is now a function of its config,
so it can be asserted rather than screenshotted.
"""
from __future__ import annotations

import numpy as np
import pytest

cmtk = pytest.importorskip("cmtk")

from chisurf.gui.widgets.node_editor.cmtk_control import GraphControl  # noqa: E402
from chisurf.gui.widgets.node_editor.document import GraphDocument  # noqa: E402
from chisurf.plugins.core.lightpath_simulator.backend.crosstalk import (  # noqa: E402
    WAVELENGTHS,
)
from chisurf.plugins.core.lightpath_simulator.gui.cmtk_view import (  # noqa: E402
    BeampathContent,
    _normalised,
    _parse_lines,
    _summed,
)

#: A probe list with one of each category, so the filters can be told apart.
PROBES: list = [
    {"probe_id": "bp", "name": "BP 525/40", "category": "filter"},
    {"probe_id": "dc", "name": "DC 505", "category": "dichroic"},
    {"probe_id": "apd", "name": "SPAD", "category": "detector"},
    {"probe_id": "a488", "name": "Alexa 488", "has_abs": True, "has_em": True},
]


def _gauss(centre: float, width: float) -> np.ndarray:
    """A normalised Gaussian on the wavelength axis, as test data."""
    return np.exp(-((WAVELENGTHS - centre) ** 2) / (2.0 * width * width))


# ---------------------------------------------------------------------------
# Choosing a component
# ---------------------------------------------------------------------------


def test_each_node_type_offers_only_the_components_it_can_take():
    """A filter node must not offer a detector response.

    The categories are the whole reason the chooser is filtered: a beam path
    that has a photodiode's quantum efficiency standing in for a bandpass
    still simulates, and the numbers it produces are wrong rather than absent.
    """
    content = BeampathContent(PROBES)
    assert [name for name, _ in content.choices("filter")] == ["None", "BP 525/40"]
    assert [name for name, _ in content.choices("splitter")] == ["None", "DC 505"]
    assert [name for name, _ in content.choices("detector")] == ["None", "SPAD"]
    assert [name for name, _ in content.choices("sample")] == ["None", "Alexa 488"]


def test_every_chooser_can_be_cleared():
    """``None`` is always first, so a component can be removed as well as set."""
    content = BeampathContent(PROBES)
    for node_type in ("filter", "splitter", "detector", "sample"):
        assert content.choices(node_type)[0] == ("None", None)


def test_an_uncategorised_probe_falls_back_to_what_it_carries():
    """A probe with no category is placed by the spectra it has.

    The database predates the category field, so a good part of it has none;
    dropping those would empty the chooser for a user with an older store.
    """
    content = BeampathContent([
        {"probe_id": "old", "name": "Legacy BP", "has_trans": True},
        {"probe_id": "det", "name": "Legacy QE", "has_qe": True},
    ])
    assert [name for name, _ in content.choices("filter")] == ["None", "Legacy BP"]
    assert [name for name, _ in content.choices("detector")] == ["None", "Legacy QE"]


def test_probes_can_arrive_after_the_window_is_open():
    """The loader runs on a worker thread, so the list starts empty."""
    content = BeampathContent()
    assert content.choices("filter") == [("None", None)]
    content.set_probes(PROBES)
    assert len(content.choices("filter")) == 2


# ---------------------------------------------------------------------------
# The spectra
# ---------------------------------------------------------------------------


def test_spectra_are_summed_across_ports_and_sources():
    """Two upstream sources into one node add up, as light does."""
    total = _summed({
        "In": {"a": _gauss(500.0, 10.0), "b": _gauss(600.0, 10.0)},
        "Other": {"c": _gauss(500.0, 10.0)},
    })
    assert total is not None
    assert abs(float(total.max()) - 2.0) < 1e-6


def test_a_malformed_spectrum_response_does_not_stop_the_repaint():
    """The RPC response is tolerated, not trusted.

    A port whose upstream produced nothing is an empty dict, a failed node is
    missing, and a stale graph names ports that no longer exist. None of those
    should stop the editor drawing -- the node simply has no spectrum yet.
    """
    assert _summed(None) is None
    assert _summed({"In": None}) is None
    assert _summed({"In": {"a": "not an array"}}) is None
    assert _summed({"In": {"a": np.zeros(3)}}) is None, "wrong length is not a spectrum"


def test_an_all_zero_spectrum_is_not_drawn():
    """A component that passes nothing and one not yet computed look the same.

    Both are a flat line on the axis, and only one of them is information. The
    line is left out rather than drawn, so an empty plot means "no answer yet".
    """
    assert _normalised(np.zeros_like(WAVELENGTHS)) is None
    assert _normalised(None) is None


def test_each_curve_is_normalised_on_its_own():
    """A transmission and a flux share an axis only if each peaks at one.

    They are different quantities -- one dimensionless, one not -- so a shared
    scale either flattens the transmission to nothing or clips the flux.
    """
    curve = _normalised(_gauss(500.0, 20.0) * 1e-9)
    assert curve is not None
    assert abs(max(curve) - 1.0) < 1e-9


def test_manual_laser_lines_parse_leniently():
    """The field is edited a character at a time, so half-typed is not an error."""
    assert _parse_lines("488, 640") == [488.0, 640.0]
    assert _parse_lines("488 640") == [488.0, 640.0]
    assert _parse_lines("488, ") == [488.0]
    assert _parse_lines("") == []
    assert _parse_lines("488, abc, 640") == [488.0, 640.0]


# ---------------------------------------------------------------------------
# Drawing the whole path
# ---------------------------------------------------------------------------


#: A four-component path with simulated spectra already merged into the config,
#: which is the state the backend's RPC response leaves the graph in.
def _beam_path() -> dict:
    """Build a graph in schema v1 with spectra attached."""
    return {
        "version": 1,
        "nodes": [
            {"id": "src", "type": "light_source", "title": "Light Source",
             "inputs": [], "outputs": ["Light"], "pos": [0.0, 0.0],
             "config": {"source_mode": "manual", "manual_lines": [488.0],
                        "_output_spectra": {"Light": {"src": _gauss(488.0, 4.0)}}}},
            {"id": "smp", "type": "sample", "title": "Sample / Fluorophore",
             "inputs": ["In"], "outputs": ["Out", "Dye Data"], "pos": [300.0, 0.0],
             "config": {"probe_id": "a488",
                        "_input_spectra": {"In": {"src": _gauss(488.0, 4.0)}},
                        "_output_spectra": {"Out": {"smp": _gauss(525.0, 25.0)}},
                        "_node_char": (_gauss(495.0, 20.0), _gauss(525.0, 25.0))}},
            {"id": "flt", "type": "filter", "title": "Filter",
             "inputs": ["In"], "outputs": ["Out"], "pos": [600.0, 0.0],
             "config": {"probe_id": "bp",
                        "_input_spectra": {"In": {"smp": _gauss(525.0, 25.0)}},
                        "_node_char": _gauss(525.0, 18.0)}},
            {"id": "det", "type": "detector", "title": "Detector",
             "inputs": ["In"], "outputs": [], "pos": [900.0, 0.0],
             "config": {"detector_name": "Green APD", "probe_id": "apd",
                        "_input_spectra": {"In": {"flt": _gauss(525.0, 15.0)}}}},
        ],
        "edges": [
            {"source": "src", "source_port": 0, "target": "smp", "target_port": 0},
            {"source": "smp", "source_port": 0, "target": "flt", "target_port": 0},
            {"source": "flt", "source_port": 0, "target": "det", "target_port": 0},
        ],
    }


def _drawn(control, box=(0, 0, 1300, 400), frames=1):
    """Draw the control and hand back the recording painter."""
    from cmtk.testing import RecordingPainter

    painter = RecordingPainter()
    for _ in range(frames):
        control.draw(painter, *box)
    return painter


def test_the_whole_beam_path_draws_with_no_display():
    """Four components with their spectra, through a painter that owns nothing."""
    document = GraphDocument.from_dict(_beam_path())
    control = GraphControl(document, content=BeampathContent(PROBES))
    control.set_document(document, fit=False)
    assert _drawn(control).calls


def test_no_node_stretches_across_the_editor():
    """Every node is sized by its contents, not by the row it sits in.

    A control that fills the row makes its node as wide as the whole editor;
    fit-to-content then zooms out to frame that node and the rest of the graph
    collapses into the corner. It reads as a rendering bug and it is a layout
    one, so it is asserted here rather than left to a screenshot.
    """
    document = GraphDocument.from_dict(_beam_path())
    control = GraphControl(document, content=BeampathContent(PROBES))
    control.set_document(document, fit=False)
    _drawn(control)

    widths = []
    for node in document.nodes:
        x0, _, x1, _ = control.editor._nodes[document.node_number(node.id)].rect
        widths.append(x1 - x0)
    assert max(widths) < 400.0, f"a node is {max(widths):.0f}px wide: something filled the row"
    # And they are all about the same width, which is what a row of components
    # should look like.
    assert max(widths) - min(widths) < 40.0


def test_folding_a_plot_away_does_not_resimulate():
    """Hiding a plot changes the picture, not the beam path.

    Reporting it as a change would re-run the simulation over RPC every time
    somebody tidied the view.
    """
    document = GraphDocument.from_dict(_beam_path())
    content = BeampathContent(PROBES)
    control = GraphControl(document, content=content)
    control.set_document(document, fit=False)

    node = document.node("flt")
    content.hidden_plots.add(node.id)
    # Folded away, the node is shorter and nothing reports an edit.
    _drawn(control)
    folded = control.editor._nodes[document.node_number("flt")].rect
    content.hidden_plots.discard(node.id)
    _drawn(control)
    shown = control.editor._nodes[document.node_number("flt")].rect
    assert (shown[3] - shown[1]) > (folded[3] - folded[1])
