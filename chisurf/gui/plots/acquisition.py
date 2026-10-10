"""The four live pages of the Acquisition fit window: decay, correlation, MCS, macro time.

Each page draws one series set of the acquisition dataset's
:class:`~chisurf.plugins.core.acq.gui.live_plots.LivePlots`, built from the latest
pipeline snapshot (the only thing that crosses from the acquisition thread). A
page never touches photons. Its *Plot settings* are the matching panel of
``live_plots.view.json`` -- the per-plot controls the acquisition tool has
always had (decay curve selection, correlation channel pairs, MCS bin width,
macro-time plot type, update rate) -- bound to the dataset's ``LivePlots``, so a
change reaches the next snapshot.
"""

from __future__ import annotations

import copy

import numpy as np

import chisurf.core.fitting
from chisurf.gui import chiplot as cp
from chisurf.gui.chiplot import style as S
from chisurf.gui.plots.plotbase import Plot


def _strip(sections: list) -> list:
    """Drop what a fit-window page cannot host: the plot itself and tab gating."""
    kept = []
    for section in sections:
        if section.get("type") == "custom" and str(section.get("key", "")).startswith("live_"):
            continue
        section = {k: v for k, v in section.items() if k != "hidden_when"}
        if "sections" in section:
            section["sections"] = _strip(section["sections"])
        kept.append(section)
    return kept


class _LivePage(Plot):
    """A fit-window page over one series set of the acquisition's live plots."""

    #: key into ``LivePlots.series``
    series_key = ""
    #: title of the matching panel in ``live_plots.view.json``
    panel_title = ""
    x_label = ""
    y_label = ""
    #: draw points instead of a line (a series whose x repeats)
    points = False

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """Declare the page's single panel; data arrives with :meth:`update`."""
        super().__init__(fit, **kwargs)
        self.panel = self.add_panel(cp.Panel(), stretch=1)
        self.panel.set_labels(bottom=self.x_label, left=self.y_label)
        self._fallback = None
        self.state = "none"

    # -- the data ------------------------------------------------------------

    def dataset(self):
        """The acquisition dataset behind the fit, or ``None``."""
        from chisurf.core.models.acquisition import acquisition_dataset

        return acquisition_dataset(self.fit)

    def live(self):
        """The dataset's live-plot settings and series (a private empty one without a dataset)."""
        ds = self.dataset()
        if ds is not None:
            return ds.live
        if self._fallback is None:
            from chisurf.plugins.core.acq.gui.live_plots import LivePlots

            self._fallback = LivePlots()
        return self._fallback

    def is_log(self, live) -> tuple[bool, bool]:
        """``(log x, log y)`` of this page (pages override)."""
        return False, False

    def update(self, *args, **kwargs) -> None:
        """Redraw from the dataset's latest snapshot."""
        super().update(*args, **kwargs)
        live = self.live()
        live.refresh()
        series = live.series.get(self.series_key, []) if live.snapshot is not None else []
        self.panel.clear()
        self.panel.set_labels(bottom=self.x_label, left=self.y_label)
        logx, logy = self.is_log(live)
        self.state = "ok" if series else ("waiting" if live.snapshot is None else "empty")
        drawn = 0
        for i, (label, x, y) in enumerate(series):
            x, y = np.asarray(x, float), np.asarray(y, float)
            if not (len(x) and len(y)):
                continue
            n = min(len(x), len(y))
            x, y = x[:n], y[:n]
            if logy:
                y = np.where(y > 0, y, np.nan)
            if logx:
                x = np.where(x > 0, x, np.nan)
            colour = tuple(int(255 * c) for c in _colour(i)[:3])
            if self.points:
                self.panel.scatter(x, y, size=3.0, brush=colour, symbol="o", name=str(label))
            else:
                self.panel.line(x, y, pen=S.to_pen(colour, width=1.6), name=str(label))
            drawn += 1
        self.panel.set_log(x=logx, y=logy)
        if drawn > 1:
            self.panel.legend()
        self.request_redraw()

    # -- settings ------------------------------------------------------------

    def settings_spec(self) -> dict | None:
        """The matching panel of the live-plot spec, without the plot itself."""
        if self._settings_spec is None:
            live = self.live()
            for tabs in live.sections:
                for panel in tabs.get("sections", []):
                    if panel.get("title") == self.panel_title:
                        spec = copy.deepcopy({"sections": panel.get("sections", [])})
                        spec["sections"] = _strip(spec["sections"])
                        self._settings_spec = spec
        return self._settings_spec

    def settings_model(self):
        """The dataset's live-plot settings, read and written by the form."""
        return self.live()

    def has_settings(self) -> bool:
        """Every live page has settings."""
        return True

    def get_settings_state(self) -> dict:
        """The persisted live-plot settings, for the project file."""
        return self.live().export_settings()

    def set_settings_state(self, state: dict) -> None:
        """Restore :meth:`get_settings_state`."""
        self.live().restore_settings(state)


def _colour(index: int):
    """Plot colour of series *index*."""
    from chisurf.plugins.core.acq.gui.live_plots import _COLOURS

    return _COLOURS[index % len(_COLOURS)]


class DecayPage(_LivePage):
    """Fluorescence decay histogram of each enabled routing window."""

    name = "Decay"
    series_key = "decay"
    panel_title = "Decay"
    x_label = "Time (ns)"
    y_label = "Counts"

    def is_log(self, live):
        """Logarithmic counts axis when set."""
        return False, bool(live.decay_log_y)


class CorrelationPage(_LivePage):
    """Live correlation curves of the enabled channel pairs."""

    name = "Correlation"
    series_key = "correlation"
    panel_title = "Correlation"
    x_label = "Lag (ms)"
    y_label = "G"

    def is_log(self, live):
        """Logarithmic lag axis when set."""
        return bool(live.corr_log_x), False


class McsPage(_LivePage):
    """Rolling multichannel-scaler trace."""

    name = "MCS"
    series_key = "mcs"
    panel_title = "MCS"
    x_label = "Time (ms)"
    y_label = "Counts"

    def update(self, *args, **kwargs) -> None:
        """Redraw, applying the manual y range when the control asks for it."""
        super().update(*args, **kwargs)
        live = self.live()
        if live.mcs_manual_y:
            self.panel.set_ylim(float(live.mcs_y_min), float(live.mcs_y_max), padding=0.0)


class MacrotimePage(_LivePage):
    """Inter-photon times (or absolute macro times) of the stream."""

    name = "Macro time"
    points = True
    series_key = "macro"
    panel_title = "Macrotime"
    x_label = "Time (s)"
    y_label = "dt (s)"

    def update(self, *args, **kwargs) -> None:
        """Redraw with axis labels that follow the plot type."""
        live = self.live()
        absolute = live.macro_type == "absolute"
        self.x_label = "Photon index" if absolute else "Time (s)"
        self.y_label = "Macro time (s)" if absolute else "dt (s)"
        super().update(*args, **kwargs)
