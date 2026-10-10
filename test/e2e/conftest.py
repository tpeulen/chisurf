"""Keep plotting objects owned by the test that created them."""
from contextlib import contextmanager

import pytest


@contextmanager
def close_created_plots():
    """Close the plots a test created, so Qt owns nothing the test forgot."""
    from qtpy.QtWidgets import QApplication

    from chisurf.gui.chiplot.canvas import Plot

    def plots():
        """Return the live top-level plots, if Qt has been initialized."""
        app = QApplication.instance()
        return [w for w in app.topLevelWidgets() if isinstance(w, Plot)] if app else []

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
