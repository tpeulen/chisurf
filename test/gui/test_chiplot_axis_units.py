"""Axis units are metadata; SI scaling changes displayed ticks, never samples."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from chisurf.chiplot import backends
from chisurf import chiplot as cp


@pytest.fixture(params=["emtk"])
def plot(request: Any) -> Iterator[cp.Panel]:
    """Exercise the real renderer while restoring the process backend."""
    previous = backends._active
    previous_env = os.environ.get("CHISURF_PLOT_BACKEND")
    backends.set_backend(request.param)
    panel = cp.Panel()
    try:
        yield panel
    finally:
        backends._active = previous
        if previous_env is None:
            os.environ.pop("CHISURF_PLOT_BACKEND", None)
        else:
            os.environ["CHISURF_PLOT_BACKEND"] = previous_env


def _draw(plot: cp.Panel, width: int, height: int) -> Any:
    """Draw one real frame of the panel through emtk's pixel painter."""
    from emtk.testing import PixelPainter

    painter = PixelPainter(width, height, background=(255, 255, 255, 255))
    plot._canvas.draw(painter, 0.0, 0.0, float(width), float(height))
    return painter


def _metadata(panel: cp.Panel, side: str) -> tuple[str, str]:
    """Read the owning backend's actual axis metadata."""
    canvas: Any = panel._canvas
    return canvas._labels.get(side, ""), canvas._units.get(side, "")


def test_units_text_updates_and_explicit_clear(plot: cp.Panel) -> None:
    """Units-only and text-only updates preserve the other field on all axes."""
    assert (
        plot.set_labels(
            left="Count rate",
            bottom="Duration",
            right="Other",
            top="Time",
            left_units="Hz",
            bottom_units="ms",
            right_units="s",
            top_units="ns",
        )
        is plot
    )
    for side, text, units in [
        ("left", "Count rate", "Hz"),
        ("bottom", "Duration", "ms"),
        ("right", "Other", "s"),
        ("top", "Time", "ns"),
    ]:
        assert _metadata(plot, side) == (text, units)
    plot.set_labels(left="Rate", bottom_units="s")
    assert _metadata(plot, "left") == ("Rate", "Hz")
    assert _metadata(plot, "bottom") == ("Duration", "s")
    plot.set_labels(left_units="")
    assert _metadata(plot, "left") == ("Rate", "")
    assert _metadata(plot, "right") == ("Other", "s")


class _RecordingPainter:
    """Record axis text while forwarding to the real headless painter."""

    def __init__(
        self,
        painter: Any,
        texts: list[str],
        boxes: list[tuple[float, float, str]] | None = None,
    ) -> None:
        self.painter, self.texts = painter, texts
        self.boxes = boxes

    def __getattr__(self, name: str) -> Any:
        return getattr(self.painter, name)

    def text(self, *args: Any, **kwargs: Any) -> Any:
        self.texts.append(args[5])
        if self.boxes is not None:
            self.boxes.append((args[0], args[2], args[5]))
        return self.painter.text(*args, **kwargs)

    def text_rotated(self, *args: Any, **kwargs: Any) -> Any:
        self.texts.append(args[5])
        return self.painter.text_rotated(*args, **kwargs)


@pytest.mark.parametrize("log", [False, True])
def test_real_frames_si_ticks_do_not_rescale_data(
    plot: cp.Panel,
    monkeypatch: Any,
    log: bool,
) -> None:
    """A 20,000 Hz axis becomes 20 kHz in real frames and toggles back to Hz."""
    x, y = np.array([0.0, 1.0, 2.0]), np.array([1000.0, 10000.0, 20000.0])
    curve = plot.line(x, y)
    plot.set_labels(left="Count rate", left_units="Hz", bottom="Duration", bottom_units="ms")
    plot.set_range(x=(0, 2), y=(1000, 20000), padding=0)
    plot.set_log(y=log)
    canvas: Any = plot._canvas
    texts: list[str] = []
    draw_axes = canvas._draw_axes

    def record(painter: Any, *args: Any) -> None:
        draw_axes(_RecordingPainter(painter, texts), *args)

    monkeypatch.setattr(canvas, "_draw_axes", record)
    for enabled, unit_label in [(False, "Hz"), (True, "kHz"), (False, "Hz")]:
        texts.clear()
        plot.set_si_prefix(y=enabled)
        plot.set_labels(left="Count rate")
        _draw(plot, 800, 450)
        assert f"Count rate ({unit_label})" in texts
        assert "Duration (ms)" in texts
        # A real tick lies at 10,000 Hz: label 10, not 10000, when SI is enabled.
        assert ("10" if enabled else "10000") in texts
        np.testing.assert_array_equal(curve.get_data()[0], x)
        np.testing.assert_array_equal(curve.get_data()[1], y)


