"""Review detected excitation windows against the current ones -- the shared emtk panel.

One panel for every place windows are decided: the Excitation Windows tool, the setup editor's
*Auto-detect windows*, and the Record tool's *From a measurement…*. The form is the AutoForm spec
``excitation_windows.view.json``; drawn here by hand are only the decay plot with the window
edges and the workspace list.

:class:`WindowsReview` is the model (no drawing state of its own beyond the form): give it the
setup whose windows are in question and either a measurement (a workspace ``photons`` row, picked
in the panel) or histograms the caller already has (the setup editor's preview, Record's live
decays). *Detect* runs :func:`chisurf.core.fluorescence.excitation.detect_windows` and
:func:`~chisurf.core.fluorescence.excitation.check_setup`; *Use detected windows* calls
``on_accept(windows, detection)`` and nothing changes before that. A donor-only measurement (one
pulse) and an unclear one are reported, and *Use detected windows* stays disabled.

:class:`WindowsReviewDialog` hosts the panel in a floating :class:`emtk.dialog_window.DialogWindow`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from emtk.i18n import tr
from tttrlib import setup_detectors

from chisurf.core.fluorescence.excitation import (
    ExcitationWindows,
    WindowCheck,
    check_setup,
    detect_windows,
    histograms_from_tttr,
)

__all__ = ["SPEC_PATH", "WindowsReview", "WindowsReviewDialog", "WorkspaceInputSection"]

_log = logging.getLogger(__name__)

#: The panel's AutoForm spec.
SPEC_PATH = Path(__file__).with_name("excitation_windows.view.json")
#: Colours of the plot: current window edges, detected ones, detector curves.
CURRENT_EDGE = (0.6, 0.6, 0.6, 0.9)
DETECTED_EDGE = (1.0, 0.55, 0.1, 1.0)
CURVES = ((0.25, 0.7, 0.35, 1.0), (0.9, 0.3, 0.25, 1.0), (0.3, 0.5, 0.9, 1.0),
          (0.7, 0.4, 0.8, 1.0))


class WindowsReview:
    """Detect a measurement's excitation windows and hold them against a setup's.

    Parameters
    ----------
    setup : mapping, optional
        The setup whose windows are reviewed (``windows``, ``detectors``, ``tttr_reading``).
    on_accept : callable, optional
        ``on_accept(windows, detection, check)`` when the user takes the detected windows;
        *windows* are in the measurement's channels (``detection.resolution_s``); *check* also
        carries the detector gates to take (``check.proposal_gates``, see
        :func:`chisurf.core.fluorescence.excitation.apply_check`).
    on_keep : callable, optional
        Called when the user closes without changing anything.
    workspace : bool
        Offer the workspace's photons rows to pick the measurement from (the Excitation Windows
        plugin's ``measurement`` input: a pick is handed to its receive hook with this review).
    example : callable, optional
        ``example(review)`` writes a demo measurement and hands it to *review* (*Load example*;
        hidden without one). The host that owns a demo passes it -- this panel imports no plugin.
    """

    def __init__(
        self,
        setup: Mapping | None = None,
        *,
        on_accept: Callable[[dict, ExcitationWindows, WindowCheck], Any] | None = None,
        on_keep: Callable[[], Any] | None = None,
        workspace: bool = True,
        example: Callable[[WindowsReview], Any] | None = None,
    ) -> None:
        from emtk.view_form import FormState

        self.setup = dict(setup or {})
        self.on_accept, self.on_keep = on_accept, on_keep
        self.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        self.form = FormState()
        self.form.custom["measurement_input"] = self._draw_input
        self.form.custom["windows_plot"] = self._draw_plot
        self.measurement = ""
        self.source_text = tr("No measurement yet.")
        self.status_text = tr("Pick a measurement, then press Detect.")
        self.detail_text = ""
        self.histograms: dict[str, np.ndarray] = {}
        self.detection: ExcitationWindows | None = None
        self.check: WindowCheck | None = None
        #: ``"accepted"`` / ``"kept"`` once the user decided (a dialog host closes then).
        self.done = ""
        self.example = example
        self.input = None
        if workspace:
            try:
                self.input = WorkspaceInputSection("excitation_windows", "photons", self)
            except Exception:  # noqa: BLE001 - no workspace (a test, a bare host): data is given
                _log.debug("no workspace input for the windows review", exc_info=True)
        self._rows: list[dict] = []

    # -- inputs ------------------------------------------------------------------------------------
    def set_measurement(self, address: str, detect: bool = True) -> None:
        """Use the measurement at *address* (a file or workspace address)."""
        self.measurement = str(address)
        self.source_text = tr("Measurement: {name}").format(name=Path(self.measurement).name)
        if detect:
            self.detect()

    def set_histograms(
        self, histograms: Mapping[str, Any], resolution_s: float, label: str = "",
        detection: ExcitationWindows | None = None,
    ) -> None:
        """Use per-detector micro-time histograms the caller already has, and detect."""
        from chisurf.core.fluorescence.excitation import detect_pie_windows

        self.measurement = ""
        self.histograms = {str(k): np.asarray(v, dtype=float) for k, v in histograms.items()}
        self.source_text = label or tr("Micro-time decays of the loaded measurement")
        n = max((v.size for v in self.histograms.values()), default=0)
        det = detection or detect_pie_windows(self.histograms, resolution_s, n_channels=n)
        self._judge(det)

    def set_setup(self, setup: Mapping | None) -> None:
        """Review the windows of another setup (re-checks the detection there is)."""
        self.setup = dict(setup or {})
        if self.detection is not None:
            self._judge(self.detection)

    # -- actions ----------------------------------------------------------------------------------
    def enabled(self, name: str) -> bool:
        """Which buttons can be pressed (the form asks)."""
        if name == "accept":
            c = self.check
            return bool(c is not None and (c.proposal or (c.mismatch and c.proposal_gates)))
        if name == "detect":
            return bool(self.measurement)
        return True

    def detect(self) -> bool:
        """Detect the windows of the measurement and check the setup's against them."""
        if not self.measurement:
            return False
        try:
            import tttrlib

            from chisurf.core.plugin.workspace_input import read_address

            tttr = tttrlib.TTTR(str(read_address(self.measurement)))
            det = detect_windows(tttr, setup=self.setup)
            if det.domain == "micro":
                self.histograms, _, _ = histograms_from_tttr(
                    tttr, setup_detectors(self.setup) or None
                )
            else:
                period = max(int(det.n_channels), 1)
                macro = np.asarray(tttr.macro_times).astype(np.int64) % period
                rc = np.asarray(tttr.routing_channels)
                groups = setup_detectors(self.setup) or {
                    f"ch {int(c)}": [int(c)] for c in np.unique(rc)
                }
                self.histograms = {
                    k: np.bincount(macro[np.isin(rc, v)], minlength=period)[:period]
                    for k, v in groups.items()
                }
        except Exception as exc:  # noqa: BLE001 - shown: an unreadable file
            self.detection = self.check = None
            self.status_text = tr("Cannot read the measurement")
            self.detail_text = str(exc)
            return False
        self._judge(det)
        return True

    def accept(self) -> bool:
        """Take the detected windows (the caller's ``on_accept`` applies them)."""
        if not self.enabled("accept"):
            return False
        if self.on_accept is not None:
            self.on_accept(dict(self.check.proposal), self.check.detection, self.check)
        self.done = "accepted"
        return True

    def keep(self) -> None:
        """Change nothing."""
        if self.on_keep is not None:
            self.on_keep()
        self.done = "kept"

    @property
    def no_example(self) -> bool:
        """No demo to load (hides *Load example*)."""
        return self.example is None

    def load_example(self) -> None:
        """Hand the host's demo measurement to this review (see *example*)."""
        if self.example is not None:
            self.example(self)

    # -- what the form shows --------------------------------------------------------------------
    def _judge(self, det: ExcitationWindows) -> None:
        self.detection = det
        hist = None
        if self.histograms and det.domain == "micro":
            hist = np.sum([np.asarray(h, float) for h in self.histograms.values()], axis=0)
        self.check = check_setup(
            self.setup, detection=det, histogram=hist,
            histograms=self.histograms if det.domain == "micro" else None,
        )
        c = self.check
        if not det.alternating:
            self.status_text = det.message
        elif not c.mismatch:
            self.status_text = tr("The windows match the data.") + " " + det.message
        else:
            self.status_text = tr("The windows do not match the data: ") + c.summary
        lines = [f"[{i.severity}] {i.message}" for i in c.issues
                 if i.code not in ("single_pulse", "unclear") and i.message not in self.status_text]
        lines += det.notes
        self.detail_text = "\n".join(lines)
        self._rows = []

    def window_rows(self) -> list[dict]:
        """Rows of the comparison table."""
        if self._rows or self.check is None:
            return self._rows
        c, det = self.check, self.check.detection
        names = list(dict.fromkeys([*c.windows, *det.windows]))
        f = det.resolution_s * 1e9
        by_window = {p.window: p for p in det.pulses}
        rows = []
        for name in names:
            cur, new = c.windows.get(name), det.windows.get(name)
            p = by_window.get(name)
            rows.append(
                {
                    "window": name,
                    "current": f"{cur[0]}–{cur[1]}" if cur else "—",
                    "proposed": f"{new[0]}–{new[1]}" if new else "—",
                    "ns": f"{new[0] * f:.2f}–{new[1] * f:.2f}" if new else "—",
                    "excites": (
                        (f"{p.role}: " if p.role else "") + ", ".join(p.excites) if p else "—"
                    ),
                }
            )
        for name, ranges in c.gates.items():
            new = c.proposal_gates.get(name)
            rows.append(
                {
                    "window": f"gate {name}",
                    "current": ", ".join(f"{a}–{b}" for a, b in ranges),
                    "proposed": ", ".join(f"{a}–{b}" for a, b in new) if new else "—",
                    "ns": ", ".join(f"{a * f:.2f}–{b * f:.2f}" for a, b in new) if new else "—",
                    "excites": tr("detector gate"),
                }
            )
        self._rows = rows
        return rows

    # -- drawing ------------------------------------------------------------------------------------
    def draw(self) -> None:
        """Draw the panel into the current emtk window."""
        from emtk.view_form import draw_form

        draw_form(self.spec, self, self.form)

    def _draw_input(self, section, model, state, width) -> None:
        from emtk import im
        from emtk.view_form import draw_form

        if self.input is None:
            im.text_wrapped(tr("Drop a measurement on ChiSurf to add it to the workspace."))
            return
        draw_form(self.input.spec, self.input.model, self.input.form)
        rect = self.input.form.rects.get("workspace_input_rows")
        if rect:
            state.rects["measurement_input"] = rect

    def _draw_plot(self, section, model, state, width) -> None:
        from emtk import im, implot

        top = im.get_cursor_screen_pos()
        height = 190.0
        if not self.histograms:
            im.dummy((width, 6.0))
            return
        det = self.detection
        macro = det is not None and det.domain == "macro"
        if implot.begin_plot("##excitation_windows", (width, height), implot.FLAGS_NO_TITLE):
            implot.setup_axes(tr("phase (ticks)") if macro else tr("micro-time channel"),
                              tr("photons"))
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for k, (name, y) in enumerate(self.histograms.items()):
                x, y = _display(np.asarray(y, dtype=float))
                implot.set_next_line_style(CURVES[k % len(CURVES)])
                implot.plot_line(str(name), x, np.maximum(y, 0.5))
            if self.check is not None and self.check.windows:
                edges = sorted({float(v) for r in self.check.windows.values() for v in r})
                implot.set_next_line_style(CURRENT_EDGE)
                implot.plot_inf_lines(tr("current"), np.asarray(edges, dtype=float))
            if det is not None and det.windows:
                edges = sorted({float(v) for r in det.windows.values() for v in r})
                implot.set_next_line_style(DETECTED_EDGE)
                implot.plot_inf_lines(tr("detected"), np.asarray(edges, dtype=float))
            implot.end_plot()
        state.rects["windows_plot"] = (top[0], top[1], width, height)


