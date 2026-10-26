"""Spot Finder takes its recordings and saved settings from the Datasets workspace."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def workspace_restored():
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before


def _rows(named, path):
    return [r for r in named.workspace_input_rows() if r.get("address") == str(path)]


def test_recordings_and_settings_come_from_the_workspace(tmp_path):
    from chisurf.core.fio.classify import classify
    from chisurf.core.plugin.workspace_input import register_result
    from chisurf.plugins.microscopy.spot_finder.gui.app import (
        SETTINGS_SCHEMA,
        make_app,
        receive_settings,
    )

    app = make_app()
    assert not hasattr(app, "on_files_dropped") and not hasattr(app, "picker")
    repo = next(p for p in Path(__file__).parents if (p / "pyproject.toml").exists())
    recording = repo / "test/data/clsm/Leica_SP5.ptu"
    register_result(str(recording), kind="photons")
    named = app.inputs["files"]
    named.workspace_input_selection = _rows(named, recording)
    named.workspace_input_use()
    assert app.model.files == [str(recording)]

    saved = tmp_path / "spot_finder.json"
    saved.write_text(json.dumps({"schema": SETTINGS_SCHEMA, **app.state_dict()}))
    assert classify(saved) == "setup"  # a drop puts saved settings in the workspace
    app.model.files.clear()
    register_result(str(saved), kind="setup")
    app.inputs["settings"].workspace_input_selected(_rows(app.inputs["settings"], saved)[-1])
    assert app.model.files == [str(recording)] and not app.error
    (tmp_path / "bad.json").write_text("{nope")
    assert not receive_settings(app, {"settings": str(tmp_path / "bad.json")}) and app.error
