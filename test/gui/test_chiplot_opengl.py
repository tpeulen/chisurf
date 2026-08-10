"""Tests for the chiplot OpenGL backend and backend-selection machinery.

These run headlessly. The contract/structure tests do not need a GL
context; the construction tests build widgets (QOpenGLWidget can be
constructed without a display) and verify the drawing API stores state
correctly. Rendering-pixel tests require a real GL context and are
gated behind ``--run-slow``.
"""

from __future__ import annotations

import os

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.gui

pytest.importorskip("qtpy")
pytest.importorskip("OpenGL")

from qtpy import QtWidgets  # noqa: E402

from chisurf.gui.chiplot import handles as H  # noqa: E402
from chisurf.gui.chiplot import style as S  # noqa: E402
from chisurf.gui.chiplot.backends import (  # noqa: E402
    _active as _cached_backend,
    available_backends,
    base,
    set_backend,
)


@pytest.fixture(scope="module")
def qapp():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_both_backends_registered():
    assert "pyqtgraph" in available_backends()
    assert "opengl" in available_backends()


def test_available_backends_sorted():
    backends = available_backends()
    assert backends == sorted(backends)


# ---------------------------------------------------------------------------
# Backend contract (structure, no GL context needed)
# ---------------------------------------------------------------------------

def test_opengl_backend_contract():
    """Every abstract method in the contract is implemented (no gaps)."""
    from chisurf.gui.chiplot.backends import opengl as glb

    for abstract, concrete in [
        (base.Canvas, glb._GlCanvas),
        (base.GridCanvas, glb._GlGrid),
        (base.ImageViewCanvas, glb._GlImageView),
        (base.Backend, glb.OpenGLBackend),
    ]:
        unimpl = sorted(getattr(concrete, "__abstractmethods__", ()))
        assert not unimpl, f"{concrete.__name__} does not implement {unimpl}"


def test_opengl_backend_signature_match():
    """Concrete signatures cover the abstract ones."""
    import inspect

    from chisurf.gui.chiplot.backends import opengl as glb

    for abstract, concrete in [
        (base.Canvas, glb._GlCanvas),
        (base.Backend, glb.OpenGLBackend),
    ]:
        for name, method in vars(abstract).items():
            if not getattr(method, "__isabstractmethod__", False) or isinstance(method, property):
                continue
            expected = set(inspect.signature(method).parameters)
            actual = set(inspect.signature(getattr(concrete, name)).parameters)
            missing = expected - actual
            assert not missing, f"{concrete.__name__}.{name} lacks {sorted(missing)}"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def test_opengl_backend_factory_creates_canvases(qapp):
    from chisurf.gui.chiplot.backends import opengl as glb
    backend = glb.OpenGLBackend()
    canvas = backend.create_canvas()
    grid = backend.create_grid()
    iv = backend.create_image_view()
    assert isinstance(canvas, base.Canvas)
    assert isinstance(grid, base.GridCanvas)
    assert isinstance(iv, base.ImageViewCanvas)
    assert backend.name == "opengl"
    assert backend.raw_module() is None


# ---------------------------------------------------------------------------
# Handle creation (no GL context needed — handles just store state)
# ---------------------------------------------------------------------------

@pytest.fixture
def gl_canvas(qapp):
    from chisurf.gui.chiplot.backends import opengl as glb
    backend = glb.OpenGLBackend()
    return backend.create_canvas()


def test_gl_curve_create_and_update(gl_canvas):
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    c = gl_canvas.add_curve(x, y, pen=S.Pen(S.Color(255, 0, 0)))
    assert c.visible
    c.set_data(x, y * 2)
    rx, ry = c.get_data()
    np.testing.assert_allclose(ry, y * 2)
    c.set_opacity(0.5)
    c.hide()
    assert not c.visible
    c.show()
    assert c.visible


def test_gl_scatter_create(gl_canvas):
    x = np.random.rand(50)
    y = np.random.rand(50)
    s = gl_canvas.add_scatter(
        x, y, size=8, pen=None, brush=S.Brush(S.Color(0, 128, 255)),
        symbol="o")
    rx, ry = s.get_data()
    assert len(rx) == 50
    s.set_data(x[:10], y[:10])
    rx2, ry2 = s.get_data()
    assert len(rx2) == 10


def test_gl_bars_create(gl_canvas):
    x = np.arange(5, dtype=float)
    h = np.array([3, 1, 4, 1, 5], dtype=float)
    b = gl_canvas.add_bars(x, h, width=0.8, pen=None, brush=S.Brush(S.Color(100, 200, 50)))
    b.set_data(x, h * 2)


