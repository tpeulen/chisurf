"""A project to repair: three linked data files, one of which has moved to a backup folder.

:func:`make_demo` writes ``study/demo.cs.pto`` linking ``data/a.tif``, ``data/b.tif`` and
``data/c.tif`` (seeded bytes), then moves ``c.tif`` to ``backup/2026/c.tif`` and leaves a different
file of the same name in ``backup/old/``: the tool finds ``c.tif`` missing, a folder search of
``backup`` proposes both candidates (the same size first), and the checksum picks the right one.
The demo is written afresh on every load: repairing it changes it.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

#: Everything that decides the demo's files.
DEMO: dict[str, Any] = {
    "files": {"a.tif": 4096, "b.tif": 8192, "c.tif": 6144},
    "moved": "c.tif",
    "decoy_size": 5000,
    "seed": 7,
}

PROJECT_NAME = "demo.cs.pto"


def demo_folder() -> Path:
    """Return the settings-owned demonstration folder for this plugin."""
    from chisurf.core.settings import get_path

    return get_path("settings") / "demos" / "project_data"


def make_demo(folder: str | Path | None = None, *, overwrite: bool = False) -> Path:
    """Write the demo project into *folder* (default :func:`demo_folder`) and return its path."""
    import numpy as np

    from chisurf.core.data import LinkedDataset
    from chisurf.core.project.session import capture_session

    root = Path(folder) if folder is not None else demo_folder()
    project_path = root / "study" / PROJECT_NAME
    if project_path.is_file() and not overwrite:
        return project_path
    if root.exists():
        shutil.rmtree(root)
    data = root / "study" / "data"
    data.mkdir(parents=True)
    rng = np.random.default_rng(DEMO["seed"])
    datasets = []
    for name, size in DEMO["files"].items():
        path = data / name
        path.write_bytes(rng.integers(0, 256, size, dtype=np.uint8).tobytes())
        datasets.append(LinkedDataset(str(path), data_kind="image", name=Path(name).stem))
    capture_session(datasets, [], name="demo").save(project_path)
    moved = root / "backup" / "2026" / DEMO["moved"]
    moved.parent.mkdir(parents=True)
    shutil.move(str(data / DEMO["moved"]), moved)
    decoy = root / "backup" / "old" / DEMO["moved"]
    decoy.parent.mkdir(parents=True)
    decoy.write_bytes(rng.integers(0, 256, DEMO["decoy_size"], dtype=np.uint8).tobytes())
    return project_path
