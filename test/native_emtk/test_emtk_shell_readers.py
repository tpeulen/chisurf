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
#: Readers whose settings have no native form yet (open in ``okf/subsystems/qt-retirement.md``).
KNOWN_GAPS: set[tuple[str, str]] = set()

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
    monkeypatch.setattr(detector_cascade, "last_used_setup", lambda: "")
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

    reader = copy.copy(
        _reader(experiments, "Image correlation", "Image correlation (RICS/STICS/TICS/iMSD)")
    )
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
        return [
            {"sample_id": "s-1", "name": "Lysozyme 10 nM"},
            {"sample_id": "s-2", "name": "Buffer"},
        ]


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
    assert (
        "Lysozyme 10 nM" in " ".join(driver.painter.strings)
        or dialog.options()[1][1] == "Lysozyme 10 nM"
    )
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


class _SamplesWithCreate(_Samples):
    def __init__(self):
        super().__init__()
        self.created: list[dict] = []

    def list_samples(self):
        return super().list_samples() + [
            {"sample_id": f"s-new-{i}", "name": d["name"]} for i, d in enumerate(self.created)
        ]

    def create_structured_sample(self, sample_data):
        self.created.append(sample_data)
        return {"sample_id": f"s-new-{len(self.created) - 1}"}


def test_new_defines_a_sample_and_the_question_uses_it(shell):
    """*New…*: the sample definition form; OK creates it in MMFDB and the question selects it."""
    data = shell.data
    client = data.sample_client = _SamplesWithCreate()
    driver = Driver(shell, size=(1300, 1000))
    driver.frame(2)
    data.read.experiment = "FCS"
    data.read.experiment_changed("FCS")
    data.read.setup = "Seidel Kristine"
    reader = data.read.reader()
    reader.sample_id = None
    assert data.ask_sample(reader)
    dialog = data.sample_dialog
    end = time.monotonic() + 30
    while dialog.loading:
        assert time.monotonic() < end, "the samples did not arrive"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)
    driver.click(dialog.rects["new"])
    driver.frame(2)
    form = dialog.new_dialog
    assert form is not None, "New… opened the sample definition"
    driver.click(form.rects["ok"])
    driver.frame(2)
    assert "Sample name is required." in form.model.message and not client.created
    form.model.name = "T4L C54/C97"
    form.model.donor, form.model.acceptor = "Alexa488", "Alexa647"
    form.model.entity_sequence = "MNIFEMLRIDE"
    form.model.add_mutation()
    form.model.edit_mutation({"row": 0}, "seq_id", "3")
    driver.frame(2)
    driver.screenshot(SHOTS / "emtk_shell_new_sample.png")
    driver.click(form.rects["ok"])
    while dialog.new_dialog is not None:
        assert time.monotonic() < end + 30, "the sample was not created"
        driver.frame(1)
        time.sleep(0.02)
    made = client.created[0]
    assert made["name"] == "T4L C54/C97" and len(made["probes"]) == 2 and made["fret_pairs"]
    assert made["entities"][0]["mutations"][0]["seq_id"] == 3
    assert dialog.sample_id == "s-new-0", "the new sample is selected"
    while dialog.loading:
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)
    driver.click(dialog.rects["ok"])
    driver.frame(2)
    assert reader.sample_id == "s-new-0"


# ── the PDA reader: detector rows, time windows and the file list ────────────────

REPO = Path(__file__).resolve().parents[2]
PDA_DATA = REPO / "chisurf/plugins/burst/burst_selection/tests/data/bh_spc132_sm_dna"
PDA_BURSTS = PDA_DATA / "burstwise_All 0.1000#15"
#: Two setups, so choosing one is a real choice; the second is the bh SPC-132 measurement's.
PDA_SETUPS = {
    **SETUPS,
    "BH SPC-132": {
        "detectors": {
            "green": {"chs": [0, 8], "micro_time_ranges": [[0, 4095]]},
            "red": {"chs": [1, 9], "micro_time_ranges": [[0, 4095]]},
        },
        "tttr_reading": {"file_type": "SPC-130"},
    },
}


