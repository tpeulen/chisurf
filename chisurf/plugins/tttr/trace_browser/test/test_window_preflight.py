"""The Trace Browser holds its detector gates against the excitation pulses of the file shown.

A detector with micro-time gates counts only the photons inside them (the binner applies them in
the data's channels). The measurement is the simulated PIE demo of Excitation Windows (32 ps,
3125 channels, pulses at 2 and 52 ns, donor on routing 0, acceptor on routing 1). Gates made for
another instrument give the line in ``load_trace``'s ``warnings`` (RPC and the CLI) and the offer
in the browser, which bins through the detected gates when taken; matching gates, ungated
detectors and a donor-only measurement say nothing.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

pytest.importorskip("tttrlib")

from chisurf.plugins.tttr.trace_browser.core.trace import load_trace  # noqa: E402

WRONG = {
    "detectors": {
        "green": {"chs": [0], "micro_time_ranges": [[2048, 4095]]},
        "red": {"chs": [1], "micro_time_ranges": [[0, 2047]]},
    }
}
MATCHING = {
    "detectors": {
        "green": {"chs": [0], "micro_time_ranges": [[0, 1612]]},
        "red": {"chs": [1], "micro_time_ranges": [[0, 3124]]},
    }
}
UNGATED = {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}}


@pytest.fixture(scope="module")
def pie(tmp_path_factory):
    from chisurf.plugins.core.excitation_windows.demo import make_demo

    return make_demo(tmp_path_factory.mktemp("pie"))


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    """The demo's photons without the acceptor-excited ones (one pulse)."""
    from chisurf.plugins.core.excitation_windows import demo as d
    from chisurf.plugins.tttr import demo_lib

    macro, micro, routing = d.photon_stream()
    keep = micro.astype(float) * d.RESOLUTION_S < 51e-9
    path = tmp_path_factory.mktemp("donor") / "donor_only.ptu"
    cfg = demo_lib.config(
        macro_resolution_s=d.MACRO_S,
        micro_resolution_s=d.RESOLUTION_S,
        n_micro=d.N_MICRO,
        seed=d.SEED,
    )
    demo_lib.write_ptu(path, cfg, macro[keep], micro[keep], routing[keep])
    return path


def test_gates_of_another_instrument_are_in_the_result(pie, tmp_path):
    data = load_trace(str(pie), 10.0, setup_settings=WRONG, cache_folder=str(tmp_path))
    assert data["labels"] == ["green", "red"]
    assert len(data["warnings"]) == 1 and "do not match the data" in data["warnings"][0]
    # A cached trace still carries the check.
    again = load_trace(str(pie), 10.0, setup_settings=WRONG, cache_folder=str(tmp_path))
    assert again["warnings"] == data["warnings"]


def test_matching_ungated_and_donor_only_say_nothing(pie, donor_only, tmp_path):
    for setup in (MATCHING, UNGATED, None):
        assert (
            load_trace(str(pie), 10.0, setup_settings=setup, cache_folder=str(tmp_path))["warnings"]
            == []
        )
    assert (
        load_trace(str(donor_only), 10.0, setup_settings=MATCHING, cache_folder=str(tmp_path))[
            "warnings"
        ]
        == []
    )


def test_the_cli_prints_the_warning(pie, tmp_path):
    from click.testing import CliRunner

    from chisurf.plugins.tttr.trace_browser.cli.main import cli

    setup = tmp_path / "setup.json"
    setup.write_text(json.dumps(WRONG))
    out = CliRunner().invoke(cli, ["load", str(pie), "--setup", str(setup)])
    assert out.exit_code == 0, out.output
    assert "warning: Detector gates do not match the data" in out.stderr
    assert "do not match" in json.loads(out.stdout)["warnings"][0]


def test_the_browser_offers_the_detected_gates_and_takes_them(pie, tmp_path):
    from chisurf.plugins.tttr.trace_browser.gui.model import TraceBrowserModel

    model = TraceBrowserModel()
    model.apply_setup(json.loads(json.dumps(WRONG)))
    model.current_folder = tmp_path
    assert model.show_file(pie)
    assert model.windows_check_offer and "do not match" in model.windows_check_text()
    assert "Detector gates do not match the data" in model.status_line
    before = np.asarray(model.trace["counts"]).sum()
    assert model.use_detected_windows()
    green = model.setup_settings["detectors"]["green"]["micro_time_ranges"]
    assert any(lo <= 2e-9 / 32e-12 < hi for lo, hi in green), green
    assert model.trace is None and model.setup_taken
    assert model.show_file(pie)
    assert np.asarray(model.trace["counts"]).sum() > before
    assert not model.windows_check_offer and model.windows_check_quiet


def test_the_setup_page_shows_the_taken_gates(pie, tmp_path):
    from chisurf.plugins.tttr.trace_browser.gui.app import TraceBrowserApp

    app = TraceBrowserApp()
    model = app.model
    model.accept_setup(json.loads(json.dumps(WRONG)))
    model.current_folder = tmp_path
    assert model.show_file(pie) and model.use_detected_windows()
    app._take_setup()
    shown = app.editor.model.get_settings()["detectors"]["green"]["micro_time_ranges"]
    assert any(lo <= 2e-9 / 32e-12 < hi for lo, hi in shown), shown
    assert not model.setup_taken
    app.close()
