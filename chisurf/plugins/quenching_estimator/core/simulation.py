"""Headless QuEst backend helpers.

This module provides a small, GUI-free service layer around the legacy
`DonorDecay` simulation so other code (CLI, notebooks, tests) can drive
the core quenching/FRET calculations without depending on any Qt widgets.

It intentionally mirrors the public surface of ``quest.api`` but keeps
the logic in one place so both the CLI and notebook users can share it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Sequence, Tuple

import csv
import json
import struct
import numpy as np

from chisurf.plugins.quenching_estimator.core.av import av_defaults as _av_defaults
from chisurf.plugins.quenching_estimator.core.dye_diffusion import DonorDecay, normalize_amino_acid_interactions
from chisurf.plugins.quenching_estimator.core.photon import simulate_decay_quench
from chisurf.plugins.quenching_estimator.core.structure import resolve_structure_path


def autocorr(x: np.ndarray, axis: int = 0, normalize: bool = True) -> np.ndarray:
    """Normalised autocorrelation of a series, via FFT.

    Twelve lines of NumPy, kept here beside its only caller rather than in a
    module of its own. ChiSurf has `chisurf.core.math.signal.autocorr`; QuEst
    does not import it, because a headless simulation should not load a host
    application to correlate an array.
    """
    x = np.asarray(x)
    if x.size == 0:
        return np.array([], dtype=x.dtype)
    n = x.shape[axis]
    centred = x - np.mean(x, axis=axis)
    # Pad to 2N so the FFT gives the linear, not the circular, correlation.
    spectrum = np.fft.fft(centred, n=2 * n, axis=axis)
    index = [slice(None)] * x.ndim
    index[axis] = slice(0, n)
    acf = np.fft.ifft(spectrum * np.conjugate(spectrum), axis=axis)[tuple(index)].real
    if not normalize:
        return acf
    index[axis] = 0
    return acf / acf[tuple(index)]


def write_mrc(filename: Path | str, grid: np.ndarray, dg: float, origin: np.ndarray) -> None:
    """Write a 3D density grid (NumPy array) to an MRC file."""
    grid = np.ascontiguousarray(grid, dtype=np.float32)
    nx, ny, nz = grid.shape
    
    header = bytearray(1024)
    
    # Word 1-3: NC, NR, NS (columns, rows, sections)
    struct.pack_into('<iii', header, 0, nx, ny, nz)
    # Word 4: MODE = 2 (float32)
    struct.pack_into('<i', header, 12, 2)
    # Word 5-7: NCSTART, NRSTART, NSSTART = 0, 0, 0
    struct.pack_into('<iii', header, 16, 0, 0, 0)
    # Word 8-10: MX, MY, MZ = NC, NR, NS
    struct.pack_into('<iii', header, 28, nx, ny, nz)
    # Word 11-13: X, Y, Z cell dimensions (in Angstroms)
    struct.pack_into('<fff', header, 40, nx * dg, ny * dg, nz * dg)
    # Word 14-16: cell angles = 90.0, 90.0, 90.0
    struct.pack_into('<fff', header, 52, 90.0, 90.0, 90.0)
    # Word 17-19: MAPC, MAPR, MAPS = 1, 2, 3 (axes order X, Y, Z)
    struct.pack_into('<iii', header, 64, 1, 2, 3)
    # Word 20-22: DMIN, DMAX, DMEAN
    dmin = float(grid.min())
    dmax = float(grid.max())
    dmean = float(grid.mean())
    struct.pack_into('<fff', header, 76, dmin, dmax, dmean)
    # Word 23: ISPG = 1
    struct.pack_into('<i', header, 88, 1)
    
    # Word 50-52: Origin X, Y, Z
    ox, oy, oz = float(origin[0]), float(origin[1]), float(origin[2])
    struct.pack_into('<fff', header, 196, ox, oy, oz)
    
    # Word 53: MAP string identifier
    header[208:212] = b'MAP '
    
    # Word 54: Machine stamp (little endian)
    struct.pack_into('<I', header, 212, 0x44410000)
    
    with open(filename, 'wb') as f:
        f.write(header)
        f.write(grid.tobytes())


def sampled_density_grid(
    points: np.ndarray,
    *,
    shape: tuple[int, int, int],
    dg: float,
    center: np.ndarray,
    allowed_density: np.ndarray | None = None,
) -> np.ndarray:
    """Return a voxel-count density grid for sampled dye positions."""

    grid = np.zeros(shape, dtype=np.float32)
    samples = np.asarray(points, dtype=np.float64)
    if samples.size == 0:
        return grid
    samples = samples.reshape((-1, 3))

    center_index = (np.asarray(shape, dtype=np.float64) - 1.0) / 2.0
    indices = np.trunc((samples - np.asarray(center, dtype=np.float64)) / float(dg) + center_index).astype(np.int64)
    inside = np.isfinite(samples).all(axis=1)
    for axis, size in enumerate(shape):
        inside &= (indices[:, axis] >= 0) & (indices[:, axis] < size)
    if allowed_density is not None:
        allowed = np.asarray(allowed_density)
        candidate = indices[inside]
        allowed_mask = allowed[tuple(candidate.T)] > 0
        inside_indices = np.flatnonzero(inside)
        inside[inside_indices] = allowed_mask
    accepted = indices[inside]
    if len(accepted):
        np.add.at(grid, tuple(accepted.T), 1.0)
    return grid


def diffusion_coefficient_grid(
    density: np.ndarray,
    *,
    diffusion_coefficient: float,
    slow_factor_grid: np.ndarray | None = None,
    slow_density: np.ndarray | None = None,
    slow_factor: float = 1.0,
) -> np.ndarray:
    """Return the local diffusion coefficient for each AV voxel."""

    accessible = np.asarray(density) > 0
    coefficients = np.zeros(accessible.shape, dtype=np.float32)
    coefficients[accessible] = float(diffusion_coefficient)

    if slow_factor_grid is not None:
        factors = np.asarray(slow_factor_grid, dtype=np.float32)
        if factors.shape != coefficients.shape:
            raise ValueError("slow_factor_grid shape must match density shape")
        coefficients[accessible] = float(diffusion_coefficient) * factors[accessible]
        return coefficients

    if slow_density is not None:
        slow = (np.asarray(slow_density) > 0) & accessible
        coefficients[slow] = float(diffusion_coefficient) * float(slow_factor)
    return coefficients


def _normalize_residue_name(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("ascii", errors="ignore").strip().upper()
    text = str(value).strip().upper()
    if text.startswith("B'") and text.endswith("'"):
        return text[2:-1].strip().upper()
    return text


def _run_length_stats(mask):
    """Return ``(event_count, total_frames, max_run)`` for a boolean sequence."""
    mask = np.asarray(mask, dtype=bool)
    if mask.size == 0:
        return 0, 0, 0
    edges = np.diff(np.concatenate(([False], mask, [False])).astype(np.int8))
    starts = np.flatnonzero(edges == 1)
    runs = np.flatnonzero(edges == -1) - starts
    return int(runs.size), int(np.count_nonzero(mask)), int(runs.max()) if runs.size else 0


def _frame_blocks(n_frames: int, width: int, budget: int = 2_000_000):
    """Yield ``(f0, f1)`` frame blocks so a ``(f1 - f0, width)`` temporary stays bounded."""
    step = max(1, budget // max(width, 1))
    for f0 in range(0, n_frames, step):
        yield f0, min(n_frames, f0 + step)


def _squared_distances(points, centers):
    """``(n_points, n_centers)`` squared distances, coordinate by coordinate."""
    d2 = np.zeros((points.shape[0], centers.shape[0]))
    for axis in range(3):
        d = points[:, axis, None] - centers[None, :, axis]
        d2 += d * d
    return d2


def _residue_type_contact_stats(
    trajectory,
    slow_centers,
    quench_centers,
    center_type,
    slow_radius,
    quench_radius,
    quench_rate,
    n_types,
):
    """Per residue type: proximity, residence events and quenching contribution.

    Vectorised over frames for each residue type; the residence events are the
    runs of frames within ``slow_radius`` of the type's nearest centre.
    """
    trajectory = np.asarray(trajectory, dtype=np.float64)
    slow_centers = np.asarray(slow_centers, dtype=np.float64)
    quench_centers = np.asarray(quench_centers, dtype=np.float64)
    center_type = np.asarray(center_type)
    n_frames = trajectory.shape[0]

    frames_near = np.zeros(n_types, dtype=np.int64)
    distance_sum = np.zeros(n_types, dtype=np.float64)
    event_count = np.zeros(n_types, dtype=np.int64)
    max_event = np.zeros(n_types, dtype=np.int64)
    quench_rate_sum = np.zeros(n_types, dtype=np.float64)
    quench_frames = np.zeros(n_types, dtype=np.int64)

    for type_id in range(n_types):
        members = np.flatnonzero(center_type == type_id)
        slow_radius2 = slow_radius[type_id] * slow_radius[type_id]
        quench_radius2 = quench_radius[type_id] * quench_radius[type_id]
        nearest2 = np.full(n_frames, np.inf)
        contacts = np.zeros(n_frames, dtype=np.int64)
        if members.size:
            for f0, f1 in _frame_blocks(n_frames, members.size):
                frames = trajectory[f0:f1]
                nearest2[f0:f1] = _squared_distances(frames, slow_centers[members]).min(axis=1)
                contacts[f0:f1] = np.count_nonzero(
                    _squared_distances(frames, quench_centers[members]) <= quench_radius2, axis=1
                )
        distance_sum[type_id] = np.sum(np.sqrt(nearest2))
        quenched = contacts > 0
        quench_rate_sum[type_id] = np.sum(contacts[quenched] * quench_rate[type_id])
        quench_frames[type_id] = np.count_nonzero(quenched)
        near = nearest2 <= slow_radius2
        events, total, longest = _run_length_stats(near)
        frames_near[type_id] = total
        event_count[type_id] = events
        max_event[type_id] = longest

    return frames_near, distance_sum, event_count, max_event, quench_rate_sum, quench_frames


def _attribute_frames_to_residue_type(
    trajectory, slow_centers, center_type, center_factor, radius
):
    """Assign each frame to the residue type it is most strongly slowed by.

    Ties on the slowing factor are broken by distance (then by centre order);
    frames with no centre in range get ``-1``.
    """
    trajectory = np.asarray(trajectory, dtype=np.float64)
    slow_centers = np.asarray(slow_centers, dtype=np.float64)
    center_type = np.asarray(center_type, dtype=np.int64)
    center_factor = np.asarray(center_factor, dtype=np.float64)
    n_frames = trajectory.shape[0]
    n_centers = slow_centers.shape[0]
    radius2 = radius * radius
    assigned = np.full(n_frames, -1, dtype=np.int64)
    if n_centers == 0:
        return assigned
    for f0, f1 in _frame_blocks(n_frames, n_centers):
        d2 = _squared_distances(trajectory[f0:f1], slow_centers)
        # A NaN factor never wins a comparison, so it never selects a centre.
        eligible = (d2 <= radius2) & ~np.isnan(center_factor)[None, :]
        factor = np.where(eligible, center_factor[None, :], np.inf)
        best = factor.min(axis=1, keepdims=True)
        candidate = eligible & (factor == best)
        dist = np.where(candidate, d2, np.inf)
        pick = np.argmin(dist, axis=1)
        found = candidate[np.arange(f1 - f0), pick]
        assigned[f0:f1] = np.where(found, center_type[pick], -1)
    return assigned


def _true_run_lengths(mask: np.ndarray) -> list[int]:
    runs: list[int] = []
    current = 0
    for value in mask:
        if bool(value):
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs


def autocorr_to_tau_window(
    values: np.ndarray | Sequence[float],
    *,
    tau0: float,
    t_step: float,
    tau_factor: float = 10.0,
) -> np.ndarray:
    """Return autocorrelation lags from 0 through approximately ``tau_factor * tau0``."""

    series = np.asarray(values)
    if len(series) == 0:
        return autocorr(series)

    tau0 = float(tau0)
    t_step = float(t_step)
    tau_factor = float(tau_factor)
    if tau0 <= 0.0 or t_step <= 0.0 or tau_factor <= 0.0:
        return autocorr(series)

    max_lag_frames = int(np.ceil((tau_factor * tau0) / t_step))
    lag_count = min(len(series), max_lag_frames + 1)
    if series.ndim != 1 or lag_count >= len(series):
        return autocorr(series)[:lag_count]

    centered = np.asarray(series, dtype=np.float64) - float(np.mean(series))
    denominator = float(np.dot(centered, centered))
    if denominator == 0.0:
        return autocorr(series)[:lag_count]

    # Linear (not circular) autocorrelation via FFT: pad to at least 2N so the
    # wrap-around terms fall outside the window we keep.
    size = int(1 << int(np.ceil(np.log2(2 * len(centered)))))
    spectrum = np.fft.rfft(centered, n=size)
    correlation = np.fft.irfft(spectrum * np.conjugate(spectrum), n=size)[:lag_count]
    return correlation / denominator


def _flatten_center_groups(
    centers_by_residue: Mapping[str, Any],
    quench_centers_by_residue: Mapping[str, Any] | None = None,
) -> tuple[list[str], np.ndarray, np.ndarray, np.ndarray]:
    """Flatten ``{residue: centers}`` groups into kernel-friendly arrays."""

    names: list[str] = []
    slow_blocks: list[np.ndarray] = []
    quench_blocks: list[np.ndarray] = []
    type_ids: list[np.ndarray] = []

    for residue_name in sorted(centers_by_residue):
        normalized_name = _normalize_residue_name(residue_name)
        slow = np.asarray(centers_by_residue[residue_name], dtype=np.float64).reshape((-1, 3))
        if slow.size == 0:
            continue
        if quench_centers_by_residue is None:
            quench = slow
        else:
            quench = np.asarray(
                quench_centers_by_residue.get(residue_name, slow), dtype=np.float64
            ).reshape((-1, 3))
            if quench.shape[0] != slow.shape[0]:
                raise ValueError(
                    f"quench centers for {normalized_name} do not match the slow centers"
                )
        type_ids.append(np.full(slow.shape[0], len(names), dtype=np.int64))
        names.append(normalized_name)
        slow_blocks.append(slow)
        quench_blocks.append(quench)

    if not names:
        empty = np.empty((0, 3), dtype=np.float64)
        return [], empty, empty, np.empty(0, dtype=np.int64)
    return names, np.vstack(slow_blocks), np.vstack(quench_blocks), np.concatenate(type_ids)


def _subsample_points(points: Any, limit: int, decimals: int | None = None) -> Optional[np.ndarray]:
    """Evenly thin a point cloud down to at most ``limit`` points.

    ``decimals`` rounds the result, which keeps the JSON payload small; use it
    only for data headed to a plot or 3D viewer, never for derived quantities.
    """
    if points is None:
        return None
    array = np.asarray(points)
    if limit > 0 and len(array) > limit:
        indices = np.linspace(0, len(array) - 1, limit, dtype=np.int64)
        array = array[indices]
    if decimals is not None and np.issubdtype(array.dtype, np.floating):
        array = np.round(array, decimals)
    return array


def _as_trajectory(trajectory: Any) -> np.ndarray:
    if trajectory is None:
        return np.empty((0, 3), dtype=np.float64)
    return np.ascontiguousarray(
        np.asarray(trajectory, dtype=np.float64).reshape((-1, 3))
    )


def calculate_aa_quenching(
    trajectory: np.ndarray | Sequence[Sequence[float]] | None,
    quench_centers_by_residue: Mapping[str, np.ndarray | Sequence[Sequence[float]]],
    *,
    quench_radii: Mapping[str, float],
    quench_rates: Mapping[str, float],
    chunk_size: int = 4096,
) -> dict[str, dict[str, float]]:
    """Decompose the time-averaged quenching rate by residue type.

    The total quenching rate experienced by the dye is the sum of the rates
    contributed by every quenching centre within its contact radius, so it
    splits exactly into per-residue-type contributions. Returns, per residue
    type, the mean contributed rate (1/ns), the fraction of the total, and the
    fraction of frames in which that residue type quenched at all.

    ``chunk_size`` is accepted for backwards compatibility and ignored.
    """

    samples = _as_trajectory(trajectory)
    if samples.shape[0] == 0:
        return {}

    names, slow_centers, quench_centers, center_type = _flatten_center_groups(
        quench_centers_by_residue, quench_centers_by_residue
    )
    if not names:
        return {}

    radii = np.asarray(
        [float(quench_radii.get(name, 0.0) or 0.0) for name in names], dtype=np.float64
    )
    rates = np.asarray(
        [float(quench_rates.get(name, 0.0) or 0.0) for name in names], dtype=np.float64
    )

    _near, _distance, _events, _max_event, rate_sum, quench_frames = _residue_type_contact_stats(
        samples,
        slow_centers,
        quench_centers,
        center_type,
        np.zeros(len(names), dtype=np.float64),
        radii,
        rates,
        len(names),
    )

    frame_count = float(samples.shape[0])
    contributions: dict[str, dict[str, float]] = {}
    for index, name in enumerate(names):
        if rates[index] <= 0.0 or radii[index] <= 0.0:
            continue
        contributions[name] = {
            "mean_quench_rate": float(rate_sum[index]) / frame_count,
            "fraction_frames_quenched": float(quench_frames[index]) / frame_count,
        }

    total = sum(item["mean_quench_rate"] for item in contributions.values())
    for item in contributions.values():
        item["quench_rate_fraction"] = item["mean_quench_rate"] / total if total > 0.0 else 0.0
    return contributions


def calculate_aa_residence(
    trajectory: np.ndarray | Sequence[Sequence[float]] | None,
    centers_by_residue: Mapping[str, np.ndarray | Sequence[Sequence[float]]],
    *,
    t_step: float,
    radius: float,
    effective_slow_factors: Mapping[str, float | None] | None = None,
    chunk_size: int = 4096,
) -> list[dict[str, Any]]:
    """Calculate dye residence statistics near residue-type center groups.

    ``chunk_size`` is accepted for backwards compatibility and ignored.
    """

    return _residue_type_metrics(
        trajectory,
        centers_by_residue,
        t_step=t_step,
        radius=radius,
        effective_slow_factors=effective_slow_factors,
    )


def _residue_type_metrics(
    trajectory: np.ndarray | Sequence[Sequence[float]] | None,
    centers_by_residue: Mapping[str, Any],
    *,
    t_step: float,
    radius: float,
    effective_slow_factors: Mapping[str, float | None] | None = None,
    quench_centers_by_residue: Mapping[str, Any] | None = None,
    quench_radii: Mapping[str, float] | None = None,
    quench_rates: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Residence and (optionally) quenching metrics, in a single trajectory pass."""

    samples = _as_trajectory(trajectory)
    frame_count = int(samples.shape[0])
    radius = float(radius)
    t_step = float(t_step)
    slow_factors = effective_slow_factors or {}
    quench_radii = quench_radii or {}
    quench_rates = quench_rates or {}

    names, slow_centers, quench_centers, center_type = _flatten_center_groups(
        centers_by_residue, quench_centers_by_residue
    )
    if not names:
        return []

    center_counts = np.bincount(center_type, minlength=len(names))
    radii = np.asarray(
        [float(quench_radii.get(name, 0.0) or 0.0) for name in names], dtype=np.float64
    )
    rates = np.asarray(
        [float(quench_rates.get(name, 0.0) or 0.0) for name in names], dtype=np.float64
    )

    if frame_count:
        (
            frames_near,
            distance_sum,
            event_count,
            max_event,
            rate_sum,
            quench_frames,
        ) = _residue_type_contact_stats(
            samples,
            slow_centers,
            quench_centers,
            center_type,
            np.full(len(names), radius, dtype=np.float64),
            radii,
            rates,
            len(names),
        )

        center_factor = np.asarray(
            [
                1.0 if slow_factors.get(names[type_id]) is None else float(slow_factors[names[type_id]])
                for type_id in center_type
            ],
            dtype=np.float64,
        )
        assigned = _attribute_frames_to_residue_type(
            samples, slow_centers, center_type, center_factor, radius
        )
    else:
        zeros = np.zeros(len(names), dtype=np.int64)
        frames_near = zeros
        distance_sum = np.zeros(len(names), dtype=np.float64)
        event_count = zeros
        max_event = zeros
        rate_sum = np.zeros(len(names), dtype=np.float64)
        quench_frames = zeros
        assigned = np.empty(0, dtype=np.int64)

    total_quench_rate = float(rate_sum.sum())

    rows: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        near_frames = int(frames_near[index])
        events = int(event_count[index])
        mean_event_frames = near_frames / events if events else 0.0

        attributed_mask = assigned == index
        attributed_events, attributed_frames, attributed_max = (
            _run_length_stats(attributed_mask) if frame_count else (0, 0, 0)
        )
        attributed_mean = attributed_frames / attributed_events if attributed_events else 0.0

        rows.append(
            {
                "residue_name": name,
                "center_count": int(center_counts[index]),
                "effective_slow_factor": slow_factors.get(name),
                "frames_near": near_frames,
                "fraction_near": near_frames / frame_count if frame_count else 0.0,
                "total_time_ns": near_frames * t_step,
                "event_count": events,
                "mean_event_time_ns": mean_event_frames * t_step,
                "max_event_time_ns": int(max_event[index]) * t_step,
                "mean_min_distance_angstrom": (
                    float(distance_sum[index]) / frame_count if frame_count else None
                ),
                "attributed_frames_near": int(attributed_frames),
                "attributed_fraction_near": attributed_frames / frame_count if frame_count else 0.0,
                "attributed_total_time_ns": attributed_frames * t_step,
                "attributed_event_count": int(attributed_events),
                "attributed_mean_event_time_ns": attributed_mean * t_step,
                "attributed_max_event_time_ns": int(attributed_max) * t_step,
                "kQ": float(rates[index]),
                "quench_radius": float(radii[index]),
                "mean_quench_rate": float(rate_sum[index]) / frame_count if frame_count else 0.0,
                "quench_rate_fraction": (
                    float(rate_sum[index]) / total_quench_rate if total_quench_rate > 0.0 else 0.0
                ),
                "fraction_frames_quenched": (
                    float(quench_frames[index]) / frame_count if frame_count else 0.0
                ),
            }
        )
    return rows


