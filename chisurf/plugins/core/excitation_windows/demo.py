"""The Excitation Windows tool's example: the core simulated PIE measurement, cached in the settings."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.fluorescence.simulation import pie_demo


def demo_folder() -> Path:
    """The settings-owned folder of the demo."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "excitation_windows"


def make_demo(folder: Path | None = None) -> Path:
    """The demo measurement in *folder* (default :func:`demo_folder`)."""
    return pie_demo.make_demo(demo_folder() if folder is None else Path(folder))
