"""Demos that moved to the shared settings cache write once, reuse, and rewrite on request."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

DEMOS = [
    "chisurf.plugins.core.pto_inspector.demo",
    "chisurf.plugins.core.user_editor.demo",
    "chisurf.plugins.fcs.fcs_merger.demo",
    "chisurf.plugins.ndxplorer.demo",
    "chisurf.plugins.tttr.trace_browser.demo",
    "chisurf.plugins.tttr.tttr_image_browser.demo",
    "chisurf.plugins.microscopy.clsm.demo",
]


def _files(result: Path) -> list[Path]:
    """Return the files a ``make_demo`` result stands for (a folder or one file)."""
    return sorted(p for p in result.iterdir() if p.is_file()) if result.is_dir() else [result]


@pytest.mark.parametrize("module", DEMOS)
def test_default_cache_is_reused_then_rewritten(module, tmp_path, monkeypatch):
    monkeypatch.setattr("chisurf.plugins.demo_cache.cache_folder", lambda plugin: tmp_path / plugin)
    demo = importlib.import_module(module)
    assert demo.demo_folder().parent == tmp_path
    try:
        first = demo.make_demo()
    except RuntimeError as exc:  # a tttrlib build without the photon simulator
        pytest.skip(str(exc))
    assert tmp_path in first.parents
    stamps = {p: p.stat().st_mtime_ns for p in _files(first) if p.suffix != ".json" or "meta" not in p.name}
    assert stamps
    assert demo.make_demo() == first
    assert {p: p.stat().st_mtime_ns for p in stamps} == stamps
    demo.make_demo(overwrite=True)
    assert all(p.is_file() for p in stamps)
