"""Example data for the k²-distribution calculator: a computed, exported distribution.

The tool computes on construction, so the example is simply the tool's own
answer: *Load example* recomputes and exports the distribution CSV the same way
the old Qt tool's *Save* did — the format of the shipped ``qt_saved.csv``.
"""

from __future__ import annotations

from pathlib import Path

STEM = "kappa2_demo"


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the calculator."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "kappa2_dist"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Compute the shipped inputs and export the distribution CSV."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.csv"
    if overwrite or not path.is_file():
        from chisurf.plugins.calculator.kappa2_dist.gui.app import make_app

        app = make_app()
        app.compute_now()
        folder.mkdir(parents=True, exist_ok=True)
        app.write_csv(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"the example distribution was not written to {path}")
    return path


def load_into(app) -> Path:
    """Recompute with the shipped inputs and export beside the settings."""
    app.compute_now()
    folder = demo_folder()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{STEM}.csv"
    app.write_csv(path)
    return path
