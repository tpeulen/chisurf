"""File / tttrlib IO for the LUT tools (no Qt, no CLI framework).

Separated from the pure math in :mod:`.lut` so that layer stays dependency-free
and unit-testable. Progress/logging is returned or raised, never printed.
"""

from __future__ import annotations

import glob
import json
import os

import numpy as np


def expand_globs(patterns: list[str]) -> list[str]:
    """Expand glob patterns to unique existing paths, preserving order.

    Parameters
    ----------
    patterns : list of str
        Glob patterns.

    Returns
    -------
    list of str
        Unique matching paths in input order (patterns matching nothing are
        silently skipped — callers may warn).
    """
    unique: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for filename in glob.glob(pattern, recursive=True):
            if filename not in seen:
                seen.add(filename)
                unique.append(filename)
    return unique


def load_microtimes(
    file_list: list[str], routine: str | None = None, channel: int | None = None
) -> np.ndarray:
    """Load and concatenate micro-time arrays from TTTR files via tttrlib.

    Parameters
    ----------
    file_list : list of str
        TTTR file paths.
    routine : str or None
        Optional tttrlib container/reading-routine (e.g. ``"SPC-130"``).
    channel : int or None
        Restrict to this routing channel. ``None`` pools every channel (only
        appropriate when a single TAC serves all channels). Because TAC
        differential non-linearity is *per routing channel*, LUTs should be
        computed per channel — pass one.

    Returns
    -------
    numpy.ndarray
        Concatenated micro-time values.

    Raises
    ------
    RuntimeError
        If no micro-times are found in any input file.
    """
    import tttrlib

    parts: list[np.ndarray] = []
    for filename in file_list:
        tttr = tttrlib.TTTR(filename) if not routine else tttrlib.TTTR(filename, routine)
        if channel is not None:
            tttr = tttr.get_tttr_by_channel([int(channel)])
        microtimes = tttr.micro_times
        if microtimes is None or len(microtimes) == 0:
            continue
        parts.append(np.asarray(microtimes))
    if not parts:
        raise RuntimeError("No microtimes found in any input file.")
    return np.concatenate(parts)


def load_micro_and_routing(
    file_list: list[str], routine: str | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """Load concatenated ``(micro_times, routing_channels)`` from TTTR files.

    Lets a caller histogram any routing channel in memory (mask by channel)
    without re-reading the files.

    Returns
    -------
    tuple of numpy.ndarray
        ``(micro_times, routing_channels)`` concatenated across files.

    Raises
    ------
    RuntimeError
        If no events are found in any input file.
    """
    import tttrlib

    micro_parts: list[np.ndarray] = []
    route_parts: list[np.ndarray] = []
    for filename in file_list:
        tttr = tttrlib.TTTR(filename) if not routine else tttrlib.TTTR(filename, routine)
        micro = tttr.micro_times
        if micro is None or len(micro) == 0:
            continue
        micro_parts.append(np.asarray(micro))
        route_parts.append(np.asarray(tttr.routing_channels))
    if not micro_parts:
        raise RuntimeError("No events found in any input file.")
    return np.concatenate(micro_parts), np.concatenate(route_parts)


def load_lut_file(path: str) -> np.ndarray:
    """Load a 1-D LUT (``NTAC_fract``) from ``.npy`` / ``.npz`` / ``.txt`` / ``.csv``.

    Parameters
    ----------
    path : str
        LUT file path.

    Returns
    -------
    numpy.ndarray
        The cumulative ``NTAC_fract`` array.

    Raises
    ------
    ValueError
        On an unknown extension or an ``.npz`` without a usable array.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path) as fh:
            payload = json.load(fh)
        for key in ("NTAC_fract", "ntac_fract"):
            if key in payload:
                return np.asarray(payload[key], dtype=float).ravel()
        raise ValueError("JSON LUT contains no NTAC_fract array.")
    if ext == ".npy":
        return np.asarray(np.load(path), dtype=float).ravel()
    if ext == ".npz":
        data = np.load(path)
        for key in ("NTAC_fract", "ntac_fract", "arr_0"):
            if key in data:
                return np.asarray(data[key], dtype=float).ravel()
        # first array in the archive
        for key in data.files:
            return np.asarray(data[key], dtype=float).ravel()
        raise ValueError(f"No array found in {path}")
    if ext in (".txt", ".csv"):
        delim = "," if ext == ".csv" else None
        return np.asarray(np.loadtxt(path, delimiter=delim), dtype=float).ravel()
    raise ValueError(f"Unknown LUT extension: {ext}")


def save_lut(path: str, table: dict) -> str:
    """Save a LUT table to disk; returns the absolute path written.

    Parameters
    ----------
    path : str
        Output path. Supported extensions: ``.txt`` / ``.csv`` / ``.npy`` / ``.npz``.
    table : dict
        LUT table from :func:`..lut.build_linearization_table`.

    Returns
    -------
    str
        The absolute path written.

    Raises
    ------
    ValueError
        On an unknown output extension.
    """
    abs_path = os.path.abspath(path)
    ext = os.path.splitext(abs_path)[1].lower()
    ntac_fract = np.asarray(table["NTAC_fract"])
    if ext == ".json":
        # Self-describing interchange format: carries the LUT *and* the inputs
        # it was built from, so a consumer can check a table against the data it
        # is applied to instead of trusting a bare column of numbers. Read by
        # CMC (src/common/tac_linearization.hpp) as well as by load_lut_file.
        payload = {}
        for key, value in table.items():
            payload[key] = value.tolist() if isinstance(value, np.ndarray) else value
        with open(abs_path, "w") as fh:
            json.dump(payload, fh, indent=2)
        return abs_path
    if ext == ".txt":
        np.savetxt(abs_path, ntac_fract.reshape(-1, 1), fmt="%.9f", header="NTAC_fract")
    elif ext == ".csv":
        np.savetxt(
            abs_path, ntac_fract.reshape(-1, 1), delimiter=",", fmt="%.9f", header="NTAC_fract"
        )
    elif ext == ".npy":
        np.save(abs_path, ntac_fract)
    elif ext == ".npz":
        np.savez_compressed(abs_path, **table)
    else:
        raise ValueError("Unknown output extension. Use .json / .txt / .csv / .npy / .npz.")
    return abs_path
