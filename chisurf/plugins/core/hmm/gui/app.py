"""Standalone EMTK HMM editor over the Qt-free view model."""
from __future__ import annotations

import numpy as np
from emtk import im
from emtk.app import ImApp

from .strings import install_translations, tr
from .view_model import HmmViewModel

install_translations()


class HmmApp(ImApp):
    def __init__(self, model=None):
        self.model = model or HmmViewModel()
        self.message = ""
        super().__init__(self.render)

    def _input_int(self, label, attr, tip):
        im.text(tr(label))
        im.same_line()
        im.set_next_item_width(120)
        changed, value = im.input_int("##" + attr, int(getattr(self.model, attr)))
        im.set_item_tooltip(tr(tip))
        if changed:
            setattr(self.model, attr, value)

    def _plot(self, series, title, height=150):
        im.text(tr(title))
        im.separator()
        ctx = im.get_current_context()
        origin = im.get_cursor_screen_pos()
        width = max(280.0, im.get_content_region_avail()[0])
        h = float(height)
        ctx.draw.add_rect_filled(origin, (origin[0] + width, origin[1] + h), (18, 18, 22, 255), 2)
        if series:
            xmin = min(float(np.min(s["x"])) for s in series)
            xmax = max(float(np.max(s["x"])) for s in series)
            ymin = min(float(np.min(s["y"])) for s in series)
            ymax = max(float(np.max(s["y"])) for s in series)
            dx = max(xmax - xmin, 1e-9)
            dy = max(ymax - ymin, 1e-9)
            for item in series:
                points = [(origin[0] + (float(x) - xmin) / dx * width,
                           origin[1] + h - (float(y) - ymin) / dy * h) for x, y in zip(item["x"], item["y"])]
                ctx.draw.add_polyline(points, (130, 190, 230, 255), thickness=max(1.0, float(item.get("width", 1))))
        im.dummy(0.0, h)

    def render(self):
        im.begin(tr("Hidden Markov model"), (0, 0, *im.get_main_viewport().size))
        im.heading(tr("Hidden Markov model"), level=2)
        im.text_wrapped(self.model.status_text if hasattr(self.model, "status_text") else "")
        self._input_int("States", "n_states", "Number of hidden states to fit")
        self._input_int("Iterations", "n_iter", "Maximum EM iterations")
        self._input_int("Minimum states", "min_states", "Smallest state count for scan")
        self._input_int("Maximum states", "max_states", "Largest state count for scan")
        changed, value = im.checkbox(tr("Accelerate"), self.model.accelerate)
        im.set_item_tooltip(tr("Use SQUAREM acceleration for EM"))
        if changed:
            self.model.accelerate = value
        if im.button(tr("Fit")):
            self.model.run()
            self.message = tr("Fit complete")
        im.set_item_tooltip(tr("Fit the HMM to loaded traces"))
        im.same_line()
        if im.button(tr("Scan states")):
            self.model.run_scan()
            self.message = tr("State scan complete")
        im.set_item_tooltip(tr("Score the configured state-count range"))
        if self.message:
            im.text_wrapped(self.message)
        self._plot(self.model.trace_series(), "Trace")
        self._plot(self.model.histogram_series(), "Histogram")
        self._plot(self.model.scan_series(), "State scan", 120)
        im.separator()
        im.heading(tr("Fitted states"), level=2)
        im.markdown(self.model.states_html())
        im.set_item_tooltip(tr("Emission means, occupancy and dwell-time summaries for each fitted state"))
        im.heading(tr("Transitions"), level=2)
        im.markdown(self.model.transitions_html())
        im.set_item_tooltip(tr("Transition probabilities and rates between fitted states"))
        im.end()

    def export_settings(self):
        return {"n_states": self.model.n_states, "n_iter": self.model.n_iter,
                "min_states": self.model.min_states, "max_states": self.model.max_states,
                "accelerate": self.model.accelerate}

    def restore_settings(self, settings):
        for key, value in settings.items():
            if hasattr(self.model, key):
                setattr(self.model, key, value)

    def close(self):
        self.model._observers.clear()


def make_app():
    return HmmApp()