@pytest.fixture
def pda_setups(monkeypatch):
    from chisurf.emtk import detector_cascade

    monkeypatch.setattr(detector_cascade, "detector_setups", lambda: dict(PDA_SETUPS))
    monkeypatch.setattr(detector_cascade, "last_used_setup", lambda: "")
    return PDA_SETUPS


def _pda_reader():
    """A PDA reader of its own (the registered one is shared by every test of the module)."""
    from chisurf.core.experiments.pda2c import Pda2cReader

    return Pda2cReader(
        channels=[[0, 3], [1, 2]],
        micro_time_ranges=[[0, 16000], [0, 16000]],
        name="PTU/HT3/SPC",
    )


def _edit(driver: Driver, target: str, text: str) -> None:
    """Replace the text of a value field as a user does: click, select all, type, Enter."""
    from emtk.events import CONTROL_MODIFIER
    from emtk.keys import KEY_A, KEY_RETURN

    driver.click(target)
    driver.key(KEY_A, modifiers=CONTROL_MODIFIER)
    driver.type(text)
    driver.key(KEY_RETURN)


def test_the_pda_form_drives_the_reader(pda_setups, tmp_path):
    """Setup, rows, time windows and the file list: each click lands on the reader."""
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = _pda_reader()
    app = ReaderSettingsApp(reader)
    loads: list[str] = []
    app.load_files = loads.append  # what the Read data dock wires: a read on its worker
    driver = Driver(app, size=(470, 900))
    driver.frame(3)
    # The first setup fills the rows: its detectors named after the colours.
    assert (reader.detector_setup, reader.channels) == ("Confocal", [[0, 2], [1, 3]])

    driver.click("pda_detector.setup")
    driver.click("BH SPC-132")
    assert reader.detector_setup == "BH SPC-132"
    assert reader.channels == [[0, 8], [1, 9]] and reader.reading_routine == "SPC-130"

    _edit(driver, "pda_detector.channels_1", "1, 9, 10")
    _edit(driver, "pda_detector.window_0", "10-2000;2500-4000")
    assert reader.channels[1] == [1, 9, 10]
    assert reader.micro_time_ranges[0] == [[10, 2000], [2500, 4000]]

    # The time-window list: TW, "+", and Delete on a selected row.
    assert {"10 ph @ 1 ms", "20 ph @ 2 ms", "30 ph @ 3 ms"} <= set(driver.painter.strings)
    _edit(driver, "pda_tw.tw_ms", "4")
    assert reader.minimum_time_window_length == pytest.approx(4e-3)
    driver.click("pda_tw.add_tw")
    assert reader.tw_configs[-1] == (reader.minimum_number_of_photons, pytest.approx(4e-3))

    # Auto load off, then files dropped onto the form join its list.
    driver.click("pda_tw.auto_load")
    assert reader.auto_load is False
    spc = tmp_path / "m000.spc"
    spc.write_bytes(b"\0")
    assert app.on_files_dropped([str(spc), str(tmp_path / "notes.txt"), str(tmp_path)])
    driver.frame(2)
    assert [row["path"] for row in reader.files] == [str(spc), str(tmp_path)]
    # Untick the folder in the table's Use column, then load: only the file is read.
    x, y, w, h = driver.rect("pda_files.file_rows")
    driver.click((x + 12, y + 2.5 * driver.painter.line_height() + 12))
    driver.frame(2)
    assert [row["use"] for row in reader.files] == [True, False]
    driver.screenshot(SHOTS / "emtk_shell_reader_pda_ptu.png")
    driver.click("pda_files.load")
    assert loads == [str(spc)]
    assert reader.files, "Auto load is off: the list stays"
    driver.click("pda_files.clear_files")
    assert reader.files == [] and reader.filename == ""
    app.close()


