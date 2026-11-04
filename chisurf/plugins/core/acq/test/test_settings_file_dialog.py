"""The Load… file chooser for acquisition settings: the model half and the dialog helper.

``Load …`` opens a real emtk file dialog for ``.json`` settings files, ``.ptu`` measurements and
``.pto`` containers. Nothing is loaded and no hardware is touched while browsing: the chosen file
is read and adopted only when it is opened (:meth:`RecordModel.load_settings_path`, through the
existing :meth:`RecordModel.adopt_settings`). The dialog itself is the helper in
``gui/settings_file_dialog.py``, driven here through a synthetic emtk host.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from emtk.i18n import tr

from chisurf.plugins.core.acq.gui.record_app import RecordModel
from chisurf.plugins.core.acq.live import devices, settings_file

REPO = Path(__file__).resolve().parents[5]
PTU = REPO / "test" / "data" / "clsm" / "Leica_SP5.ptu"
PTO_MEMBER = str(REPO / "test" / "data" / "clsm" / "Leica_SP5.pto" / "Leica_SP5.ptu")


@pytest.fixture
def model(tmp_path):
    m = RecordModel(output_dir=tmp_path / "rec", realtime=False)
    m.laser_kind = "simulated"
    yield m
    m.close()


@pytest.fixture(autouse=True)
def no_attached_devices(monkeypatch):
    """The chooser's tests never probe for instruments: enumeration returns nothing."""
    monkeypatch.setattr(devices, "attached_devices", lambda drivers=None: [])


def _json_doc(**over) -> dict:
    doc = settings_file.new_settings(
        name="PIE 485/640",
        run={"duration_s": 12.0, "name": "sample_{date}", "project_data": "link"},
    )
    doc.update(over)
    return doc


# -- the request (the Load … button's model half) -------------------------------------------------
def test_request_settings_file_sets_a_lazy_flag(model):
    assert not getattr(model, "settings_file_requested", False)
    assert model.request_settings_file() is True
    assert model.settings_file_requested is True


def test_request_is_refused_while_a_run_is_on(model, monkeypatch):
    monkeypatch.setattr(RecordModel, "running", property(lambda self: True))
    assert model.request_settings_file() is False
    assert not getattr(model, "settings_file_requested", False)


def test_request_is_refused_while_a_load_is_in_flight(model):
    model.connecting = True
    assert model.request_settings_file() is False
    assert not getattr(model, "settings_file_requested", False)


def test_file_settings_are_blocked_during_a_power_adjustment(model,tmp_path):
    from types import SimpleNamespace
    path=tmp_path/'power_busy.json'
    settings_file.save(_json_doc(),path)
    model.power_servo=SimpleNamespace(active=True)
    try:
        assert not model.request_settings_file()
        assert not model.enabled('request_settings_file')
        assert not model.load_settings_path(path)
        assert model.duration_s!=12.0
    finally:model.power_servo=None


def test_request_is_refused_in_guided_mode(model):
    model.ui_mode = "guided"
    assert model.request_settings_file() is False
    assert not getattr(model, "settings_file_requested", False)


# -- loading a path --------------------------------------------------------------------------------
def test_load_settings_path_json_fills_the_form_and_connects_nothing(model, tmp_path):
    path = tmp_path / "pie.json"
    settings_file.save(_json_doc(), path)
    assert model.load_settings_path(path) is True
    assert model.duration_s == 12.0
    assert model.run_name == "sample_{date}"
    assert model.recording_store == "link"
    assert model.settings_name == "pie.json"
    assert model.device is None and not model.laser_connected
    assert model.settings_file_path == str(path)


def test_load_settings_path_json_applies_explicit_storage(model, tmp_path):
    local, archive = tmp_path / "data", tmp_path / "archive"
    path = tmp_path / "with_storage.json"
    settings_file.save(
        _json_doc(storage={"local_directory": str(local), "archive_directory": str(archive)}),
        path,
    )
    assert model.load_settings_path(path) is True
    assert model.output_dir == local
    assert model.archive_directory == str(archive)


