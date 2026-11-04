"""Burst MLE's IRF is the IRF Estimation tool's: one extraction, routed there, shown there.

On the simulated session of Burst Analysis (``burst_analysis/demo.py``: a Gaussian IRF of known
width, a measured water scatter and an Rh110 reference beside it) the IRF Burst MLE takes from the
reference dye is the tool's extraction (handed to it, the tool computes the identical IRF), and it
matches the measured scatter. The exact difference used before ``D[i] - a D[i-1]`` read the
rotation of the dye into the VH IRF: 82 ps late, TV 0.26 from the scatter.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.plugins.burst.burst_analysis import demo
from chisurf.plugins.burst.burst_mle_analysis import engine
from chisurf.plugins.fluorescence_decay.irf_estimator.gui.view_model import IRFViewModel


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    return demo.make_demo(tmp_path_factory.mktemp("irf_tool_demo"))


@pytest.fixture(scope="module")
def session():
    s = engine.MleSession()
    s.set_definition(demo.SETUP)
    return s


def _tv(a, b) -> float:
    a, b = np.clip(a, 0, None), np.clip(b, 0, None)
    return 0.5 * float(np.abs(a / a.sum() - b / b.sum()).sum())


def test_the_reference_dye_irf_is_the_tools_and_matches_the_scatter(session, files):
    irf, text = session.irf_pattern("G|G", [files["reference"]])
    assert "Rh110" in text and "deconvolved" in text and "rotation" in text
    source = session.irf_inputs["G|G"]
    assert source["kind"] == "reference" and source["dye"] == "Rh110"

    # the tool, given what Burst MLE extracted from, extracts the same IRF
    tool = IRFViewModel()
    tool.receive_source(dict(source, detector="G|G", origin="Burst MLE"))
    assert tool.source == "reference" and tool.vv_vh
    tool.estimate()
    np.testing.assert_allclose(np.asarray(tool.result.irf), irf, atol=1e-12)
    assert tool.extraction.text == text

    # ... and it is the scatter measured beside it (the IRF of the simulation)
    scatter, scatter_text = session.irf_pattern("G|G", [files["irf"]])
    assert scatter_text.startswith("scatter")
    half = irf.size // 2
    for got, measured in ((irf[:half], scatter[:half]), (irf[half:], scatter[half:])):
        assert _tv(got, measured) < 0.12
        t = np.arange(half)
        centre = float((got * t).sum() / got.sum() - (measured * t).sum() / measured.sum())
        assert abs(centre) < 0.6  # bins (64 ps): the centre within ~40 ps


def test_a_scatter_wins_and_is_routed_too(session, files):
    irf, text = session.irf_pattern("G|G", [files["reference"], files["irf"]])
    assert text.startswith("scatter") and session.irf_inputs["G|G"]["kind"] == "scatter"
    tool = IRFViewModel()
    tool.receive_source(session.irf_inputs["G|G"])
    tool.estimate()
    np.testing.assert_allclose(np.asarray(tool.result.irf), irf, atol=1e-12)


def test_the_irf_tool_button_hands_the_source_to_the_irf_tool(session, files):
    """Burst MLE's **IRF tool** hands what the detector's IRF came from to IRF Estimation (the
    shell's hand-off), whose receive hook extracts the same IRF."""
    import json
    from pathlib import Path

    from chisurf.core.plugin import handoff
    from chisurf.plugins.burst.burst_mle_analysis.gui.native import MleNativeApp
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui import app as tool_app

    manifest = json.loads((Path(tool_app.__file__).parents[1] / "manifest.json").read_text())

    class Host:
        def __init__(self):
            self.sent = []

        def accepts(self, plugin_id, kind):
            return handoff.accepted(plugin_id, kind, manifest) if plugin_id == "irf_estimator" else None

        def hand_off(self, plugin_id, kind, payload, **_extra):
            self.sent.append((plugin_id, kind, payload))

    window = MleNativeApp()
    host = Host()
    handoff.install_host(host)
    try:
        session.irf_pattern("G|G", [files["reference"]])
        window.model.session.irf_inputs["G|G"] = session.irf_inputs["G|G"]
        window.model.session.current_detector = "G|G"
        assert window.open_in_irf_tool()
        (plugin_id, kind, payload), = host.sent
        assert (plugin_id, kind) == ("irf_estimator", "irf_source")
        assert payload["irf_source"]["detector"] == "G|G" and payload["irf_source"]["origin"] == "Burst MLE"
        tool = tool_app.IRFEstimatorApp()
        try:
            tool_app.receive_irf_source(tool, payload)
            assert tool.future is not None
            tool.future.result(timeout=60)
        finally:
            tool.close()
        window.model.session.irf_inputs.pop("G|G")
        assert not window.open_in_irf_tool()  # nothing extracted from a measurement: said, not sent
        assert len(host.sent) == 1
    finally:
        handoff.uninstall_host(host)
        window.close()
