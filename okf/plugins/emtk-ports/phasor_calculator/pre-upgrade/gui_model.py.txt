"""Numerical calculator state, independent of Qt hosting."""

from __future__ import annotations

import pathlib

_GUI_DIR = pathlib.Path(__file__).parent


class _PhasorCalcModel:
    """Backing model for the phasor calculator; fields declared in phasor.view.json."""

    #: Plot extent (slightly padded around the universal semicircle).
    PHASOR_G_RANGE = (-0.05, 1.05)
    PHASOR_S_RANGE = (-0.02, 0.62)

    def __init__(self) -> None:
        self.frequency = 80.0
        self.harmonic = 1
        self.taus = "0.5, 1, 2, 4, 8"
        self.show_grid = True
        self.show_ticks = True
        self.show_polar_grid = False
        self.show_fret = False
        self.tau_d0 = 4.0
        self.show_component = False
        self.g1, self.s1 = 0.80, 0.35
        self.g2, self.s2 = 0.30, 0.45
        # N-component mixing region / fraction-weighted mixture (uses c1/c2 above)
        self.show_mixing = False
        self.frac1 = 0.5
        # gating cursor outline
        self.show_cursor = False
        self.cursor_g, self.cursor_s = 0.55, 0.30
        self.cursor_radius = 0.05

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_GUI_DIR / "phasor.view.json")

    # -- helpers ----------------------------------------------------------------------
    def _tau_list(self) -> list[float]:
        out: list[float] = []
        for tok in str(self.taus).replace(";", ",").split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                out.append(float(tok))
            except ValueError:
                pass
        return out or [1.0]

    def _sets(self) -> list[str]:
        sets: list[str] = []
        if self.show_grid:
            sets.append("lifetime_grid")
        if self.show_ticks:
            sets.append("lifetime_ticks")
        if self.show_polar_grid:
            sets.append("polar_grid")
        if self.show_fret:
            sets.append("fret")
        if self.show_component:
            sets.append("component_line")
        if self.show_mixing:
            sets.append("components")
        if self.show_cursor:
            sets.append("cursor")
        return sets

    # -- AutoForm sources -------------------------------------------------------------
    def phasor_overlays(self) -> list[dict]:
        from chisurf.plugins.microscopy.img_pixel_phasor import analysis

        f1 = min(max(float(self.frac1), 0.0), 1.0)
        return analysis.build_overlays(
            frequency_mhz=float(self.frequency),
            harmonic=int(self.harmonic),
            sets=self._sets(),
            taus=self._tau_list(),
            c1=(self.g1, self.s1),
            c2=(self.g2, self.s2),
            tau_d0=float(self.tau_d0),
            components=[[self.g1, self.s1], [self.g2, self.s2]],
            fractions=[f1, 1.0 - f1],
            cursors=[
                {
                    "center": [self.cursor_g, self.cursor_s],
                    "radius": float(self.cursor_radius),
                    "name": "cursor",
                }
            ],
        )

    def results_html(self) -> str:
        from chisurf.plugins.microscopy.img_pixel_phasor import analysis

        freq = float(self.frequency) * int(self.harmonic)
        rows = "".join(
            f"<tr><td>{t:g}</td><td>{float(g):.3f}</td><td>{float(s):.3f}</td></tr>"
            for t in self._tau_list()
            for g, s in [analysis.lifetime_to_phasor(t, freq)]
        )
        return (
            f"<b>Effective f = {freq:g} MHz</b>"
            "<table><tr><th>&tau; (ns)</th><th>g</th><th>s</th></tr>"
            f"{rows}</table>"
        )
