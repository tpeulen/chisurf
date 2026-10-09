"""Native header editor isolation, validation and lossless scientific copies."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.tttr.tttr_header_edit.gui.view_model import HeaderEditorViewModel


def test_native_factory_draw_without_qt():
    script = """
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from emtk.pil_painter import PilPainter
from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app
app=create_app()
app.draw(PilPainter(1200,800),0,0,1200,800)
app.close()
"""
    result = subprocess.run([sys.executable, "-c", script], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_conversion_arrays_booleans_timing_and_invalid_edits():
    model = HeaderEditorViewModel()
    assert model.convert_value_by_type("1e-9", "Float8") == 1e-9
    assert model.convert_value_by_type("[1,2.5]", "Float8Array") == [1, 2.5]
    assert model.convert_value_by_type("1", "Bool") is True
    assert model.convert_value_by_type("0xFF", "BitSet64") == 255
    before = model.json_text
    with pytest.raises(ValueError):
        model.set_tags([{"name": "x", "type": "Float8", "value": "oops", "idx": -1}])
    assert model.json_text == before
    with pytest.raises(ValueError):
        model.convert_value_by_type("nan", "Float8")


def test_unknown_tag_types_survive_table_commit():
    from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

    app = create_app(
        json.dumps({"tags": [{"name": "custom", "type": 12345, "value": "raw", "idx": -1}]})
    )
    app.header_gui._commit()
    assert app.model.tags == [{"name": "custom", "type": 12345, "value": "raw", "idx": -1}]
    app.close()


def test_load_runs_in_background_and_publishes_only_when_polled(monkeypatch):
    from threading import Event

    from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

    entered, release = Event(), Event()

    def load(model, path):
        entered.set()
        assert release.wait(5)
        model.opened_path = path
        model.load_json('{"tags":[]}')

    monkeypatch.setattr(HeaderEditorViewModel, "load_file", load)
    app = create_app()
    try:
        assert app.load("synthetic.ptu")
        assert entered.wait(5)
        assert app.model.opened_path is None
        assert not app.load("second.ptu")
        release.set()
        app.job.future.result(timeout=5)
        assert app.model.opened_path is None
        app.job.poll()
        assert app.model.opened_path == "synthetic.ptu"
        assert app.header_gui._rows == []
    finally:
        release.set()
        app.close()


def test_failed_writer_preserves_existing_destination(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import tttrlib

    class BrokenWriter:
        header = SimpleNamespace(json='{"tags":[]}', set_json=lambda _: None)
        macro_times = micro_times = routing_channels = event_types = []

        def append_events(self, **kwargs):
            pass

        def write(self, path):
            Path(path).write_bytes(b"partial")
            raise OSError("write failed")

    monkeypatch.setattr(tttrlib, "TTTR", lambda *args: BrokenWriter())
    model = HeaderEditorViewModel()
    model.opened_path = str(tmp_path / "source.ptu")
    destination = tmp_path / "destination.ptu"
    destination.write_bytes(b"original destination")
    with pytest.raises(OSError, match="write failed"):
        model.save(destination)
    assert destination.read_bytes() == b"original destination"
    assert not list(tmp_path.glob(".header-*"))


def test_native_save_preserves_all_event_arrays_and_source(tmp_path):
    import tttrlib

    from chisurf.plugins.tttr.tttr_header_edit.gui.native import create_app

    source = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"
    if not source.exists():
        pytest.skip("Real PTU fixture unavailable")
    digest = hashlib.sha256(source.read_bytes()).digest()
    app = create_app()
    try:
        assert app.load(source)
        app.job.future.result(timeout=30)
        app.job.poll()
        app.header_gui._rows.append(
            {"name": "Native_Test", "type": "AnsiString", "value": "preserved", "idx": "-1"}
        )
        output = tmp_path / "edited.PTU"
        assert app.save(output)
        app.job.future.result(timeout=30)
        app.job.poll()
        assert output.is_file()
        original, saved = tttrlib.TTTR(str(source)), tttrlib.TTTR(str(output))
        for attr in ("macro_times", "micro_times", "routing_channels", "event_types"):
            np.testing.assert_array_equal(getattr(original, attr), getattr(saved, attr))
        assert any(tag["name"] == "Native_Test" for tag in json.loads(saved.header.json)["tags"])
        assert hashlib.sha256(source.read_bytes()).digest() == digest
        with pytest.raises(ValueError, match="source"):
            app.model.save(source)
    finally:
        app.close()