def test_the_three_colour_pda_form_has_three_rows_and_two_excitations(pda_setups):
    from chisurf.emtk.reader_settings import ReaderSettingsApp

    reader = _pda_reader()
    app = ReaderSettingsApp(reader)
    driver = Driver(app, size=(470, 900))
    driver.frame(3)
    reader.n_colors = 3
    driver.frame(3)
    rects = set(app.form.rects)
    assert {"pda_detector.detector_2", "pda_detector.channels_2"} <= rects
    _edit(driver, "pda_detector.window_1", "8000-16000")
    assert reader.micro_time_ranges[1] == [8000, 16000]
    assert len(reader.detection_windows()) == 5
    driver.screenshot(SHOTS / "emtk_shell_reader_pda_3c.png")
    app.close()


def _reader_child(shell):
    """The Read data dock's reader form: its app and its box in the shell."""
    data = shell.data
    app = data.reader_settings_app(data.read.reader())
    _key, _app, box = shell._drawn[f"reader.{id(app)}"]
    return app, box


def reveal_in_reader(driver: Driver, shell, target: str) -> None:
    """Wheel until *target* of the reader form is fully on screen, as a user does.

    The Read data dock scrolls, and the form inside it scrolls: the dock first, over the strip beside the form,
    until the form's box is in the window, then the form, over its own left edge, until the control is in it.
    """
    height = driver.size[1]
    for _ in range(160):
        app, box = _reader_child(shell)
        x, y, w, h = app.form.rects[target]
        if 0 <= y and y + h <= box[3] and box[1] >= 0 and box[1] + box[3] <= height:
            return
        if box[1] + box[3] > height or box[1] < 0:
            before = box[1]
            driver.wheel(-3 if box[1] > 0 else 3, at=(box[0] + box[2] + 3, 200))
            assert _reader_child(shell)[1][1] != before, "the Read data dock does not scroll to the form"
        else:
            before = y
            driver.wheel(-3 if y > 0 else 3, at=(box[0] + 2, box[1] + box[3] / 2))
            assert _reader_child(shell)[0].form.rects[target][1] != before, (
                f"the form does not scroll to reveal {target}"
            )
    raise AssertionError(f"{target} could not be scrolled into view")


def _click_in_reader(driver: Driver, shell, target: str) -> None:
    """Click a control of the reader form, wheeling the dock and the form first when it lies out of view."""
    reveal_in_reader(driver, shell, target)
    app, box = _reader_child(shell)
    x, y, w, h = app.form.rects[target]
    driver.click((box[0] + x + w / 2, box[1] + y + h / 2))


def _select_pda(shell, driver: Driver) -> None:
    from chisurf.emtk.fit_docks import READ_KEY

    data = shell.data
    data.read.experiment = "PDA"
    data.read.experiment_changed("PDA")
    data.read.setup = "PTU/HT3/SPC"
    shell.docks.focus(READ_KEY)
    driver.frame(3)


@pytest.mark.skipif(not PDA_BURSTS.is_dir(), reason="burst-analysis fixture missing")
def test_a_burst_table_dropped_on_the_pda_form_is_read_into_the_datasets(shell, pda_setups):
    """Drop a ``.bur`` onto the PDA form, read the list: the measurement it names is a dataset."""
    data = shell.data
    # An ordinary window: the form's Load button sits under the file list, at the end of the form, and is
    # reached by scrolling it (``_click_in_reader``).
    driver = Driver(shell, size=(1300, 900))
    driver.frame(2)
    _select_pda(shell, driver)
    reader = data.read.reader()
    saved = (list(reader.files), reader.auto_load, reader.channels, reader.reading_routine)
    try:
        app, _box = _reader_child(shell)
        reader.files[:] = []
        _click_in_reader(driver, shell, "pda_detector.setup")
        driver.click("BH SPC-132")
        assert reader.reading_routine == "SPC-130" and reader.channels == [[0, 8], [1, 9]]
        if reader.auto_load:
            _click_in_reader(driver, shell, "pda_tw.auto_load")
        assert reader.auto_load is False
        table = PDA_BURSTS / "bi4_bur" / "m000.bur"
        assert shell.on_files_dropped([str(table)]), "the focused PDA form takes the drop"
        driver.frame(2)
        assert reader.filename == str(table)
        before = len(data.datasets.datasets)
        if app.load_files is not None:
            _click_in_reader(driver, shell, "pda_files.load")
        else:
            # The dock reads the reader's list when its File field is empty.
            data.read.path = ""
            driver.click("read.load")
        end = time.monotonic() + 120
        while len(data.datasets.datasets) <= before:
            assert "failed" not in str(data.status), data.status
            assert time.monotonic() < end, f"the read did not land: {data.status}"
            driver.frame(1)
            time.sleep(0.02)
        names = [row["name"] for row in data.datasets.datasets]
        assert any(str(name).startswith("m000") for name in names), names
    finally:
        reader.files[:], reader.auto_load = saved[0], saved[1]
        reader.channels, reader.reading_routine = saved[2], saved[3]


