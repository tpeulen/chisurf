"""Benchmark for chimol's density-map contouring (:mod:`chimol.volume`).

Measures what a user waits for when a map is on screen:

``cold contour``
    One full-quality isosurface of a level never asked for -- the cost of a
    release after a drag, and of opening a map.

``cached re-ask``
    The same level again -- what a colour or opacity edit, a surface/mesh
    toggle, and every redraw of an unchanged level costs. This must be
    effectively free; it is served from the contour memo.

``preview contour``
    The same level under the reduced drag budget (2 M voxels) -- the cost of
    the surface following a marker mid-drag.

``histogram, first / again``
    What the density panel's paint costs before and after the memo. The panel
    redraws every frame, so "again" is the number that decides how it feels.

The contour numbers are for the NumPy marching cubes after the reference
viewer's habits were ported into it (single precision in place, normals sampled
only at surface vertices, ``uint8`` corner cases); the regression test below
pins that fast path to a float64 run of the same code, so the port cannot drift
into a different mesh.

Run standalone for a markdown table to paste into
``docs/development/benchmarks.md``::

    PYTHONPATH=. python test/benchmarks/benchmark_map_contour.py

or as a (slow) regression test::

    pytest test/benchmarks/benchmark_map_contour.py -q -m slow
"""

from __future__ import annotations

import time

import numpy as np
import pytest
from chimol.geometry.marching_cubes import marching_cubes
from chimol.volume import VolumeGrid

#: Grid edge lengths per case. 180 is a routine cryo-EM working size; 256 is
#: at the display voxel budget (16.8 M voxels, stride 1 still).
SIZES = [96, 180, 256]


def _blob_map(n: int) -> VolumeGrid:
    """Build a seeded two-blob density on a noise floor, ``float32`` like a real map."""
    rng = np.random.default_rng(7)
    ax = np.linspace(-1.5, 1.5, n)
    x, y, z = np.meshgrid(ax, ax, ax, indexing="ij")
    values = (
        np.exp(-((x - 0.4) ** 2 + y * y + z * z) * 8)
        + 0.7 * np.exp(-((x + 0.5) ** 2 + (y - 0.3) ** 2 + z * z) * 12)
        + 0.02 * rng.standard_normal(x.shape)
    ).astype(np.float32)
    return VolumeGrid.from_array(values, name=f"blob-{n}")


def _best_of(repeats: int, fn) -> float:
    best = np.inf
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        best = min(best, time.perf_counter() - start)
    return best


def run(sizes=SIZES) -> list[dict]:
    """Time the contour paths per grid size and print a markdown table."""
    records = []
    for n in sizes:
        grid = _blob_map(n)
        level = float(np.quantile(grid.values, 0.99))

        fresh = _blob_map(n)
        cold = _best_of(1, lambda: fresh.isosurface(level))
        cached = _best_of(3, lambda: fresh.isosurface(level))
        preview_grid = _blob_map(n)
        preview = _best_of(1, lambda: preview_grid.isosurface(level, voxel_limit_m=2.0))

        hist_grid = _blob_map(n)
        hist_first = _best_of(1, lambda: hist_grid.histogram(200))
        hist_again = _best_of(3, lambda: hist_grid.histogram(200))

        surface = fresh.isosurface(level)
        records.append(
            dict(
                n=n,
                verts=0 if surface is None else int(surface[0].shape[0]),
                cold=cold,
                cached=cached,
                preview=preview,
                hist_first=hist_first,
                hist_again=hist_again,
            )
        )

    print(
        "| Grid | Vertices | cold contour | cached re-ask | preview (2 M) "
        "| histogram, first | histogram, again |"
    )
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for r in records:
        print(
            f"| {r['n']}³ | {r['verts']:,} | {r['cold'] * 1e3:.1f} ms "
            f"| {r['cached'] * 1e6:.1f} µs | {r['preview'] * 1e3:.1f} ms "
            f"| {r['hist_first'] * 1e3:.1f} ms | {r['hist_again'] * 1e6:.1f} µs |"
        )
    return records


@pytest.mark.slow
def test_single_precision_contour_matches_a_float64_run():
    """The fast path must produce the float64 mesh, not a cheaper cousin.

    Same welded topology (vertex and face counts are exact) and the same
    geometry to within a tolerance far below a voxel. This is the property the
    speed was bought with; losing it silently would look like data.
    """
    grid = _blob_map(96)
    level = float(np.quantile(grid.values, 0.99))
    v32, f32, n32 = marching_cubes(grid.values, level, (1.0, 1.0, 1.0))
    v64, f64, n64 = marching_cubes(grid.values.astype(np.float64), level, (1.0, 1.0, 1.0))
    assert v32.shape == v64.shape and np.array_equal(f32, f64)
    assert float(np.abs(v32 - v64).max()) < 1e-3
    assert float(np.abs(n32 - n64).max()) < 1e-3


@pytest.mark.slow
def test_an_unchanged_level_is_served_from_memory():
    """A colour edit or a mode toggle must not pay for marching cubes again."""
    grid = _blob_map(96)
    level = float(np.quantile(grid.values, 0.99))
    first = grid.isosurface(level)
    again = grid.isosurface(level)
    assert first is again


if __name__ == "__main__":
    run()
