"""Plots and images appear in the console's transcript, as in a notebook.

The owner's report: ``import pylab as plt; x = np.linspace(0, 10); y = np.sin(x);
plt.plot(x, y)`` printed ``Out[4]: [<matplotlib.lines.Line2D ...>]`` and no plot.
The shipped ``console_init`` no longer starts with ``%matplotlib inline`` (matplotlib
stopped being a ChiSurf dependency), so nothing selected the inline backend and the
figure went to a non-interactive one. The console now selects it itself
(:func:`chisurf.core.console.mpl_inline.install`).

The engine half runs without Qt.
"""

from __future__ import annotations

import io

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
PIL = pytest.importorskip("PIL")

from chisurf.core.console import Shell  # noqa: E402
from chisurf.core.console.mpl_inline import BACKEND  # noqa: E402

#: The exact cell of the bug report.
SNIPPET = "import pylab as plt; x = np.linspace(0, 10); y = np.sin(x); plt.plot(x, y)"
#: matplotlib's first colour, the colour of the plotted line.
C0 = (0x1F, 0x77, 0xB4)


@pytest.fixture(autouse=True)
def _restore_backend(monkeypatch):
    """Undo the console's backend choice after each test (it is process-wide)."""
    monkeypatch.setenv("MPLBACKEND", "agg")
    before = matplotlib.get_backend()
    yield
    import matplotlib.pyplot as plt

    plt.close("all")
    matplotlib.use(before, force=True)


def pixels(png: bytes) -> np.ndarray:
    """Decode *png* to an RGBA array."""
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def has_colour(rgba: np.ndarray, colour, tolerance: int = 40) -> int:
    """Count pixels close to *colour*."""
    diff = np.abs(rgba[..., :3].astype(int) - np.asarray(colour)).max(axis=2)
    return int((diff <= tolerance).sum())


def assert_plot(png: bytes) -> None:
    """*png* is a real plot: not blank, and the line is drawn in matplotlib's blue."""
    rgba = pixels(png)
    assert rgba.shape[0] > 100 and rgba.shape[1] > 100
    assert rgba[..., :3].std() > 5, "the image is blank"
    assert has_colour(rgba, C0) > 200, "the sine line is not in the image"


@pytest.fixture()
def shell():
    """A shell recording what it displays, with inline figures as a console has them."""
    shown: list[tuple[dict, dict, str]] = []
    written: list[tuple[str, str]] = []
    engine = Shell(
        user_ns={"np": np},
        display=lambda data, meta, kind, count: shown.append((data, meta, kind)),
        write=lambda name, text: written.append((name, text)),
    )
    assert engine.enable_inline_figures()
    engine.shown, engine.written = shown, written
    return engine


def images(shell) -> list[bytes]:
    return [data["image/png"] for data, _meta, _kind in shell.shown if "image/png" in data]


# ----------------------------------------------------------------------
# the engine
# ----------------------------------------------------------------------


def test_the_reported_snippet_shows_the_plot_inline(shell):
    """The bug report's cell: the Line2D list as Out, then the plot as an image."""
    result = shell.run_cell(SNIPPET)
    assert result.success
    assert matplotlib.get_backend() == BACKEND
    (png,) = images(shell)
    assert_plot(png)
    kinds = [kind for _data, _meta, kind in shell.shown]
    assert kinds == ["execute_result", "display_data"]
    # Closed after it was shown: the next cell starts a new figure, as in a notebook.
    shell.run_cell("1 + 1")
    assert len(images(shell)) == 1


def test_plt_show_publishes_at_once_and_does_not_block(shell):
    shell.run_cell("import matplotlib.pyplot as plt")
    shell.run_cell("plt.plot([0, 1], [0, 1]); plt.show(); print('after')")
    datas = [entry for entry in shell.shown]
    assert "image/png" in datas[0][0]
    assert any("after" in text for _name, text in shell.written)
    assert len(images(shell)) == 1, "plt.show() closed the figure: no second copy at cell end"


def test_fig_show_publishes_once(shell):
    shell.run_cell("import matplotlib.pyplot as plt")
    shell.run_cell("fig = plt.figure(); fig.add_subplot().plot([1, 3]); fig.show()")
    assert len(images(shell)) == 1


def test_a_figure_from_an_earlier_cell_is_shown_when_evaluated(shell):
    shell.run_cell("import matplotlib.pyplot as plt\nfig, ax = plt.subplots()\nax.plot([0, 1])")
    assert len(images(shell)) == 1
    shell.run_cell("fig")
    assert len(images(shell)) == 2
    assert shell.shown[-1][2] == "execute_result"


def test_an_empty_figure_is_not_published(shell):
    shell.run_cell("import matplotlib.pyplot as plt; plt.figure()")
    assert images(shell) == []


def test_percent_matplotlib_inline_is_accepted(shell):
    shell.run_cell("%matplotlib inline")
    assert not any(name == "stderr" for name, _text in shell.written)
    shell.run_cell(SNIPPET)
    assert len(images(shell)) == 1


def test_svg_figure_format_is_published_as_svg(shell):
    shell.run_cell("%config InlineBackend.figure_format = 'svg'")
    shell.run_cell(SNIPPET)
    svgs = [data for data, _m, _k in shell.shown if "image/svg+xml" in data]
    assert len(svgs) == 1 and "<svg" in svgs[0]["image/svg+xml"]


def test_display_draws_a_numpy_image(shell):
    shell.run_cell("display(np.outer(np.arange(20), np.ones(30)))")
    (png,) = images(shell)
    rgba = pixels(png)
    assert rgba.shape[:2] == (20, 30)
    assert rgba[0, 0, 0] == 0 and rgba[-1, 0, 0] == 255, "grey scaled min..max"
    shell.run_cell("display(np.zeros((4, 5, 3), dtype=np.uint8) + [255, 0, 0])")
    assert tuple(pixels(images(shell)[-1])[0, 0, :3]) == (255, 0, 0)


def test_a_trailing_array_stays_text(shell):
    shell.run_cell("np.zeros((3, 3))")
    assert images(shell) == []


def test_pil_images_and_emtk_figures_and_repr_svg_objects_are_images(shell):
    shell.run_cell("from PIL import Image\nImage.new('RGB', (12, 8), 'red')")
    assert pixels(images(shell)[-1]).shape[:2] == (8, 12)
    shell.run_cell(
        "import emtk.figure as ef\nf = ef.Figure(size=(200, 120))\nf.ax().line([0, 1], [0, 1])\nf"
    )
    assert pixels(images(shell)[-1]).shape[:2] == (120, 200)
    shell.run_cell(
        "class Box:\n    def _repr_svg_(self):\n"
        '        return \'<svg width="10" height="10"><rect width="10" height="10"/></svg>\'\n'
        "Box()"
    )
    assert "image/svg+xml" in shell.shown[-1][0]
