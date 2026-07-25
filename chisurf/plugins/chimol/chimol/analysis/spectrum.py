"""Colouring by a property — PyMOL's ``spectrum``.

Ramping colour along a per-atom value is how a b-factor, a charge or a per-residue
score is read off a structure at a glance, which makes it one of the few colouring
modes that carries data rather than decoration.

Transcribed from ``spectrumany`` in ``modules/pymol/viewing.py``. Two details are
easy to get subtly wrong and are pinned by tests:

* the ramp puts the palette's colours at **equal intervals** and interpolates
  between the two bracketing them, rather than blending all of them by distance;
  the last bucket is clamped to ``n - 2`` so that the maximum value lands exactly
  on the final colour instead of falling off the end;
* a palette name not in the table has its underscores turned into spaces and is
  read as a **list of colour names**, which is why ``blue_red`` works without being
  a defined palette. Treating an unknown palette as an error would reject half the
  spectrum commands people actually write.

Non-numeric values are enumerated rather than refused, as PyMOL does, so
``spectrum resn`` gives each residue type its own colour.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "PALETTES",
    "EXPRESSION_ALIASES",
    "palette_colors",
    "spectrum_colors",
]

#: ``palette_colors_dict`` from ``modules/pymol/viewing.py``, verbatim.
PALETTES: dict[str, str] = {
    "rainbow_cycle": "magenta blue cyan green yellow orange red magenta",
    "rainbow_cycle_rev": "magenta red orange yellow green cyan blue magenta",
    "rainbow": "blue cyan green yellow orange red",
    "rainbow_rev": "red orange yellow green cyan blue",
    "rainbow2": "blue cyan green yellow orange red",
    "rainbow2_rev": "red orange yellow green cyan blue",
    "gcbmry": "green cyan blue magenta red yellow",
    "yrmbcg": "yellow red magenta blue cyan green",
    "cbmr": "cyan blue magenta red",
    "rmbc": "red magenta blue cyan",
}

#: Short spellings PyMOL maps before evaluating the expression.
EXPRESSION_ALIASES: dict[str, str] = {
    "pc": "partial_charge",
    "fc": "formal_charge",
    "resi": "resv",
}


def palette_colors(palette: str) -> list[str]:
    """Resolve a palette to its list of colour names.

    Parameters
    ----------
    palette : str
        A named palette, or a list of colour names separated by spaces or
        underscores.

    Returns
    -------
    list of str
        At least two colour names.

    Raises
    ------
    ValueError
        If fewer than two colours result -- a ramp between one colour is not a
        ramp, and PyMOL rejects it too.
    """
    text = str(palette or "rainbow").strip()
    if " " not in text:
        text = PALETTES.get(text.lower()) or text.replace("_", " ")
    names = [c for c in text.split() if c]
    if len(names) < 2:
        raise ValueError("a spectrum needs at least two colours")
    return names


def spectrum_colors(
    values,
    colors: np.ndarray,
    minimum: float | None = None,
    maximum: float | None = None,
) -> tuple[np.ndarray, float, float]:
    """Ramp ``values`` across ``colors``, as ``spectrumany`` does.

    Parameters
    ----------
    values : sequence
        One value per atom. Non-numeric values are enumerated in sorted order,
        which is what makes ``spectrum resn`` meaningful.
    colors : numpy.ndarray
        ``(n, 3)`` or ``(n, 4)`` palette colours, in order.
    minimum, maximum : float, optional
        Range ends. Taken from the data when omitted.

    Returns
    -------
    tuple
        ``(rgba, minimum, maximum)`` -- the per-value colours and the range used,
        which the caller reports so a ramp can be reproduced or compared.
    """
    palette = np.asarray(colors, dtype=float)
    if palette.ndim != 2 or palette.shape[0] < 2:
        raise ValueError("a spectrum needs at least two colours")
    if palette.shape[1] == 3:
        palette = np.column_stack([palette, np.ones(len(palette))])

    numeric = _as_numeric(values)
    lo = float(np.min(numeric)) if minimum is None else float(minimum)
    hi = float(np.max(numeric)) if maximum is None else float(maximum)

    n = palette.shape[0]
    if hi - lo == 0.0:
        # A constant property is not a ramp; PyMOL colours it with the first
        # entry rather than dividing by zero.
        return np.repeat(palette[:1], len(numeric), axis=0), lo, hi

    scaled = np.clip((numeric - lo) / (hi - lo), 0.0, 1.0) * (n - 1)
    # Clamped to n-2 so the maximum lands on the final colour rather than
    # indexing past the end of the palette.
    index = np.minimum(scaled.astype(int), n - 2)
    frac = (scaled - index)[:, None]
    return palette[index] * (1.0 - frac) + palette[index + 1] * frac, lo, hi


def _as_numeric(values) -> np.ndarray:
    """Coerce values to floats, enumerating them when they are not numbers."""
    try:
        return np.asarray([float(v) for v in values], dtype=float)
    except (TypeError, ValueError):
        # PyMOL: "Expression is non-numeric, enumerating values". Sorted so the
        # assignment is stable between runs rather than depending on file order.
        order = {value: i for i, value in enumerate(sorted({str(v) for v in values}))}
        return np.asarray([order[str(v)] for v in values], dtype=float)
