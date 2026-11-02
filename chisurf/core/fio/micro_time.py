"""The micro-time channels of one excitation period -- not the TDC range the header names.

A MultiHarp (and other TCSPC units) writes ``MeasDesc_NumberMicrotimes`` as the full range of its
time digitiser (32768 channels), whatever the laser rate: at 25 MHz and 80 ps only the first 500
channels can hold a photon. Taken from the header, a decay histogram was 32768 bins long, a fit
window ran to 32k, and a lifetime fit's period was 2.6 us instead of 40 ns. tttrlib knows the
effective count (from the sync period); these helpers use it everywhere a histogram or a period is
built.
"""

from __future__ import annotations

from typing import Any

import numpy as np

__all__ = ["channels_per_period", "period_histogram"]


def channels_per_period(tttr: Any) -> int:
    """Micro-time channels in one excitation period of *tttr* (at least 1).

    tttrlib's effective count when it has one; otherwise macro / micro resolution (macro ticks are
    the sync in T3 data); never more than the header's range.
    """
    header = getattr(tttr, "header", None)
    if header is None:
        return 1
    adc = int(getattr(header, "number_of_micro_time_channels", 0) or 0)
    micro = float(getattr(header, "micro_time_resolution", 0.0) or 0.0)
    effective = 0
    # The laser's sync rate is the period itself, when the file names it (PicoQuant's
    # TTResult_SyncRate): a macro clock need not be the sync (ChiSurf's recordings tick at 9.77 ns
    # with a 32 ns laser), so it is the first answer.
    sync = _sync_rate(header)
    if sync > 0.0 and micro > 0.0:
        effective = int(round(1.0 / (sync * micro)))
    get = getattr(header, "get_effective_number_of_micro_time_channels", None) if effective <= 0 else None
    if callable(get):
        try:
            effective = int(get())
        except Exception:  # noqa: BLE001 - an old tttrlib: compute it below
            effective = 0
    if effective <= 0:
        macro = float(getattr(header, "macro_time_resolution", 0.0) or 0.0)
        if micro > 0.0 and macro > 0.0:
            effective = int(round(macro / micro))
    if effective > 0 and adc > 0:
        effective = min(effective, adc)
    return max(1, effective or adc or 1)


def _sync_rate(header: Any) -> float:
    """The header's ``TTResult_SyncRate`` (Hz), 0 when it has none."""
    get = getattr(header, "tag", None)
    if not callable(get):
        return 0.0
    try:
        tag = get("TTResult_SyncRate")
    except Exception:  # noqa: BLE001 - no such tag
        return 0.0
    value = tag.get("value") if isinstance(tag, dict) else tag
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return 0.0


def period_histogram(tttr: Any, binning: int = 1, *, period: int | None = None) -> np.ndarray:
    """The micro-time histogram of *tttr* at *binning*, one excitation period long.

    *period* (raw channels) overrides the period of *tttr* -- a subset of photons keeps its file's
    header, but pass the file's period when the histogram must line up with others.
    """
    b = max(1, int(binning))
    hist = np.asarray(tttr.get_microtime_histogram(b)[0], dtype=np.float64)
    n = int(period) if period else channels_per_period(tttr)
    bins = max(1, -(-n // b))  # ceil
    return hist[:bins]
