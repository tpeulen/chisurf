"""End to end: load -> add fit -> edit -> fit -> undo -> redo -> save -> reload.

Every step goes through the real owner (``chisurf`` process globals), the real
history with its scientific snapshots, and the real ``.cs.pto`` storage; the
reload must give back exactly the snapshot that was saved.
"""

from __future__ import annotations

import numpy as np
import pytest

from test.project.test_e2e_fit_save import E2ELinearModel


@pytest.fixture
def owner(monkeypatch, tmp_path):
    """Headless chisurf owner with one dataset and science-bound history."""
    import chisurf as cs
    from chisurf.core.data import DataCurve
    from chisurf.core.experiments.core.experiment import Experiment
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.transition import replace_project
    from chisurf.history.core import OperationHistory
    from chisurf.macros.core_fit import get_project_payload

    x = np.arange(8, dtype=float)
    dataset = DataCurve(x=x, y=x + 7.5, ey=np.ones_like(x), name="undo_redo_ds")
    experiment = Experiment(name="E2E")
    experiment.add_model_class(E2ELinearModel)
    dataset.experiment = experiment

    history = OperationHistory()
    monkeypatch.setattr(cs, "history", history, raising=False)
    monkeypatch.setattr(cs, "imported_datasets", [dataset])
    monkeypatch.setattr(cs, "fits", [])
    monkeypatch.setattr(cs, "cs", None, raising=False)
    monkeypatch.setattr(cs, "__client__", None, raising=False)
    monkeypatch.setattr(cs, "project_resources", ResourceContext(), raising=False)
    history.configure_science(
        get_project_payload, lambda project: replace_project(project, owner=cs)
    )
    return cs, history


def _p0(cs):
    return float(cs.fits[0].model.p0.value)


def test_undo_redo_then_save_and_reload_is_lossless(owner, tmp_path):
    from chisurf.core.project import storage
    from chisurf.core.project.lifecycle import snapshot_fingerprint
    from chisurf.macros.core_fit import add_fit, get_project_payload

    cs, history = owner
    add_fit(dataset_indices=[0], model_name="E2ELinearModel")
    assert len(cs.fits) == 1
    assert _p0(cs) == 0.0
    # Headless add_fit leaves the range empty (the fit window sets it in the GUI).
    cs.fits[0].fit_range = (0, 8)
    history.record("fit.range.set", "fit range 0-8", persist=False)
    before_edit = history.cursor_index()

    def set_p0(session):
        session.fits[0].model.p0.value = 7.5

    history.apply_edit(set_p0, "parameter.value", "set p0", persist=False)
    edit_index = history.cursor_index()
    assert edit_index == before_edit + 1
    assert _p0(cs) == 7.5

    fit = cs.fits[0]
    fit.run()
    history.record("fit.run.finish", "fit finished", persist=False)
    finish_index = history.cursor_index()
    assert history.can_navigate(finish_index)
    fitted = _p0(cs)
    assert fitted == pytest.approx(7.5, abs=1e-3)

    # Undo past the fit and the edit: p0 is back to its model default.
    assert history.navigate(edit_index - 1)["ok"] is True
    assert _p0(cs) == 0.0
    # Redo the edit, then the fit.
    assert history.navigate(edit_index)["ok"] is True
    assert _p0(cs) == 7.5
    assert history.navigate(finish_index)["ok"] is True
    assert _p0(cs) == pytest.approx(fitted)

    project = get_project_payload("undo_redo")
    path = storage.save_file(project, tmp_path / "e.cs.pto")
    reloaded = storage.load_file(path)
    assert snapshot_fingerprint(reloaded) == snapshot_fingerprint(project)
