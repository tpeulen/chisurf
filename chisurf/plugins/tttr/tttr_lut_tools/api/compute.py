"""High-level LUT orchestration shared by the cli / rpc / gui layers.

These functions tie the pure math (:mod:`.lut`) to file IO (:mod:`.io`) so the
backend service and the CLI can compute a LUT from raw files in one call.
"""

from __future__ import annotations

import numpy as np

from . import io, lut


def compute_lut_from_counts(
    counts: np.ndarray,
    linear_start: int | None = None,
    linear_stop: int | None = None,
    ntac_required: int | None = None,
    noffset: int = 0,
) -> dict:
    """Build a LUT from a TAC histogram, auto-detecting the region if needed.

    Parameters
    ----------
    counts : numpy.ndarray
        TAC histogram of a uniform-illumination measurement.
    linear_start, linear_stop : int or None
        Linear-region bounds; auto-detected when either is ``None``.
    ntac_required : int or None
        Target NTAC bin count; defaults to ``len(counts)``.
    noffset : int
        Offset subtracted from corrected indices.

    Returns
    -------
    dict
        The LUT table from :func:`.lut.build_linearization_table`.
    """
    counts = np.asarray(counts)
    if linear_start is None or linear_stop is None:
        linear_start, linear_stop = lut.autodetect_linear_region(counts, noffset_guess=noffset)
    if not ntac_required or ntac_required <= 0:
        ntac_required = int(len(counts))
    return lut.build_linearization_table(
        counts, int(linear_start), int(linear_stop), int(ntac_required), int(noffset)
    )


def compute_lut_from_files(
    files: list[str],
    routine: str | None = None,
    n_bins: int | None = None,
    linear_start: int | None = None,
    linear_stop: int | None = None,
    ntac_required: int | None = None,
    noffset: int = 0,
    channel: int | None = None,
) -> dict:
    """Compute a LUT directly from raw TTTR files (load → histogram → build).

    Parameters
    ----------
    files : list of str
        TTTR files of a uniform-illumination measurement.
    routine : str or None
        tttrlib reading routine.
    n_bins : int or None
        TAC bin count; inferred from the data when ``None``.
    linear_start, linear_stop : int or None
        Linear-region bounds; auto-detected when either is ``None``.
    ntac_required : int or None
        Target NTAC bin count.
    noffset : int
        Offset subtracted from corrected indices.
    channel : int or None
        Routing channel to compute the LUT for (per-channel LUTs are the
        physically correct unit). ``None`` pools all channels.

    Returns
    -------
    dict
        The LUT table (``NTAC_fract`` + metadata).
    """
    micro = io.load_microtimes(files, routine=routine, channel=channel)
    nb = lut.infer_n_bins(micro, n_bins)
    counts = lut.histogram_micro(micro, nb)
    return compute_lut_from_counts(counts, linear_start, linear_stop, ntac_required, noffset)
