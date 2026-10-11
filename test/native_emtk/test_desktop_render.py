"""Real GPU screenshots of declared native factories; workflow parity is separate."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pytest

from chisurf.emtk.plugins import load_plugin, manifests

CATALOG = manifests()
NATIVE = sorted(key for key, value in CATALOG.items() if value.get("entrypoints", {}).get("emtk"))


@pytest.fixture(scope="module")
def gpu_device():
    import emtk

    assert hasattr(emtk, "Texture"), (emtk.__spec__, list(emtk.__path__))
    pytest.importorskip("wgpu")
    pytest.importorskip("rendercanvas")
    from emtk.wgpu_host import default_device

    try:
        return default_device()
    except Exception as error:
        pytest.skip(f"Native GPU unavailable: {error}")


@pytest.mark.parametrize("plugin_id", NATIVE)
def test_native_plugin_desktop_render(plugin_id, gpu_device, caplog):
    from emtk.native import NativeHost
    from emtk.testing import save_png

    output = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
    output.mkdir(parents=True, exist_ok=True)
    app = load_plugin(plugin_id, locale="en")
    host = None
    try:
        with caplog.at_level(logging.ERROR):
            host = NativeHost(app, size=(1200, 800), backend="offscreen", device=gpu_device)
            pixels = np.asarray(host.draw_frame())
            assert pixels.shape[:2] == (800, 1200)
            assert len(np.unique(pixels[..., :3].reshape(-1, 3), axis=0)) > 10
            failures = [
                record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR
            ]
            assert not failures, failures
            save_png(
                output / f"{plugin_id}.png",
                pixels.shape[1],
                pixels.shape[0],
                np.ascontiguousarray(pixels).reshape(-1).tobytes(),
            )
    finally:
        if host is not None:
            host.close()
        else:
            close = getattr(app, "close", None)
            if callable(close):
                close()


def test_native_help_rich_document_gpu(gpu_device, caplog):
    from emtk.native import NativeHost
    from emtk.testing import save_png

    source = (
        Path(__file__).resolve().parents[2]
        / "okf/plugins/emtk-references/help-rich-document/fixture/feature_reference.md"
    )
    assert source.is_file()
    app = load_plugin("help", locale="en", persist=False)
    assert app.model.open_page(source)
    output = Path(os.environ.get("CHISURF_NATIVE_SCREENSHOTS", "/private/tmp/chisurf-native-gpu"))
    output.mkdir(parents=True, exist_ok=True)
    host = NativeHost(app, size=(1280, 900), backend="offscreen", device=gpu_device)
    try:
        with caplog.at_level(logging.ERROR):
            pixels = np.asarray(host.draw_frame())
            host.draw_frame()
        assert not [record for record in caplog.records if record.levelno >= logging.ERROR]
        save_png(
            output / "help-rich-document.png",
            1280,
            900,
            np.ascontiguousarray(pixels).reshape(-1).tobytes(),
        )
    finally:
        host.close()
