"""Process-global *active detector-setup* LUT/shift context.

The invariant is **LUT on ⇒ apply the LUT on every TTTR read**. Rather than
thread the setup's per-channel LUTs to every ``tttrlib.TTTR`` call site, an
analysis tool *publishes* the active setup's correction here when a setup is
selected/edited, and :func:`chisurf.core.fio.staging.open_tttr` consults it
whenever a caller does not pass an explicit correction. So every read that flows
through the single TTTR-open seam is LUT-aware for free.

Design notes / caveats
-----------------------
- This is a **single** global correction — appropriate when one detector setup is
  active at a time (the common workflow). If two setups with different LUTs are
  used at once, the last one published wins; pass an explicit correction to
  :func:`open_tttr` in that case.
- Callers that must read **raw** (inspection/editor tools — header edit, splitter,
  micro-time shifter, count-rate, trace/image browsers) pass ``apply_lut=False``
  explicitly to :func:`open_tttr` to opt out of the context.
- It is process-local, so a headless RPC server does not inherit a GUI's context;
  headless callers pass the correction explicitly (see
  :func:`chisurf.core.data_io.detector_setups.setup_lut_open_kwargs`).
"""

from __future__ import annotations

_active: dict = {"channel_luts": {}, "channel_shifts": {}, "apply_lut": False}


def set_active_setup_lut(
    channel_luts: dict | None = None,
    channel_shifts: dict | None = None,
    apply_lut: bool = False,
) -> None:
    """Publish the active setup's per-channel LUTs/shifts + master gate."""
    _active["channel_luts"] = {int(k): v for k, v in (channel_luts or {}).items()}
    _active["channel_shifts"] = {int(k): int(v) for k, v in (channel_shifts or {}).items()}
    _active["apply_lut"] = bool(apply_lut)


def get_active_setup_lut() -> tuple[dict, dict, bool]:
    """Return ``(channel_luts, channel_shifts, apply_lut)`` for the active setup."""
    return _active["channel_luts"], _active["channel_shifts"], _active["apply_lut"]


def clear_active_setup_lut() -> None:
    """Forget the active setup correction (subsequent reads are raw)."""
    set_active_setup_lut()
