"""Workflow evidence: real TTTR data roundtrips and API equivalence."""

import time
from pathlib import Path

import numpy as np
import pytest
import tttrlib

from chisurf.plugins.tttr.ptu_alex_creator import core
from chisurf.plugins.tttr.ptu_alex_creator.api import AlexRequest, run
from chisurf.plugins.tttr.ptu_alex_creator.gui.app import AlexApp

SAMPLE = Path(__file__).resolve().parents[5] / "test/data/clsm/Leica_SP5.ptu"


def finish(app):
    deadline = time.monotonic() + 20
    while app.job.running and time.monotonic() < deadline:
        app.job.poll()
        time.sleep(0.005)
    assert not app.job.running, "ALEX worker did not finish"


@pytest.fixture
def source(tmp_path):
    if not SAMPLE.is_file():
        pytest.skip("Leica TTTR sample unavailable")
    stream = tttrlib.TTTR(str(SAMPLE))[:5000]
    path = tmp_path / "source.ptu"
    stream.write(str(path))
    return path


def assert_same(first, second):
    a, b = tttrlib.TTTR(str(first)), tttrlib.TTTR(str(second))
    for attr in ("macro_times", "micro_times", "routing_channels", "event_types"):
        np.testing.assert_array_equal(getattr(a, attr), getattr(b, attr))
    assert a.header.json == b.header.json


def test_load_live_preview_and_single_output_matches_core(source, tmp_path):
    app = AlexApp(tmp_path / "preferences.json")
    try:
        assert app.load(source)
        finish(app)
        assert app.model.has_data
        assert sum(app.histogram) == len(app.model._tttr)
        app.model.alex_period = 4000
        app.model.period_shift = 23
        assert app.preview()
        finish(app)
        np.testing.assert_array_equal(app.histogram, core.alex_histogram(str(source), 4000, 23))
        expected, actual = tmp_path / "expected.ptu", tmp_path / "actual.ptu"
        core.convert_file(str(source), str(expected), 4000, 23, "PTU", "Auto")
        assert app.save(actual)
        finish(app)
        assert actual.exists()
        assert_same(expected, actual)
        assert app.outputs == [str(actual)]
        assert not app.save(source)
        assert "preserve" in app.message
    finally:
        app.close()


@pytest.mark.parametrize("mode", ["convert", "merge"])
def test_batch_matches_api_and_snapshot(source, tmp_path, mode):
    app = AlexApp(tmp_path / "preferences.json")
    try:
        second = tmp_path / "second.ptu"
        second.write_bytes(source.read_bytes())
        app.add_paths([source, second, source])
        assert app.model.batch_files == [str(source), str(second)]
        app.model.batch_mode = mode
        app.model.batch_output_folder = str(tmp_path / "native")
        app.model.alex_period = 4000
        app.model.period_shift = 7
        expected = run(
            AlexRequest(
                files=list(app.model.batch_files),
                mode=mode,
                output_dir=str(tmp_path / "reference"),
                alex_period=4000,
                period_shift=7,
            )
        ).output_paths
        assert app.run_batch()
        app.model.alex_period = 3  # Worker owns the request, never mutable UI state.
        finish(app)
        assert len(app.outputs) == len(expected)
        for first, second in zip(expected, app.outputs):
            assert_same(first, second)
    finally:
        app.close()


def test_validation_queue_and_preferences(tmp_path):
    state = tmp_path / "preferences.json"
    app = AlexApp(state)
    try:
        assert not app.save(tmp_path / "empty.ptu")
        assert "load" in app.message.lower()
        assert not app.run_batch()
        assert not app.load(tmp_path / "missing.ptu")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "file.sm").touch()
        (tmp_path / "sub" / "ignore.txt").touch()
        app.add_paths([tmp_path / "sub", tmp_path / "sub"])
        assert len(app.model.batch_files) == 1
        assert not app.run_batch()
        assert "folder" in app.message.lower()
        app.model.alex_period = 1500
        app.model.period_shift = -22
        app.model.batch_mode = "merge"
    finally:
        app.close()
    restored = AlexApp(state)
    try:
        assert restored.model.alex_period == 1500
        assert restored.model.period_shift == -22
        assert restored.model.batch_mode == "merge"
        assert len(restored.model.batch_files) == 1
        assert not restored.model.has_data
    finally:
        restored.close()


def test_all_locales_and_control_tooltips(tmp_path, monkeypatch):
    from emtk import im
    from emtk.i18n import get_locale, set_locale, tr
    from emtk.testing import RecordingPainter

    from chisurf.plugins.tttr.ptu_alex_creator.gui.translations import ROWS

    assert all(len(line.split("|")) == 6 for line in ROWS.splitlines())
    previous = get_locale()
    app = AlexApp(tmp_path / "state.json")
    tips = []
    original = im.set_item_tooltip

    def capture(text, *args, **kwargs):
        tips.append(str(text))
        return original(text, *args, **kwargs)

    monkeypatch.setattr(im, "set_item_tooltip", capture)
    try:
        for locale in ("en", "de", "fr", "es", "pt", "ru"):
            set_locale(locale)
            painter = RecordingPainter()
            tips.clear()
            app.draw(painter, 0, 0, 1200, 800)
            assert len(tips) >= 17
            assert all(tip.strip() for tip in tips)
            assert tr("Run batch") in painter.strings
            app.show_help()
            assert app.help.sections
            app.help.hide()
            app.start_guide()
            assert app.guide.steps[0]["title"] == tr("Load a photon file")  # from guide.json, through the translation table
            app.guide.active = False
            if locale != "en":
                assert tr("Run batch") != "Run batch"
                assert tr("Read the file entered above.") != "Read the file entered above."
    finally:
        app.close()
        set_locale(previous)