#: Qt controls of the Read data dock that belong to another reader: the Qt dock keeps every
#: reader's settings widget alive in a stack, so its inventory counts the CSV reader's too
#: (compared in ``test_emtk_shell_fits.py``).
OTHER_READERS = {
    "columns(csvonly)",
    "mode",
    "noisemodel",
    "none/uniform",
    "photon-noise(suren)",
    "splinelocalvariance(5knots)",
    "fromfile(default)",
    "starchev",
    "x-error",
    "y-error",
    "xcol",
    "ycol",
    "photons",
}
#: PDA controls of the Qt dock that are not drawn in the emtk form (an open ledger item each).
PDA_KNOWN_GAPS: set[str] = set()
#: PDA controls present under another spelling.
PDA_RENAMED = {
    "data": "the dock's + Data button (Qt draws the + as an icon)",
    "dropfileshere.": "the File field's placeholder",
}
_NUMBER = __import__("re").compile(r"^[-+]?(\d+\.?\d*|\.\d+)(e[-+]?\d+)?$")


def test_the_pda_form_has_the_qt_controls(shell, monkeypatch):
    """Control inventory of the Qt Read data dock with the PDA reader, against the emtk dock.

    The before-half is ``shell_s2_models_qt_inventory.json`` (``readers`` → ``pda_ptu``,
    ``capture_shell_s2_models_qt_before.py``), taken with no saved detector setup.
    """
    import json
    import sys

    from chisurf.emtk import detector_cascade
    from chisurf.emtk.pda_sections import load_spec

    monkeypatch.setattr(detector_cascade, "detector_setups", lambda: {})
    monkeypatch.setattr(detector_cascade, "last_used_setup", lambda: "")
    sys.path.insert(0, str(REPO / "test" / "gui"))
    from migration_parity import _normalize_control_text

    before = json.loads(
        Path(__file__).with_name("shell_s2_models_qt_inventory.json").read_text("utf-8")
    )["readers"]["pda_ptu"]
    driver = Driver(shell, size=(1300, 950))
    driver.frame(2)
    _select_pda(shell, driver)
    data = shell.data
    app, _box = _reader_child(shell)
    assert not data.reader_settings_error(data.read.reader())
    found = {_normalize_control_text(t) for t in driver.painter.strings}
    # What the choices offer, as the Qt inventory reads every combo's list.
    model = next(iter(app.drop_handlers)).__self__.model
    options = [*data.read.experiment_names(), *data.read.setup_names()]
    options += [*model.setup_names(), *model.routine_names()]
    from chisurf.emtk.reader_settings import native_reader_spec

    for panel in native_reader_spec(data.read.reader().view_spec())["sections"]:
        for section in panel.get("sections", []):
            options += [str(label) for label in section.get("labels") or []]
    options += [s.get("placeholder", "") for s in load_spec("pda_detector")["sections"]]
    options += [
        json.loads((REPO / "chisurf/emtk/views/read_data.view.json").read_text())["sections"][2][
            "placeholder"
        ]
    ]
    found |= {_normalize_control_text(t) for t in options}

    qt = set(before["controls"])
    lost = {c for c in qt - found if not _NUMBER.match(c)} - OTHER_READERS
    unexplained = lost - PDA_KNOWN_GAPS - set(PDA_RENAMED)
    assert not unexplained, f"Qt PDA controls missing from the emtk form: {sorted(unexplained)}"
    closed = PDA_KNOWN_GAPS & found
    assert not closed, f"these gaps are closed now; strike them: {sorted(closed)}"
