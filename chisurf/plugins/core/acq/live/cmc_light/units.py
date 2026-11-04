"""Formatting of physical quantities shared by the laser GUI and the light sensor."""

import math

# Names and scales offered wherever a power is typed in or shown.
POWER_UNITS = (("W", 1.0), ("mW", 1e-3), ("uW", 1e-6), ("nW", 1e-9), ("pW", 1e-12))


def fmt_power(w):
    """A power in the unit that keeps it readable: 1.2 mW, 340 uW, 5.6 nW."""
    if w is None or not math.isfinite(w):
        return "-"
    if w == 0:
        return "0 W"
    for unit, scale in POWER_UNITS:
        if abs(w) >= scale:
            return "%.4g %s" % (w / scale, unit)
    return "%.3g fW" % (w / 1e-15)
