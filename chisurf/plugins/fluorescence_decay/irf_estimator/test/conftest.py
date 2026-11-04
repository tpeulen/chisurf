"""Test fixtures: workspace curves added by a test leave with it."""

from test.gui.curve_workspace import workspace_restored  # noqa: F401

import pytest


@pytest.fixture(autouse=True, scope="session")
def _advanced():
    """The window opens Simple (the source and the estimate); these tests drive every setting,
    so they start in Advanced. The Simple view is ``test_reference_source.py``'s."""
    from chisurf.plugins.fluorescence_decay.irf_estimator.gui.view_model import IRFViewModel

    original = IRFViewModel.__init__

    def init(self, *args, **kwargs):
        original(self, *args, **kwargs)
        self.advanced = True

    patch = pytest.MonkeyPatch()
    patch.setattr(IRFViewModel, "__init__", init)
    yield
    patch.undo()