def top_quenchers(aa_residence: Any, limit: int = 3) -> list[dict[str, Any]]:
    """Residue types that actually quenched at a site, strongest first.

    Lets a scan answer "is this site quenched, and by what?" without carrying
    the whole residence table for every scanned position.
    """

    rows = [row for row in (aa_residence or []) if (row.get("mean_quench_rate") or 0.0) > 0.0]
    rows.sort(key=lambda row: row.get("quench_rate_fraction") or 0.0, reverse=True)
    return [
        {
            "residue_name": row["residue_name"],
            "quench_rate_fraction": row.get("quench_rate_fraction"),
            "mean_quench_rate": row.get("mean_quench_rate"),
        }
        for row in rows[:limit]
    ]


def aa_residence_from_model(model: DonorDecay) -> list[dict[str, Any]]:
    """Return residue-type residence metrics for a completed donor model."""

    raw_trajectory = getattr(getattr(model, "diffusion", None), "_traj", None)
    if raw_trajectory is None:
        return []

    try:
        centers, quench_centers, residue_names = model.residue_site_data
    except Exception:
        return []

    centers_by_residue: dict[str, list[np.ndarray]] = {}
    quench_centers_by_residue: dict[str, list[np.ndarray]] = {}
    for center, quench_center, residue_name in zip(
        np.asarray(centers, dtype=np.float64),
        np.asarray(quench_centers, dtype=np.float64),
        residue_names,
    ):
        normalized_name = _normalize_residue_name(residue_name)
        centers_by_residue.setdefault(normalized_name, []).append(center)
        quench_centers_by_residue.setdefault(normalized_name, []).append(quench_center)

    effective_slow_factors: dict[str, float | None] = {}
    quench_rates: dict[str, float] = {}
    quench_radii: dict[str, float] = {}
    for residue_name in centers_by_residue:
        try:
            effective_slow_factors[residue_name] = float(model._slow_facts_for_residue_names([residue_name])[0])
        except Exception:
            effective_slow_factors[residue_name] = None
        try:
            quench_rates[residue_name] = float(model._kq_for_residue_names([residue_name])[0])
            quench_radii[residue_name] = float(model._quench_radii_for_residue_names([residue_name])[0])
        except Exception:
            quench_rates[residue_name] = 0.0
            quench_radii[residue_name] = 0.0

    return _residue_type_metrics(
        raw_trajectory,
        {name: np.vstack(points) for name, points in centers_by_residue.items()},
        t_step=float(getattr(model, "t_step", 0.0) or 0.0),
        radius=float(getattr(model, "slow_radius", 0.0) or 0.0),
        effective_slow_factors=effective_slow_factors,
        quench_centers_by_residue={
            name: np.vstack(points) for name, points in quench_centers_by_residue.items()
        },
        quench_radii=quench_radii,
        quench_rates=quench_rates,
    )