def test_gl_image_create(gl_canvas):
    data = np.random.rand(16, 16).astype(np.float32)
    img = gl_canvas.add_image(data)
    img.set_levels(0.0, 1.0)
    img.set_colormap("viridis")
    img.set_rect(0, 0, 16, 16)


def test_gl_region_and_marker(gl_canvas):
    r = gl_canvas.add_region(
        (1.0, 3.0), orientation=H.Orientation.VERTICAL,
        movable=True, brush=S.Brush(S.Color(0, 200, 200, 50)),
        pen=S.Pen(S.Color(0, 200, 200)))
    assert r.bounds == (1.0, 3.0)
    r.set_bounds(2.0, 5.0)
    assert r.bounds == (2.0, 5.0)
    r.set_limits(0.0, 10.0)

    m = gl_canvas.add_marker(
        4.0, orientation=H.Orientation.HORIZONTAL,
        movable=True, pen=S.Pen(S.Color(255, 0, 0)))
    assert m.value == 4.0
    m.set_value(6.0)
    assert m.value == 6.0


def test_gl_text_handle(gl_canvas):
    t = gl_canvas.add_text("hello", (1.0, 2.0), color=S.Color(0, 0, 0))
    assert t.text == "hello"
    t.text = "world"
    assert t.text == "world"
    t.set_position(3.0, 4.0)


def test_gl_remove_and_clear(gl_canvas):
    x = np.linspace(0, 1, 10)
    y = x ** 2
    c1 = gl_canvas.add_curve(x, y, pen=S.Pen(S.Color(0, 0, 0)))
    c2 = gl_canvas.add_curve(x, y * 2, pen=S.Pen(S.Color(255, 0, 0)))
    assert len(gl_canvas._handles) == 2
    gl_canvas.remove(c1)
    assert c1 not in gl_canvas._handles
    gl_canvas.clear()
    assert len(gl_canvas._handles) == 0


def test_gl_grid_panels(qapp):
    from chisurf.gui.chiplot.backends import opengl as glb
    backend = glb.OpenGLBackend()
    grid = backend.create_grid()
    p1 = grid.add_panel(row=0, col=0)
    p2 = grid.add_panel(row=0, col=1)
    assert isinstance(p1, base.Canvas)
    assert isinstance(p2, base.Canvas)
    grid.clear()


def test_gl_view_range(gl_canvas):
    gl_canvas.set_range(x=(0, 10), y=(-1, 1))
    (x0, x1), (y0, y1) = gl_canvas.get_range()
    assert (x0, x1) == (0, 10)
    assert (y0, y1) == (-1, 1)
    gl_canvas.enable_auto_range(x=True, y=True)
    gl_canvas.auto_range()


def test_gl_labels_and_log(gl_canvas):
    gl_canvas.set_labels(left="counts", bottom="t / ns")
    gl_canvas.set_title("decay")
    gl_canvas.set_log(y=True)
    gl_canvas.set_grid(x=True, y=True)


def test_gl_callbacks(gl_canvas):
    clicks = []
    moves = []
    ranges = []
    gl_canvas.on_click(lambda x, y, btn: clicks.append((x, y)))
    gl_canvas.on_mouse_move(lambda x, y: moves.append((x, y)))
    gl_canvas.on_range_changed(lambda xr, yr: ranges.append((xr, yr)))


# ---------------------------------------------------------------------------
# Backend selection / settings
# ---------------------------------------------------------------------------

def test_backend_resolution_env_var(qapp):
    """CHISURF_PLOT_BACKEND overrides everything."""
    import chisurf.gui.chiplot.backends as backends
    old_active = backends._active
    old_env = os.environ.pop("CHISURF_PLOT_BACKEND", None)
    try:
        os.environ["CHISURF_PLOT_BACKEND"] = "opengl"
        backends._active = None
        b = backends.get_backend()
        assert b.name == "opengl"
    finally:
        os.environ.pop("CHISURF_PLOT_BACKEND", None)
        if old_env:
            os.environ["CHISURF_PLOT_BACKEND"] = old_env
        backends._active = old_active


# ---------------------------------------------------------------------------
# UX parity: the same behaviours the pyqtgraph tests cover
# ---------------------------------------------------------------------------

@pytest.fixture
def gl_backend(qapp):
    """Force the OpenGL backend for the duration of one test."""
    import chisurf.gui.chiplot.backends as backends
    old_active = backends._active
    old_env = os.environ.pop("CHISURF_PLOT_BACKEND", None)
    backends._active = None
    os.environ["CHISURF_PLOT_BACKEND"] = "opengl"
    from chisurf.gui.chiplot.canvas import Plot
    yield Plot
    backends._active = old_active
    if old_env:
        os.environ["CHISURF_PLOT_BACKEND"] = old_env


