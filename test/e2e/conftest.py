"""Keep plotting objects owned by the test that created them."""
from contextlib import contextmanager

import pytest


@contextmanager
def close_created_plots():
    """Close new plots and remove only deleted Qt view registry entries."""
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
        try:
            from PyQt5 import sip
            from pyqtgraph.graphicsItems.ViewBox import ViewBox
        except ImportError:
            sip = None
        if sip is not None:
            for view in [v for v in ViewBox.AllViews if sip.isdeleted(v)]:
                ViewBox.AllViews.pop(view, None)
            for name in [n for n, v in ViewBox.NamedViews.items() if sip.isdeleted(v)]:
                ViewBox.NamedViews.pop(name, None)


@pytest.fixture(autouse=True)
def _close_plots_this_test_created():
    """Apply plot ownership cleanup without bootstrapping a Qt application."""
    with close_created_plots():
        yield
