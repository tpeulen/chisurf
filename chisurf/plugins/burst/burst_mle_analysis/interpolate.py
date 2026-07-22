"""Sub-bin IRF shift.

The implementation now lives in :mod:`chisurf.core.fluorescence.mle.irf` and is
shared with the pixel-wise and molecule-wise imaging MLE tools. This module
re-exports it so existing imports keep working.
"""

from chisurf.core.fluorescence.mle.irf import interpolate_shift

__all__ = ["interpolate_shift"]
