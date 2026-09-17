#!/usr/bin/env python3
"""What ``ray`` costs per representation, and how that scales with the scene.

Why this model
--------------
T4 lysozyme (**148L**, 1 314 atoms) is the repo's standard protein and ships in
the test data, so this benchmark needs no download and no network. It is small
as structures go, which is the point: if a molecule this ordinary is slow to
ray trace, nothing larger is usable at all.

What is measured
----------------
The **trace**, not the scene build -- the scene is built once per representation
and excluded from the timing, because
``benchmark_chimol_representations.py`` already owns that number. What is timed
is the call a user waits on after typing ``ray``.

Reported beside each time is the geometry the tracer was handed, because a time
without it can always be made to look good by drawing less. The second table
is the one that matters for judging the acceleration structure: the same
picture at four resolutions, where a tracer testing every primitive per ray
grows linearly with the sample count and one with a tree does not grow much
faster than the pixels do.

Run
---
    PYTHONPATH=. python test/benchmarks/benchmark_chimol_ray.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

PDB = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test"
    / "data"
    / "atomic_coordinates"
    / "pdb_files"
    / "148l.pdb"
)

#: Representations worth timing: every one the tracer draws differently.
#: ``spheres`` is the case it intersects analytically, the rest are meshes.
REPRESENTATIONS = ("cartoon", "ribbon", "sticks", "lines", "spheres", "surface")

#: Where the per-representation table is taken. Small enough to stay quick,
#: large enough that the tree build is not most of the measurement.
BENCH_W, BENCH_H, BENCH_SSAA = 320, 240, 2

#: The scaling table, ending at a size a figure is actually rendered at.
SCALES = ((160, 120, 1), (320, 240, 1), (640, 480, 2), (1024, 768, 2))

#: Two lights, matching the tracer's own default rig.
LIGHTS = np.array([[0.0, 0.0, 1.0], [-0.55, -0.7, 0.4]])


def scene_geometry(scene) -> tuple[int, int]:
    """Return ``(spheres, triangles)`` the tracer will be handed for *scene*."""
    n_sph = n_tri = 0
    for obj in scene.objects:
        geom = obj.geometry
        if geom.kind == "mesh" and (geom.meta or {}).get("spheres") is not None:
            # A ball mesh that kept the spheres it was built from; the tracer
            # intersects those exactly instead of their triangles.
            n_sph += len(geom.meta["spheres"]["centers"])
        elif geom.kind == "mesh":
            n_tri += (
                geom.indices.shape[0]
                if geom.indices is not None
                else np.asarray(geom.positions).shape[0] // 3
            )
        elif geom.kind in ("points", "line"):
            n_sph += int(np.asarray(geom.positions).reshape(-1, 3).shape[0])
    return n_sph, n_tri


def main() -> int:
    """Time every representation, then one of them at four resolutions."""
    from qtpy import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    from chimol.commands.command import Cmd
    from chimol.hosts.qt.window import MolViewPluginWindow
    from chimol.render.raytracer import _camera_from_view_state, render_scene

    window = MolViewPluginWindow()
    window._load_structure_from_path(PDB, name="148l")
    cmd = Cmd(window)
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda m: print(f"  error: {m}"))
    viewer = getattr(window, "viewer", None) or window._viewer

    def current():
        return (
            viewer.get_current_scene(),
            _camera_from_view_state(viewer.get_ray_view_state()),
        )

    # Compile the kernels before anything is timed, or the first row pays for
    # every row.
    cmd.do("as cartoon")
    render_scene(*current(), LIGHTS, 16, 12, ssaa=1)

    print(
        f"{PDB.name}: ray tracing at {BENCH_W}x{BENCH_H}, "
        f"{BENCH_SSAA}x{BENCH_SSAA} samples per pixel\n"
    )
    print(f"{'representation':<16}{'trace (s)':>11}{'spheres':>10}{'triangles':>12}")
    print("-" * 49)
    for rep in REPRESENTATIONS:
        cmd.do(f"as {rep}")
        scene, camera = current()
        n_sph, n_tri = scene_geometry(scene)
        started = time.perf_counter()
        render_scene(scene, camera, LIGHTS, BENCH_W, BENCH_H, ssaa=BENCH_SSAA)
        elapsed = time.perf_counter() - started
        print(f"{rep:<16}{elapsed:>11.3f}{n_sph:>10,}{n_tri:>12,}")

    # Scaling. A tracer without an acceleration structure grows with the sample
    # count times the primitive count; with one, only with the samples.
    cmd.do("as cartoon")
    scene, camera = current()
    _n_sph, n_tri = scene_geometry(scene)
    print(f"\ncartoon ({n_tri:,} triangles) at four resolutions\n")
    print(f"{'resolution':<16}{'samples':>12}{'trace (s)':>11}{'us/sample':>12}")
    print("-" * 51)
    for width, height, ssaa in SCALES:
        started = time.perf_counter()
        render_scene(scene, camera, LIGHTS, width, height, ssaa=ssaa)
        elapsed = time.perf_counter() - started
        samples = width * height * ssaa * ssaa
        print(
            f"{f'{width}x{height} ssaa{ssaa}':<16}{samples:>12,}"
            f"{elapsed:>11.3f}{elapsed / samples * 1e6:>12.3f}"
        )

    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
