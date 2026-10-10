"""Rotating the 3-D PSF stays interactive on a 64^3 volume (the target is 30 frames a second)."""

from __future__ import annotations

import statistics
import time

import numpy as np
import pytest

from chisurf.plugins.calculator.psf_calculator.gui.app import make_app

from .driving import BIG, PSFDriver, hermetic_env

FRAME_BUDGET_S = 1 / 30


@pytest.fixture(autouse=True)
def hermetic(tmp_path, monkeypatch):
    hermetic_env(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)


def test_rotating_a_64_cubed_volume_runs_at_30_fps():
    app = make_app()
    model = app.model
    model.nxy = model.nz = 64
    axis = np.linspace(-1.0, 1.0, 64)
    z, y, x = np.meshgrid(axis * 3.0, axis, axis, indexing="ij")
    model._volume = np.exp(-(x * x + y * y) * 60.0 - z * z * 20.0).astype(np.float32)
    model._key = model._compute_key()
    drv = PSFDriver(app, BIG)
    try:
        drv.draw(3)
        if app.volume_view.error:
            pytest.skip(app.volume_view.error)  # no WebGPU adapter here
        x0, y0, w, h = drv.rect("volume_view")
        cx, cy = x0 + w / 2, y0 + h / 2
        app.pointer_move(cx, cy)
        drv.draw(1)
        app.press(cx, cy)
        drv.draw(1)
        frames = []
        for i in range(1, 31):
            app.pointer_move(cx + 4 * i, cy + 2 * i, 1)
            start = time.perf_counter()
            drv.draw(1)
            frames.append(time.perf_counter() - start)
        app.release()
        assert statistics.median(frames) < FRAME_BUDGET_S, f"median {statistics.median(frames) * 1000:.1f} ms"
    finally:
        app.close()
        app._executor.shutdown(wait=True)
