"""The Record tool's excitation-window check: the model half of the warning under the setup.

:class:`WindowCheckMixin` is mixed into :class:`~chisurf.plugins.core.acq.gui.record_app.RecordModel`.

* **During a run** the live decays are checked against the run's windows
  (:class:`~chisurf.plugins.core.acq.live.window_check.LiveWindowCheck`, the shared core check).
  A mismatch shows a warning in the *Experiment setup* panel with **Update windows** (take the
  detected ones -- for the next run; the photons of this one are recorded whole and can be
  re-analysed) and **Keep**. Nothing changes silently, and the run is not interrupted. One pulse
  only is an info line: a donor-only sample or not PIE, windows not checked.
* **µs-ALEX** runs keep their first photons' macro times (the session's ``alex_photons``) and
  the period and laser windows are checked on them; a session that cannot say so gives the info
  line "ALEX windows not checked live; checked when the run is analysed".
* **From a measurement…** opens the shared windows review on a measurement of the workspace (an
  earlier FRET recording), so its windows -- detected from its decays -- become this run's.
"""

from __future__ import annotations

from typing import Any

from emtk.i18n import tr

from chisurf.plugins.core.acq.live.window_check import LiveWindowCheck


class WindowCheckMixin:
    """The live window check and the windows taken from a measurement."""

    def _init_window_check(self) -> None:
        self.live_windows = LiveWindowCheck()
        #: the warning line and its details (empty: nothing to say)
        self.window_check_text = ""
        self.window_check_detail = ""
        #: ``"warning"`` (offer Update / Keep), ``"info"`` or ``""`` -- what the panel shows
        self.window_check_level = ""
        #: µs-ALEX laser windows taken from the data (seconds of the cycle; ``None``: halves)
        self.alex_windows_override: dict | None = None
        #: the review dialog the view hosts for *From a measurement…* (the view draws it)
        self.windows_review_requested = None

    # -- during a run ---------------------------------------------------------------------------
    def window_check_reset(self) -> None:
        """A new run: forget the previous verdict."""
        self.live_windows.reset()
        self.window_check_text = self.window_check_detail = self.window_check_level = ""

    def window_check_poll(self) -> None:
        """Check the run's windows against its decays (cheap until enough photons arrived)."""
        session = getattr(self, "session", None)
        snap = getattr(self, "snapshot", None)
        if session is None or not snap or getattr(self, "mode", "") not in ("point", ""):
            return
        exp = session.experiment
        info = session.source.info
        if exp.preset == "alex":  # the alternation is in the macro time: not in these decays
            self._alex_poll(session, exp, info)
            return
        windows = dict(exp.setup.get("windows") or {})
        from tttrlib import setup_detectors, setup_gates

        if not self.live_windows.update(snap, windows, info.micro_res_s, info.n_micro,
                                        gates=setup_gates(exp.setup),
                                        gate_channels=setup_detectors(exp.setup)):
            return
        self._show_check()

    def _alex_poll(self, session, exp, info) -> None:
        """µs-ALEX: the period and windows from the run's macro times (when the session keeps
        them), else say that the check waits for the analysis."""
        from tttrlib import setup_detectors

        get = getattr(session, "alex_photons", None)
        if get is None or not exp.alex_period_s:
            self.window_check_level = "info"
            self.window_check_text = tr(
                "ALEX windows not checked live; checked when the run is analysed."
            )
            return
        macro, channels = get()
        if not self.live_windows.update_alex(
            macro, channels, info.macro_clock_s, exp.alex_period_s,
            windows_s=getattr(exp, "alex_windows_s", None),
            detectors=setup_detectors(exp.setup) or None,
        ):
            if self.live_windows.check is None:
                self.window_check_level = "info"
                self.window_check_text = tr("ALEX windows: waiting for photons to check them.")
            return
        self._show_check()

    def _show_check(self) -> None:
        check = self.live_windows.check
        if check is None:
            return
        det = check.detection
        if not det.alternating:
            self.window_check_level = "info" if det.kind == "single" else ""
            self.window_check_text = (
                tr("One excitation pulse seen — donor-only or not PIE; windows not checked.")
                if det.kind == "single" else ""
            )
            self.window_check_detail = det.message
            return
        if not check.mismatch:
            self.window_check_level, self.window_check_text = "", ""
            self.window_check_detail = det.message
            return
        if self.live_windows.kept:
            self.window_check_level = "info"
            self.window_check_text = tr("Windows kept although they do not match the data.")
        else:
            self.window_check_level = "warning"
            self.window_check_text = tr("⚠ The windows do not match the data: {why}").format(
                why=check.summary
            )
        unit = tr(" ticks") if det.domain == "macro" else ""
        self.window_check_detail = "\n".join(
            # the first finding is the warning line itself
            [f"[{i.severity}] {i.message}" for i in check.issues
             if i.message not in self.window_check_text]
            + [tr("Detected: ") + ", ".join(f"{k} {v[0]}–{v[1]}{unit}"
                                           for k, v in check.proposal.items())]
        )

    @property
    def window_check_asking(self) -> bool:
        """Show Update windows / Keep."""
        return self.live_windows.asking

    @property
    def window_check_quiet(self) -> bool:
        """Nothing to say (hides the line)."""
        return not self.window_check_text

    def update_windows_from_check(self) -> bool:
        """Take the detected windows (the next run uses them)."""
        check = self.live_windows.check
        if check is None or not check.proposal:
            return False
        det = check.detection
        if det.domain == "macro":
            self._take_alex(det, dict(check.proposal))
        else:
            self._take_windows(dict(check.proposal), det.resolution_s, check.proposal_gates)
        self.live_windows.keep()
        self.window_check_level = "info"
        self.window_check_text = tr(
            "Windows updated from the decays; the next run uses them (this one is recorded "
            "whole and can be re-analysed)."
        )
        return True

    def keep_windows(self) -> None:
        """Keep the windows for the picture shown now (a changed picture asks again)."""
        self.live_windows.keep()
        self._show_check()

    def _take_alex(self, detection: Any, windows: dict) -> None:
        """µs-ALEX: the detected period and the laser windows (phase ticks -> seconds)."""
        tick = detection.resolution_s
        self.alex_period_us = detection.n_channels * tick * 1e6
        self.alex_windows_override = {k: (v[0] * tick, v[1] * tick) for k, v in windows.items()}
        self.status_text = tr("ALEX period and windows from the data")
        self.status_detail = f"{self.alex_period_us:.2f} µs; " + ", ".join(
            f"{k} {v[0] * 1e6:.1f}–{v[1] * 1e6:.1f} µs" for k, v in self.alex_windows_override.items()
        )

    def _take_windows(self, windows: dict, resolution_s: float, gates: dict | None = None) -> None:
        """The windows (and detector gates) replace the setup's (in channels of *resolution_s*,
        the device's)."""
        self.window_override = {k: [int(v[0]), int(v[1])] for k, v in windows.items()}
        self.gate_override = {k: [list(r) for r in v] for k, v in (gates or {}).items()}
        self.window_override_resolution_s = float(resolution_s)
        self.window_override_label = tr("windows from the data")
        self.status_text = tr("Windows from the data")
        self.status_detail = ", ".join(
            f"{k} {v[0]}–{v[1]}" for k, v in self.window_override.items()
        )

    # -- from a measurement ----------------------------------------------------------------------
    def windows_from_measurement(self) -> bool:
        """Open the windows review: pick an earlier FRET measurement, take its windows."""
        from chisurf.emtk.excitation_windows import WindowsReview

        n_micro, res = self._clock()
        try:
            setup = self.make_experiment(n_micro, micro_res_s=res).setup
        except Exception:  # noqa: BLE001 - a setup that cannot be read: review without it
            setup = {}

        def accepted(windows: dict, detection: Any, check: Any = None) -> None:
            if detection.domain == "macro":
                self._take_alex(detection, windows)
                return
            # the measurement's channels, in this device's: the same nanoseconds
            from tttrlib import (
                rescale_micro_time_ranges,
            )

            src = detection.resolution_s
            gates = check.proposal_gates if check is not None else {}
            if res:
                windows = rescale_micro_time_ranges(windows, src, res)
                gates = rescale_micro_time_ranges(gates, src, res)
            self._take_windows(windows, res or src, gates)

        self.windows_review_requested = WindowsReview(setup, on_accept=accepted)
        return True

    def window_check_enabled(self, action: str) -> bool | None:
        """Which of this mixin's actions can be pressed (``None``: not ours)."""
        if action in ("update_windows_from_check", "keep_windows"):
            return self.live_windows.asking
        if action == "windows_from_measurement":
            return True
        return None