def test_plain_labels_and_unit_only_bottom(plot: cp.Panel) -> None:
    """Legacy labels stay plain, and a unit-only bottom title gets a visible row."""
    plot.set_labels(left="Counts", bottom="Time")
    assert _metadata(plot, "left") == ("Counts", "")
    plot.set_labels(bottom="", bottom_units="ms")
    plot.line([0, 1], [1, 2])
    _draw(plot, 800, 450)
    assert _metadata(plot, "bottom") == ("", "ms")


def test_real_bottom_si_prefix_preserves_seconds(
    plot: cp.Panel, monkeypatch: Any
) -> None:
    """Millisecond tick display keeps original second-valued samples."""
    canvas: Any = plot._canvas
    texts: list[str] = []
    if backends.get_backend().name == "emtk":
        draw_axes = canvas._draw_axes

        def record(painter: Any, *args: Any) -> None:
            draw_axes(_RecordingPainter(painter, texts), *args)

        monkeypatch.setattr(canvas, "_draw_axes", record)
    x = np.array([0.001, 0.002])
    curve = plot.line(x, [1, 2])
    plot.set_labels(bottom="Time", bottom_units="s")
    plot.set_range(x=(0.001, 0.002), padding=0)
    plot.set_si_prefix(x=True)
    _draw(plot, 800, 450)
    assert "Time (ms)" in texts
    assert "2.0" in texts
    np.testing.assert_array_equal(curve.get_data()[0], x)


@pytest.mark.parametrize("plot", ["emtk"], indirect=True)
def test_unit_only_title_and_boundary_tick_are_actually_visible(
    plot: cp.Panel,
    monkeypatch: Any,
) -> None:
    """Reserve the unit-only title row and keep right-edge tick text on canvas."""
    canvas: Any = plot._canvas
    texts: list[str] = []
    boxes: list[tuple[float, float, str]] = []
    draw_axes = canvas._draw_axes

    def record(painter: Any, *args: Any) -> None:
        draw_axes(_RecordingPainter(painter, texts, boxes), *args)

    monkeypatch.setattr(canvas, "_draw_axes", record)
    plot.line([0, 1000, 2000], [1, 2, 3])
    plot.set_labels(bottom_units="ms")
    plot.set_range(x=(0, 2000), padding=0)
    _draw(plot, 800, 450)
    assert "(ms)" in texts
    boundary = [(left, width) for left, width, text in boxes if text == "2000"]
    assert boundary
    assert all(0 <= left and left + width <= 800 for left, width in boundary)


def test_raw_samples_survive_log_downsampling_update_and_empty(
    plot: cp.Panel
) -> None:
    """The public curve handle returns source samples, including after edits/clear."""
    x = np.arange(1.0, 1001.0)
    y = x * 100.0
    curve = plot.line(x, y)
    plot.set_downsampling(auto=True, mode="subsample")
    _draw(plot, 300, 200)
    for logarithmic in (True, False, True):
        plot.set_log(x=logarithmic, y=logarithmic)
        np.testing.assert_array_equal(curve.get_data()[0], x)
        np.testing.assert_array_equal(curve.get_data()[1], y)
    curve.set_data(x, y * 2.0)
    np.testing.assert_array_equal(curve.get_data()[1], y * 2.0)
    curve.set_data(np.array([]), np.array([]))
    for values in curve.get_data():
        assert isinstance(values, np.ndarray)
        assert values.size == 0
    empty = plot.line([], [])
    for values in empty.get_data():
        assert isinstance(values, np.ndarray)
        assert values.size == 0
