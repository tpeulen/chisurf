"""Images of a flattened multi-dimensional fit, for any experiment.

A measurement recorded on a grid -- an image, a correlation carpet -- is fitted
as one flat vector, and its reader describes the grid under
``meta_data['grid']`` (``shape``, ``order``). These accessors reshape the data,
the model curve and the residual back onto that grid for the 2D plot. Nothing
here knows which experiment produced the grid: the leading axes of a grid with
more than two dimensions are frames, and the last two are the image.
"""

from __future__ import annotations

import numpy as np


def _fit_of(fit_group):
    return getattr(fit_group, "selected_fit", fit_group)


def _grid(fit_group):
    data = getattr(_fit_of(fit_group), "data", None)
    grid = (getattr(data, "meta_data", None) or {}).get("grid") or {}
    shape = tuple(int(n) for n in grid.get("shape", ()) or ())
    return shape, str(grid.get("order", "C") or "C")


def _on_grid(values, fit_group):
    shape, order = _grid(fit_group)
    if len(shape) < 2 or values is None:
        return None
    values = np.asarray(values, dtype=float)
    if values.size != int(np.prod(shape)):
        return None
    stack = values.reshape(shape, order=order)
    return stack.reshape((-1,) + stack.shape[-2:])


def _slice(stack, frame_index):
    if stack is None:
        return None, None, None
    image = stack[int(np.clip(frame_index, 0, stack.shape[0] - 1))]
    return image, np.arange(image.shape[1], dtype=float), np.arange(image.shape[0], dtype=float)


def get_grid_n_frames(fit_group) -> int:
    """How many images the grid holds along its leading axes (0 without a grid)."""
    shape, _ = _grid(fit_group)
    return int(np.prod(shape[:-2])) if len(shape) >= 2 else 0


def get_grid_data_image(fit_group, frame_index: int = 0):
    """One measured image as ``(image, x, y)``, or ``(None, None, None)``."""
    data = getattr(_fit_of(fit_group), "data", None)
    return _slice(_on_grid(getattr(data, "y", None), fit_group), frame_index)


def get_grid_model_image(fit_group, frame_index: int = 0):
    """One model image as ``(image, x, y)``, or ``(None, None, None)``."""
    model = getattr(_fit_of(fit_group), "model", None)
    return _slice(_on_grid(getattr(model, "y", None), fit_group), frame_index)


def get_grid_residual_image(fit_group, weighted: bool = True, frame_index: int = 0):
    """One residual image as ``(image, x, y)``, weighted by the data's errors."""
    fit = _fit_of(fit_group)
    data = getattr(fit, "data", None)
    model = getattr(fit, "model", None)
    y = getattr(data, "y", None)
    m = getattr(model, "y", None)
    if y is None or m is None or np.size(y) != np.size(m):
        return None, None, None
    residual = np.asarray(y, dtype=float) - np.asarray(m, dtype=float)
    if weighted:
        ey = np.asarray(getattr(data, "ey", np.ones_like(residual)), dtype=float)
        residual = residual / np.where(ey > 0, ey, 1.0)
    return _slice(_on_grid(residual, fit_group), frame_index)
