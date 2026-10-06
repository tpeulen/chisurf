"""Smoke test of the native wizard (the full port tests are in test_emtk_boarding_parity.py).

Updated for the eight-step wizard: the earlier four pages (Welcome, Repair settings, Status,
Finish) are the steps of the Qt wizard now, and the remembered state is the step index.
"""

from __future__ import annotations

import pytest
from emtk.testing import RecordingPainter

from ..app import BoardingApp


@pytest.fixture(autouse=True)
def temporary_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("CHISURF_SETTINGS_DIR", str(tmp_path / "settings"))
    monkeypatch.setenv("MMFDB_SETTINGS_DIR", str(tmp_path / "mmfdb"))
    monkeypatch.setenv("MMFDB_DATABASE_PATH", str(tmp_path / "mmfdb" / "m.db"))


def test_native_boarding_steps_and_state_roundtrip():
    app = BoardingApp()
    app.model.go_to(4)
    assert app.export_settings()["step"] == 4
    other = BoardingApp()
    other.restore_settings({"step": 7})
    assert other.model.step_id == "finish"


def test_native_boarding_renders_tooltips():
    app = BoardingApp()
    painter = RecordingPainter()
    app.draw(painter, 0, 0, 980, 700)
    assert "Welcome to ChiSurf" in " ".join(painter.strings)
