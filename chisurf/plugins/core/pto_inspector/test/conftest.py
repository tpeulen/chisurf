"""Fixtures of the PTO Inspector tests."""

import pytest


@pytest.fixture(autouse=True)
def workspace_restored():
    """The session's dataset list (the workspace) as it was: Load example and packing add rows."""
    from chisurf.core.api import dataset_container

    held = dataset_container()
    before = list(held)
    yield
    held[:] = before
