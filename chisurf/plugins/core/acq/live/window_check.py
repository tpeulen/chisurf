"""The excitation windows of a live run, held against what the decays show (Qt-free).

During a run the analyzer histograms the micro times per detector (``snapshot()["decays"]``:
``n_bins`` bins over the device's ``n_micro`` channels). :class:`LiveWindowCheck` looks at them
once enough photons have arrived, and again whenever the photon count has doubled; it runs the
shared detection and check of :mod:`chisurf.core.fluorescence.excitation` and keeps the verdict.
A changed picture (another pulse pattern) asks the user again even after *Keep*; the same picture
does not.

Nothing here changes the windows: the Record model offers *Update windows* / *Keep*.
"""

from __future__ import annotations

from chisurf.core.fluorescence.excitation import (
    ExcitationWindows,
    WindowCheck,
    check_windows,
    detect_pie_windows,
)

__all__ = ["LiveWindowCheck", "convert_setup_windows"]

#: Photons in the decays before the first look.
MIN_PHOTONS = 5_000


def convert_setup_windows(setup: dict, micro_res_s: float) -> tuple[dict, str]:
    """*setup* with its windows in channels of *micro_res_s* (the device's), and a note.

    A setup's windows are raw channels of the resolution it declares
    (``tttr_reading.micro_time_resolution``, ps). Applied unconverted to a device of another
    resolution or binning they land somewhere else entirely (a 50 ps / 4096-channel setup on
    32 ps / 3125-channel data); converted, they cover the same nanoseconds. The returned setup
    declares the device's resolution, so converting twice changes nothing.
    """
    from chisurf.core.fluorescence.excitation import (
        rescale_gates,
        rescale_windows,
        setup_gates,
        setup_window_resolution_s,
    )

    declared = setup_window_resolution_s(setup)
    windows = setup.get("windows") or {}
    gates = setup_gates(setup)
    if not (windows or gates) or not declared or not micro_res_s:
        return setup, ""
    if abs(declared / micro_res_s - 1.0) <= 0.01:
        return setup, ""
    out = dict(setup)
    if windows:
        out["windows"] = rescale_windows(windows, declared, micro_res_s)
    if gates:
        conv = rescale_gates(gates, declared, micro_res_s)
        out["detectors"] = {
            k: ({**v, "micro_time_ranges": conv[k]} if k in conv else v)
            for k, v in (setup.get("detectors") or {}).items()
        }
    out["tttr_reading"] = {**(setup.get("tttr_reading") or {}),
                           "micro_time_resolution": micro_res_s * 1e12}
    what = " and ".join(x for x, y in (("windows", windows), ("detector gates", gates)) if y)
    note = f"{what} converted from {declared * 1e12:.4g} ps to {micro_res_s * 1e12:.4g} ps channels"
    return out, note


def _signature(det: ExcitationWindows, tolerance: int) -> tuple:
    """What the user decided about: the kind and the pulse positions (to *tolerance* channels)."""
    return (det.kind, tuple(sorted(int(p.rise) // max(tolerance, 1) for p in det.pulses)))


class LiveWindowCheck:
    """The verdict on a run's windows, refreshed as photons arrive.

    Attributes
    ----------
    check : WindowCheck or None
        The latest check (``None`` before enough photons).
    kept : bool
        The user pressed *Keep* for the picture :attr:`check` shows.
    """

    def __init__(self, min_photons: int = MIN_PHOTONS) -> None:
        self.min_photons = int(min_photons)
        self.reset()

    def reset(self) -> None:
        """Forget the run (a new run starts)."""
        self.check: WindowCheck | None = None
        self.kept = False
        self._signature: tuple | None = None
        self._kept_signature: tuple | None = None
        self._checked_at = 0

    def update(self, snapshot: dict, windows: dict, micro_res_s: float, n_micro: int,
               gates: dict | None = None, gate_channels: dict | None = None) -> bool:
        """Look at the decays of *snapshot*; ``True`` when :attr:`check` changed.

        *windows* are the run's windows (and *gates* its detectors' micro-time gates) in device
        channels (``micro_res_s``, ``n_micro`` per period).
        """
        decays = (snapshot or {}).get("decays") or {}
        hists = {k: v for k, v in decays.items() if " " not in str(k) and len(v)}
        total = float(sum(float(v.sum()) for v in hists.values()))
        if total < self.min_photons or total < 2 * self._checked_at:
            return False
        self._checked_at = total
        n_bins = max(len(v) for v in hists.values())
        bin_s = float(micro_res_s) * float(n_micro) / float(n_bins)
        coarse = detect_pie_windows(hists, bin_s, n_channels=n_bins)
        det = coarse.rescaled(float(micro_res_s), int(n_micro))
        sig = _signature(det, max(2, int(n_micro) // 100))
        self.check = check_windows(windows, det, gates=gates, gate_channels=gate_channels)
        if sig != self._signature:
            self._signature = sig
        self.kept = sig == self._kept_signature
        return True

    def update_alex(self, macro, channels, macro_clock_s: float, period_s: float,
                    windows_s: dict | None = None, detectors: dict | None = None) -> bool:
        """µs-ALEX: detect the alternation in the run's first photons and check the run's period
        and windows (*windows_s*: ``{name: (start, stop)}`` in seconds of the cycle; default the
        two halves). ``True`` when :attr:`check` changed."""
        from chisurf.core.fluorescence.excitation import detect_alex_windows

        n = int(len(macro))
        if n < max(self.min_photons, 20_000) or n < 2 * self._checked_at:
            return False
        self._checked_at = n
        det = detect_alex_windows(macro, channels, float(macro_clock_s), detectors=detectors)
        ticks = float(period_s) / float(macro_clock_s)
        if windows_s is None:
            windows_s = {"prompt": (0.0, period_s / 2), "delayed": (period_s / 2, period_s)}
        windows = {k: [int(round(lo / macro_clock_s)), int(round(hi / macro_clock_s))]
                   for k, (lo, hi) in windows_s.items()}
        self.check = check_windows(windows, det, alex_period_ticks=ticks)
        sig = (det.kind, int(det.n_channels) // 10)
        self._signature = sig
        self.kept = sig == self._kept_signature
        return True

    def keep(self) -> None:
        """The user keeps the windows for the picture shown now."""
        self._kept_signature = self._signature
        self.kept = True

    @property
    def asking(self) -> bool:
        """The windows do not match, there are windows to offer (two or more pulses), and the
        user has not decided for this picture."""
        c = self.check
        return bool(c is not None and c.mismatch and c.proposal and not self.kept)
