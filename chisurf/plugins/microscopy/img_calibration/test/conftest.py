"""Shared fixtures for this directory's tests."""

import pytest

from .test_emtk_calibration_parity import spc  # noqa: F401


@pytest.fixture(autouse=True)
def workspace_restored():
    """The Datasets workspace as it was: a test's rows do not leak into the next test."""
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before


def pick(app, name, *paths, kind="photons"):
    """Put *paths* in the Datasets workspace (as a drop does) and pick them in Input section *name*."""
    from chisurf.core.plugin.workspace_input import register_result

    named = app.inputs[name]
    rows = []
    for path in paths:
        register_result(str(path), kind=kind)
        found = [r for r in named.workspace_input_rows() if r.get("address") == str(path)]
        assert found, f"{path} is not offered by the {name!r} Input section"
        rows.append(found[-1])
    spec = named._workspace_input()
    if spec is not None and spec[1].many:
        named.workspace_input_selection = rows
        named.workspace_input_use()
    else:
        named.workspace_input_selected(rows[-1])
    return named.workspace_input_status
