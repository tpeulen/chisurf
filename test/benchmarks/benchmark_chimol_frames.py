#!/usr/bin/env python3
"""What one interactive ChiMOL frame costs, and what it is spending on.

Why this model
--------------
T4 lysozyme (**148L**, 1 314 atoms) ships in the test data, so this needs no
download. It is deliberately an *ordinary* molecule: a viewer that cannot hold a
frame rate here has nothing to offer on anything larger.

What is measured
----------------
One frame of the toolkit-free window on the offscreen canvas
(``ChimolApp.draw_frame``, the viewer ChiSurf embeds): scene, chrome and the
read-back of the image, so the GPU has finished when the clock stops and the
number is the frame and not the queue depth. The median of many is reported,
because the first frames after a representation change pay for buffer uploads
that a steady state does not. (It used to time ``paintGL`` + ``glFinish`` of the
retired Qt window's OpenGL widget; numbers from before the WebGPU port and the
Qt retirement are not comparable with these.)

The **second table is the diagnostic**, and is the reason this script exists in
this shape. It renders the same scene at four pixel counts. A frame that is
fill-bound scales with the pixels; one that is vertex-bound or CPU-bound does
not. When this was written every representation came out *flat* — 8x the pixels
for the same milliseconds — which ruled out fill and vertex work together and
pointed at fixed per-frame CPU work. That turned out to be the whole scene being
rebuilt inside ``paintGL``, through a colour query the sequence strip makes once
per object per frame: 82 ms of an 82 ms surface frame.

Keep the scaling table. A single frame time says a number is bad; the scaling
says *where to look*, and it is what stopped a shader rewrite that would have
bought a millisecond.

Requires a WebGPU adapter
-------------------------
No window and no GUI toolkit: the offscreen canvas renders through wgpu, so this
runs over ssh and in CI wherever an adapter exists.

Run
---
    PYTHONPATH=. python test/benchmarks/benchmark_chimol_frames.py
"""

from __future__ import annotations

import os
import pathlib
import sys
import time

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

REPRESENTATIONS = ("cartoon", "sticks", "spheres", "lines", "surface")

#: Where the per-representation table is taken.
BENCH_SIZE = (1280, 860)

#: The scaling table: same scene, 1x to 8x the pixels.
SCALES = ((640, 430), (905, 608), (1280, 860), (1810, 1216))

FRAMES = 30


def scene_vertices(scene) -> tuple[int, int]:
    """Vertices the frame draws, and the triangles behind them."""
    n_vertices = n_triangles = 0
    for obj in scene.objects:
        geom = obj.geometry
        positions = getattr(geom, "positions", None)
        if positions is None:
            continue
        n_vertices += int(np.asarray(positions).reshape(-1, 3).shape[0])
        if geom.kind == "mesh":
            n_triangles += (
                geom.indices.shape[0]
                if geom.indices is not None
                else np.asarray(positions).shape[0] // 3
            )
    return n_vertices, n_triangles


def main() -> int:
    """Print the per-representation table, then the scaling table."""
    from chimol.hosts.native.app import ChimolApp

    app = ChimolApp(backend="offscreen", size=BENCH_SIZE)
    app.host.load_structure_from_path(PDB, name="148l")
    cmd = app.cmd
    cmd.set_message_callback(lambda _m: None)
    cmd.set_error_callback(lambda m: print(f"  error: {m}"))
    viewer = app.viewer

    def frame_ms() -> float:
        times = []
        for _ in range(FRAMES):
            started = time.perf_counter()
            app.draw_frame()  # rendered and read back: the GPU is done
            times.append((time.perf_counter() - started) * 1e3)
        times.sort()
        return times[len(times) // 2]

    def settle(rep: str) -> None:
        cmd.do(f"as {rep}")
        frame_ms()  # absorb the upload the change just queued

    width, height = BENCH_SIZE
    print(f"{PDB.name}: one offscreen frame at {width}x{height}\n")
    print(f"{'representation':<16}{'vertices':>10}{'triangles':>11}{'frame (ms)':>12}{'fps':>8}")
    print("-" * 57)
    for rep in REPRESENTATIONS:
        settle(rep)
        n_vertices, n_triangles = scene_vertices(viewer.get_current_scene())
        elapsed = frame_ms()
        print(
            f"{rep:<16}{n_vertices:>10,}{n_triangles:>11,}{elapsed:>12.2f}"
            f"{1000.0 / max(elapsed, 1e-9):>8.0f}"
        )

    print("\nsame scene, more pixels -- flat means the frame is CPU-bound\n")
    print(f"{'representation':<16}" + "".join(f"{w}x{h}".rjust(12) for w, h in SCALES))
    print("-" * (16 + 12 * len(SCALES)))
    for rep in REPRESENTATIONS:
        settle(rep)
        row = []
        for width, height in SCALES:
            app.renderer.resize(width, height)
            row.append(frame_ms())
        app.renderer.resize(*BENCH_SIZE)
        print(f"{rep:<16}" + "".join(f"{ms:11.2f}ms" for ms in row))

    print(
        f"\n{'':16}"
        + "".join(f"{w * h / (SCALES[0][0] * SCALES[0][1]):11.0f}x" for w, h in SCALES)
        + "   <- pixels"
    )

    app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
