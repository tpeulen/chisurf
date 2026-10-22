"""Example data for the FPS JSON editor: a labelling plan from the shipped examples.

``make_demo`` stages the FRET-modelling plugin's ``pair_selection_tutorial``
fps.json into the demo folder, so the headless half of this plugin (the payload
model: load, edit, save, validate) has a real document to work on. The editor
itself is a ChiMOL window — *Load example* opens the structure there and the
payload is loaded headlessly beside it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

STEM = "sample"

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "modelling"
    / "fret"
    / "examples"
    / "olga_t4l"
    / "pair_selection_tutorial.fps.json"
)


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the FPS JSON editor."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "fps_json_editor"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Stage (or reuse) the sample fps.json document."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.fps.json"
    if overwrite or not path.is_file():
        if not SOURCE.is_file():
            raise FileNotFoundError(f"the shipped fps.json example is missing: {SOURCE}")
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copy(SOURCE, path)
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not stage the sample fps.json at {path}")
    return path


def load_document():
    """Load the sample into the payload model; return the model (headless half)."""
    from chisurf.plugins.modelling.fps_json_editor.core.model import FpsJsonModel

    model = FpsJsonModel()
    model.load_file(str(make_demo()))
    return model


def load_into(app) -> Path:
    """Open the structure in the ChiMOL viewer; the sample document is staged."""
    app.load_example()
    return make_demo()
