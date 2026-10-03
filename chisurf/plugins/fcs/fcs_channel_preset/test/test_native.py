"""Real store/JSON workflows and Qt-blocked native renderer coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from chisurf.plugins.fcs.fcs_channel_preset.gui.app import create_app
from chisurf.plugins.fcs.fcs_channel_preset.gui.view_model import FCSChannelViewModel


@pytest.fixture
def files(tmp_path):
    detectors = tmp_path / "detectors.json"
    setup = {
        "windows": {"prompt": [0, 64]},
        "detectors": {
            "green": {"chs": [0], "micro_time_ranges": [[0, 32]]},
            "red": {"chs": [1], "micro_time_ranges": [[0, 32]]},
        },
    }
    detectors.write_text(json.dumps({"setups": {"bench": setup, "other": setup}}))
    presets = tmp_path / "presets.json"
    return detectors, presets


def app_for(files, **kwargs):
    return create_app(detector_file=files[0], preset_file=files[1], **kwargs)


def add(app, name="GR"):
    app.channel_a, app.channel_b, app.pair_name = "green", "red", name
    app.add_pair()


def test_pair_crud_save_reopen_optional_overrides_and_apply(files):
    applied = []
    app = app_for(files, apply_callback=lambda *args: applied.append(args))
    assert app.model.channel_names == ["green", "red"]
    add(app)
    app.model.update_pair(0, "name", "renamed")
    app.model.update_pair(0, "n_bins", None)
    app.model.update_pair(0, "n_casc", 12)
    app.model.update_pair(0, "make_fine", False)
    result = app.apply()
    assert result["pairs"][0] == {
        "name": "renamed",
        "channel_a": "green",
        "channel_b": "red",
        "kind": "CCF",
        "n_casc": 12,
        "make_fine": False,
    }
    assert applied[0] == ("bench", result)
    applied[0][1]["pairs"].clear()
    assert len(app.model.pairs) == 1  # callback receives an independent copy
    reopened = app_for(files)
    assert reopened.model.pairs[0]["name"] == "renamed"
    reopened.model.remove_pair(0)
    assert reopened.save()
    assert app_for(files).model.pairs == []


def test_setup_drafts_restore_state_and_delete_only_fcs(files):
    app = app_for(files)
    add(app)
    app.select_setup("other")
    app.model.add_pair("green", "green")
    app.select_setup("bench")
    assert app.model.pairs[0]["name"] == "GR"
    state = app.export_settings()
    other = app_for(files)
    other.restore_settings(state)
    assert other.model.pairs == app.model.pairs
    assert other.drafts == app.drafts
    other.save()
    before = files[0].read_bytes()
    other.delete()
    assert files[0].read_bytes() == before
    assert "bench" not in json.loads(files[1].read_text())["setups"]
    other.request_close()
    assert other.close_requested


def test_malformed_persisted_drafts_are_ignored(files):
    app = app_for(files)
    app.restore_state({"drafts": {"other": {"pairs": "bad"}, "bench": None}})
    app.select_setup("other")
    assert app.model.pairs == []


@pytest.mark.parametrize(
    "change",
    [
        {"n_bins": -2},
        {"n_casc": "bad"},
        {"n_bins": 1.5},
        {"make_fine": "False"},
        {"channel_a": "unknown"},
    ],
)
def test_invalid_records_cannot_overwrite_saved_config(files, change):
    app = app_for(files)
    add(app)
    app.save()
    before = files[1].read_bytes()
    app.model.pairs[0].update(change)
    with pytest.raises(ValueError):
        app.save()
    assert files[1].read_bytes() == before


def test_duplicate_names_cannot_silently_overwrite_child_rows(files):
    app = app_for(files)
    add(app)
    add(app)
    with pytest.raises(ValueError, match="unique"):
        app.save()


def test_library_export_import_preserves_other_setups_and_active_selection(files, tmp_path):
    app = app_for(files)
    add(app)
    app.save()
    app.select_setup("other")
    app.model.add_pair("green", "green")
    app.save()
    exported = tmp_path / "export.json"
    app.model.export_presets(exported)
    target = tmp_path / "new-presets.json"
    model = FCSChannelViewModel(detector_file=files[0], preset_file=target)
    model.import_presets(exported)
    actual = json.loads(target.read_text())
    assert set(actual["setups"]) == {"bench", "other"}
    assert actual["last_used_setup"] == "other"
    assert model.current_setup == "other"
    assert model.pairs[0]["name"].endswith("ACF")
    corrupt = tmp_path / "invalid.json"
    data = json.loads(exported.read_text())
    data["setups"]["bench"]["pairs"][0]["n_bins"] = 0
    corrupt.write_text(json.dumps(data))
    before = target.read_bytes()
    with pytest.raises(ValueError):
        model.import_presets(corrupt)
    assert target.read_bytes() == before


def test_real_mmfdb_db_path_is_used_for_both_load_and_save(tmp_path, monkeypatch):
    from mmfdb.repository import MFDatabase

    from chisurf.core.fio import setup_store
    from chisurf.core.setup_channel_definition import ChannelDefinition

    db_path = str(tmp_path / "real.db")
    monkeypatch.setattr(setup_store, "resolve_active_user_id", lambda: "preset-user")
    with MFDatabase(db_path) as db:
        db.add_user("preset-user", "Preset user")
        definition = ChannelDefinition(
            settings={
                "windows": {"prompt": [0, 32]},
                "detectors": {"green": {"chs": [0], "micro_time_ranges": [[0, 32]]}},
            },
            db=db,
        )
        definition.save_setup("bench")
    model = FCSChannelViewModel(db_path=db_path)
    assert model.setup_names() == ["bench"]
    model.add_pair("green", "green", "auto")
    model.is_public = True
    assert model.save()
    with MFDatabase(db_path) as db:
        rows = [row for row in db.list_setups() if row.get("name") == "bench"]
        fcs = next(row for row in rows if "fcs_channel_setup" in row["setup_id"])
        assert bool(fcs["is_public"])
        assert db.get_setup(fcs["setup_id"])["fcs_pairs"][0]["name"] == "auto"
    reopened = FCSChannelViewModel(db_path=db_path)
    assert reopened.pairs[0]["name"] == "auto"
    reopened.remove_pair(0)
    assert reopened.save()
    assert FCSChannelViewModel(db_path=db_path).pairs == []
    reopened.delete_preset()
    assert FCSChannelViewModel(db_path=db_path).pairs == []


def test_public_flag_rejects_foreign_owner_edits(files):
    app = app_for(files)
    app.model._can_edit_public = False
    with pytest.raises(PermissionError):
        app.model.is_public = not app.model.is_public


def test_actual_save_pointer_and_delayed_hover_tooltip(files):
    from emtk.app import LEFT_BUTTON
    from emtk.testing import RecordingPainter

    app = app_for(files)
    add(app)
    app.io.wall_clock = False
    for _ in range(2):
        app.draw(RecordingPainter(), 0, 0, 1200, 800)
    x, y, w, h = app.item_rects["Save"]
    app.pointer_move(x + w / 2, y + h / 2)
    app.io.delta_time = 0.3
    for _ in range(3):
        painter = RecordingPainter()
        app.draw(painter, 0, 0, 1200, 800)
    assert any("persist pairs" in s for s in painter.strings)
    app.pointer_press(x + w / 2, y + h / 2, LEFT_BUTTON)
    app.pointer_release(x + w / 2, y + h / 2, LEFT_BUTTON)
    app.draw(RecordingPainter(), 0, 0, 1200, 800)
    assert files[1].is_file()
    assert json.loads(files[1].read_text())["setups"]["bench"]["pairs"][0]["name"] == "GR"


def test_export_to_canonical_json_path_is_a_file_not_database_action(files, tmp_path, monkeypatch):
    from chisurf.core.fluorescence.fcs import channel_setups

    app = app_for(files)
    add(app)
    canonical = tmp_path / "canonical.json"
    monkeypatch.setattr(channel_setups, "FCS_CHANNEL_SETUPS_FILE", canonical)
    app.model.export_presets(canonical)
    assert json.loads(canonical.read_text())["setups"]["bench"]["pairs"][0]["name"] == "GR"


def test_qt_blocked_factory_draw_help_guide_tooltips_and_state(tmp_path, files):
    script = """