def test_load_settings_path_json_with_broken_storage_is_refused_whole(model, tmp_path):
    path = tmp_path / "broken_storage.json"
    settings_file.save(
        _json_doc(storage={"local_directory": "  ", "archive_directory": "/x"}), path
    )
    out = model.output_dir
    assert model.load_settings_path(path) is False
    assert model.settings_text == tr("Not a settings file")
    assert model.output_dir == out, "a refused file must not change the setup"


def test_load_settings_path_ptu_reads_the_header(model):
    assert PTU.is_file(), f"missing fixture {PTU}"
    assert model.load_settings_path(PTU) is True
    assert model.settings_name == "Leica_SP5.ptu"
    assert model.device_values, "the PTU's TCSPC settings must reach the form"
    assert "Not recorded by the measurement" in model.settings_detail


def test_load_settings_path_pto_member_reads_its_ptu(model):
    assert model.load_settings_path(PTO_MEMBER) is True
    assert model.settings_name == "Leica_SP5.ptu"
    assert model.device_values


def test_load_settings_path_reports_malformed_json(model, tmp_path):
    path = tmp_path / "junk.json"
    path.write_text("{not json", encoding="utf-8")
    assert model.load_settings_path(path) is False
    assert model.settings_text == tr("Not a settings file")
    assert "not valid JSON" in model.settings_detail


def test_load_settings_path_reports_an_unreadable_ptu(model, tmp_path):
    path = tmp_path / "junk.ptu"
    path.write_bytes(b"sure looks like a PTU" * 16)
    assert model.load_settings_path(path) is False
    assert model.settings_text == tr("Not a settings file")
    assert model.settings_detail


def test_load_settings_path_reports_a_missing_file(model, tmp_path):
    assert model.load_settings_path(tmp_path / "nope.ptu") is False
    assert model.settings_detail


def test_load_settings_path_is_refused_while_running(model, tmp_path, monkeypatch):
    path = tmp_path / "pie.json"
    settings_file.save(_json_doc(), path)
    monkeypatch.setattr(RecordModel, "running", property(lambda self: True))
    assert model.load_settings_path(path) is False
    assert model.duration_s != 12.0


def test_load_settings_path_is_refused_in_guided_mode(model, tmp_path):
    path = tmp_path / "pie.json"
    settings_file.save(_json_doc(), path)
    model.ui_mode = "guided"
    assert model.load_settings_path(path) is False
    assert model.duration_s != 12.0


# -- the chooser (gui/settings_file_dialog.py), driven through a synthetic emtk host --------------
import emtk  # noqa: E402
from emtk.testing import RecordingPainter  # noqa: E402

from chisurf.plugins.core.acq.gui.settings_file_dialog import SettingsFileDialog  # noqa: E402

SIZE = (760.0, 560.0)


class Host:
    """Draws the helper into a plain emtk frame, frame by frame, and clicks what it drew."""

    def __init__(self, helper: SettingsFileDialog):
        self.helper = helper
        self.io, self.storage = emtk.IO(), {}
        self.painter = None

    def frame(self) -> bool:
        self.painter = RecordingPainter()
        with emtk.frame(self.painter, (0.0, 0.0, *SIZE), io=self.io, storage=self.storage):
            open_ = self.helper.draw((0.0, 0.0, *SIZE))
        return open_

    def where(self, string: str) -> tuple[float, float]:
        for x, y, w, h, _align, text, *_rest in self.painter.texts:
            if text == string:
                return x + 3.0, y + h / 2.0
        raise AssertionError(f"{string!r} is not drawn: {self.painter.strings}")

    def click(self, string: str) -> None:
        self.frame()
        pos = self.where(string)
        io = self.io
        io.mouse_pos = io.mouse_clicked_pos[0] = pos
        io.mouse_down[0] = io.mouse_clicked[0] = True
        self.frame()
        io.mouse_down[0] = False
        io.mouse_released[0] = True
        self.frame()


