"""Scaling a model decay onto measured counts, for the lifetime-fitting tool.

``rescale_w_bg`` used to be a private numba copy of the shared one in
:mod:`chisurf.core.fluorescence.tcspc.tcspc`; it is re-exported from there now,
so there is one weighted least-squares solution in the tree rather than two that
can disagree. Only :func:`scale_model_to_data` is genuinely local: it is the
convenience layer that builds Poisson weights and applies the factor, which the
shared function deliberately does not do.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fluorescence.tcspc.tcspc import rescale_w_bg  # noqa: F401

__all__ = ["rescale_w_bg", "scale_model_to_data"]


def scale_model_to_data(
        model_decay: np.array,
        experimental_decay: np.array,
        start: int,
        stop: int,
        experimental_background: float = 0.0,
        use_weights: bool = True
) -> float:
    """
    Scale a model decay to an experimental decay.

    Parameters
    ----------
    model_decay : numpy.array
        Model decay to scale. **Modified in place** by the returned factor.
    experimental_decay : numpy.array
        Experimental decay to scale to
    start : int
        Start index for scaling
    stop : int
        Stop index for scaling
    experimental_background : float
        Background to subtract from experimental decay
    use_weights : bool
        Whether to use weights for scaling

    Returns
    -------
    float
        Scaling factor
    """
    if use_weights:
        # Poisson weights, floored at one count so an empty channel gets a
        # finite weight rather than dividing by zero.
        #
        # Built over the **whole** decay, not the fit window. The local copy of
        # `rescale_w_bg` this used to call indexed its weights as `w[i - start]`
        # -- a pre-sliced array -- while the shared one indexes `w[i]` like
        # every other array it is handed. The two agree only when `start == 0`,
        # which is exactly how the guard test called them, so the divergence was
        # invisible. One convention now: weights are indexed like the decay.
        weights = 1.0 / np.sqrt(np.maximum(experimental_decay, 1.0))
        scale = rescale_w_bg(
            model_decay=model_decay,
            experimental_decay=experimental_decay,
            experimental_weights=weights,
            experimental_background=experimental_background,
            start=start,
            stop=stop
        )
    else:
        # Simple scaling using ratio of sums
        scale = np.sum(experimental_decay[start:stop] - experimental_background) / np.sum(model_decay[start:stop])

    # Apply scaling
    model_decay *= scale

    return scale
