"""Transport-agnostic functions behind the ``img_flow.*`` RPC methods.

Every one returns plain JSON-serialisable data, so the same call works
in-process, over ZMQ, and from the CLI.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .. import core as _core


def compute_map(filename: str, **kwargs: Any) -> dict[str, Any]:
    """Compute a velocity field for *filename* and return it as plain data.

    Parameters
    ----------
    filename : str
        TIFF stack or photon stream.
    **kwargs
        Forwarded to :func:`..core.analyse_file`; ``min_quality`` and
        ``output_path`` are consumed here.

    Returns
    -------
    dict
        ``summary``, ``vectors`` (one row per kept tile), the grid shape, the
        timing used and the number of refused tiles.
    """
    min_quality = float(kwargs.pop("min_quality", 0.5) or 0.0)
    output_path = kwargs.pop("output_path", "") or ""
    analysis = _core.analyse_file(filename, **kwargs)
    result: dict[str, Any] = {
        "summary": analysis.summary(min_quality),
        "vectors": _core.to_rows(analysis, min_quality),
        "shape": [int(analysis.vx.shape[0]), int(analysis.vx.shape[1])],
        "method": analysis.method,
        "n_escaped": int(analysis.n_escaped),
        "timing": analysis.timing.to_dict(),
        "min_quality": min_quality,
        "meta": {k: v for k, v in analysis.meta.items()
                 if isinstance(v, (str, int, float, bool, list, tuple))},
    }
    if output_path:
        result["output_path"] = _core.write_csv(analysis, output_path, min_quality)
    return result


def list_methods() -> dict[str, Any]:
    """List the estimators and what each of them can and cannot see."""
    return {
        "methods": list(_core.METHODS),
        "labels": {
            "stics": "STICS — track where the correlation peak moves (2-D)",
            "pcf": "Pair correlation — when molecules arrive δ away (1-D, per pixel)",
        },
        "notes": {
            "stics": "Two-dimensional and direct. Blind to a flow too slow to "
                     "shift the peak, and wrong if the peak leaves its tile.",
            "pcf": "One-dimensional along the fast scan axis, resolved per pixel, "
                   "and the only one that reports *no* transport rather than slow "
                   "transport — which is what a barrier looks like.",
        },
    }


def create_demo(**kwargs: Any) -> dict[str, Any]:
    """Simulate the demo photon stream; see :func:`..demo.create_demo`."""
    from ..demo import create_demo as _create

    return _create(**kwargs)


def profile_check(filename: str, **kwargs: Any) -> dict[str, Any]:
    """Return the recovered flow profile beside the demo's true one.

    Reduces a field to one number per row of tiles, which is what makes the
    demo checkable: the true profile is parabolic across the channel, so the
    recovered rows must rise to the middle and fall again.

    Parameters
    ----------
    filename : str
        The demo photon stream.
    **kwargs
        Forwarded to :func:`..core.analyse_file`.

    Returns
    -------
    dict
        ``y_um``, ``v_recovered`` and ``v_true`` per row of tiles.
    """
    from ..demo import expected_profile

    analysis = _core.analyse_file(filename, **kwargs)
    y = np.asarray(analysis.y)[:, 0]
    with np.errstate(invalid="ignore"):
        recovered = np.nanmean(np.where(analysis.kept(0.5), analysis.vx, np.nan), axis=1)
    return {
        "y_um": [float(v) for v in y],
        "v_recovered": [float(v) for v in recovered],
        "v_true": [float(v) for v in expected_profile(y)],
    }