@dataclass
class DecaySimulationResult:
    """Container for a single QuEst decay simulation."""

    time: np.ndarray
    donor_counts: np.ndarray
    fret_counts: Optional[np.ndarray]
    quantum_yield_donor: float
    quantum_yield_fret: Optional[float]
    collisions_fraction: float
    fret_efficiency: Optional[float]
    project: Mapping[str, Any]
    trajectory_distance_to_mean: Optional[np.ndarray] = None
    trajectory_time_ns: Optional[np.ndarray] = None
    trajectory_autocorr: Optional[np.ndarray] = None
    trajectory_autocorr_lag_ns: Optional[np.ndarray] = None
    trajectory_points: Optional[np.ndarray] = None
    av_points: Optional[np.ndarray] = None
    acv_points: Optional[np.ndarray] = None
    job_id: Optional[str] = None
    lifetime_donor: Optional[float] = None
    av_volume: Optional[float] = None
    contact_volume: Optional[float] = None
    contact_to_free_ratio: Optional[float] = None
    aa_residence: Optional[list[dict[str, Any]]] = None


def load_project(path: Path | str) -> MutableMapping[str, Any]:
    """Load a QuEst project JSON file into a mutable dictionary."""

    p = Path(path)
    with p.open("r", encoding="utf8") as fp:
        return json.load(fp)


