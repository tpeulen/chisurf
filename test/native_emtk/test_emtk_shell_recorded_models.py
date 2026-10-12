"""Models that failed only in the emtk shell, driven as a user drives them.

* The shell records every change (undo history, autosave). Reading two files
  with one TXT/CSV reader, and adding a bunching term to an FCS model, each
  made that recording fail -- logged, so the shell looked fine and had no undo.
* ProteinMC's Structure page drew nothing: the structure dataset reached the
  server as an empty curve, which the page handed to chimol.
* A *Lifetime mixture* could not mix a *Lifetime* fit made in the shell.

The shell gets a real in-process server with a fresh session state, as in
``test_emtk_shell_session.py``.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

import numpy as np
import pytest
from emtk.testing import Driver

from chisurf.emtk.fit_docks import ANALYSIS_KEY, DATASETS_KEY, READ_KEY
from chisurf.emtk.main_app import EmtkShellApp

REPO = Path(__file__).resolve().parents[2]
TCSPC = REPO / "test" / "data" / "tcspc" / "decay_fit"
KRISTINE = REPO / "test" / "data" / "fcs" / "kristine" / "Kristine_with_error.cor"
PDB = REPO / "test" / "data" / "atomic_coordinates" / "pdb_files" / "148l.pdb"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
FCS_GENERAL = "FCS (general: diffusion + bunching/anticorr)"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    return tmp_path


@pytest.fixture
def shell(isolated):
    from chisurf.emtk.session import start_session
    from chisurf.server.session import SessionState

    state = SessionState()
    session = start_session(state=state)
    app = EmtkShellApp({}, loader=lambda plugin_id: None)
    app.data.adopt(session)
    app.state = state
    yield app
    app.close()
    session.close()


def _idle(shell) -> bool:
    project = shell.project
    return (
        not shell.data.busy
        and not shell.data._dirty
        and not project.busy
        and not project._record_topic
    )


def _settle(driver: Driver, predicate, what: str, timeout: float = 180.0) -> None:
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, f"timed out waiting for {what}: {driver.app.data.status}"
        driver.frame(1)
        time.sleep(0.02)
    driver.frame(2)


def _load(driver: Driver, shell, path: Path, experiment: str, setup: str) -> dict:
    data = shell.data
    shell.docks.focus(READ_KEY)
    driver.frame(2)
    data.read.experiment = experiment
    data.read.experiment_changed(experiment)
    data.read.setup = setup
    data.read.path = str(path)
    count = len(data.datasets.datasets)
    driver.click("read.load")
    _settle(driver, lambda: _idle(shell) and len(data.datasets.datasets) > count, path.name)
    return data.datasets.datasets[-1]


def _add_fit(driver: Driver, shell, dataset: dict, model: str) -> str:
    data = shell.data
    shell.docks.focus(DATASETS_KEY)
    driver.frame(2)
    data.datasets.select_dataset(dataset)
    data.datasets.model = model
    count = len(data.datasets.fits)
    driver.click("datasets.add_fit")
    _settle(driver, lambda: _idle(shell) and len(data.datasets.fits) > count, f"the {model} fit")
    return data.datasets.fits[-1]["uid"]


def _show(driver: Driver, shell, uid: str) -> None:
    data = shell.data
    data.datasets.select_fit({"uid": uid})
    _settle(driver, lambda: _idle(shell) and data.editor.uid == uid, "the fit's editor")
    shell.docks.focus(ANALYSIS_KEY)
    driver.frame(3)


def _click_editor(driver: Driver, shell, name: str) -> None:
    key = f"editor.{name}"
    last = None
    for _ in range(10):
        driver.frame(1)
        rect = shell.item_rects.get(key)
        if rect is not None and rect == last:
            break
        last = rect
    assert key in shell.item_rects, f"{name} is not drawn"
    driver.click(key)


def _model(shell, uid: str):
    return next(f for f in shell.state.fits if str(f.unique_identifier) == uid).model


def _recording_failures(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno >= logging.ERROR
        and ("Recording" in r.getMessage() or "Autosav" in r.getMessage())
    ]


def test_two_files_of_one_reader_and_a_bunching_term_are_recorded(shell, caplog):
    caplog.set_level(logging.ERROR)
    driver = Driver(shell, size=(1500, 2400))
    project = shell.project
    _settle(driver, lambda: _idle(shell) and project.history_ready, "the session")
    _load(driver, shell, TCSPC / "Prompt.txt", "TCSPC", "TXT/CSV")
    _load(driver, shell, TCSPC / "Decay_577D.txt", "TCSPC", "TXT/CSV")
    kristine = _load(driver, shell, KRISTINE, "FCS", "Seidel Kristine")
    uid = _add_fit(driver, shell, kristine, FCS_GENERAL)
    _show(driver, shell, uid)
    editor = shell.data.editor

    def unfold(sections):
        for section in sections:
            if section.get("type") == "panel" and section.get("title"):
                editor.form.folds[section["title"]] = True
            unfold(section.get("sections") or [])

    unfold(editor.spec.get("sections", []))
    _click_editor(driver, shell, editor.action_for("add", "bunching"))
    _settle(
        driver, lambda: _idle(shell) and len(_model(shell, uid).bunching) == 1, "the bunching term"
    )
    assert _recording_failures(caplog) == []
    assert project.can_undo(), "the changes were recorded"
    # And the recorded project restores: undo the bunching term, redo it.
    project.undo()
    _settle(driver, lambda: _idle(shell), "the undo")
    assert len(_model(shell, uid).bunching) == 0
    project.redo()
    _settle(driver, lambda: _idle(shell), "the redo")
    assert len(_model(shell, uid).bunching) == 1
    assert _recording_failures(caplog) == []
    driver.screenshot(SHOTS / "emtk_shell_recorded_bunching.png")


def test_the_proteinmc_structure_page_shows_the_structure(shell, caplog):
    from chisurf.core.structure import Structure

    caplog.set_level(logging.WARNING)
    driver = Driver(shell, size=(1500, 1100))
    structure = _load(driver, shell, PDB, "Modelling", "StructureReader")
    uid = _add_fit(driver, shell, structure, "ProteinMC")
    assert isinstance(_model(shell, uid).structure, Structure)
    data = shell.data
    _settle(driver, lambda: _idle(shell) and uid in data.windows, "the fit window")
    window = data.windows[uid]
    index = next(i for i, name in enumerate(window.names) if "tructure" in name)
    window.surface.current = index
    shell.docks.focus(window.key)
    for _ in range(20):
        driver.frame(1)
    page = window.plots[index]
    assert page is not None
    assert "Unsupported structure type" not in caplog.text
    assert getattr(page, "viewer", None) is None or page.object_id is not None
    driver.screenshot(SHOTS / "emtk_shell_proteinmc_structure.png")


def _wait_for_rect(driver: Driver, shell, key: str) -> None:
    for _ in range(40):
        driver.frame(1)
        if key in shell.item_rects:
            driver.frame(2)
            return
    raise AssertionError(f"{key} is not drawn: {sorted(k for k in shell.item_rects if 'run' in k)}")


def test_proteinmc_sampling_starts_and_stops_from_its_buttons(shell, tmp_path):
    """The editor's ▶ Sample / ■ Stop (``background_run``) drive the model's run."""
    driver = Driver(shell, size=(1500, 2400))
    structure = _load(driver, shell, PDB, "Modelling", "StructureReader")
    uid = _add_fit(driver, shell, structure, "ProteinMC")
    model = _model(shell, uid)
    # Enough frames that the run is still going when Stop is pressed.
    model.output_directory = str(tmp_path / "proteinmc")
    model.n_written = 10_000
    _show(driver, shell, uid)
    editor = shell.data.editor
    for section in editor.spec.get("sections", []):
        if section.get("type") == "panel" and section.get("title"):
            editor.form.folds[section["title"]] = True
    start = None
    for _ in range(40):
        driver.frame(1)
        start = next(
            (k for k in shell.item_rects if k.startswith("editor.run.") and k.endswith(".start")),
            None,
        )
        if start:
            break
    assert start, "the Sample button is not drawn"
    stop = start[: -len(".start")] + ".stop"
    _wait_for_rect(driver, shell, stop)

    driver.click(start)
    _settle(driver, lambda: model.is_sampling or model.frame_count > 0, "the run to start", 120)
    _settle(driver, lambda: model.frame_count > 0, "a first frame", 120)
    driver.screenshot(SHOTS / "emtk_shell_proteinmc_sampling.png")
    assert model.is_sampling, "the run ended before Stop could be pressed"
    driver.click(stop)
    _settle(driver, lambda: not model.is_sampling, "the run to stop", 120)
    frames = model.frame_count
    assert 0 < frames < model.n_written + 1, frames
    assert model.sampling_status != "starting…"
    driver.frame(5)
    assert model.frame_count == frames, "frames kept arriving after Stop"
    driver.screenshot(SHOTS / "emtk_shell_proteinmc_stopped.png")


def test_a_lifetime_mixture_mixes_a_lifetime_fit_made_in_the_shell(shell):
    driver = Driver(shell, size=(1500, 2400))
    _prompt = _load(driver, shell, TCSPC / "Prompt.txt", "TCSPC", "TXT/CSV")
    decay = _load(driver, shell, TCSPC / "Decay_577D.txt", "TCSPC", "TXT/CSV")
    lifetime = _add_fit(driver, shell, decay, "Lifetime")
    mixture = _add_fit(driver, shell, decay, "Lifetime mixture")
    api = shell.data.session.api
    for uid in (lifetime, mixture):
        assert api.model_curve_set("convolve.irf", _prompt["uid"], fit_uid=uid)["ok"]
    added = api.model_section_call("fit_mixer:", "add", {"fit_uids": [lifetime]}, fit_uid=mixture)
    assert added["ok"], added
    model = _model(shell, mixture)
    assert model.problem is not None
    model.update()
    assert np.all(np.isfinite(np.asarray(model.y))) and np.asarray(model.y).max() > 0
    _show(driver, shell, mixture)
    driver.screenshot(SHOTS / "emtk_shell_lifetime_mixture.png")
