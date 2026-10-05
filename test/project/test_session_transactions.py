"""Transactional project restore tests for the macro entry points."""

import numpy as np
import pytest

import chisurf as cs
from chisurf.core.data import DataCurve
from chisurf.core.project import Project, SessionCodecError, capture_session
from chisurf.macros.core_fit import load_project, load_project_payload


def _curve(uid: str) -> DataCurve:
    x = np.arange(4.0)
    return DataCurve(x=x, y=x, ex=np.ones(4), ey=np.ones(4), unique_identifier=uid)


def test_invalid_staged_restore_preserves_live_datasets_and_fits():
    old_curve = _curve("live")
    cs.imported_datasets[:] = [old_curve]
    cs.fits[:] = []
    project = capture_session([_curve("replacement")], [])
    project.datasets["replacement"]["arrays"]["y"]["values"] = [1.0]

    with pytest.raises(SessionCodecError):
        load_project_payload(project)

    assert cs.imported_datasets == [old_curve]
    assert cs.imported_datasets[0] is old_curve
    assert cs.fits == []


def test_file_read_errors_propagate_and_do_not_clear_live_state(tmp_path):
    old_curve = _curve("still-live")
    cs.imported_datasets[:] = [old_curve]
    cs.fits[:] = []

    with pytest.raises(Exception, match="Could not load project file"):
        load_project(tmp_path / "corrupt.cs.pto")

    assert cs.imported_datasets[0] is old_curve
    assert cs.fits == []