def test_gl_context_menu_enabled(gl_backend):
    """The GL backend does not provide a native menu, so chiplot's menu fires."""
    plot = gl_backend()
    assert not plot._canvas.provides_native_menu()
    assert plot._context_menu_enabled


def test_gl_add_menu_action_registers(gl_backend):
    """Custom menu actions register on the GL backend."""
    plot = gl_backend()
    fired = []
    plot.add_menu_action("Do thing", lambda: fired.append(True))
    assert plot._extra_menu_actions[0][0] == "Do thing"
    plot._extra_menu_actions[0][1]()
    assert fired == [True]


def test_gl_menu_enabled_round_trip(gl_backend):
    """set_menu_enabled / menu_enabled round-trip on the GL backend."""
    plot = gl_backend()
    plot.set_menu_enabled(False)
    assert plot.menu_enabled() is False
    plot.set_menu_enabled(True)
    assert plot.menu_enabled() is True


def test_gl_set_interactive_returns_self(gl_backend):
    """set_interactive returns self for chaining."""
    plot = gl_backend()
    r = plot.set_interactive(mouse=False, menu=False)
    assert r is plot


def test_gl_clicked_signal_wired(gl_backend):
    """The clicked signal is connectable and emits (x, y)."""
    plot = gl_backend()
    got = []
    plot.clicked.connect(lambda x, y: got.append((x, y)))
    plot.clicked.emit(1.0, 2.0)
    assert got == [(1.0, 2.0)]


def test_gl_autoscale_fits_data(gl_backend):
    """autoscale fits the view to the data range."""
    import numpy as np
    plot = gl_backend()
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    plot.line(x, y, pen=S.Pen(S.Color(255, 128, 0)))
    plot.autoscale()
    (x0, x1), (y0, y1) = plot.get_range()
    assert x0 <= 0 and x1 >= 10
    assert y0 <= -1 and y1 >= 1


def test_gl_export_csv(gl_backend, tmp_path):
    """export_csv writes named series columns."""
    import numpy as np
    plot = gl_backend()
    x = np.array([0, 1, 2])
    y = np.array([3, 4, 5])
    plot.line(x, y, pen=S.Pen(S.Color(255, 0, 0)), name="signal")
    path = tmp_path / "gl_export.csv"
    plot.export_csv(str(path))
    text = path.read_text()
    assert "signal" in text
    assert "3" in text


def test_gl_set_xlim_ylim(gl_backend):
    """set_xlim / set_ylim set the view range."""
    plot = gl_backend()
    plot.set_xlim(0, 10)
    plot.set_ylim(-1, 1)
    (x0, x1), (y0, y1) = plot.get_range()
    assert (x0, x1) == (0, 10)
    assert (y0, y1) == (-1, 1)


def test_gl_link_x(gl_backend):
    """link_x shares the x-axis range between two plots."""
    plot_a = gl_backend()
    plot_b = gl_backend()
    plot_a.link_x(plot_b)
    plot_a.set_xlim(5, 15)
    (x0, x1), _ = plot_b.get_range()
    assert (x0, x1) == (5, 15)


def test_gl_chaining_returns_self(gl_backend):
    """All Plot setters return self for chaining."""
    plot = gl_backend()
    assert plot.set_labels(left="y") is plot
    assert plot.set_title("t") is plot
    assert plot.set_log(y=True) is plot
    assert plot.grid(x=True) is plot
    assert plot.set_background("k") is plot
    assert plot.set_aspect_locked(True) is plot
    assert plot.set_context_menu_enabled(True) is plot
    assert plot.set_menu_enabled(True) is plot
    assert plot.on_range_changed(lambda xr, yr: None) is plot


def test_gl_clear_resets(gl_backend):
    """clear() removes all handles."""
    import numpy as np
    plot = gl_backend()
    plot.line([0, 1], [0, 1], pen=S.Pen(S.Color(255, 0, 0)))
    assert len(plot._canvas._handles) == 1
    plot.clear()
    assert len(plot._canvas._handles) == 0
    assert plot._series == []


def test_backend_set_backend(qapp):
    import chisurf.gui.chiplot.backends as backends
    old_active = backends._active
    old_env = os.environ.pop("CHISURF_PLOT_BACKEND", None)
    try:
        backends._active = None
        set_backend("opengl")
        b = backends.get_backend()
        assert b.name == "opengl"
    finally:
        os.environ.pop("CHISURF_PLOT_BACKEND", None)
        if old_env:
            os.environ["CHISURF_PLOT_BACKEND"] = old_env
        backends._active = old_active


# ---------------------------------------------------------------------------
# UX parity: the same behaviours the pyqtgraph tests cover
# ---------------------------------------------------------------------------

