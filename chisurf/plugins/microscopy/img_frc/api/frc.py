"""Transport-agnostic API of the FRC resolution calculator.

Every function here takes and returns plain JSON-safe values, so the same call
serves the in-process client, a ZMQ server and a script.
"""

from __future__ import annotations

from typing import Any

from chisurf.core.fluorescence.imaging import frc as frc_mod

from .. import core


def compute_resolution(
    filename: str,
    split: str = "even_odd",
    channel: Any = 0,
    channel_2: Any = None,
    second_filename: str | None = None,
    pixel_size_nm: float | None = None,
    criterion: str = "fixed_1/7",
    bin_width: float | None = None,
    smooth: int = 3,
    axis_order: str = "auto",
    output_path: str | None = None,
    **load_kwargs: Any,
) -> dict[str, Any]:
    """Measure an image's resolution and return a JSON-safe summary.

    Parameters
    ----------
    filename : str
        TIFF stack or photon stream to measure.
    split, channel, channel_2, second_filename, pixel_size_nm, criterion, bin_width, smooth, axis_order
        See :func:`chisurf.plugins.microscopy.img_frc.core.analyse`.
    output_path : str, optional
        Write the curve to this CSV path as well.
    **load_kwargs
        Photon streams only: ``channels`` / ``windows``.

    Returns
    -------
    dict
        :meth:`~...core.FrcAnalysis.to_dict` plus ``output_path``.
    """
    analysis = core.analyse(
        filename,
        split=split,
        channel=channel,
        channel_2=channel_2,
        second_filename=second_filename,
        pixel_size_nm=pixel_size_nm,
        criterion=criterion,
        bin_width=bin_width,
        smooth=smooth,
        axis_order=axis_order,
        **load_kwargs,
    )
    payload = analysis.to_dict()
    payload["output_path"] = core.write_csv(analysis, output_path) if output_path else ""
    return payload


def list_criteria() -> dict[str, Any]:
    """Return the criteria, the splits that feed them and the TIFF axis orders."""
    return {
        "criteria": list(frc_mod.CRITERIA),
        "splits": list(core.SPLITS),
        "axis_orders": list(core.AXIS_ORDERS),
    }
