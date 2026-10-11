"""Plots and images in the emtk shell's Console dock, as in the Qt console and a notebook.

The owner's report: ``import pylab as plt; x = np.linspace(0, 10); y = np.sin(x);
plt.plot(x, y)`` printed ``Out[4]: [<matplotlib.lines.Line2D ...>]`` and no plot. In the
emtk console a rich display was written as its text form only; it now draws the image in
the transcript (:class:`chisurf.emtk.console.InlineImage`), narrowed to the dock's width,
scrolling with the text, with *Copy image* / *Save image as…* on its right-click menu.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import numpy as np
import pytest

matplotlib = pytest.importorskip("matplotlib")
pytest.importorskip("PIL")

from emtk.events import RIGHT_BUTTON  # noqa: E402
from emtk.keys import KEY_RETURN  # noqa: E402
from emtk.testing import Driver  # noqa: E402

from chisurf.emtk.main_app import EmtkShellApp  # noqa: E402

SNIPPET = "import pylab as plt; x = np.linspace(0, 10); y = np.sin(x); plt.plot(x, y)"
SHOTS = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
C0 = (0x1F, 0x77, 0xB4)


@pytest.fixture(autouse=True)
def _restore_backend(monkeypatch):
    """The console picks matplotlib's backend process-wide; put it back afterwards."""
    monkeypatch.setenv("MPLBACKEND", "agg")
    before = matplotlib.get_backend()
    yield
    import matplotlib.pyplot as plt

    plt.close("all")
    matplotlib.use(before, force=True)


@pytest.fixture
def shell(tmp_path, monkeypatch):
    import chisurf
    from chisurf.core.project import recent

    monkeypatch.setattr(recent, "recent_projects_file", lambda: tmp_path / "recent_projects.json")
    monkeypatch.setattr(chisurf, "working_path", tmp_path, raising=False)
    monkeypatch.chdir(tmp_path)
    app = EmtkShellApp(
        {},
        loader=lambda plugin_id: None,
        console_history=tmp_path / "history.txt",
        console_session_file=tmp_path / "session.py",
    )
    app.console.push({"np": np})
    yield app
    app.close()


@pytest.fixture
def driver(shell):
    drv = Driver(shell, size=(1400, 900))
    drv.frame(3)
    drv.click(shell.console.item_rects["console.input"])
    return drv


def _submit(driver: Driver, text: str) -> None:
    driver.app.console.set_input(text)
    driver.press(KEY_RETURN)
    driver.frame(2)


def _rgba(png: bytes) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(io.BytesIO(png)).convert("RGBA"))


def _blue(rgba: np.ndarray) -> int:
    return int((np.abs(rgba[..., :3].astype(int) - np.asarray(C0)).max(axis=2) <= 40).sum())


def test_the_reported_snippet_draws_the_plot_in_the_transcript(driver, shell):
    console = shell.console
    _submit(driver, SNIPPET)
    text = console.transcript.text()
    assert "Line2D" in text, "the cell's value is still shown, as in a notebook"
    (image,) = console.transcript.images
    plot = _rgba(image.data)
    assert plot[..., :3].std() > 5 and _blue(plot) > 200, "a real plot, not a blank image"

    # Drawn on screen inside the output box, narrowed to it with the aspect kept.
    (box,) = [entry for entry in console.control.image_boxes if entry[4] is image]
    x, y, w, h, _image = box
    ox, oy, ow, oh = console.control.boxes["output"]
    assert ox <= x and x + w <= ox + ow
    assert abs(h / w - image.height / image.width) < 0.01
    png = driver.screenshot(SHOTS / "emtk_console_inline_plot.png")
    shot = _rgba(png)
    region = shot[int(max(y, oy)): int(min(y + h, oy + oh)), int(x): int(x + w)]
    assert _blue(region) > 30, "the plot's pixels reach the screen"


def test_a_narrow_dock_narrows_the_image_and_it_scrolls(driver, shell):
    console = shell.console
    _submit(driver, SNIPPET)
    (image,) = console.transcript.images
    wide = console.control.image_boxes[0][2]
    driver.draw(size=(400, 900))
    driver.frame(2)
    out = console.control.boxes["output"]
    (box,) = console.control.image_boxes
    assert box[2] < wide and box[0] + box[2] <= out[0] + out[2], "narrowed to the dock"
    assert abs(box[3] / box[2] - image.height / image.width) < 0.01, "aspect kept"
    driver.screenshot(SHOTS / "emtk_console_inline_plot_narrow.png")
    # More output pushes the plot up and out of view; scrolling back brings it in again.
    for _ in range(30):
        _submit(driver, "print('more output')")
    assert not console.control.image_boxes, "scrolled out of the transcript's view"
    console.control.scroll(-1000)
    driver.frame(2)
    (box,) = console.control.image_boxes
    assert box[1] >= out[1], "scrolled back to the top, the plot's first row is in view"


def test_right_click_copies_and_saves_the_image(driver, shell, monkeypatch, tmp_path):
    from emtk import clipboard

    console = shell.console
    _submit(driver, SNIPPET)
    (image,) = console.transcript.images
    x, y, w, h, _image = console.control.image_boxes[0]
    oy, oh = console.control.boxes["output"][1], console.control.boxes["output"][3]
    point = (x + w / 2, max(y, oy) + min(h, oh) / 4)
    assert console.control.image_at(*point) is image

    copied = []
    monkeypatch.setattr(clipboard, "copy_image", lambda png: copied.append(png) or True)
    driver.hover(point)
    driver.surface.on_pointer_press(*point, RIGHT_BUTTON, 0)
    driver.frame()
    driver.surface.on_pointer_release(*point, RIGHT_BUTTON, 0)
    driver.frame(2)
    driver.screenshot(SHOTS / "emtk_console_image_menu.png")
    driver.click("Copy image")
    driver.frame(2)
    assert copied == [image.data]

    target = tmp_path / "plot.png"
    console.save_image(image, target)
    assert target.read_bytes() == image.data
    console.save_image(image)
    assert console.file_dialog is not None and console.file_dialog.mode == "save"


def test_display_and_rich_reprs_are_images(driver, shell):
    console = shell.console
    _submit(driver, "display(np.outer(np.arange(32), np.ones(48)))")
    _submit(driver, "from PIL import Image; Image.new('RGB', (40, 20), 'red')")
    _submit(
        driver,
        "class Box:\n    def _repr_svg_(self):\n        return '<svg width=\"30\" height=\"10\">"
        "<rect width=\"30\" height=\"10\" fill=\"lime\"/></svg>'\n\nBox()",
    )
    sizes = [(image.width, image.height) for image in console.transcript.images]
    assert sizes == [(48, 32), (40, 20), (30, 10)]
    assert tuple(_rgba(console.transcript.images[2].data)[5, 15, :3]) == (0, 255, 0)
    assert "Out[" in console.transcript.text()
    _submit(driver, "%matplotlib inline")
    assert not any(kind == "stderr" for _text, kind in console.transcript.lines[-2:])
    driver.screenshot(SHOTS / "emtk_console_inline_images.png")
