#!/usr/bin/env python3
"""Per-representation build cost for ChiMOL, on one spoke of the nuclear pore.

Why this model
--------------
``PDBDEV_00000010`` is one spoke of the yeast nuclear pore: **29,273 beads**,
about an eighth of the eight-spoke entry. It is the smallest thing that is still
honestly *large* — every representation has to cross the thresholds that matter
(the impostor budget, the surface-only cull, the density grid) — while staying
small enough that a full sweep of every representation finishes in a couple of
minutes rather than an afternoon.

What is measured
----------------
The **build**, not the frame: how long the viewer takes to turn coordinates into
scene geometry. That is what a user waits for when a representation is switched
on, and it is what a scene rebuild repeats. Frame time is the graphics card's
problem and is measured separately.

Each representation is timed alone, from a cold cache, and reported beside the
size of what it produced — vertices are the unit that matters downstream, and a
time without them can be made to look good by producing less.

Run
---
    PYTHONPATH=. python test/benchmarks/benchmark_chimol_representations.py

The entry is downloaded once to ``~/.chisurf/structures/chimol`` and reused.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import ssl
import sys
import time
import urllib.request

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

#: One spoke. `PDBDEV_00000012` is the whole eight-spoke pore, ~8x this.
ENTRY = "pdbdev_00000010"
CACHE = pathlib.Path.home() / ".chisurf" / "structures" / "chimol"


def entry_path() -> pathlib.Path:
    """Return the local mmCIF, downloading it once if needed."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"chimol_pdb_ihm_{ENTRY}.cif"
    if path.is_file() and path.stat().st_size > 0:
        return path
    try:
        import certifi

        context = ssl.create_default_context(cafile=certifi.where())
    except Exception:  # pragma: no cover - certifi is a normal dependency
        context = None
    partial = path.with_suffix(".part")
    with (
        urllib.request.urlopen(
            f"https://pdb-ihm.org/cif/{ENTRY}.cif", timeout=120, context=context
        ) as response,
        partial.open("wb") as handle,
    ):
        shutil.copyfileobj(response, handle)
    partial.replace(path)
    return path


def _vertices(objects) -> int:
    """Total vertex count of a builder's output."""
    if not objects:
        return 0
    if not isinstance(objects, (list, tuple)):
        objects = [objects]
    total = 0
    for obj in objects:
        positions = getattr(getattr(obj, "geometry", None), "positions", None)
        if positions is not None:
            total += int(np.asarray(positions).shape[0])
    return total


def main() -> int:
    """Time every representation and print the table."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from chimol.core.settings.config import _DISPLAY_CONFIG
    from chimol.core.viewer import MolView
    from chimol.io.structure import load_structure_payload

    path = entry_path()
    started = time.perf_counter()
    _structure, payload = load_structure_payload(path)
    read_s = time.perf_counter() - started

    view = MolView()
    started = time.perf_counter()
    view.add_payload(payload, name="spoke")
    load_s = time.perf_counter() - started

    coords = np.asarray(view._coords, dtype=float)
    n_points = coords.shape[0]
    colours = view._colors_per_ca
    print(f"{path.name}: {len(payload.coords)} beads, read {read_s:.2f}s, load {load_s:.2f}s")

    def cfg(section: str) -> dict:
        return _DISPLAY_CONFIG.get(section, {})

    # Each entry: label, a flag to switch on first, and the builder call.
    cases = [
        ("cartoon", None, lambda: view._update_cartoon(coords, n_points, cfg("cartoon"), colours)),
        ("trace", None, lambda: view._update_trace(coords, colours)),
        (
            "spheres (impostor)",
            "_show_atoms",
            lambda: view._update_atoms(coords, n_points, cfg("balls"), colours),
        ),
        (
            "spheres (mesh)",
            "_show_atoms",
            lambda: view._bead_scene_object({**cfg("balls"), "impostor_min_atoms": 10**9}, colours),
        ),
        ("sticks", "_show_sticks", lambda: view._update_sticks(cfg("sticks"), colours)),
        ("lines", "_show_lines", lambda: view._update_lines(colours)),
        ("nonbonded", "_show_nonbonded", lambda: view._update_nonbonded(colours)),
        ("dots", "_show_dots", lambda: view._update_dots(coords, colours)),
        (
            "surface",
            "_surface_visible",
            lambda: view._update_surface(coords, cfg("surface"), colours),
        ),
        (
            "metaballs",
            "_metaballs_visible",
            lambda: view._update_metaballs(coords, cfg("metaball"), colours),
        ),
    ]

    print(f"\n{'representation':<22}{'build (s)':>11}{'vertices':>12}")
    print("-" * 45)
    results = []
    for label, flag, build in cases:
        if flag is not None:
            setattr(view, flag, True)
        started = time.perf_counter()
        try:
            objects = build()
        except Exception as exc:  # a representation that cannot build says so
            print(f"{label:<22}{'error':>11}   {type(exc).__name__}: {exc}")
            continue
        elapsed = time.perf_counter() - started
        count = _vertices(objects)
        results.append((label, elapsed, count))
        print(f"{label:<22}{elapsed:>11.2f}{count:>12,}")

    total = sum(t for _l, t, _v in results)
    print("-" * 45)
    print(f"{'total':<22}{total:>11.2f}")

    # What a representation toggle costs today: the whole scene, every time.
    started = time.perf_counter()
    view._build_scene_for_current_object()
    print(f"\nfull scene rebuild (what one toggle costs): {time.perf_counter() - started:.2f}s")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
