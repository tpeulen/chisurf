"""The emtk shell's Read data dock: a native settings form for every file type, and the sample question.

Each reader's ``view.json`` is drawn by :class:`chisurf.emtk.reader_settings.ReaderSettingsApp`;
its ``custom`` sections need a native renderer (the photon-stream readers' detector cascade and
ROI in :mod:`chisurf.emtk.detector_cascade`, the TCSPC simulator's own frontend). After a file
is chosen for a measurement reader the shell asks which MMFDB sample it is of
(:mod:`chisurf.emtk.sample_picker`). No database and no saved setups are touched: the setups and
the sample list are fakes handed in.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
#: Readers whose settings have no native form yet (open in ``okf/subsystems/qt-retirement.md``):
#: the PDA reader's detector rows and time-window list live in its 2,000-line Qt controller.
KNOWN_GAPS = {("PDA", "PTU/HT3/SPC")}

SETUPS = {
    "Confocal": {
        "detectors": {
            "green": {"chs": [0, 2], "micro_time_ranges": [[0, 4095]]},
            "red": {"chs": [1, 3], "micro_time_ranges": [[100, 3000]]},
        },
        "tttr_reading": {"file_type": "PTU"},
        "channel_luts": {"0": [1.0, 2.0]},
        "channel_shifts": {"1": 7},
        "apply_lut": True,
    }
}


@pytest.fixture(scope="module")
def experiments():
    import chisurf
    from chisurf.core.experiments.bootstrap import ensure_experiments_registered

    ensure_experiments_registered(allow_widgets=False)
    return {str(e.name): e for e in chisurf.experiment.values()}


def _reader(experiments, experiment: str, name: str):
    return next(r for r in experiments[experiment].readers if str(r.name) == name)


@pytest.fixture
def fake_setups(monkeypatch):
    from chisurf.emtk import detector_cascade

    monkeypatch.setattr(detector_cascade, "detector_setups", lambda: dict(SETUPS))
    return SETUPS


def test_every_reader_but_the_known_gaps_has_a_native_settings_form(experiments, fake_setups):
    from chisurf.emtk.reader_settings import reader_settings_app

    missing = set()
    for experiment in experiments.values():
        for reader in getattr(experiment, "readers", None) or []:
            try:
                reader_settings_app(reader, context=object()).close()
            except Exception:  # noqa: BLE001 - recorded, compared below
                missing.add((str(experiment.name), str(reader.name)))
    assert missing == KNOWN_GAPS, "a gap closed (strike it) or a reader lost its form"


@pytest.mark.parametrize(
    ("experiment", "name", "key"),
    [
        ("TCSPC", "TTTR-file", "tcspc_tttr_detector"),
        ("PCH", "PCH (TTTR)", "pch_detector"),
        ("Image correlation", "Image correlation (RICS/STICS/TICS/iMSD)", "ics_detector"),
    ],
)
def test_the_detector_cascade_writes_the_detector_onto_the_reader(
    experiments, fake_setups, experiment, name, key
):
    """Setup → Detector, as the Qt widget: channels, window, LUTs, shifts and routine on the reader."""
    import copy

    from chisurf.emtk.detector_cascade import DetectorCascade
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = copy.copy(_reader(experiments, experiment, name))
    reader.detector_setup = ""
    app = ReaderSettingsApp(reader)
    driver = Driver(app, size=(520, 900))
    driver.frame(2)
    assert f"{key}.setup" in app.form.rects, "the cascade is drawn in the reader's form"
    cascade = DetectorCascade(reader, SETUPS)
    assert cascade.setup == "Confocal" and cascade.detector == "green"
    assert list(np.asarray(reader.channel_numbers)) == [0, 2]
    cascade.detector = "red"
    assert list(np.asarray(reader.channel_numbers)) == [1, 3]
    assert (reader.detector_setup, reader.detector_name) == ("Confocal", "red")
    assert reader.channel_luts == {0: [1.0, 2.0]} and reader.channel_shifts == {1: 7}
    assert reader.apply_lut is True
    cascade.setup = "Confocal"
    assert reader.reading_routine == "PTU", "the setup's file type is the routine"
    cascade.channels = "5; 6"
    assert cascade.channels == "5, 6"
    if hasattr(reader, "micro_time_range"):
        assert tuple(reader.micro_time_range) == (0, 4095)
    app.close()


def test_the_image_correlation_roi_is_the_readers_pixel_rectangle(experiments, fake_setups):
    import copy

    from chisurf.emtk.detector_cascade import IcsRoi
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = copy.copy(_reader(experiments, "Image correlation", "Image correlation (RICS/STICS/TICS/iMSD)"))
    app = ReaderSettingsApp(reader)
    driver = Driver(app, size=(520, 900))
    driver.frame(2)
    assert "ics_roi.x0" in app.form.rects
    roi = IcsRoi(reader)
    roi.x0, roi.x1, roi.y0, roi.y1 = 4, 60, 2, -1
    assert tuple(reader.x_range) == (4, 60) and tuple(reader.y_range) == (2, -1)
    driver.screenshot(SHOTS / "emtk_shell_reader_ics.png")
    app.close()


def test_the_tttr_reader_form_renders(experiments, fake_setups):
    """The TTTR reader's whole form, with the cascade in place of the Qt widget (looked at)."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    app = ReaderSettingsApp(_reader(experiments, "TCSPC", "TTTR-file"))
    driver = Driver(app, size=(520, 700))
    driver.frame(3)
    strings = " ".join(driver.painter.strings)
    assert "Confocal" in strings and "Routing chs" in strings
    driver.screenshot(SHOTS / "emtk_shell_reader_tttr.png")
    app.close()