@pytest.fixture
def chooser_dir(tmp_path):
    for name in ("pie.json", "run.ptu", "box.pto", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    return tmp_path


def _helper(model, directory) -> SettingsFileDialog:
    return SettingsFileDialog(model, directory=str(directory))


def test_draw_without_a_request_draws_nothing(model, chooser_dir):
    host = Host(_helper(model, chooser_dir))
    assert host.frame() is False
    assert "Open" not in host.painter.strings


def test_the_chooser_opens_on_the_request_and_lists_the_accepted_suffixes(model, chooser_dir):
    assert model.request_settings_file() is True
    host = Host(_helper(model, chooser_dir))
    assert host.frame() is True
    strings = host.painter.strings
    for name in ("pie.json", "run.ptu", "box.pto"):
        assert name in strings, strings
    assert "notes.txt" not in strings, "the chooser offers settings files and measurements"
    assert model.settings_file_requested is False, "the request is one-shot"


def test_choosing_a_json_file_loads_it_and_closes(model, chooser_dir):
    (chooser_dir / "pie.json").write_text(
        settings_file.dumps(_json_doc()), encoding="utf-8"
    )
    model.request_settings_file()
    host = Host(_helper(model, chooser_dir))
    host.frame()
    host.click("pie.json")
    host.click("Open")
    assert host.frame() is False, "the chooser closes after the choice"
    model.wait_connected(10)  # Open adopts in a worker thread, never in the frame
    assert model.settings_name == "pie.json" and model.duration_s == 12.0
    assert model.device is None and not model.laser_connected


def test_choosing_a_ptu_file_loads_its_header(model):
    model.request_settings_file()
    host = Host(_helper(model, PTU.parent))
    host.frame()
    host.click("Leica_SP5.ptu")
    host.click("Open")
    host.frame()
    model.wait_connected(10)
    assert model.settings_name == "Leica_SP5.ptu"
    assert model.device_values, "the measurement's TCSPC settings reach the form"


def test_choosing_a_pto_container_loads_its_measurement(model):
    pto = REPO / "test" / "data" / "clsm" / "Leica_SP5.pto"
    model.request_settings_file()
    host = Host(_helper(model, pto.parent))
    host.frame()
    host.click(pto.name)
    host.click("Open")
    host.frame()
    model.wait_connected(10)
    assert model.settings_name == pto.name
    assert model.device_values


def test_open_runs_off_the_frame_and_reports_unsupported_types(model, chooser_dir, tmp_path, monkeypatch):
    from chisurf.plugins.core.acq.gui.settings_file_dialog import FILTERS

    assert [patterns for _, patterns in FILTERS] == [("*.json", "*.ptu", "*.pto")], (
        "no catch-all or extra filter invites arbitrary files")
    (chooser_dir / "pie.json").write_text(
        settings_file.dumps(_json_doc()), encoding="utf-8"
    )
    # A small JSON adoption can finish before the caller looks again (it did in a full
    # suite run, where the worker had the machine to itself for a scheduler slice), so
    # the visible-connecting contract is pinned with the adoption held open: while it
    # runs, `connecting` is set; the frame thread never blocks on it.
    import threading

    real = RecordModel._adopt_settings_path
    started, gate = threading.Event(), threading.Event()

    def held_adoption(self, path):
        started.set()
        assert gate.wait(10), "the held adoption must be releasable"
        return real(self, path)

    monkeypatch.setattr(RecordModel, "_adopt_settings_path", held_adoption)
    assert model.load_settings_path_async(chooser_dir / "pie.json") is True
    assert started.wait(10), "the adoption runs in its worker thread, not in the caller"
    assert model.connecting, "the adoption is visibly in progress while it runs"
    gate.set()
    model.wait_connected(10)
    assert not model.connecting and model.duration_s == 12.0
    movie = tmp_path / "movie.mp4"
    movie.write_bytes(b"not a settings file")
    assert model.load_settings_path(movie) is False
    assert "Unsupported file type" in model.settings_text
    assert model.duration_s == 12.0, "a refused type leaves the form untouched"


def test_cancel_loads_nothing_and_connects_nothing(model, chooser_dir):
    model.request_settings_file()
    host = Host(_helper(model, chooser_dir))
    host.frame()
    host.click("pie.json")
    host.click("Cancel")
    assert host.frame() is False
    assert model.settings_name == "" and model.duration_s != 12.0
    assert model.device is None and not model.laser_connected
    assert not model.laser_program


def test_closing_the_window_is_a_cancellation(model, chooser_dir):
    model.request_settings_file()
    host = Host(_helper(model, chooser_dir))
    host.frame()
    host.click("×")
    assert host.frame() is False
    assert model.settings_name == "" and model.device is None
