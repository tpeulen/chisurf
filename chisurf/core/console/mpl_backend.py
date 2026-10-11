"""The console's matplotlib backend: ``module://chisurf.core.console.mpl_backend``.

Figures are drawn by Agg and published into the console that is running the
cell, as a PNG in its transcript -- what a Jupyter notebook does with
``matplotlib_inline``, without IPython. Three ways reach it:

* the end of every cell (:func:`chisurf.core.console.mpl_inline.flush_figures`,
  a post-execute hook), so ``plt.plot(x, y)`` alone shows the plot;
* ``plt.show()`` (:func:`show`), which publishes at once, mid-cell;
* ``fig.show()`` (:meth:`FigureManager.show`), which publishes one figure.

No window ever opens and nothing blocks: this module is imported only by
matplotlib, when the console selected it (see
:func:`chisurf.core.console.mpl_inline.install`).
"""

from __future__ import annotations

from matplotlib.backend_bases import FigureManagerBase
from matplotlib.backends.backend_agg import FigureCanvasAgg

__all__ = ["FigureCanvas", "FigureManager", "show"]


class FigureManager(FigureManagerBase):
    """A figure's manager: ``show`` puts it in the console instead of a window."""

    def show(self) -> None:
        """Publish this figure to the running console (``fig.show()``) and close it.

        Closed as ``plt.show()`` closes what it shows, or the end of the cell
        would publish the same figure a second time.
        """
        from chisurf.core.console import mpl_inline

        figure = self.canvas.figure
        if mpl_inline.publish_figure(figure):
            import matplotlib.pyplot as pyplot

            pyplot.close(figure)


class FigureCanvas(FigureCanvasAgg):
    """Agg, with the console's manager."""

    manager_class = FigureManager


def show(close: bool | None = None, block: bool | None = None) -> None:
    """``plt.show()``: publish every open figure to the console and close them.

    Parameters
    ----------
    close : bool, optional
        Close the figures afterwards (the default), as the end of a cell does.
    block : bool, optional
        Accepted for matplotlib's signature; nothing here ever blocks.
    """
    from chisurf.core.console import mpl_inline

    mpl_inline.flush_figures(None, close=close is not False)
