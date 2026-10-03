"""Result plots shared by the emtk H2MM windows: transition density with a gate, and dwell-time histograms.

Both draw only what :mod:`.result_view` derives from the analysis, or an empty-state message.
"""

from __future__ import annotations

import json

from emtk import im, implot

from . import result_view

REGION_FILL = (46, 117, 182, 60)


class ResultPlots:
    """Holds the TDP gate and draws the plots of an ``H2mmAnalysis`` (or says there is none)."""

    def __init__(self) -> None:
        self.gate_x_min, self.gate_x_max = 0.2, 0.8
        self.gate_y_min, self.gate_y_max = 0.2, 0.8
        self._last_dropped_region = None

    def draw_tdp(self, ana) -> None:
        points = result_view.transition_points(ana)
        if points is None:
            im.text_wrapped(
                "No transition density yet: it shows the FRET efficiency before and after every decoded "
                "transition once an H2MM fit has finished."
            )
        elif implot.begin_plot("Transition density (E before vs E after)", (-1, -1)):
            implot.setup_axes("E before", "E after")
            implot.setup_axes_limits(0.0, 1.0, 0.0, 1.0)

            # Gate: drag the box (or drop a BURST_REGION onto the plot); the count below is computed from the points.
            res_rect = implot.drag_rect(
                401,
                self.gate_x_min,
                self.gate_y_min,
                self.gate_x_max,
                self.gate_y_max,
                REGION_FILL,
            )
            if res_rect.modified:
                self.gate_x_min, self.gate_x_max = res_rect.x_min, res_rect.x_max
                self.gate_y_min, self.gate_y_max = res_rect.y_min, res_rect.y_max
            implot.plot_scatter("Transitions", points[0], points[1], size=3.5)
            implot.end_plot()
        if points is not None:
            inside, total = result_view.transitions_in_gate(
                points, (self.gate_x_min, self.gate_x_max), (self.gate_y_min, self.gate_y_max)
            )
            im.text(f"{inside} of {total} transitions inside the gate")
            im.set_item_tooltip("Transitions whose E before and E after both lie inside the dragged box.")

        # Region Drop Target
        if im.begin_drag_drop_target():
            payload = im.accept_drag_drop_payload("BURST_REGION")
            if payload:
                try:
                    data = json.loads(payload.decode("utf-8"))
                    self._last_dropped_region = data
                    x_rng = data.get("x_range", [self.gate_x_min, self.gate_x_max])
                    if len(x_rng) == 2:
                        self.gate_x_min, self.gate_x_max = float(x_rng[0]), float(x_rng[1])
                    y_rng = data.get("y_range", [self.gate_y_min, self.gate_y_max])
                    if len(y_rng) == 2:
                        self.gate_y_min, self.gate_y_max = float(y_rng[0]), float(y_rng[1])
                except Exception:
                    pass
            im.end_drag_drop_target()

    def draw_dwells(self, ana) -> None:
        histograms, censored = result_view.dwell_histograms(ana)
        if ana is None:
            im.text_wrapped("No dwell times yet: they are drawn here once an H2MM fit has finished.")
            return
        if not histograms:
            im.text_wrapped("No state has a dwell that ended inside a burst, so there is no dwell-time distribution.")
            return
        if implot.begin_plot("Dwell times (burst-edge dwells excluded)", (-1, -1)):
            implot.setup_axes("Dwell time (ms)", "Counts")
            for h in histograms:
                implot.plot_line(f"S{h.state}", h.centers_ms, h.counts)
            implot.end_plot()
        if censored:
            im.text_wrapped(", ".join(f"S{s}" for s in censored) + ": no dwell ended within a burst")