def _display(y: np.ndarray, points: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """*y* summed in bins of whole channels so a plot shows at most about *points* of them, at
    the bins' centres (in channels): a sparse decay reads as a curve, not as noise."""
    k = max(1, -(-y.size // points))
    n = (y.size // k) * k
    if k == 1 or n == 0:
        return np.arange(y.size, dtype=float), y
    return np.arange(n // k) * k + 0.5 * k, y[:n].reshape(-1, k).sum(axis=1)


class WorkspaceInputSection:
    """An Input section over the Datasets workspace: the rows of *kind* that plugin *plugin*
    accepts, a pick handed to that plugin's receive hook with *app* -- built from the core
    workspace-input contract, so no plugin module is imported."""

    def __init__(self, plugin: str, kind: str, app: Any, height: float = 56.0) -> None:
        from emtk.view_form import FormState

        from chisurf.core.plugin.workspace_input import WorkspaceInputMixin, input_section, spec_for
        from chisurf.emtk.plugins import manifests

        found = spec_for(manifests().get(plugin), kind=kind)
        if found is None:
            raise LookupError(f"plugin {plugin!r} declares no {kind} input")

        class _Model(WorkspaceInputMixin):
            workspace_input_plugin = plugin
            workspace_input_kind = kind

        self.model = _Model()
        self.model.workspace_input_app = app
        section = input_section(found[1], title="")
        for part in section.get("sections", []):
            if (part.get("options") or {}).get("source") == "workspace_input_rows":
                part["options"]["height"] = height
        self.spec = {"sections": [section]}
        self.form = FormState()


class WindowsReviewDialog:
    """A floating window around a :class:`WindowsReview` (closes itself once the user decided).

    Parameters
    ----------
    title : str
    key : str
        Distinguishes two such windows of one host.
    """

    def __init__(self, title: str | None = None, key: str = "excitation_windows") -> None:
        from emtk.dialog_window import DialogWindow

        spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        size = (float(spec["window"]["width"]), float(spec["window"]["height"]))
        self.window = DialogWindow(title or tr("Excitation windows"), size=size, key=key)
        self.review: WindowsReview | None = None

    @property
    def open(self) -> bool:
        """Whether the window shows."""
        return bool(self.window.open and self.review is not None)

    def show(self, review: WindowsReview) -> None:
        """Show *review*."""
        self.review = review
        self.window.show()

    def draw(self, frame) -> None:
        """Draw the window in *frame* (the host's viewport box)."""
        if not self.open:
            return
        pressed = self.window.begin(frame)
        self.review.draw()
        self.window.end()
        if pressed == "close" and not self.review.done:
            self.review.keep()
        if self.review.done:
            self.window.hide()
            self.review = None
