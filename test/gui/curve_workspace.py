"""Test helpers for the curve tools: put a curve in the Datasets workspace and pick it in a tool's
Input section, the way a person does since the tools no longer open input files."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def workspace_restored():
    """The session's dataset list (the workspace) as it was: a test's curves do not leak into the
    next test's Input section. A plugin's ``conftest.py`` imports it to make it autouse there."""
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before


def add_curve(x: Any, y: Any, name: str = "decay", kind: str = "decay", **kwargs: Any) -> Any:
    """A curve read into the session (as a drop puts it there); returns the dataset."""
    from chisurf.plugins.curve_input import add_curve as _add

    dataset = _add(np.asarray(x, float), np.asarray(y, float), name=name, kind=kind, **kwargs)
    assert dataset is not None, f"{name} did not enter the workspace"
    return dataset


def pick(section: Any, *datasets: Any) -> None:
    """Pick the rows of *datasets* in the Input *section* (a
    :class:`~chisurf.plugins.curve_input.CurveInput`) and hand them over, in that order; a
    many-row section uses *Use selected*."""
    offered = section.workspace_input_rows()
    rows = []
    for dataset in datasets:
        uid = str(getattr(dataset, "unique_identifier", ""))
        found_rows = [r for r in offered if str(r.get("uid")) == uid]
        assert found_rows, f"{getattr(dataset, 'name', uid)} is not offered by the Input section"
        rows.append(found_rows[0])
    found = section._workspace_input()
    if found is not None and found[1].many:
        section.workspace_input_selection = rows
        section.workspace_input_use()
    else:
        section.workspace_input_selected(rows[0])
    assert not section.workspace_input_status.startswith("Could not"), (
        section.workspace_input_status
    )


def pick_curve(section: Any, x: Any, y: Any, name: str = "decay", kind: str = "decay") -> Any:
    """Add a curve to the workspace and pick it in *section*; returns the dataset."""
    dataset = add_curve(x, y, name=name, kind=kind)
    pick(section, dataset)
    return dataset
