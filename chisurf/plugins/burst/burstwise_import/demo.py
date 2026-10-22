"""Example data for the Burstwise importer: the shipped legacy sample folder.

The plugin's own test data is a real legacy burstwise folder (``.bur`` splits, a
``.mti`` metadata file, ``bg4`` backgrounds). ``make_demo`` returns that folder —
shipped data is referenced in place, never copied — and *Load example* points
the importer at it and inventories it, ready to convert.
"""

from __future__ import annotations

from pathlib import Path

STEM = "burstwise_sample"
FIXTURE = (
    Path(__file__).resolve().parent / "tests" / "data" / "burstwise" / "burstwise_All 0.1066#60"
)


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the importer."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "burstwise_import"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """The example legacy folder (shipped with the plugin's tests)."""
    if not FIXTURE.is_dir():
        raise FileNotFoundError(f"the shipped burstwise sample folder is missing: {FIXTURE}")
    return FIXTURE


def load_into(model) -> Path:
    """Point the importer at the example folder and inventory it."""
    folder = make_demo()
    model.set_folder(str(folder))
    model.scan()
    return folder
