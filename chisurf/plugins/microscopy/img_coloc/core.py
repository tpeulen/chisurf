"""Qt-free compute for the colocalization plugin.

Loads a two-or-more-channel image (TIFF stack or photon stream) through the
shared image-source seam and evaluates the colocalization coefficients on a
selected channel pair. The GUI, the CLI, and the tests all call
:func:`compute_colocalization`.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from chisurf.core.fluorescence.imaging import (
    ColocalizationResult,
    colocalization_metrics,
    estimate_background,
    load_image_stack,
)


def compute_colocalization(
    filename: str,
    channel_a: Any = 0,
    channel_b: Any = 1,
    *,
    frame: int | None = None,
    windows: dict | None = None,
    channel_axis: Any = None,
    auto_background: bool = False,
    background_quantile: float = 0.05,
    background_a: float = 0.0,
    background_b: float = 0.0,
    threshold_a: float = 0.0,
    threshold_b: float = 0.0,
    auto_threshold: bool = False,
    gate: tuple[float, float, float, float] | None = None,
    bins: int = 128,
    costes_test: bool = False,
    costes_block: int = 4,
    costes_randomizations: int = 200,
    costes_seed: int = 0,
    ccf_max_shift: int = 0,
) -> dict:
    """Compute colocalization coefficients for a channel pair of one image file.

    Parameters
    ----------
    filename : str
        TIFF/camera image or photon-stream (PTU/HT3/…) file.
    channel_a, channel_b : int or str
        The two channels, given as indices or channel names.
    frame : int, optional
        Analyse this single frame; ``None`` sums all frames.
    windows : dict, optional
        Photon streams only: named detector windows used as channels.
    channel_axis : int or str, optional
        Images only: force which array axis holds the channels.
    auto_background : bool
        Estimate each channel's background as its ``background_quantile``
        quantile instead of using the supplied values.
    background_quantile : float
        Quantile used by ``auto_background``.
    background_a, background_b : float
        Manual per-channel background.
    threshold_a, threshold_b : float
        Manual per-channel intensity thresholds (after background subtraction).
    auto_threshold : bool
        Derive the thresholds with Costes' automatic method.
    gate : tuple of float, optional
        ``(a_min, a_max, b_min, b_max)`` rectangle in the scatter plane.
    bins : int
        Joint-histogram bin count per axis.
    costes_test : bool
        Run Costes' randomization significance test.
    costes_block, costes_randomizations, costes_seed : int
        Parameters of that test.
    ccf_max_shift : int
        When > 0, also compute the van Steensel shift profile.

    Returns
    -------
    dict
        ``{"metrics", "result", "stack", "image_a", "image_b", "channel_names",
        "shape"}`` — the scalar coefficients, the full
        :class:`~chisurf.core.fluorescence.imaging.colocalization.ColocalizationResult`,
        and the loaded stack for display.
    """
    stack = load_image_stack(filename, windows=windows, channel_axis=channel_axis)
    if stack.n_channels < 2:
        raise ValueError(
            f"{filename} has only {stack.n_channels} channel(s); colocalization needs two"
        )
    image_a = stack.image(channel_a, frame)
    image_b = stack.image(channel_b, frame)
    if auto_background:
        background_a = estimate_background(image_a, background_quantile)
        background_b = estimate_background(image_b, background_quantile)
    result: ColocalizationResult = colocalization_metrics(
        image_a,
        image_b,
        background_a=background_a,
        background_b=background_b,
        threshold_a=threshold_a,
        threshold_b=threshold_b,
        auto_threshold=auto_threshold,
        gate=gate,
        bins=bins,
        costes_test=costes_test,
        costes_block=costes_block,
        costes_randomizations=costes_randomizations,
        costes_seed=costes_seed,
        ccf_max_shift=ccf_max_shift,
    )
    if result.metrics.get("n_pixels", 0) == 0:
        result.metrics["warning"] = (
            "no pixel passes both thresholds — check the background/threshold settings "
            "and that both channels carry signal"
        )
    return {
        "metrics": result.metrics,
        "result": result,
        "stack": stack,
        "image_a": result.image_a,
        "image_b": result.image_b,
        "channel_names": list(stack.channel_names),
        "shape": tuple(np.asarray(image_a).shape),
    }


#: Ordered ``(key, label)`` pairs used to present the metric set.
METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("pearson", "Pearson PCC (thresholded)"),
    ("pearson_all", "Pearson PCC (all pixels)"),
    ("manders_overlap", "Manders overlap MOC"),
    ("manders_m1", "Manders M1 (A with B)"),
    ("manders_m2", "Manders M2 (B with A)"),
    ("li_icq", "Li ICQ"),
    ("spearman", "Spearman rank"),
    ("coloc_area_fraction", "Colocalized area fraction"),
    ("threshold_a", "Threshold A"),
    ("threshold_b", "Threshold B"),
    ("background_a", "Background A"),
    ("background_b", "Background B"),
    ("n_pixels", "Pixels above threshold"),
    ("n_pixels_total", "Pixels total"),
    ("gated_pearson", "Gate: Pearson PCC"),
    ("gated_manders_overlap", "Gate: Manders MOC"),
    ("n_pixels_gated", "Gate: pixels"),
    ("costes_p_value", "Costes p-value"),
    ("costes_r_random_mean", "Costes random PCC mean"),
    ("ccf_peak_shift", "van Steensel peak shift (px)"),
    ("ccf_peak", "van Steensel peak PCC"),
)


def metric_rows(metrics: dict) -> list[dict]:
    """Return the metrics as ordered ``{"name", "value"}`` rows for a table.

    Parameters
    ----------
    metrics : dict
        The ``metrics`` mapping of :func:`compute_colocalization`.

    Returns
    -------
    list of dict
        One row per present metric, in presentation order.
    """
    rows: list[dict] = []
    for key, label in METRIC_LABELS:
        if key not in metrics:
            continue
        value = metrics[key]
        if isinstance(value, float):
            text = "n/a" if not np.isfinite(value) else f"{value:.4g}"
        else:
            text = str(value)
        rows.append({"name": label, "value": text})
    return rows
