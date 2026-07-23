"""File / tttrlib IO for the LUT tools (no Qt, no CLI framework).

Separated from the pure math in :mod:`.lut` so that layer stays dependency-free
and unit-testable. Progress/logging is returned or raised, never printed.
"""

from __future__ import annotations

import glob
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


def load_microtimes(file_list: list[str], routine: str | None = None) -> np.ndarray:
    """Load and concatenate micro-time arrays from TTTR files via tttrlib.

    Parameters
    ----------
    file_list : list of str
        TTTR file paths.
    routine : str or None
        Optional tttrlib container/reading-routine (e.g. ``"SPC-130"``).

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
        microtimes = tttr.micro_times
        if microtimes is None or len(microtimes) == 0:
            continue
        parts.append(np.asarray(microtimes))
    if not parts:
        raise RuntimeError("No microtimes found in any input file.")
    return np.concatenate(parts)


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
    if ext == ".txt":
        np.savetxt(abs_path, ntac_fract.reshape(-1, 1), fmt="%.9f", header="NTAC_fract")
    elif ext == ".csv":
        np.savetxt(abs_path, ntac_fract.reshape(-1, 1), delimiter=",", fmt="%.9f",
                   header="NTAC_fract")
    elif ext == ".npy":
        np.save(abs_path, ntac_fract)
    elif ext == ".npz":
        np.savez_compressed(abs_path, **table)
    else:
        raise ValueError("Unknown output extension. Use .txt / .csv / .npy / .npz.")
    return abs_path
