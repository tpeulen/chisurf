"""Result plots shared by the emtk H2MM windows: transition density with a gate, and dwell-time histograms.

Both draw only what :mod:`.result_view` derives from the analysis, or an empty-state message.
"""

from __future__ import annotations

import json

import numpy as np

from emtk import im, implot

from . import result_view

REGION_FILL = (46, 117, 182, 60)
#: One colour per state, the Qt tool's palette (cycles beyond eight states).
STATE_COLORS = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2", "#edc948", "#ff9da7"]
#: Line colour per detection colour (a decay is drawn in the colour of the light that made it).
COLOUR_RGB = {"green": "#2ca02c", "donor": "#2ca02c", "red": "#d62728", "acceptor": "#d62728", "yellow": "#e8b400", "aex": "#e8b400"}


def rgba(colour: str, alpha: int = 255) -> tuple[int, int, int, int]:
    """``#rrggbb`` -> RGBA."""
    colour = colour.lstrip("#")
    return int(colour[0:2], 16), int(colour[2:4], 16), int(colour[4:6], 16), alpha


def state_colour(i: int) -> tuple[int, int, int, int]:
    return rgba(STATE_COLORS[i % len(STATE_COLORS)])


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


    # -- the remaining plots (card H4) -------------------------------------------------------------------------- #
    def draw_dwell_fret(self, ana, uncertainty=None) -> None:
        """Measured per-dwell E histograms per state with the model E marked; the E-S scatter with an Aex stream."""
        info = result_view.dwell_fret(ana)
        if info is None:
            im.text_wrapped("No dwell FRET states yet: they are drawn here once an H2MM fit has finished.")
            return
        if info.has_alex:
            if implot.begin_plot("Dwell E-S scatter", (-1, -1)):
                implot.setup_axes("Dwell E", "Dwell S")
                implot.setup_axes_limits(0.0, 1.0, 0.0, 1.0)
                for state, (e, s) in info.es_points.items():
                    implot.set_next_marker_style(implot.MARKER_CIRCLE, 4.0, fill=rgba(STATE_COLORS[state % 8], 128))
                    implot.plot_scatter(f"S{state}", e, s)
                implot.end_plot()
            return
        if implot.begin_plot("Dwell FRET states", (-1, -1)):
            implot.setup_axes("Apparent FRET E", "Dwells (photon-weighted)")
            implot.setup_axes_limits(0.0, 1.0, 0.0, max([float(c.max()) for c in info.counts.values()] + [1.0]) * 1.1)
            for state, counts in info.counts.items():
                implot.set_next_line_style(state_colour(state), 2.0)
                implot.plot_line(f"S{state}", info.centers, counts)
            for state, e in enumerate(info.model_e):
                if e == e:  # model E of the state, dashed in the Qt tool
                    implot.set_next_line_style(state_colour(state), 1.0)
                    implot.plot_inf_lines(f"model E S{state}", [float(e)])
            implot.end_plot()

    def draw_model_selection(self, ana) -> None:
        """BIC and ICL against the number of states."""
        sel = result_view.model_selection(ana)
        if sel is None:
            im.text_wrapped("No model selection yet: BIC and ICL of every fitted state count appear here after a fit.")
            return
        ns, bic, icl = sel
        if implot.begin_plot("Model selection", (-1, -1)):
            implot.setup_axes("Number of states", "Criterion (lower is better)")
            implot.set_next_line_style(rgba("#4e79a7"), 2.0)
            implot.plot_line("BIC", ns, bic)
            implot.set_next_line_style(rgba("#e15759"), 2.0)
            implot.plot_line("ICL", ns, icl)
            implot.end_plot()

    def draw_state_path(self, ana, data, burst: int) -> None:
        """One burst's Viterbi path: the E of the state per photon, photons coloured by state."""
        path = result_view.burst_path(ana, data, burst)
        if path is None:
            im.text_wrapped("No state path yet: after a fit, pick a burst to see its photons coloured by decoded state.")
            return
        if implot.begin_plot("State path", (-1, -1)):
            implot.setup_axes("Time in burst (ms)", "E of the state")
            implot.set_next_line_style((153, 153, 153, 255), 1.0)
            implot.plot_line("state E", path.t_ms, path.e)
            for state in sorted(set(int(v) for v in path.state)):
                m = path.state == state
                implot.set_next_marker_style(implot.MARKER_CIRCLE, 5.0, fill=state_colour(state))
                implot.plot_scatter(f"S{state}", path.t_ms[m], path.e[m])
            implot.end_plot()
        im.text(f"burst {path.burst}, {path.t_ms.size} photons, {path.n_transitions} transitions")

    def draw_decays(self, decays, colours: set[str], states: set[int]) -> None:
        """Per-state decays by detection colour (the photons of one colour only)."""
        if decays is None:
            im.text_wrapped(
                "No per-state decays: they need the photons' micro times, which a fit of this folder did not carry."
            )
            return
        x = decays.centers_ns()
        if implot.begin_plot("Per-state decay", (-1, -1)):
            implot.setup_axes("Micro time (ns)" if decays.micro_time_ns else "Micro time", "Counts")
            implot.setup_axis_scale(implot.AXIS_Y1, implot.SCALE_LOG10)
            for k, colour in enumerate(decays.colours):
                if colour not in colours:
                    continue
                for state in range(decays.n_states):
                    if state not in states:
                        continue
                    y = decays.colour_counts[state, k]
                    keep = y > 0
                    if keep.any():
                        implot.set_next_line_style(rgba(COLOUR_RGB.get(str(colour).lower(), "#999999")), 2.0)
                        implot.plot_line(f"{colour} S{state}", x[keep], y[keep])
            implot.end_plot()

    def draw_scans(self, scans, uncertainty=None) -> None:
        """Likelihood profiles (deviance against E or S) of every state."""
        if not scans:
            im.text_wrapped("No likelihood scan yet: press LL scan after a fit.")
            return
        for param, title in (("E", "FRET-E profile"), ("S", "Stoichiometry profile")):
            subset = [s for s in scans if s.param == param]
            if not subset:
                continue
            if implot.begin_plot(title, (-1, 200)):
                implot.setup_axes("Apparent FRET E" if param == "E" else "Stoichiometry S", "Delta(2 logL)")
                lo = min(float(np.min(s.values)) for s in subset)
                hi = max(float(np.max(s.values)) for s in subset)
                pad = max((hi - lo) * 0.05, 1e-3)
                implot.setup_axes_limits(lo - pad, hi + pad, -0.3, 12.0)  # the scanned window, not the whole 0..1 axis
                for s in subset:
                    implot.set_next_line_style(state_colour(s.state), 2.0)
                    implot.plot_line(f"S{s.state}", np.asarray(s.values, float), result_view.scan_deviance(s))
                    implot.set_next_line_style(state_colour(s.state), 1.0)
                    implot.plot_inf_lines(f"MLE S{s.state}", [float(s.mle)])
                implot.plot_inf_lines("threshold", [float(subset[0].threshold)], flags=implot.INF_LINES_FLAGS_HORIZONTAL)
                implot.end_plot()