def build_donor_from_project(
    project: Mapping[str, Any],
    pdb_path: Optional[Path | str] = None,
) -> DonorDecay:
    """Create and configure a :class:`DonorDecay` from a project mapping."""

    p = project

    attachment = p.get("attachment") or {}

    fret_block = p.get("fret") or {}
    dyes = fret_block.get("dyes") or []
    if not dyes:
        raise KeyError("Project must define at least one dye with a diffusion coefficient 'D'.")
    donor_dye = dyes[0]
    donor_D = donor_dye.get("D")
    if donor_D is None:
        raise KeyError("Donor dye entry must define diffusion coefficient 'D'.")
    slow_radius = p.get("slow_radius", donor_dye.get("slow_radius", 8.5))
    amino_acid_interactions = p.get("amino_acid_interactions", donor_dye.get("amino_acid_interactions"))
    parallel_trajectories = p.get("parallel_trajectories", -1)
    if parallel_trajectories is None:
        parallel_trajectories = -1

    d = DonorDecay(
        tau0=p["tau0"],
        kQ=p.get("kQ", 0.0),
        nph=p["n_photons"],
        verbose=False,
        auto_update=False,
        pdb=None,
        attachment_residue=attachment.get("residue"),
        attachment_atom=attachment.get("atom"),
        attachment_chain=attachment.get("chain"),
        dg=p["dg"],
        sticky_mode="surface",
        save_avs=p.get("save_avs", False),
        D=donor_D,
        slow_fact=1.0,
        critical_distance=p["critical_distance"],
        output_file=p.get("output_file", "out"),
        av_parameter=p["av_parameter"],
        quencher={},
        t_max=p["t_max"],
        t_step=p["t_step"],
        slow_radius=slow_radius,
        all_quencher_atoms=False,
        stickiness_mode="amino_acid",
        amino_acid_interactions=amino_acid_interactions,
        random_seed=donor_dye.get("random_seed", p.get("random_seed")),
        parallel_trajectories=int(parallel_trajectories),
        coarse_grained=bool(p.get("coarse_grained", donor_dye.get("coarse_grained", False))),
    )

    structure_source = pdb_path or p.get("pdb")
    if structure_source is None:
        raise ValueError("Project must define a 'pdb' path or pdb_path must be given.")
    d.structure = str(resolve_structure_path(structure_source))

    fret = p.get("fret") or {}
    if fret.get("enabled"):
        d.fret_enabled = True
        dyes = fret.get("dyes") or []
        if len(dyes) > 1:
            acceptor = dyes[1]
            acc_att = acceptor.get("attachment") or {}
            d.acceptor_chain = acc_att.get("chain")
            d.acceptor_residue = acc_att.get("residue")
            d.acceptor_atom = acc_att.get("atom")
            av_param_acc = acceptor.get("av_parameter")
            if av_param_acc is not None:
                d.fret_av_parameter = av_param_acc

            # The acceptor is its own dye. Its diffusion coefficient, stickiness
            # radius and per-residue interaction table are read from its own
            # entry; each falls back to the donor's when absent, so a project
            # that says nothing about acceptor chemistry behaves as before.
            if acceptor.get("D") is not None:
                d.acceptor_diffusion_coefficient = float(acceptor["D"])
            if acceptor.get("slow_radius") is not None:
                d.acceptor_slow_radius = float(acceptor["slow_radius"])
            if acceptor.get("slow_fact") is not None:
                d.acceptor_slow_fact = float(acceptor["slow_fact"])
            if acceptor.get("amino_acid_interactions") is not None:
                d.acceptor_amino_acid_interactions = normalize_amino_acid_interactions(
                    acceptor["amino_acid_interactions"]
                )

        # Whether the acceptor diffuses too, or is averaged over its volume.
        dynamics = fret.get("acceptor_dynamics")
        if dynamics is not None:
            allowed = ("trajectory", "averaged")
            if str(dynamics).lower() not in allowed:
                raise ValueError(
                    f"fret.acceptor_dynamics must be one of {allowed}, got {dynamics!r}"
                )
            d.acceptor_dynamics = str(dynamics).lower()

        # Forster radii in Angstrom; the donor->acceptor cell is the one used.
        R0_matrix: Sequence[Sequence[Optional[float]]] = fret.get("R0_matrix") or []
        if R0_matrix and len(R0_matrix[0]) > 1:
            r01 = R0_matrix[0][1]
            if r01 is not None:
                d.fret_R0 = float(r01)

        # The orientation factor. **Stated, not modelled** -- QuEst's dye is a
        # point in a volume with no transition dipole, so this is the averaging
        # regime the user asserts, and 2/3 (isotropic) is what a published R0
        # already assumes. Validated in `_kappa2_scale`, so a project carrying
        # kappa2 = 9 is refused rather than quietly producing a rate 13x too
        # large. Closes OBJ-01 item 6 as *chosen and documented*.
        kappa2 = fret.get("kappa2")
        if kappa2 is not None:
            from chisurf.plugins.quenching_estimator.core.av import _kappa2_scale

            _kappa2_scale(kappa2)  # validate now, not eight frames into a run
            d.fret_kappa2_value = float(kappa2)

    return d


