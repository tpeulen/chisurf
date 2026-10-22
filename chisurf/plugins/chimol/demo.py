"""Example data for the ChiMOL host: the T4 lysozyme structure the viewer loads.

The host's *Load example* opens ``148l.pdb`` from the chimol package's demo
catalogue. ``make_demo`` stages that structure (or, when the catalogue is
unavailable, a minimal synthetic PDB) into the settings-owned demo folder, so a
script or test has a structure file that does not depend on the install.
"""

from __future__ import annotations

import shutil
from pathlib import Path

STEM = "example"


def demo_folder() -> Path:
    """The settings-owned demonstration folder of the ChiMOL host."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "chimol"


def bundled_demo_pdb() -> Path | None:
    """The demo structure the chimol package ships, when it is installed."""
    try:
        from chimol.plugins.demos.catalog import DEMO_DIR
    except Exception:  # noqa: BLE001 - chimol is an optional install
        return None
    path = Path(DEMO_DIR) / "148l.pdb"
    return path if path.is_file() else None


def minimal_pdb() -> str:
    """A tiny but valid PDB: an alpha helix of ten CA atoms (spacing 1.5 Å)."""
    lines = ["HEADER    CHISURF DEMO STRUCTURE"]
    for i in range(10):
        x, y, z = 0.0, i * 1.5, 2.0
        lines.append(
            f"ATOM  {i + 1:5d}  CA  ALA A{i + 1:4d}    {x:8.3f}{y:8.3f}{z:8.3f}  1.00 20.00           C"
        )
    lines.append("TER")
    lines.append("END")
    return "\n".join(lines) + "\n"


def make_demo(folder: Path | None = None, *, overwrite: bool = False) -> Path:
    """Stage the example structure into the demo folder."""
    folder = demo_folder() if folder is None else Path(folder)
    path = folder / f"{STEM}.pdb"
    if overwrite or not path.is_file():
        folder.mkdir(parents=True, exist_ok=True)
        source = bundled_demo_pdb()
        if source is not None:
            shutil.copy(source, path)
        else:
            path.write_text(minimal_pdb(), encoding="utf-8")
    if not path.is_file() or path.stat().st_size == 0:
        raise OSError(f"could not stage the demo structure at {path}")
    return path


def load_into(app) -> Path:
    """The host's own Load example (the chimol catalogue's 148l)."""
    app.load_example()
    return make_demo()