import importlib.abc, sys, json
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,*args):
  if name.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide2','PySide6','pyqtgraph'}: raise AssertionError(name)
sys.meta_path.insert(0,Block())
from chisurf.plugins.fcs.fcs_channel_preset.gui.app import create_app
from emtk.testing import RecordingPainter
app=create_app(detector_file=sys.argv[1],preset_file=sys.argv[2])
app.channel_a='green'; app.channel_b='red'; app.add_pair()
from emtk import im
tips=[]; original=im.set_item_tooltip
def tip(value): tips.append(value); return original(value)
im.set_item_tooltip=tip
for w,h in ((1200,800),(800,550)):
 painter=RecordingPainter(); app.draw(painter,0,0,w,h); assert painter.strings
assert all(tips) and len(tips)>20
app.help.show(); app.draw(RecordingPainter(),0,0,1200,800)
app.help.hide(); app.tour.start(); app.draw(RecordingPainter(),0,0,1200,800)
json.dumps(app.export_state())
assert not any(k.split('.')[0] in {'qtpy','PyQt5','PyQt6','PySide6'} for k in sys.modules)
"""
    env = dict(
        os.environ,
        CHISURF_SETTINGS_DIR=str(tmp_path / "settings"),
        MPLCONFIGDIR=str(tmp_path / "mpl"),
    )
    subprocess.run(
        [sys.executable, "-c", script, str(files[0]), str(files[1])],
        env=env,
        check=True,
        timeout=30,
    )
