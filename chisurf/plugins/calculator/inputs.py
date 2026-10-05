"""Bounded numeric controls shared by calculator ports.

Every calculator parameter rides a slider now: drag the track for the quick
sweep, Ctrl+Click the track to type an exact value (Enter or a click
elsewhere commits, Escape cancels). The bounds are the track's ends, so the
old clamp-by-wrapper is the widget's own behaviour; the wrapper keeps one
guard -- a commit that is not a finite number (an empty field) falls back to
the value it was handed -- and passes ``ALWAYS_CLAMP`` so a typed value
outside the bounds lands on the nearest end, as the old spin boxes did.

Wide positive ranges (lifetimes, rates, distances in Å) ride a
**logarithmic** track -- seven decades of tau-donor is unusable linear and
one-decade-per-centimetre is exactly what a physical parameter wants; small
or signed ranges (efficiency 0..1, anisotropy components) stay linear. The
value's display precision follows the old ``step=`` argument, so a
``step=0.01`` parameter shows -- and a drag stores -- two decimals, exactly
like the field it replaced; a dragged value is rounded to what the format
shows, so what the user sees and what the model carries are the same number.
"""

import math

from emtk import im

#: A positive range spanning at least this many decades rides a log track.
_LOG_DECADES = 2.0


def _fmt_for(step) -> str:
    """The display format the old +/- ``step`` implied: 0.01 → two decimals.

    Ceil, not round: a 0.5 step needs one decimal, and rounding 0.3 down to
    zero decimals would display whole degrees for a half-degree parameter.
    """
    if not step or step <= 0.0:
        return "%.3f"
    decimals = max(0, min(6, int(math.ceil(-math.log10(step)))))
    return f"%.{decimals}f"


def _wants_log(minimum: float, maximum: float) -> bool:
    """Whether the range is wide, positive and therefore better logarithmic."""
    return 0.0 < minimum < maximum and math.log10(maximum / minimum) >= _LOG_DECADES


def bounded_float(label, value, *, minimum, maximum, step=None, fmt=None, **kwargs):
    """A bounded float parameter, drawn as a slider.

    Parameters
    ----------
    label : str
    value : float
    minimum, maximum : float
        The slider's ends; drags always land inside, typed commits are
        clamped inside (``ALWAYS_CLAMP``).
    step : float, optional
        The old +/- step; now only the display precision: ``0.01`` shows two
        decimals and a drag stores two decimals.
    fmt : str, optional
        Overrides the step-derived format (``%.4g`` on log tracks).
    kwargs :
        Forwarded to :func:`emtk.im.slider_float` (``flags`` included).
    """
    value = float(value)
    minimum = float(minimum)
    maximum = float(maximum)
    logarithmic = _wants_log(minimum, maximum)
    if fmt is None:
        fmt = "%.4g" if logarithmic else _fmt_for(step)
    flags = kwargs.pop("flags", 0) | im.SliderFlags.ALWAYS_CLAMP
    if logarithmic:
        flags |= im.SliderFlags.LOGARITHMIC
    changed, new = im.slider_float(label, value, minimum, maximum, fmt, flags, **kwargs)
    if not math.isfinite(new):
        return False, value
    # ALWAYS_CLAMP already kept the widget honest; this repeat of the clamp
    # is the wrapper's own contract, testable without a frame.
    new = min(max(new, minimum), maximum)
    return changed and new != value, new


def bounded_int(label, value, *, minimum, maximum, **kwargs):
    """A bounded whole-number parameter, drawn as a slider (Ctrl+Click to type)."""
    kwargs.pop("step", None)    # a slider has no +/- step; the track is the step
    changed, new = im.slider_int(label, int(value), int(minimum), int(maximum), "%d", **kwargs)
    new = min(max(int(new), int(minimum)), int(maximum))
    return changed and new != int(value), new