def _histogram_decay(
    model: DonorDecay,
    nbins: int,
    tac_range: Tuple[float, float],
) -> tuple[np.ndarray, np.ndarray]:
    edges, donor_counts = model.get_histogram(nbins=nbins, range=tac_range)
    time = 0.5 * (edges[:-1] + edges[1:])
    return time, donor_counts


def _curve_decay_from_model(
    model: DonorDecay,
    nbins: int,
    tac_range: Tuple[float, float],
    dt_tac: Optional[float],
    n_curves: Optional[int],
) -> tuple[np.ndarray, np.ndarray]:
    """Approximate legacy curve-mode decay using per-frame quenching rates.

    This uses the existing diffusion trajectory inside ``model`` together with
    a simple frame-wise quenching rate derived from ``model.kQ`` and the
    boolean collision trajectory. It falls back to the standard histogram
    behaviour if anything unexpected happens.
    """

    if nbins <= 0:
        return np.empty(0, dtype=float), np.empty(0, dtype=float)

    lo, hi = float(tac_range[0]), float(tac_range[1])
    if dt_tac is not None and dt_tac > 0.0:
        dt = float(dt_tac)
    else:
        span = hi - lo
        if span <= 0.0:
            span = float(nbins)
        dt = span / float(nbins)

    decay = np.zeros(int(nbins), dtype=np.float64)

    try:
        diffusion = model.diffusion
        collided = diffusion.quenched
        t_step = float(diffusion.t_step)
    except Exception:
        # If diffusion is unavailable, reuse the standard histogram path.
        return _histogram_decay(model, nbins, tac_range)

    # Build a per-frame quenching rate array from the collision trajectory.
    try:
        k_quench = diffusion.k_quench
    except Exception:
        kQ = float(getattr(model, "kQ", 2.0))
        k_quench = np.where(collided > 0, kQ, 0.0).astype(np.float32)

    curves = int(n_curves) if n_curves is not None else 0
    if curves <= 0:
        try:
            curves = int(getattr(model, "n_photons", 0)) // 1000
        except Exception:
            curves = 0
    if curves <= 0:
        curves = 1024

    simulate_decay_quench(
        n_curves=curves,
        decay=decay,
        dt_tac=dt,
        k_quench=k_quench,
        t_step=t_step,
        tau0=float(model.tau0),
    )

    edges = np.linspace(lo, lo + dt * nbins, nbins + 1, dtype=float)
    time = 0.5 * (edges[:-1] + edges[1:])
    return time, decay


