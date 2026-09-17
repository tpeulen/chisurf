"""A/B screenshot comparison of the chiplot backends.

Renders the same example plots through each backend and saves paired PNGs so
the output can be compared side by side::

    renders/ab_decay_pg.png     renders/ab_decay_emtk.png
    renders/ab_scatter_pg.png   renders/ab_scatter_emtk.png
    ...

Usage::

    python test/gui/chiplot_ab_screenshots.py                # pyqtgraph + emtk

Both backends paint through QPainter, so they grab headlessly like any other
widget and this script needs no display.

The recipes are deliberately *realistic*: the decay carries a constant
background, because an IRF modelled as a bare Gaussian falls to ``exp(-2304)``
by the end of the window, and a log axis asked to span 300 decades tells you
nothing about either renderer.
"""

from __future__ import annotations

import os
import pathlib
import sys

RENDER_DIR = pathlib.Path("renders")
SUFFIX = {"pyqtgraph": "pg", "emtk": "emtk"}

_backends = [a for a in sys.argv[1:] if not a.startswith("-")] or ["pyqtgraph", "emtk"]
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qtpy import QtCore, QtGui, QtWidgets  # noqa: E402


def _settle(app, rounds=15):
    """Let Qt process layout/expose/paint events before grabbing."""
    for _ in range(rounds):
        app.processEvents()


def _grab_widget(widget: QtWidgets.QWidget, backend: str) -> QtGui.QImage:
    """Grab a widget to a QImage."""
    widget.setAttribute(QtCore.Qt.WA_DontShowOnScreen, True)
    widget.resize(480, 360)
    widget.show()
    _settle(QtWidgets.QApplication.instance())
    return widget.grab().toImage()


# ---------------------------------------------------------------------------
# Example plot recipes — identical data/params for every backend
# ---------------------------------------------------------------------------


def plot_decay(plot):
    """TCSPC-style decay: exponential + IRF over a background, log-y."""
    import numpy as np

    t = np.linspace(0, 50, 512)
    bg = 3.0
    irf = 1000 * np.exp(-((t - 2) ** 2) / 0.5) + bg
    decay = 5000 * np.exp(-t / 4.0) + 1000 * np.exp(-t / 12.0) + bg
    plot.line(t, decay, pen="#ffa629", width=2, name="data")
    plot.line(t, irf, pen="#4284f5", width=2, name="IRF")
    plot.set_labels(left="counts", bottom="t / ns")
    plot.set_log(y=True)
    plot.grid(x=True, y=True)
    plot.legend()


def plot_scatter(plot):
    """FRET efficiency scatter: a 2-D cloud."""
    import numpy as np

    rng = np.random.default_rng(42)
    n = 2000
    e = rng.beta(5, 5, n)
    tau = 0.5 + 3.0 * (1 - e) + rng.normal(0, 0.2, n)
    plot.scatter(e, tau, size=5, brush="#26a298", pen=None, symbol="o")
    plot.set_labels(left="tau / ns", bottom="E")
    plot.grid(x=True, y=True)


def plot_bars(plot):
    """Draw a FRET histogram."""
    import numpy as np

    bins = np.linspace(0, 1, 40)
    centers = (bins[:-1] + bins[1:]) / 2
    counts = 80 * np.exp(-((centers - 0.5) ** 2) / 0.02)
    plot.bars(centers, counts, width=0.02, brush="#3b674a", pen="#8fd3a5")
    plot.set_labels(left="counts", bottom="E")
    plot.grid(y=True)


def plot_image(plot):
    """Draw a 2-D heatmap."""
    import numpy as np

    x = np.linspace(-3, 3, 100)
    y = np.linspace(-3, 3, 100)
    X, Y = np.meshgrid(x, y)
    data = np.exp(-(X**2 + Y**2) / 2.0) * np.sin(3 * np.arctan2(Y, X))
    plot.image(data, colormap="RdBu")
    plot.set_labels(left="y", bottom="x")


def plot_region(plot):
    """Decay with a fit-range region and a dashed model line."""
    import numpy as np

    t = np.linspace(0, 50, 256)
    data = 5000 * np.exp(-t / 4.0)
    model = 4900 * np.exp(-t / 3.8)
    plot.line(t, data, pen="#ffa629", width=2, name="data")
    plot.line(t, model, pen="#d400cd", width=2, style="dash", name="model")
    plot.region((5.0, 40.0), brush="#26a29844", movable=True)
    plot.set_labels(left="counts", bottom="t / ns")
    plot.grid(x=True, y=True)
    plot.legend()


def plot_errorbars(plot):
    """Draw a weighted residual panel: markers with error bars around zero."""
    import numpy as np

    rng = np.random.default_rng(7)
    x = np.arange(30, dtype=float)
    y = rng.normal(0, 1, len(x))
    err = np.full(len(x), 1.0)
    plot.errorbars(x, y, height=2 * err, pen="#888888")
    plot.scatter(x, y, size=6, brush="#ffa629", pen=None, symbol="o")
    plot.hline(0.0, pen="#ff5555")
    plot.set_labels(left="w. res.", bottom="channel")
    plot.grid(y=True)


RECIPES = {
    "decay": plot_decay,
    "scatter": plot_scatter,
    "bars": plot_bars,
    "image": plot_image,
    "region": plot_region,
    "errorbars": plot_errorbars,
}


def _make_plot(backend_name: str):
    """Build a chiplot Plot using the given backend."""
    import chisurf.gui.chiplot.backends as backends

    backends._active = None
    os.environ["CHISURF_PLOT_BACKEND"] = backend_name
    from chisurf.gui.chiplot.canvas import Plot

    return Plot()


def main():
    """Render every recipe on every requested backend."""
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    failures = 0

    for name, recipe in RECIPES.items():
        for backend in _backends:
            suffix = SUFFIX.get(backend, backend)
            print(f"  {name} / {backend} ...", end=" ", flush=True)
            plot = None
            try:
                plot = _make_plot(backend)
                recipe(plot)
                img = _grab_widget(plot, backend)
                path = RENDER_DIR / f"ab_{name}_{suffix}.png"
                img.save(str(path))
                print(f"saved {path} ({img.width()}x{img.height()})")
            except Exception as exc:
                failures += 1
                print(f"FAILED: {type(exc).__name__}: {exc}")
                import traceback

                traceback.print_exc()
            finally:
                if plot is not None:
                    plot.close()
                app.processEvents()

    print(f"\nDone ({failures} failure(s)). Compare: open {RENDER_DIR}/ab_*.png")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
