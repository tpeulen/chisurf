"""Keep plotting objects owned by the test that created them."""

from contextlib import contextmanager

import pytest


@contextmanager
def close_created_plots():
    """Close the plots a test created, so Qt owns nothing the test forgot."""
    from qtpy.QtWidgets import QApplication

    from chisurf.gui.chiplot.canvas import ImagePanelHost, PanelHost

    def plots():
        """Return the live top-level plot hosts, if Qt has been initialized."""
        app = QApplication.instance()
        hosts = (PanelHost, ImagePanelHost)
        return [w for w in app.topLevelWidgets() if isinstance(w, hosts)] if app else []

    existing = {id(plot) for plot in plots()}
    try:
        yield
    finally:
        for plot in plots():
            if id(plot) not in existing:
                try:
                    plot.close()
                    plot.deleteLater()
                except RuntimeError:
                    continue


@pytest.fixture(autouse=True)
def _close_plots_this_test_created():
    """Apply plot ownership cleanup without bootstrapping a Qt application."""
    with close_created_plots():
        yield


def pytest_collection_modifyitems(config, items):
    """Mark every test under ``test/e2e`` as ``e2e``.

    The suites are carved out by marker (see ``test/test_suite_partition.py``), so the
    directory must announce itself with the marker rather than rely on a path list in
    the ``test-e2e`` task.
    """
    import pathlib

    here = pathlib.Path(__file__).parent.resolve()
    for item in items:
        if here in pathlib.Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.e2e)