def test_readers_without_a_spec_now_declare_one(experiments):
    """DEER, the three-colour PDA readers and the global-fit pseudo-reader."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    deer = _reader(experiments, "DEER", "DEER (BES3T/CSV)")
    app = ReaderSettingsApp(deer)
    Driver(app, size=(420, 300)).frame(2)
    assert {"phase_correction", "normalize", "exp_type"} <= set(app.form.rects)
    app.close()
    simulator = _reader(experiments, "PDA", "Simulator (3-colour)")
    app = ReaderSettingsApp(simulator)
    driver = Driver(app, size=(520, 600))
    driver.frame(2)
    assert {"r_gr", "sigma", "n_bursts", "r0_bg"} <= set(app.form.rects)
    driver.screenshot(SHOTS / "emtk_shell_reader_pda3c_simulator.png")
    app.close()


def test_the_simulator_reader_has_its_own_frontend(experiments):
    from chisurf.emtk.reader_settings import reader_settings_app
    from chisurf.emtk.tcspc_simulator import SimulatorSettingsApp

    reader = _reader(experiments, "TCSPC", "Simulator")
    app = reader_settings_app(reader, context=object())
    assert isinstance(app, SimulatorSettingsApp)
    app.close()


class _Samples:
    def __init__(self):
        self.calls = 0

    def list_samples(self):
        self.calls += 1
        return [{"sample_id": "s-1", "name": "Lysozyme 10 nM"}, {"sample_id": "s-2", "name": "Buffer"}]


@pytest.fixture
def shell():
    from chisurf.emtk.main_app import EmtkShellApp
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    session = start_session(state=SessionState())
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    yield app
    app.close()


def test_a_chosen_file_is_followed_by_the_sample_question(shell):
    """FCS: Browse → a file → which sample? OK writes ``sample_id`` onto the reader; Skip does not."""
    data = shell.data
    data.sample_client = _Samples()
    driver = Driver(shell, size=(1300, 900))
    driver.frame(2)
    data.read.experiment = "FCS"
    data.read.experiment_changed("FCS")
    data.read.setup = "Seidel Kristine"
    reader = data.read.reader()
    reader.sample_id = None
    data.open_file_dialog()
    assert data._file_done is None
    data.file_dialog.draw = lambda: ["/tmp/measurement.cor"]
    driver.frame(2)
    assert data.read.path == "/tmp/measurement.cor"
    dialog = data.sample_dialog
    assert dialog is not None
    end = time.monotonic() + 30
    while dialog.loading or not dialog.samples:
        assert time.monotonic() < end, "the samples did not arrive"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)
    assert "Lysozyme 10 nM" in " ".join(driver.painter.strings) or dialog.options()[1][1] == "Lysozyme 10 nM"
    driver.screenshot(SHOTS / "emtk_shell_sample_picker.png")
    dialog.sample_id = "s-1"
    driver.click(dialog.rects["ok"])
    driver.frame(2)
    assert reader.sample_id == "s-1" and data.sample_dialog is None
    # Skip leaves it as it was; a reader that records no sample is not asked.
    data.ask_sample(reader)
    driver.frame(2)
    driver.click(data.sample_dialog.rects["skip"])
    driver.frame(2)
    assert reader.sample_id == "s-1" and data.sample_dialog is None
    assert not data.ask_sample(object())