@pytest.fixture
def gl_backend(qapp):
    """Force the OpenGL backend for the duration of one test."""
    import chisurf.gui.chiplot.backends as backends
    old_active = backends._active
    old_env = os.environ.pop("CHISURF_PLOT_BACKEND", None)
    backends._active = None
    os.environ["CHISURF_PLOT_BACKEND"] = "opengl"
    from chisurf.gui.chiplot.canvas import Plot
    yield Plot
    backends._active = old_active
    if old_env:
        os.environ["CHISURF_PLOT_BACKEND"] = old_env


def test_gl_context_menu_enabled(gl_backend):
    """The GL backend does not provide a native menu, so chiplot's menu fires."""
    plot = gl_backend()
    assert not plot._canvas.provides_native_menu()
    assert plot._context_menu_enabled


def test_gl_add_menu_action_registers(gl_backend):
    """Custom menu actions register on the GL backend."""
    plot = gl_backend()
    fired = []
    plot.add_menu_action("Do thing", lambda: fired.append(True))
    assert plot._extra_menu_actions[0][0] == "Do thing"
    plot._extra_menu_actions[0][1]()
    assert fired == [True]


def test_gl_menu_enabled_round_trip(gl_backend):
    """set_menu_enabled / menu_enabled round-trip on the GL backend."""
    plot = gl_backend()
    plot.set_menu_enabled(False)
    assert plot.menu_enabled() is False
    plot.set_menu_enabled(True)
    assert plot.menu_enabled() is True


def test_gl_set_interactive_returns_self(gl_backend):
    """set_interactive returns self for chaining."""
    plot = gl_backend()
    r = plot.set_interactive(mouse=False, menu=False)
    assert r is plot


def test_gl_clicked_signal_wired(gl_backend):
    """The clicked signal is connectable and emits (x, y)."""
    plot = gl_backend()
    got = []
    plot.clicked.connect(lambda x, y: got.append((x, y)))
    plot.clicked.emit(1.0, 2.0)
    assert got == [(1.0, 2.0)]


def test_gl_autoscale_fits_data(gl_backend):
    """autoscale fits the view to the data range."""
    import numpy as np
    plot = gl_backend()
    x = np.linspace(0, 10, 100)
    y = np.sin(x)
    plot.line(x, y, pen=S.Pen(S.Color(255, 128, 0)))
    plot.autoscale()
    (x0, x1), (y0, y1) = plot.get_range()
    assert x0 <= 0 and x1 >= 10
    assert y0 <= -1 and y1 >= 1


def test_gl_export_csv(gl_backend, tmp_path):
    """export_csv writes named series columns."""
    import numpy as np
    plot = gl_backend()
    x = np.array([0, 1, 2])
    y = np.array([3, 4, 5])
    plot.line(x, y, pen=S.Pen(S.Color(255, 0, 0)), name="signal")
    path = tmp_path / "gl_export.csv"
    plot.export_csv(str(path))
    text = path.read_text()
    assert "signal" in text
    assert "3" in text


def test_gl_set_xlim_ylim(gl_backend):
    """set_xlim / set_ylim set the view range."""
    plot = gl_backend()
    plot.set_xlim(0, 10)
    plot.set_ylim(-1, 1)
    (x0, x1), (y0, y1) = plot.get_range()
    assert (x0, x1) == (0, 10)
    assert (y0, y1) == (-1, 1)


def test_gl_link_x(gl_backend):
    """link_x shares the x-axis range between two plots."""
    plot_a = gl_backend()
    plot_b = gl_backend()
    plot_a.link_x(plot_b)
    plot_a.set_xlim(5, 15)
    (x0, x1), _ = plot_b.get_range()
    assert (x0, x1) == (5, 15)


def test_gl_chaining_returns_self(gl_backend):
    """All Plot setters return self for chaining."""
    plot = gl_backend()
    assert plot.set_labels(left="y") is plot
    assert plot.set_title("t") is plot
    assert plot.set_log(y=True) is plot
    assert plot.grid(x=True) is plot
    assert plot.set_background("k") is plot
    assert plot.set_aspect_locked(True) is plot
    assert plot.set_context_menu_enabled(True) is plot
    assert plot.set_menu_enabled(True) is plot
    assert plot.on_range_changed(lambda xr, yr: None) is plot


def test_gl_clear_resets(gl_backend):
    """clear() removes all handles."""
    import numpy as np
    plot = gl_backend()
    plot.line([0, 1], [0, 1], pen=S.Pen(S.Color(255, 0, 0)))
    assert len(plot._canvas._handles) == 1
    plot.clear()
    assert len(plot._canvas._handles) == 0
    assert plot._series == []