def simulate_project(
    project: Mapping[str, Any],
    *,
    pdb_path: Optional[Path | str] = None,
    nbins: Optional[int] = None,
    tac_range: Tuple[float, float] = (0.0, 50.0),
    mode: Optional[str] = None,
    n_curves: Optional[int] = None,
    dt_tac: Optional[float] = None,
    n_tac: Optional[int] = None,
    project_dir: Optional[Path | str] = None,
    save_outputs: bool = False,
    render_data: Optional[bool] = None,
) -> DecaySimulationResult:
    """Run a full QuEst simulation from a project dictionary.

    Parameters
    ----------
    project:
        QuEst project mapping (same schema as the GUI JSON).
    pdb_path:
        Optional override for the structure path.
    nbins:
        Number of TAC bins for the donor (and FRET) histograms. Defaults to
        ``project['n_bins']`` or 4096 if not present.
    tac_range:
        Time range (ns) for the TAC histograms; defaults to ``(0.0, 50.0)``.
    mode:
        Optional legacy simulation mode. If ``None``, this is read from
        ``project['decay_mode']`` when present, otherwise ``"photon"``.
        Currently recognised modes are:

        - ``"photon"`` (default): standard Monte-Carlo photon trace.
        - ``"curve"``: legacy-style curve mode. This uses the same photon
          backend but allows ``n_curves``, ``dt_tac`` and ``n_tac`` to control
          histogram resolution and effective photon statistics.
    n_curves:
        Optional legacy parameter used in ``"curve"`` mode. If provided (or
        present as ``project['n_curves']``), it will multiply the effective
        ``n_photons`` used in the simulation.
    dt_tac:
        Optional legacy bin width in ns for ``"curve"`` mode. If supplied
        (or present as ``project['dt_tac']``) together with ``n_tac``, it will
        be used to derive ``tac_range`` when the caller did not override it.
    n_tac:
        Optional legacy number of TAC bins for ``"curve"`` mode. If supplied
        (or present as ``project['n_tac']``), it overrides ``nbins``.
    project_dir:
        Optional project directory (base path for output jobs).
    save_outputs:
        Write the per-run job directory: ``result.json``, the ``.mrc`` volumes,
        the ``.xyz`` point clouds, the CSV tables.

        **Defaults to False**: artefacts are opt-in. It used to default to
        ``True`` writing into ``Path.cwd()``, so every library call, notebook
        and forgetful test left a directory behind -- 2870 of them, 39 GB, by
        2026-07-28. The surfaces whose users asked for a run record (the CLI,
        the web backend) pass ``save_outputs=True`` explicitly; nothing else
        should. When it *is* true and no ``project_dir`` is given, the run goes
        to :func:`quest.runs.user_runs_directory`, never the working directory.
    render_data:
        Build the thinned trajectory, autocorrelation and point clouds that a
        plot or a 3D viewer needs. Defaults to ``True``.

        This used to be part of ``save_outputs``, which conflated two unrelated
        questions — *write files?* and *return something to draw?*. The Qt form
        passes ``save_outputs=False`` so a GUI run leaves nothing behind, and
        silently lost its trajectory and AV plots with it. A scan wants neither
        and should pass ``render_data=False``: thinning point clouds it never
        reads is pure overhead when the same structure is simulated once per
        residue.
    """
    if render_data is None:
        render_data = True

    # Resolve decay mode with backwards-compatible precedence:
    # 1) explicit function argument, 2) project['decay_mode'], 3) default.
    if mode is None:
        decay_mode = str(project.get("decay_mode", "photon")).lower()
    else:
        decay_mode = str(mode).lower()

    # Legacy configuration for curve mode
    if n_curves is None:
        legacy_n_curves = project.get("n_curves")
        n_curves = int(legacy_n_curves) if legacy_n_curves is not None else None

    if dt_tac is None:
        legacy_dt = project.get("dt_tac")
        dt_tac = float(legacy_dt) if legacy_dt is not None else None

    if n_tac is None:
        legacy_n_tac = project.get("n_tac")
        n_tac = int(legacy_n_tac) if legacy_n_tac is not None else None

    # Determine histogram bin count, allowing curve-mode overrides.
    if nbins is None:
        nbins = int(project.get("n_bins", 4096))
    effective_nbins = nbins
    if decay_mode == "curve" and n_tac is not None:
        effective_nbins = n_tac

    # Derive tac_range from dt_tac / n_tac when running in curve mode and the
    # caller did not explicitly override tac_range via the function argument.
    if decay_mode == "curve" and dt_tac is not None and n_tac is not None:
        # Only adjust if tac_range still at its default and the project did
        # not provide an explicit tac_range.
        project_has_tac_range = "tac_range" in project
        if tac_range == (0.0, 50.0) and not project_has_tac_range:
            tac_range = (0.0, float(dt_tac) * float(n_tac))

    # Generate a unique job folder. `runs_directory` decides *where*: under an
    # explicit `project_dir`, else the per-user artefact root -- never `cwd`.
    import uuid

    from chisurf.plugins.quenching_estimator.core.runs import runs_directory

    job_name = str(uuid.uuid4())
    job_dir = runs_directory(project_dir) / job_name
    if save_outputs:
        job_dir.mkdir(parents=True, exist_ok=True)

    project_dict = dict(project)
    project_dict["save_avs"] = save_outputs
    project_dict["output_file"] = str(job_dir / "out")
    parallel_trajectories = project_dict.get("parallel_trajectories", -1)
    project_dict["parallel_trajectories"] = int(-1 if parallel_trajectories is None else parallel_trajectories)

    model = build_donor_from_project(project_dict, pdb_path=pdb_path)

    # In curve mode, optionally scale photon statistics by n_curves to mimic
    # the legacy behaviour where multiple curves were accumulated. This only
    # affects the stochastic photon-based quantities (e.g. quantum yield), not
    # the deterministic curve integration below.
    if decay_mode == "curve" and n_curves is not None:
        try:
            model.n_photons = int(model.n_photons) * int(n_curves)
        except Exception:
            # If anything unexpected happens, fall back to the original count.
            pass

    model.update_all(verbose=False)

    if decay_mode == "curve":
        time, donor_counts = _curve_decay_from_model(
            model,
            effective_nbins,
            tac_range,
            dt_tac,
            n_curves,
        )
    else:
        time, donor_counts = _histogram_decay(model, effective_nbins, tac_range)

    fret_counts: Optional[np.ndarray] = None
    qy_fret: Optional[float] = None
    fret_eff: Optional[float] = None

    if getattr(model, "fret_enabled", False):
        xf, yf = model.get_histogram_fret(nbins=effective_nbins, range=tac_range)
        if xf is not None and yf is not None:
            fret_counts = yf
            qy_fret = model.quantum_yield_fret
            fret_eff = model.fret_efficiency

    trajectory_distance_to_mean: Optional[np.ndarray] = None
    trajectory_time_ns: Optional[np.ndarray] = None
    trajectory_autocorr: Optional[np.ndarray] = None
    trajectory_autocorr_lag_ns: Optional[np.ndarray] = None
    trajectory_points: Optional[np.ndarray] = None
    av_points: Optional[np.ndarray] = None
    acv_points: Optional[np.ndarray] = None
    aa_residence: list[dict[str, Any]] = []
    try:
        if render_data and hasattr(model, "diffusion") and model.diffusion is not None:
            max_trajectory_points = int(project_dict.get("trajectory_display_points", 2000))
            t_step_ns = float(
                getattr(model.diffusion, "t_step", project_dict.get("t_step", 0.0)) or 0.0
            )
            distances = model.diffusion.distance_to_mean
            if distances is not None:
                # Correlate the full series, then thin only what gets plotted.
                trajectory_autocorr = autocorr_to_tau_window(
                    distances,
                    tau0=float(getattr(model, "tau0", project_dict.get("tau0", 0.0)) or 0.0),
                    t_step=t_step_ns,
                )
                trajectory_autocorr_lag_ns = np.arange(len(trajectory_autocorr)) * t_step_ns
                frame_times = np.arange(len(distances)) * t_step_ns
                trajectory_distance_to_mean = _subsample_points(
                    distances, max_trajectory_points, decimals=3
                )
                trajectory_time_ns = _subsample_points(
                    frame_times, max_trajectory_points, decimals=3
                )
            raw_trajectory = getattr(model.diffusion, "_traj", None)
            if raw_trajectory is not None and len(raw_trajectory) > 0:
                trajectory_points = _subsample_points(
                    raw_trajectory, max_trajectory_points, decimals=2
                )
        if render_data and hasattr(model, "av") and model.av is not None:
            # The full clouds stay on disk as .xyz/.mrc; what travels through
            # JSON to a 3D viewer is capped, since a browser cannot usefully
            # draw hundreds of thousands of points anyway.
            max_render_points = int(project_dict.get("render_display_points", 25000))
            av_points = _subsample_points(model.av.points_fast, max_render_points, decimals=2)
            acv_points = _subsample_points(model.av.points_slow, max_render_points, decimals=2)
        aa_residence = aa_residence_from_model(model)
    except Exception:
        pass

    # Save the result to job_dir / "result.json"
    def _make_json_serializable(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: _make_json_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [_make_json_serializable(x) for x in obj]
        elif isinstance(obj, Path):
            return str(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, int)):
            return int(obj)
        elif isinstance(obj, (np.floating, float)):
            return float(obj)
        return obj

    try:
        dts, phs = model.photon_trace
        lifetime_donor = float(np.mean(dts[phs == 1])) if np.sum(phs) > 0 else 0.0
    except Exception:
        lifetime_donor = 0.0

    # Calculate AV and contact volume metrics in Ang3. These must come from the
    # complete point clouds, not the thinned copies shipped to the viewer.
    dg = float(
        project_dict.get("dg")
        or (project_dict.get("av_parameter") or {}).get("simulation_grid_resolution")
        or _av_defaults()["simulation_grid_resolution"]
    )
    dg3 = dg ** 3
    full_av_points = getattr(getattr(model, "av", None), "points_fast", None)
    full_acv_points = getattr(getattr(model, "av", None), "points_slow", None)
    av_volume = float(len(full_av_points)) * dg3 if full_av_points is not None else None
    contact_volume = float(len(full_acv_points)) * dg3 if full_acv_points is not None else None
    if av_volume is not None and contact_volume is not None:
        free_av_volume = av_volume - contact_volume
        contact_to_free_ratio = contact_volume / free_av_volume if free_av_volume > 0.0 else 0.0
    else:
        contact_to_free_ratio = None

    res_dict = {} if not save_outputs else {
        "job_id": job_name,
        "time_ns": time.tolist() if hasattr(time, "tolist") else list(time),
        "donor_counts": donor_counts.tolist() if hasattr(donor_counts, "tolist") else list(donor_counts),
        "fret_counts": None if fret_counts is None else (fret_counts.tolist() if hasattr(fret_counts, "tolist") else list(fret_counts)),
        "quantum_yield_donor": float(model.quantum_yield),
        "quantum_yield_fret": float(qy_fret) if qy_fret is not None else None,
        "collisions_fraction": float(model.collisions),
        "fret_efficiency": float(fret_eff) if fret_eff is not None else None,
        "project": _make_json_serializable(project_dict),
        "trajectory_distance_to_mean": None if trajectory_distance_to_mean is None else (trajectory_distance_to_mean.tolist() if hasattr(trajectory_distance_to_mean, "tolist") else list(trajectory_distance_to_mean)),
        "trajectory_autocorr": None if trajectory_autocorr is None else (trajectory_autocorr.tolist() if hasattr(trajectory_autocorr, "tolist") else list(trajectory_autocorr)),
        "trajectory_time_ns": None if trajectory_time_ns is None else (trajectory_time_ns.tolist() if hasattr(trajectory_time_ns, "tolist") else list(trajectory_time_ns)),
        "trajectory_autocorr_lag_ns": None if trajectory_autocorr_lag_ns is None else (trajectory_autocorr_lag_ns.tolist() if hasattr(trajectory_autocorr_lag_ns, "tolist") else list(trajectory_autocorr_lag_ns)),
        "trajectory_points": None if trajectory_points is None else (trajectory_points.tolist() if hasattr(trajectory_points, "tolist") else list(trajectory_points)),
        "av_points": None if av_points is None else (av_points.tolist() if hasattr(av_points, "tolist") else list(av_points)),
        "acv_points": None if acv_points is None else (acv_points.tolist() if hasattr(acv_points, "tolist") else list(acv_points)),
        "lifetime_donor": lifetime_donor,
        "av_volume": av_volume,
        "contact_volume": contact_volume,
        "contact_to_free_ratio": contact_to_free_ratio,
        "aa_residence": aa_residence,
    }
    if save_outputs:
        try:
            with open(job_dir / "result.json", "w", encoding="utf8") as f:
                json.dump(res_dict, f, indent=2)
        except Exception:
            pass

    if save_outputs:
        # Save individual results in the job folder
        try:
            # Save trajectory.npy
            if hasattr(model, "diffusion") and model.diffusion is not None and model.diffusion._traj is not None:
                np.save(job_dir / "trajectory.npy", model.diffusion._traj)
            
            # Save av.mrc and acv.mrc
            if hasattr(model, "av") and model.av is not None:
                av_obj = model.av
                if hasattr(av_obj, "density_fast") and av_obj.density_fast is not None:
                    write_mrc(job_dir / "av.mrc", av_obj.density_fast, av_obj.dg, av_obj.x0)
                    diffusion_grid = diffusion_coefficient_grid(
                        av_obj.density_fast,
                        diffusion_coefficient=float(model.diffusion_coefficient),
                        slow_factor_grid=getattr(av_obj, "slow_factor_grid", None),
                        slow_density=getattr(av_obj, "density_slow", None),
                        slow_factor=float(model.slow_fact),
                    )
                    write_mrc(job_dir / "diffusion_coefficients.mrc", diffusion_grid, av_obj.dg, av_obj.x0)
                    if getattr(av_obj, "k_quench_grid", None) is not None:
                        write_mrc(job_dir / "quenching_rates.mrc", av_obj.k_quench_grid, av_obj.dg, av_obj.x0)
                if hasattr(av_obj, "density_slow") and av_obj.density_slow is not None:
                    write_mrc(job_dir / "acv.mrc", av_obj.density_slow, av_obj.dg, av_obj.x0)
                if (
                    hasattr(model, "diffusion")
                    and model.diffusion is not None
                    and getattr(model.diffusion, "_traj", None) is not None
                    and hasattr(av_obj, "density_fast")
                    and av_obj.density_fast is not None
                ):
                    dye_density = sampled_density_grid(
                        model.diffusion._traj,
                        shape=av_obj.density_fast.shape,
                        dg=av_obj.dg,
                        center=av_obj.x0,
                        allowed_density=av_obj.density_fast,
                    )
                    write_mrc(job_dir / "sampled_dye_density.mrc", dye_density, av_obj.dg, av_obj.x0)
                
            # Save decay.csv
            decay_file = job_dir / "decay.csv"
            with open(decay_file, "w", encoding="utf-8") as f:
                if fret_counts is not None:
                    f.write("time_ns,donor_counts,fret_counts\n")
                    for t, d, fr in zip(time, donor_counts, fret_counts):
                        f.write(f"{t:.4f},{d:.4f},{fr:.4f}\n")
                else:
                    f.write("time_ns,donor_counts\n")
                    for t, d in zip(time, donor_counts):
                        f.write(f"{t:.4f},{d:.4f}\n")
                    
            # Save results.csv
            results_file = job_dir / "results.csv"
            with open(results_file, "w", encoding="utf-8") as f:
                f.write("Parameter,Value\n")
                f.write(f"quantum_yield_donor,{float(model.quantum_yield)}\n")
                if qy_fret is not None:
                    f.write(f"quantum_yield_fret,{float(qy_fret)}\n")
                f.write(f"collisions_fraction,{float(model.collisions)}\n")
                if fret_eff is not None:
                    f.write(f"fret_efficiency,{float(fret_eff)}\n")
                f.write(f"lifetime_donor,{float(lifetime_donor)}\n")
                if av_volume is not None:
                    f.write(f"av_volume,{float(av_volume)}\n")
                if contact_volume is not None:
                    f.write(f"contact_volume,{float(contact_volume)}\n")
                if contact_to_free_ratio is not None:
                    f.write(f"contact_to_free_ratio,{float(contact_to_free_ratio)}\n")

            aa_residence_file = job_dir / "aa_residence.csv"
            with open(aa_residence_file, "w", newline="", encoding="utf-8") as f:
                fieldnames = [
                    "residue_name",
                    "center_count",
                    "effective_slow_factor",
                    "frames_near",
                    "fraction_near",
                    "total_time_ns",
                    "event_count",
                    "mean_event_time_ns",
                    "max_event_time_ns",
                    "mean_min_distance_angstrom",
                    "attributed_frames_near",
                    "attributed_fraction_near",
                    "attributed_total_time_ns",
                    "attributed_event_count",
                    "attributed_mean_event_time_ns",
                    "attributed_max_event_time_ns",
                    "kQ",
                    "quench_radius",
                    "mean_quench_rate",
                    "quench_rate_fraction",
                    "fraction_frames_quenched",
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(aa_residence)
            
            # Save project.json
            with open(job_dir / "project.json", "w", encoding="utf8") as f:
                json.dump(_make_json_serializable(project_dict), f, indent=2)
        except Exception as e:
            print("Failed to save individual zip files:", e)

    return DecaySimulationResult(
        time=time,
        donor_counts=donor_counts,
        fret_counts=fret_counts,
        quantum_yield_donor=model.quantum_yield,
        quantum_yield_fret=qy_fret,
        collisions_fraction=model.collisions,
        fret_efficiency=fret_eff,
        project=project,
        trajectory_distance_to_mean=trajectory_distance_to_mean,
        trajectory_time_ns=trajectory_time_ns,
        trajectory_autocorr=trajectory_autocorr,
        trajectory_autocorr_lag_ns=trajectory_autocorr_lag_ns,
        trajectory_points=trajectory_points,
        av_points=av_points,
        acv_points=acv_points,
        job_id=job_name,
        lifetime_donor=lifetime_donor,
        av_volume=av_volume,
        contact_volume=contact_volume,
        contact_to_free_ratio=contact_to_free_ratio,
        aa_residence=aa_residence,
    )


__all__ = [
    "DecaySimulationResult",
    "sampled_density_grid",
    "diffusion_coefficient_grid",
    "autocorr_to_tau_window",
    "calculate_aa_quenching",
    "calculate_aa_residence",
    "aa_residence_from_model",
    "load_project",
    "build_donor_from_project",
    "simulate_project",
]
