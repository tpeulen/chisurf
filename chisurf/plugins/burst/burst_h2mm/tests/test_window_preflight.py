"""H2MM runs the shared excitation-window pre-flight on the micro-time ranges of its streams.

On the simulated PIE demo of Excitation Windows (pulses at 2 and 52 ns, routing 0 donor / 1
acceptor): streams gated for another instrument warn in the result, on the CLI's stderr and in
the window, which offers the detected gates and takes them into its detector definition; PIE's
standard streams (green and red prompt, yellow delayed on the red channel) say nothing; ungated
streams are not checked; a donor-only measurement gives no false warning. StreamDef ranges are
inclusive, the shared check's gates half-open.
"""

from __future__ import annotations

import copy

import pytest

tttrlib = pytest.importorskip("tttrlib")

from chisurf.plugins.burst.burst_bva.tests import pie_folder  # noqa: E402
from chisurf.core.fluorescence.burst.streams import (  # noqa: E402
    stream_detectors,
    window_warnings,
)
from chisurf.plugins.burst.burst_h2mm.backend.services import run_analysis  # noqa: E402
from chisurf.plugins.burst.burst_h2mm.core.photons import StreamDef  # noqa: E402

PIE = [
    StreamDef("green", [0], [(0, 1612)]),
    StreamDef("red", [1], [(0, 1612)]),
    StreamDef("yellow", [1], [(1613, 3124)]),
]
WRONG = [StreamDef("green", [0], [(2048, 4094)]), StreamDef("red", [1], [(0, 2047)])]


def stream_window_warnings(tttrs, stream_defs):
    return window_warnings(tttrs, stream_detectors(
        {s.name: (s.channels, s.micro_time_ranges) for s in stream_defs}))


@pytest.fixture(scope="module")
def folder(tmp_path_factory):
    return pie_folder.build(tmp_path_factory.mktemp("pie"))


@pytest.fixture(scope="module")
def demo(folder):
    return {"demo.ptu": tttrlib.TTTR(str(next(folder.parent.glob("*.ptu"))))}


@pytest.fixture(scope="module")
def donor_only(tmp_path_factory):
    return {"d.ptu": tttrlib.TTTR(str(pie_folder.donor_only(tmp_path_factory.mktemp("d"))))}


def test_streams_of_another_instrument_warn(demo):
    lines = stream_window_warnings(demo, WRONG)
    assert len(lines) == 1 and "do not match the data" in lines[0], lines
    assert "1613" in lines[0]


def test_the_pie_streams_say_nothing(demo):
    assert stream_window_warnings(demo, PIE) == []


def test_ungated_streams_are_not_checked(demo):
    assert stream_window_warnings(demo, [StreamDef("g", [0], []), StreamDef("r", [1], [])]) == []


def test_a_donor_only_measurement_gives_no_false_warning(donor_only):
    assert stream_window_warnings(donor_only, PIE) == []


def _settings(streams):
    from chisurf.plugins.burst.burst_h2mm.api.models import H2mmSettings, StreamSettings

    return H2mmSettings(
        streams=[StreamSettings(s.name, list(s.channels), list(s.micro_time_ranges))
                 for s in streams],
        min_states=1,
        max_states=1,
        n_restarts=1,
        max_iter=20,
        file_type="PTU",
    )


def test_the_result_carries_the_warning(folder):
    result, _ = run_analysis(_settings(WRONG), analysis_folder=folder)
    assert len(result.warnings) == 1 and "do not match the data" in result.warnings[0]
    assert run_analysis(_settings(PIE), analysis_folder=folder)[0].warnings == []


def _model(setup_gates):
    from chisurf.plugins.burst.burst_h2mm.gui.model import H2mmViewModel

    model = H2mmViewModel()
    setup = copy.deepcopy(model.setup)
    setup["detectors"] = {
        name: {"chs": chs, "micro_time_ranges": gates}
        for name, (chs, gates) in setup_gates.items()
    }
    model.set_setup(setup)
    model.donor, model.acceptor = "green", "red"
    return model


def test_the_window_offers_and_takes_the_detected_gates(demo):
    model = _model({"green": ([0], [[2048, 4095]]), "red": ([1], [[0, 2048]])})
    assert "do not match the data" in (model.check_windows(demo) or "")
    assert not model.windows_check_quiet and model.windows_check_offer
    assert model.use_detected_windows()
    assert model.setup["detectors"]["green"]["micro_time_ranges"] == [[0, 3125]]
    assert model.check_windows(demo) is None
    assert model.windows_check_quiet and not model.windows_check_offer


def test_the_window_says_nothing_on_the_pie_split(demo):
    model = _model({"green": ([0], [[0, 1613]]), "red": ([1], [[0, 1613]]),
                    "yellow": ([1], [[1613, 3125]])})
    assert model.check_windows(demo) is None and model.windows_check_quiet


def test_the_window_draws_the_check(demo, tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "db.sqlite"))
    from emtk.testing import Driver

    from chisurf.plugins.burst.burst_h2mm.gui.native import H2mmNativeApp

    app = H2mmNativeApp(_model({"green": ([0], [[2048, 4095]]), "red": ([1], [[0, 2048]])}))
    try:
        app.model.check_windows(demo)
        driver = Driver(app, size=(1100, 720))
        driver.draw(3)
        assert app.model.windows_check_offer
        app.model.use_detected_windows()
        driver.draw(2)
        gates = app.editor.model.data["detectors"]["green"]["micro_time_ranges"]
        assert gates == [[0, 3125]]
    finally:
        app.close()
