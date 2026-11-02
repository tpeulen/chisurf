"""The workflow tests run whole pipelines, which register their runs in the session's dataset list.

That list -- and the session folder of the project's analysis containers -- is process-wide: left
behind, a later test file that expects an empty workspace (the
BVA and 2CDE input sections) found this file's runs in it and failed by test order.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _workspace_restored(tmp_path, monkeypatch):
    """The dataset list restored, and the project's analysis containers (whose runs the workspace
    lists) in a folder of this test's own."""
    from chisurf.core.api import dataset_container
    from chisurf.core.project import analysis

    monkeypatch.setenv("CHISURF_ANALYSIS_DIR", str(tmp_path / "analysis-session"))
    monkeypatch.setattr(analysis, "_SESSION", None)
    held = dataset_container()
    before = list(held)
    yield
    held[:] = before
