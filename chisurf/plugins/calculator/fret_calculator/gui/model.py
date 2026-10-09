"""Qt-free state and coupled recomputation of the FRET calculator.

Two models, one per tab. A field edit runs the one method the Qt tool wired to
that field's ``editingFinished`` (forward from the distance, inverse from the
lifetime, efficiency or rate, back-map from the homo-FRET distance); the
results are written back into the fields the way the Qt spin boxes took them,
rounded to the field's decimals and clamped to its range.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

_GUI_DIR = Path(__file__).parent

#: kappa^2 the Qt tool always passed (isotropic dynamic average).
KAPPA2 = 0.667


def default_client() -> SimpleNamespace:
    """The backend handlers the Qt tool reached through its in-process client."""
    from ..backend import services

    return SimpleNamespace(
        compute_fret=services.fret_compute_handler,
        compute_fret_from_lifetime=services.fret_from_lifetime_handler,
        compute_fret_from_efficiency=services.fret_from_efficiency_handler,
        compute_fret_from_rate=services.fret_from_rate_handler,
        compute_homo_fret=services.homo_compute_handler,
        homo_backmap=services.homo_backmap_handler,
    )


def distribution_series(mean, sigma, chi_active, xform=None, wide=False, trim=False):
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


class _CoupledModel:
    """What both tabs share: a client, a status line, the Qt spin boxes' rounding."""

    #: ``attr -> (decimals, minimum, maximum)`` of the fields results are written to.
    result_fields: dict[str, tuple[int, float, float]] = {}
    #: ``attr -> (decimals, minimum, maximum)`` of the input fields (restore clamps to these).
    input_fields: dict[str, tuple[int, float, float]] = {}
    spec_file = ""

    def __init__(self, client: Any = None) -> None:
        self.client = client if client is not None else default_client()
        #: The last backend error, empty when the last computation succeeded.
        self.status = ""
        self._series_cache: dict[str, tuple] = {}

    def view_spec(self):
        """The tab's view spec (shared with the generated plugin documentation)."""
        import json

        return json.loads((_GUI_DIR / self.spec_file).read_text(encoding="utf-8"))

    def status_text(self) -> str:
        """One line under the buttons: the last backend error, else a hint."""
        return self.status or "Edit any field; the linked quantities update."

    # -- shared plumbing ---------------------------------------------------- #
    def _call(self, label: str, answer: dict) -> dict | None:
        """The result of a backend call, or ``None`` with the error on the status line."""
        if answer.get("ok"):
            self.status = ""
            return answer["result"]
        self.status = f"{label} failed: {answer.get('error', 'unknown error')}"
        return None

    def _store(self, attr: str, value: Any) -> None:
        """Write one computed value as a spin box takes it: finite only, rounded, clamped."""
        decimals, lo, hi = self.result_fields[attr]
        value = float(value)
        if np.isnan(value):
            return
        setattr(self, attr, round(float(np.clip(value, lo, hi)), decimals))

    def _cached(self, key: str, params: tuple, build):
        """Series are rebuilt only when their inputs change (a frame must stay cheap)."""
        hit = self._series_cache.get(key)
        if hit is not None and hit[0] == params:
            return hit[1]
        series = build()
        self._series_cache[key] = (params, series)
        return series

    # -- persistence --------------------------------------------------------- #
    def export_settings(self) -> dict:
        """The input fields (the outputs are recomputed on restore)."""
        return {attr: getattr(self, attr) for attr in (*self.input_fields, "use_chi")}

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; invalid or out-of-range entries are ignored."""
        if not isinstance(settings, dict):
            return
        for attr, (_decimals, lo, hi) in self.input_fields.items():
            value = settings.get(attr)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            if np.isfinite(value) and lo <= float(value) <= hi:
                setattr(self, attr, float(value))
        if isinstance(settings.get("use_chi"), bool):
            self.use_chi = settings["use_chi"]
        self.recompute()


class HeteroFretModel(_CoupledModel):
    """The donor-acceptor tab: distance, lifetime, efficiency and rate are one quantity."""

    spec_file = "fret.view.json"
    result_fields = {
        "R": (2, 0.1, 9999.0),
        "E": (6, 0.0, 1.0),
        "tau": (4, 0.0, 9999.0),
        "kFRET": (6, 0.0, 9999.0),
    }
    input_fields = {
        "tau0": (4, 0.001, 9999.0),
        "R0": (2, 0.1, 999.0),
        "R": (2, 0.1, 9999.0),
        "sigma": (2, 0.1, 999.0),
    }

    def __init__(self, client: Any = None) -> None:
        super().__init__(client)
        self.tau0 = 4.0
        self.R0 = 52.0
        self.tau = 3.0
        self.R = 50.0
        self.sigma = 6.0
        self.use_chi = False
        self.E = 0.5
        self.kFRET = 0.25

    def _apply(self, result: dict) -> None:
        for attr, key in (("R", "R"), ("E", "E"), ("tau", "tau_DA"), ("kFRET", "kFRET")):
            self._store(attr, result[key])

    # -- the handlers the Qt tab wired to editingFinished -------------------- #
    def compute_forward(self, _value: Any = None) -> None:
        """Distance (and sigma, R0, tau0, distribution) given: the other three follow."""
        result = self._call(
            "FRET from distance",
            self.client.compute_fret(
                R=self.R,
                R0=self.R0,
                tau0=self.tau0,
                kappa2=KAPPA2,
                sigma=self.sigma,
                distribution="chi" if self.use_chi else "gaussian",
            ),
        )
        if result is not None:
            self._apply(result)

    recompute = compute_forward

    def from_lifetime(self, _value: Any = None) -> None:
        """Lifetime given: the effective single distance, efficiency and rate follow."""
        result = self._call(
            "FRET from lifetime",
            self.client.compute_fret_from_lifetime(tau_DA=self.tau, R0=self.R0, tau0=self.tau0),
        )
        if result is not None:
            self._apply(result)

    def from_efficiency(self, _value: Any = None) -> None:
        """Efficiency given: the effective single distance, lifetime and rate follow."""
        result = self._call(
            "FRET from efficiency",
            self.client.compute_fret_from_efficiency(E=self.E, R0=self.R0, tau0=self.tau0),
        )
        if result is not None:
            self._apply(result)

    def from_rate(self, _value: Any = None) -> None:
        """Rate constant given: the effective single distance, lifetime and efficiency follow."""
        result = self._call(
            "FRET from rate",
            self.client.compute_fret_from_rate(kFRET=self.kFRET, R0=self.R0, tau0=self.tau0),
        )
        if result is not None:
            self._apply(result)

    # -- plots ---------------------------------------------------------------- #
    def _rate(self, r):
        from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
            distance_to_fret_rate_constant,
        )

        return distance_to_fret_rate_constant(r, self.R0, self.tau0, KAPPA2)

    def distance_plot_series(self) -> list[dict]:
        """p(R) of both distributions around the distance."""
        params = (self.R, self.sigma, bool(self.use_chi))
        return self._cached(
            "distance",
            params,
            lambda: distribution_series(self.R, self.sigma, bool(self.use_chi), wide=True),
        )

    def rate_plot_series(self) -> list[dict]:
        """The FRET-rate-constant distribution induced by the distance distribution."""
        params = (self.R, self.sigma, bool(self.use_chi), self.R0, self.tau0)
        return self._cached(
            "rate",
            params,
            lambda: distribution_series(
                self.R, self.sigma, bool(self.use_chi), xform=self._rate, trim=True
            ),
        )


class HomoFretModel(_CoupledModel):
    """The like-dye tab: migration time, rotational time and the implied distance."""

    spec_file = "homofret.view.json"
    result_fields = {
        "k_homo": (6, 0.0, 9999.0),
        "R_DA": (2, 0.0, 9999.0),
        "t_RM": (4, 0.001, 9999.0),
    }
    input_fields = {
        "tau0": (4, 0.001, 9999.0),
        "R0": (2, 0.1, 999.0),
        "t_RM": (4, 0.001, 9999.0),
        "rho": (4, 0.001, 9999.0),
        "sigma": (2, 0.1, 999.0),
    }

    def __init__(self, client: Any = None) -> None:
        super().__init__(client)
        self.tau0 = 2.3
        self.R0 = 52.0
        self.t_RM = 1.0
        self.rho = 16.0
        self.sigma = 6.0
        self.use_chi = False
        self.k_homo = 0.0
        self.R_DA = 50.0

    def compute_forward(self, _value: Any = None) -> None:
        """Migration time given: the rate and, when it exists, the implied distance follow."""
        result = self._call(
            "Homo-FRET rate",
            self.client.compute_homo_fret(t_RM=self.t_RM, rho=self.rho, tau0=self.tau0, R0=self.R0),
        )
        if result is None:
            return
        self._store("k_homo", result["k_homo"])
        r_da = result["R_DA"]
        if np.isfinite(r_da) and r_da > 0:
            self._store("R_DA", r_da)

    recompute = compute_forward

    def backmap(self, _value: Any = None) -> None:
        """Distance given: the rate and the migration time follow."""
        result = self._call(
            "Homo-FRET back-map",
            self.client.homo_backmap(R_DA=self.R_DA, R0=self.R0, tau0=self.tau0, rho=self.rho),
        )
        if result is None:
            return
        if np.isfinite(result["k_homo"]):
            self._store("k_homo", result["k_homo"])
        if np.isfinite(result["t_RM"]) and result["t_RM"] > 0:
            self._store("t_RM", result["t_RM"])

    def _rate(self, r):
        from chisurf.plugins.calculator.fret_calculator.core.algorithms import (
            distance_to_fret_rate_constant,
        )

        return distance_to_fret_rate_constant(r, self.R0, self.tau0, KAPPA2)

    def distance_plot_series(self) -> list[dict]:
        """p(R) of both distributions around the homo-FRET distance."""
        params = (self.R_DA, self.sigma, bool(self.use_chi))
        return self._cached(
            "distance",
            params,
            lambda: distribution_series(self.R_DA, self.sigma, bool(self.use_chi), wide=True),
        )

    def aniso_time_plot_series(self) -> list[dict]:
        """Characteristic anisotropy-decay time: rotation (rho) in parallel with 2 k_FRET."""
        params = (self.R_DA, self.sigma, bool(self.use_chi), self.rho, self.R0, self.tau0)

        def build():
            rho = max(float(self.rho), 1e-9)

            def _tau(r):
                return 1.0 / (1.0 / rho + 2.0 * np.asarray(self._rate(r), dtype=float))

            return distribution_series(
                self.R_DA, self.sigma, bool(self.use_chi), xform=_tau, trim=True
            )

        return self._cached("aniso", params, build)


class FretCalculatorModel:
    """Both tabs and the selected one: what a window (or the Qt host) shares."""

    TABS = ("HeteroFRET", "HomoFRET")

    def __init__(self, client: Any = None) -> None:
        client = client if client is not None else default_client()
        self.hetero = HeteroFretModel(client)
        self.homo = HomoFretModel(client)
        self.tab = 0
        # The Qt tool computed both tabs once at construction: the first frame shows outputs.
        self.hetero.compute_forward()
        self.homo.compute_forward()

    def export_settings(self) -> dict:
        """Inputs of both tabs and the selected tab."""
        return {
            "hetero": self.hetero.export_settings(),
            "homo": self.homo.export_settings(),
            "tab": self.tab,
        }

    def restore_settings(self, settings: dict) -> None:
        """Restore :meth:`export_settings`; invalid entries are ignored."""
        if not isinstance(settings, dict):
            return
        self.hetero.restore_settings(settings.get("hetero"))
        self.homo.restore_settings(settings.get("homo"))
        tab = settings.get("tab")
        if isinstance(tab, int) and not isinstance(tab, bool) and 0 <= tab < len(self.TABS):
            self.tab = tab


# Names the migration stream's host and tests import.
_distribution_series = distribution_series
_FretModel = HeteroFretModel
_HomoFretModel = HomoFretModel
