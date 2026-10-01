"""Numerical calculator state, independent of Qt hosting."""

from __future__ import annotations

from pathlib import Path

import numpy as np

_GUI_DIR = Path(__file__).parent


def _distribution_series(mean, sigma, chi_active, xform=None, wide=False, trim=False):
    """Build Gaussian + chi distribution series for the plots.

    ``xform`` maps the sampled distances to the plotted x-axis (identity for the
    distance distribution, a rate / time transform for the derived plots). The
    active distribution is drawn solid, the other dashed. ``wide`` evaluates the
    distance distribution on a broad common grid (so a sharp peak at large R is
    still shown in context); ``trim`` drops the extreme weight tails (used for
    the rate/time transforms whose tails extend over many decades).
    """
    from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
        distance_distribution,
    )

    sigma = max(float(sigma), 0.1)
    bins = None
    if wide:
        # Cover 0 well past the peak, independent of sigma, so a narrow
        # distribution centred at large R is still framed with context.
        r_max = max(2.0 * float(mean), float(mean) + 5.0 * sigma, 80.0)
        bins = np.linspace(0.0, r_max, 400)

    out = []
    for kind, color in (("gaussian", "#1f77b4"), ("chi", "#d62728")):
        r, w = distance_distribution(mean, sigma, kind, bins=bins)
        x = np.asarray(xform(r) if xform is not None else r, dtype=float)
        w = np.asarray(w, dtype=float)
        order = np.argsort(x)
        x, w = x[order], w[order]
        if trim and w.sum() > 0:
            cw = np.cumsum(w) / w.sum()
            keep = (cw >= 0.005) & (cw <= 0.995)
            if keep.any():
                x, w = x[keep], w[keep]
        active = chi_active if kind == "chi" else not chi_active
        out.append(
            {
                "x": x,
                "y": w,
                "name": "chi" if kind == "chi" else "Gaussian",
                "color": color,
                "width": 2 if active else 1,
                "style": "solid" if active else "dash",
            }
        )
    return out


class _FretModel:
    """Backing model for the DA-FRET tab; fields render in the EMTK app."""

    def __init__(self) -> None:
        self.tau0 = 4.0
        self.R0 = 52.0
        self.tau = 3.0
        self.R = 50.0
        self.sigma = 6.0
        self.use_chi = False
        self.E = 0.5
        self.kFRET = 0.25

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_GUI_DIR / "fret.view.json")

    def _rate(self, r):
        from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
            distance_to_fret_rate_constant,
        )

        return distance_to_fret_rate_constant(r, self.R0, self.tau0, 0.667)

    def distance_plot_series(self) -> list[dict]:
        return _distribution_series(self.R, self.sigma, bool(self.use_chi), wide=True)

    def rate_plot_series(self) -> list[dict]:
        # FRET-rate-constant distribution induced by the distance distribution.
        return _distribution_series(
            self.R,
            self.sigma,
            bool(self.use_chi),
            xform=self._rate,
            trim=True,
        )


class _HomoFretModel:
    """Backing model for the homo-FRET tab."""

    def __init__(self) -> None:
        self.tau0 = 2.3
        self.R0 = 52.0
        self.t_RM = 1.0
        self.rho = 16.0
        self.sigma = 6.0
        self.use_chi = False
        self.k_homo = 0.0
        self.R_DA = 50.0

    def view_spec(self):
        from chisurf.core.dataspec import load_view_spec

        return load_view_spec(_GUI_DIR / "homofret.view.json")

    def _rate(self, r):
        from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
            distance_to_fret_rate_constant,
        )

        return distance_to_fret_rate_constant(r, self.R0, self.tau0, 0.667)

    def distance_plot_series(self) -> list[dict]:
        return _distribution_series(self.R_DA, self.sigma, bool(self.use_chi), wide=True)

    def aniso_time_plot_series(self) -> list[dict]:
        # Characteristic anisotropy-decay time: rotational depolarisation (rho)
        # in parallel with energy-transfer depolarisation (2·k_FRET).
        rho = max(float(self.rho), 1e-9)

        def _tau(r):
            return 1.0 / (1.0 / rho + 2.0 * np.asarray(self._rate(r), dtype=float))

        return _distribution_series(
            self.R_DA,
            self.sigma,
            bool(self.use_chi),
            xform=_tau,
            trim=True,
        )
