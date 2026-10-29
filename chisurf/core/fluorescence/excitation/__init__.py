"""Excitation windows: detect PIE / µs-ALEX excitations from the data and check windows against them.

The core of ChiSurf's window handling (Qt-free). One result shape for both schemes
(:class:`ExcitationWindows`), one check (:func:`check_windows` / :func:`check_setup`) that the
Record tool, the setup editor and the burst / PIE analyses all call before they use windows.

* :func:`detect_pie_windows` -- pulses in per-detector micro-time histograms (:mod:`.pie`);
* :func:`detect_alex_windows` -- µs-ALEX alternation in the macro time (:mod:`.alex`);
* :func:`detect_windows` -- either, from a TTTR object or file;
* :func:`check_windows`, :func:`check_setup` -- existing windows held against a detection;
* :func:`windows_preflight`, :func:`windows_message` -- what an analysis runs before it uses
  windows, and the one line it reports;
* :func:`rescale_windows` -- windows from one channel width (TAC range, binning) to another.

Method and assumptions: ``docs/concepts/excitation_windows.md``.
"""

from .check import check_windows
from .measure import (
    check_setup,
    detect_alex_windows,
    detect_windows,
    histograms_from_tttr,
    setup_detectors,
    setup_gates,
    setup_window_resolution_s,
)
from .pie import detect_pie_windows, rising_edges
from .preflight import (
    WindowsPreflightMixin,
    apply_check,
    windows_message,
    windows_preflight,
)
from .result import (
    ExcitationWindows,
    Issue,
    Pulse,
    WindowCheck,
    rescale_gates,
    rescale_windows,
)

__all__ = [
    "ExcitationWindows",
    "Issue",
    "Pulse",
    "WindowCheck",
    "WindowsPreflightMixin",
    "apply_check",
    "check_setup",
    "check_windows",
    "detect_alex_windows",
    "detect_pie_windows",
    "detect_windows",
    "histograms_from_tttr",
    "rescale_gates",
    "rescale_windows",
    "rising_edges",
    "setup_detectors",
    "setup_gates",
    "setup_window_resolution_s",
    "windows_message",
    "windows_preflight",
]
