"""The session's dataset list (the Datasets workspace) as it was after each test: rows a test put
in the workspace do not leak into the next test's Input sections."""

import pytest


@pytest.fixture(autouse=True)
def workspace_restored():
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before
