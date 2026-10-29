"""The Record tool's excitation-window check: the model half of the warning under the setup.

:class:`WindowCheckMixin` is mixed into :class:`~chisurf.plugins.core.acq.gui.record_app.RecordModel`.

* **During a run** the live decays are checked against the run's windows
  (:class:`~chisurf.plugins.core.acq.live.window_check.LiveWindowCheck`, the shared core check).
  A mismatch shows a warning in the *Experiment setup* panel with **Update windows** (take the
  detected ones -- for the next run; the photons of this one are recorded whole and can be
  re-analysed) and **Keep**. Nothing changes silently, and the run is not interrupted. One pulse
  only is an info line: a donor-only sample or not PIE, windows not checked.
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
        if exp.preset == "alex":  # the alternation is in the macro time: not in these decays
            return
        info = session.source.info
        windows = dict(exp.setup.get("windows") or {})
        if not self.live_windows.update(snap, windows, info.micro_res_s, info.n_micro):
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
            self.window_check_text = tr("⚠ The windows do not match the decays: {why}").format(
                why=check.summary
            )
        self.window_check_detail = "\n".join(
            [f"[{i.severity}] {i.message}" for i in check.issues]
            + [tr("Detected: ") + ", ".join(f"{k} {v[0]}–{v[1]}"
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
        self._take_windows(dict(check.proposal), check.detection.resolution_s)
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

    def _take_windows(self, windows: dict, resolution_s: float) -> None:
        """The windows replace the setup's (in channels of *resolution_s*, the device's)."""
        self.window_override = {k: [int(v[0]), int(v[1])] for k, v in windows.items()}
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

        def accepted(windows: dict, detection: Any) -> None:
            if detection.domain == "macro":
                self.alex_period_us = detection.n_channels * detection.resolution_s * 1e6
                self.status_text = tr("ALEX period from the measurement")
                self.status_detail = f"{self.alex_period_us:.2f} µs"
                return
            # the measurement's channels, in this device's: the same nanoseconds
            conv = detection.rescaled(res, n_micro).windows if res else windows
            self._take_windows(conv, res or detection.resolution_s)

        self.windows_review_requested = WindowsReview(setup, on_accept=accepted)
        return True

    def window_check_enabled(self, action: str) -> bool | None:
        """Which of this mixin's actions can be pressed (``None``: not ours)."""
        if action in ("update_windows_from_check", "keep_windows"):
            return self.live_windows.asking
        if action == "windows_from_measurement":
            return True
        return None
