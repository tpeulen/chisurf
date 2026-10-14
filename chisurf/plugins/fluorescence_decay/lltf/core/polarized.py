"""Joint VV/VH fit for LLTF: lifetimes and rotational correlation times from a polarized pair.

Both channels share the population decay ``F(t) = sum_i x_i exp(-t/tau_i)`` and
the anisotropy ``r(t) = sum_j b_j exp(-t/rho_j) (+ r_inf)``. The channel models
are ChiSurf's own Schaffer/Eggeling forward model
(:func:`chisurf.core.fluorescence.anisotropy.decay.calculcate_spectrum`):

    VV = F (1 + (2 - 3 l1) r),    VH = F (1 - (1 - 3 l2) r) / G

with ``G = S_par / S_perp``. Each channel is a sum of exponentials, reconvolved
with its own (shifted) IRF and scaled by one shared factor, so ``G`` fixes the
VH/VV ratio. Each channel has its own constant background and IRF shift. The
objective is the Poisson deviance summed over both channels (or the Neyman chi^2),
and the number of lifetimes can be chosen by the same extra-sum-of-squares F test
the magic-angle scan uses.
"""

from __future__ import annotations

import contextlib
import logging
import pathlib
import typing

import numpy as np

from chisurf.core.fitting.minimizer import ier_is_success, minimize
from chisurf.core.fluorescence.anisotropy.decay import anisotropy_rt, calculcate_spectrum
from chisurf.core.fluorescence.anisotropy.rt import rt_curves

from .convolve import convolve_lifetime_spectrum
from .fitter import (
    Decay,
    _optimizer_provenance,
    _shift_irf_numba,
    nested_f_probabilities,
    select_number_of_lifetimes,
    weighted_residuals,
)
from .settings import merged_settings

#: Stand-in correlation time of a residual anisotropy r_inf (ns): exp(-t/1e9) = 1
#: over any TCSPC window, and the product lifetime stays tau to 1e-8.
R_INF_RHO = 1.0e9


@contextlib.contextmanager
def _quiet_minimizer():
    """Hold back the minimizer's non-convergence warnings of intermediate fits.

    The magic-angle pre-fit only seeds the joint fit, and the joint fit runs from
    two starts and in two stages; a ``minimize:`` warning from any of these read
    as a failed fit in the log although the fit that is kept converged. The seed's
    status is reported as the seed's (``seed_fit`` in the result), and
    :meth:`PolarizedDecay.fit` warns once, for the fit it keeps.
    """

    def drop(record):
        return not str(record.getMessage()).startswith("minimize:")

    root = logging.getLogger()
    root.addFilter(drop)
    try:
        yield
    finally:
        root.removeFilter(drop)


SEED_NOTE = "Seed fit (magic angle) stopped at its evaluation limit; the joint fit converged."


# ── input ─────────────────────────────────────────────────────────────────────
class PolarizedData(typing.NamedTuple):
    """A VV/VH pair on one time axis, with the calibration the data carried."""

    time: np.ndarray
    vv: np.ndarray
    vh: np.ndarray
    calibration: dict  # any of g_factor, l1, l2 found in the data


def _columns(path) -> np.ndarray:
    data = np.genfromtxt(path, comments="#")
    data = np.atleast_2d(data)
    if data.shape[0] == 1 and data.shape[1] > 3:  # a single row: one column read flat
        data = data.T
    return data[np.all(np.isfinite(data), axis=1)]


def read_polarized(path, vh_path=None, channel_width: float | None = None) -> PolarizedData:
    """Read a VV/VH pair from one or two text files.

    Parameters
    ----------
    path : str or pathlib.Path
        One of: a stacked VV/VH file (one column, VV then VH, the ``vv_vh``
        format; its footer may carry ``g_factor``, ``l1``, ``l2``, ``dt``); a
        three-column file (time, VV, VH); or, with *vh_path*, the VV channel as
        a two-column file (time, counts).
    vh_path : str or pathlib.Path, optional
        The VH channel as a two-column file (time, counts).
    channel_width : float, optional
        Channel width in ns of a stacked file without ``dt`` in its footer.

    Returns
    -------
    PolarizedData
    """
    if vh_path is not None:
        a, b = _columns(path), _columns(vh_path)
        if a.shape[1] < 2 or b.shape[1] < 2 or len(a) != len(b):
            raise ValueError("VV and VH files need two columns (time, counts) of equal length")
        return PolarizedData(a[:, 0], a[:, 1].astype(float), b[:, 1].astype(float), {})
    data = _columns(path)
    if data.shape[1] >= 3:
        return PolarizedData(data[:, 0], data[:, 1].astype(float), data[:, 2].astype(float), {})
    if data.shape[1] == 2:
        raise ValueError(
            f"{pathlib.Path(path).name} has one decay (time, counts); give the VH channel too"
        )
    from chisurf.core.fio.vv_vh import read_vv_vh

    channels, meta = read_vv_vh(path, split=True, return_metadata=True)
    if isinstance(channels, tuple):
        vv, vh = channels
    else:
        vv, vh = channels["VV"], channels["VH"]
    dt = meta.get("dt", meta.get("channel_width", channel_width))
    if dt is None:
        raise ValueError("a stacked VV/VH file needs its channel width (dt)")
    calibration = {k: float(meta[k]) for k in ("g_factor", "l1", "l2") if k in meta}
    return PolarizedData(
        np.arange(len(vv)) * float(dt), np.asarray(vv, float), np.asarray(vh, float), calibration
    )


def from_data_group(group) -> PolarizedData:
    """The VV/VH pair of a ChiSurf ``DataCurveGroup`` (TTTR reader with VH channels, VV/VH CSV).

    Parameters
    ----------
    group : chisurf.core.data.DataCurveGroup
        Two curves, VV then VH; its ``meta_data`` may carry ``g_factor``, ``l1``, ``l2``.

    Returns
    -------
    PolarizedData
    """
    curves = list(group)
    if len(curves) < 2:
        raise ValueError("a VV/VH group needs two curves (VV, VH)")
    meta = getattr(group, "meta_data", None) or {}
    calibration = {k: float(meta[k]) for k in ("g_factor", "l1", "l2") if k in meta}
    vv, vh = curves[0], curves[1]
    return PolarizedData(
        np.asarray(vv.x, float), np.asarray(vv.y, float), np.asarray(vh.y, float), calibration
    )


def read_irf(path, vh_path=None, channel_width=None) -> tuple[np.ndarray, np.ndarray]:
    """IRF for VV and VH: one two-column file used for both, or a pair in any :func:`read_polarized` form."""
    data = _columns(path)
    if vh_path is None and data.shape[1] == 2:
        return data[:, 1].astype(float), data[:, 1].astype(float)
    pair = read_polarized(path, vh_path, channel_width)
    return pair.vv, pair.vh


def calibration(data: PolarizedData, settings: dict, overrides: dict | None = None) -> dict:
    """g, l1, l2 to use: an explicit override, else the data's, else the settings'; with sources."""
    out = {}
    for key in ("g_factor", "l1", "l2"):
        if overrides and overrides.get(key) is not None:
            out[key], out[f"{key}_source"] = float(overrides[key]), "given"
        elif key in data.calibration:
            out[key], out[f"{key}_source"] = data.calibration[key], "data"
        else:
            out[key], out[f"{key}_source"] = float(settings[key]), "settings"
    return out


# ── model and fit ─────────────────────────────────────────────────────────────
class PolarizedDecay:
    """A VV/VH pair, its IRFs and calibration, and the joint fit of both channels.

    Parameters
    ----------
    time : numpy.ndarray
        Time axis in ns, shared by both channels.
    vv, vh : numpy.ndarray
        Parallel and perpendicular counts.
    irf_vv, irf_vh : numpy.ndarray
        Instrument responses of the two channels (each normalised to unit area
        after its baseline, the median, is removed).
    g_factor, l1, l2 : float
        ``G = S_par / S_perp`` (divides VH) and the Schaffer mixing factors.
    noise_model : str
        ``"poisson"`` (deviance) or ``"neyman"``.
    """

    def __init__(
        self, time, vv, vh, irf_vv, irf_vh, g_factor=1.0, l1=0.0, l2=0.0, noise_model="poisson"
    ):
        self.time = np.asarray(time, float)
        self.data = (np.asarray(vv, float), np.asarray(vh, float))
        self.irfs = tuple(self._clean_irf(i) for i in (irf_vv, irf_vh))
        if not all(len(a) == len(self.time) for a in (*self.data, *self.irfs)):
            raise ValueError("VV, VH and both IRFs must have the length of the time axis")
        self.g_factor, self.l1, self.l2 = float(g_factor), float(l1), float(l2)
        if self.g_factor <= 0:
            raise ValueError("g_factor must be positive")
        if noise_model not in ("neyman", "poisson"):
            raise ValueError(f"noise_model must be 'neyman' or 'poisson', not {noise_model!r}")
        self.noise_model = noise_model
        self.dt = float(self.time[1] - self.time[0]) if len(self.time) > 1 else 1.0
        self.start, self.stop = 0, len(self.time)
        self.irf_shifts = [0.0, 0.0]
        self.backgrounds = [0.0, 0.0]
        self.result: dict | None = None

    @staticmethod
    def _clean_irf(irf) -> np.ndarray:
        """Baseline (median) removed, restricted to the channels the response occupies, unit area.

        Clipping the baseline-subtracted IRF at zero alone keeps the positive half
        of its baseline noise: a flat pedestal the convolution turns into an offset
        under the decay (chi2r 3.8 on the tr_anisotropy demo, whose IRF sits on 4
        counts). So the IRF is zeroed outside the contiguous window around its peak
        where the 5-channel average stands above the baseline noise (3 sigma, sigma
        from the median absolute deviation). A fixed fraction of the peak would cut
        a real tail instead: the LLTF example IRF has a zero baseline and 0.25 % of
        its area beyond 1e-3 of its peak, and cutting it moved a 1 ns lifetime to 1.05.
        """
        irf = np.asarray(irf, float)
        irf = irf - np.median(irf)
        sigma = 1.4826 * np.median(np.abs(irf))
        smooth = np.convolve(irf, np.ones(5) / 5.0, mode="same")
        peak = int(np.argmax(smooth))
        threshold = 3.0 * sigma / np.sqrt(5.0)
        below = np.nonzero(smooth <= threshold)[0]
        first = below[below < peak].max() + 1 if np.any(below < peak) else 0
        last = below[below > peak].min() if np.any(below > peak) else len(irf)
        window = np.zeros_like(irf)
        window[first:last] = np.clip(irf[first:last], 0.0, None)
        irf = window
        total = irf.sum()
        if total <= 0:
            raise ValueError("the IRF holds no signal above its baseline")
        return irf / total

    # magic-angle view ---------------------------------------------------------
    def magic_angle(self, vv, vh) -> np.ndarray:
        """``((1 - 3 l2) VV + (2 - 3 l1) G VH) / (3 (1 - l1 - l2))``: the population decay F."""
        g, l1, l2 = self.g_factor, self.l1, self.l2
        return ((1 - 3 * l2) * vv + (2 - 3 * l1) * g * vh) / (3 * (1 - l1 - l2))

    def _vm_decay(self) -> Decay:
        vm = self.magic_angle(*self.data)
        irf = 0.5 * (self.irfs[0] + self.irfs[1])
        decay = Decay(decay=vm, irf=irf * vm.max() / irf.max(), time_axis=self.time)
        decay.noise_model = "neyman"  # VM is not counts once G != 1: only a start
        return decay

    # setup --------------------------------------------------------------------
    def setup(self, settings: dict, verbose: bool = False) -> Decay:
        """Fit range, backgrounds and IRF shift from the magic-angle sum, as the magic-angle LLTF does."""
        vm = self._vm_decay()
        rng = settings["analysis_range_parameter"]
        vm.get_analysis_range(
            count_threshold=rng["count_threshold"],
            area=rng["area"],
            start_at_peak=rng["start_at_peak"],
            start_fraction=rng["start_fraction"],
            skip_first_channels=rng["skip_first_channels"],
            skip_last_channels=rng["skip_last_channels"],
            verbose=verbose,
        )
        self.start, self.stop = vm.start, vm.stop
        window = int(settings["estimate_background_parameter"]["average_window"])
        self.backgrounds = [float(np.mean(d[-window:])) for d in self.data]
        vm.decay_background = float(np.mean(vm.decay[-window:]))
        shift = settings["estimate_irf_shift_parameters"]
        if shift["enabled"] and shift["apply_shift"]:
            vm.estimate_irf_shift(
                irf_time_shift_scan_range=tuple(shift["irf_time_shift_scan_range"]),
                irf_time_shift_scan_n_steps=int(shift["irf_time_shift_scan_n_steps"]),
                verbose=verbose,
            )
        self.irf_shifts = [float(vm.irf_shift)] * 2
        # Every fit starts from the setup's estimates, not from the last fit's.
        self._setup_shift = float(vm.irf_shift)
        self._setup_backgrounds = list(self.backgrounds)
        self._vm = vm
        return vm

    # parameters ---------------------------------------------------------------
    def _layout(self, n_lifetimes, n_rotations, r_inf):
        return n_lifetimes, n_rotations, bool(r_inf)

    def unpack(self, p, layout):
        """Lifetime spectrum, rotation spectrum (with r_inf), shifts and backgrounds of a parameter vector."""
        n, m, r_inf = layout
        x = np.abs(p[:n])
        x = x / x.sum() if x.sum() > 0 else np.full(n, 1.0 / n)
        tau = p[n : 2 * n]
        b, rho = p[2 * n : 2 * n + m], p[2 * n + m : 2 * n + 2 * m]
        k = 2 * n + 2 * m
        lifetime = np.column_stack([x, tau]).ravel()
        rotation = np.column_stack([b, rho]).ravel()
        if r_inf:
            rotation = np.concatenate([rotation, [p[k], R_INF_RHO]])
            k += 1
        return lifetime, rotation, p[k : k + 2], p[k + 2 : k + 4]

    def channel_models(self, p, layout) -> tuple[np.ndarray, np.ndarray]:
        """VV and VH models (full length) for parameter vector *p*: shared scale, own background."""
        lifetime, rotation, shifts, bgs = self.unpack(p, layout)
        shapes = []
        for role, irf, shift in zip(("VV", "VH"), self.irfs, shifts):
            spectrum = calculcate_spectrum(
                lifetime, rotation, role, self.g_factor, self.l1, self.l2
            )
            out = np.zeros_like(self.time)
            convolve_lifetime_spectrum(
                out,
                spectrum,
                _shift_irf_numba(irf, float(shift) / self.dt),
                convolution_stop=self.stop,
                time_axis=self.time,
            )
            shapes.append(out)
        sl = slice(self.start, self.stop)
        net = [d[sl] - bg for d, bg in zip(self.data, bgs)]
        if self.noise_model == "poisson":
            # Count conservation over both channels: the ML scale of a Poisson model.
            denominator = sum(s[sl].sum() for s in shapes)
            scale = sum(n_.sum() for n_ in net) / denominator if denominator > 0 else 0.0
        else:
            w = [1.0 / np.maximum(d[sl], 1.0) for d in self.data]
            num = sum((wi * ni * s[sl]).sum() for wi, ni, s in zip(w, net, shapes))
            den = sum((wi * s[sl] ** 2).sum() for wi, s in zip(w, shapes))
            scale = num / den if den > 0 else 0.0
        return tuple(np.maximum(scale * s + bg, 0.0) for s, bg in zip(shapes, bgs))

    def residuals(self, p, layout) -> np.ndarray:
        """Concatenated weighted residuals of VV and VH over the analysis range."""
        sl = slice(self.start, self.stop)
        models = self.channel_models(p, layout)
        return np.concatenate(
            [weighted_residuals(d[sl], m[sl], self.noise_model) for d, m in zip(self.data, models)]
        )

    def _rotation_start(self, n_rotations: int) -> tuple[np.ndarray, np.ndarray]:
        """r0 and rho from the corrected r(t) of the data, binned to about 0.1 ns."""
        sl = slice(self.start, self.stop)
        width = max(1, int(round(0.1 / self.dt)))
        net = [np.clip(d[sl] - bg, 0, None) for d, bg in zip(self.data, self.backgrounds)]
        n = (len(net[0]) // width) * width
        sums = [a[:n].reshape(-1, width).sum(1) for a in net]
        t = self.time[sl][:n].reshape(-1, width).mean(1)
        peak = int(np.argmax(sums[0] + 2 * self.g_factor * sums[1]))
        _, _, r = rt_curves(
            t[peak:], sums[0][peak:], sums[1][peak:], self.g_factor, self.l1, self.l2
        )
        r = r[np.isfinite(r)]
        r0 = float(np.clip(np.median(r[:3]) if r.size >= 3 else 0.3, 0.05, 0.38))
        below = np.nonzero(r < r0 / np.e)[0]
        rho = float(np.clip((below[0] if below.size else 20) * width * self.dt, 0.1, 50.0))
        spread = 3.0 ** (np.arange(n_rotations) - (n_rotations - 1) / 2.0)
        return np.full(n_rotations, r0 / n_rotations), rho * spread

    def fit(
        self,
        n_lifetimes: int = 1,
        n_rotations: int = 1,
        fit_r_inf: bool = False,
        lifetime_spectrum=None,
        rotation_spectrum=None,
        settings: dict | None = None,
    ) -> dict:
        """Joint fit with a fixed number of lifetimes and rotations.

        Parameters
        ----------
        n_lifetimes, n_rotations : int
            Components of F(t) and of r(t).
        fit_r_inf : bool
            Add a residual anisotropy r_inf (a rotation that does not decay).
        lifetime_spectrum, rotation_spectrum : sequence of float, optional
            Interleaved starts; the lifetimes default to a magic-angle LLTF fit
            of ``n_lifetimes``, the rotations to an estimate from the data's r(t).
        settings : dict, optional
            Merged LLTF configuration (for the magic-angle start).

        Returns
        -------
        dict
            The result (see :meth:`_report`).
        """
        settings = merged_settings(settings)
        if not hasattr(self, "_vm"):
            self.setup(settings)
        rand = settings["lifetime_fit_parameter"]["randomize_initial_values"]
        starts = []
        if lifetime_spectrum is None:
            # Two starts, the better kept: a magic-angle LLTF fit of the G-weighted sum
            # (which can stop far off on its own: 5.0 / 2.78 ns for 4 + 1 ns), and the
            # deterministic spread the magic-angle scan starts from.
            vm = self._vm
            vm.irf_shift = self._setup_shift
            with _quiet_minimizer():
                seed = vm.fit(
                    n_lifetimes=n_lifetimes,
                    randomize_initial_values=True,
                    min_lifetime=rand["min_lifetime"],
                    max_lifetime=rand["max_lifetime"],
                    amplitude_variation=rand["amplitude_variation"],
                    seed=rand.get("seed", 0),
                )
            self._seed_fit = {
                "converged": bool(seed.get("converged", True)),
                "optimizer_status": seed.get("optimizer_status"),
                "optimizer_message": seed.get("optimizer_message", ""),
            }
            starts.append((np.asarray(vm.lifetime_spectrum, float), float(vm.irf_shift)))
            spread = np.linspace(rand["max_lifetime"], rand["min_lifetime"], n_lifetimes + 2)[1:-1]
            starts.append(
                (
                    np.column_stack([np.full(n_lifetimes, 1.0 / n_lifetimes), spread]).ravel(),
                    float(vm.irf_shift),
                )
            )
        else:
            starts.append((np.asarray(lifetime_spectrum, float), self.irf_shifts[0]))
        if rotation_spectrum is None:
            b, rho = self._rotation_start(n_rotations)
        else:
            rotation_spectrum = np.asarray(rotation_spectrum, float)
            b, rho = rotation_spectrum[0::2], rotation_spectrum[1::2]
        layout = self._layout(n_lifetimes, n_rotations, fit_r_inf)
        bounds = (
            [(0.0, 1.0)] * n_lifetimes
            + [(0.01, 50.0)] * n_lifetimes
            + [(-0.2, 0.4)] * n_rotations
            + [(0.01, 1000.0)] * n_rotations
            + ([(-0.2, 0.4)] if fit_r_inf else [])
            + [(None, None)] * 2
            + [(0.0, None)] * 2
        )
        results: list = []
        with _quiet_minimizer():
            self._run_starts(starts, b, rho, fit_r_inf, layout, bounds, results)
        best = min(results, key=lambda item: item[0])
        if not ier_is_success(best[2]):
            # The kept fit did not converge: that is a real warning.
            logging.warning(
                "minimize: " + _optimizer_provenance(best[2], len(best[1]))["optimizer_message"]
            )
        self.result = self._report(best[1], layout, best[2])
        self.result["seed_fit"] = getattr(self, "_seed_fit", None)
        return self.result

    def _run_starts(self, starts, b, rho, fit_r_inf, layout, bounds, results):
        """Optimise from every start; append ``(objective, parameters, status)`` to *results*."""
        for spectrum, shift in starts:
            p0 = np.concatenate(
                [
                    spectrum[0::2],
                    spectrum[1::2],
                    b,
                    rho,
                    [0.0] if fit_r_inf else [],
                    [shift, shift],
                    self._setup_backgrounds,
                ]
            )
            p, status = self._optimize(p0, layout, bounds)
            results.append((float(np.sum(self.residuals(p, layout) ** 2)), p, status))

    def _optimize(self, p0, layout, bounds):
        """MINPACK from *p0*; the deviance is refined from the Neyman optimum, as in the magic-angle fit."""
        noise_model = self.noise_model
        stages = ("neyman", "poisson") if noise_model == "poisson" else (noise_model,)
        try:
            for stage in stages:
                self.noise_model = stage
                p0, status = minimize(
                    lambda p: self.residuals(p, layout),
                    p0,
                    args=(),
                    bounds=bounds,
                    ftol=1.49012e-8,
                    xtol=1.49012e-8,
                    gtol=0.0,
                    maxfev=0,
                    epsfcn=0.0,
                    factor=1000,
                    diag=None,
                )
        finally:
            self.noise_model = noise_model
        return p0, status

    def scan(
        self,
        maximum_number_of_lifetimes: int = 3,
        n_rotations: int = 1,
        fit_r_inf: bool = False,
        prob_threshold: float = 0.68,
        selection_mode: str = "lower",
        settings: dict | None = None,
    ) -> dict:
        """Fit 1 … *maximum_number_of_lifetimes* lifetimes and keep the count the F test supports.

        Returns
        -------
        dict
            The selected fit, with ``optimal_fitting`` holding every model tried.
        """
        settings = merged_settings(settings)
        results = [
            self.fit(n, n_rotations, fit_r_inf, settings=settings)
            for n in range(1, int(maximum_number_of_lifetimes) + 1)
        ]
        chi2 = [r["chi_square"] for r in results]
        dofs = [r["dof"] for r in results]
        probs = nested_f_probabilities(chi2, dofs)
        scores = [r["reduced_chi_square"] for r in results]
        best = select_number_of_lifetimes(scores, probs, prob_threshold, selection_mode)
        chosen = dict(results[best])
        chosen["optimal_fitting"] = {
            "n_lifetimes_tried": [r["n_lifetimes"] for r in results],
            "scores": scores,
            "chi_squares": chi2,
            "dofs": dofs,
            "probabilities": probs,
            "lifetime_spectra": [r["lifetime_spectrum"] for r in results],
        }
        self.result = chosen
        return chosen

    def _report(self, p, layout, status) -> dict:
        n, m, r_inf = layout
        lifetime, rotation, shifts, bgs = self.unpack(p, layout)
        self.irf_shifts, self.backgrounds = [float(s) for s in shifts], [float(b) for b in bgs]
        sl = slice(self.start, self.stop)
        models = self.channel_models(p, layout)
        chi = [
            float(np.sum(weighted_residuals(d[sl], mo[sl], self.noise_model) ** 2))
            for d, mo in zip(self.data, models)
        ]
        n_points = 2 * (self.stop - self.start)
        dof = n_points - len(p)
        order = np.argsort(-lifetime[1::2])
        lifetime = np.column_stack([lifetime[0::2][order], lifetime[1::2][order]]).ravel()
        rot = rotation[: 2 * m]
        order_r = np.argsort(rot[1::2])
        rot = np.column_stack([rot[0::2][order_r], rot[1::2][order_r]]).ravel()
        r_infinity = float(rotation[-2]) if r_inf else 0.0
        t = self.time[sl]
        net_data = [d[sl] - bg for d, bg in zip(self.data, bgs)]
        net_model = [mo[sl] - bg for mo, bg in zip(models, bgs)]
        _, _, r_data = rt_curves(t, *net_data, self.g_factor, self.l1, self.l2)
        _, _, r_model = rt_curves(t, *net_model, self.g_factor, self.l1, self.l2)
        x = lifetime[0::2]
        tau = lifetime[1::2]
        result = {
            "mode": "vv_vh",
            "noise_model": self.noise_model,
            "n_lifetimes": n,
            "lifetime_spectrum": lifetime.tolist(),
            "lifetimes": [{"amplitude": float(a), "lifetime": float(b)} for a, b in zip(x, tau)],
            "n_rotations": m,
            "anisotropy_spectrum": rot.tolist(),
            "rotations": [{"b": float(a), "rho": float(b)} for a, b in zip(rot[0::2], rot[1::2])],
            "r_infinity": r_infinity,
            "fit_r_infinity": r_inf,
            "r0": float(np.sum(rot[0::2]) + r_infinity),
            "g_factor": self.g_factor,
            "l1": self.l1,
            "l2": self.l2,
            "irf_shift_vv": self.irf_shifts[0],
            "irf_shift_vh": self.irf_shifts[1],
            "decay_background_vv": self.backgrounds[0],
            "decay_background_vh": self.backgrounds[1],
            "chi_square": float(sum(chi)),
            "dof": int(dof),
            "reduced_chi_square": float(sum(chi) / max(1, dof)),
            # Per channel: its objective over its channels minus half the parameters.
            "chi_square_vv": chi[0],
            "chi_square_vh": chi[1],
            "reduced_chi_square_vv": chi[0] / max(1.0, n_points / 2 - len(p) / 2),
            "reduced_chi_square_vh": chi[1] / max(1.0, n_points / 2 - len(p) / 2),
            "time_range": {
                "start": float(self.time[self.start]),
                "stop": float(self.time[self.stop - 1]),
                "start_idx": int(self.start),
                "stop_idx": int(self.stop),
            },
            "model": {
                "time": t.tolist(),
                "vv": models[0][sl].tolist(),
                "vh": models[1][sl].tolist(),
                "magic_angle": self.magic_angle(*models)[sl].tolist(),
            },
            "anisotropy": {
                "time": t.tolist(),
                "data": np.where(np.isfinite(r_data), r_data, 0.0).tolist()
                if len(r_data) == len(t)
                else [],
                "model": r_model.tolist() if len(r_model) == len(t) else [],
                "rt": anisotropy_rt(t - t[0], rotation).tolist(),
            },
        }
        result.update(_optimizer_provenance(status, len(p)))
        return result

    # output -------------------------------------------------------------------
    def plot(self, filename: str | None = None):
        """VV and VH with fits, their weighted residuals, and r(t) data against model, to a PNG.

        Returns
        -------
        emtk.figure.Figure or None
        """
        if filename is None or self.result is None:
            return None
        from emtk.figure import Figure

        res = self.result
        sl = slice(self.start, self.stop)
        t = self.time
        figure = Figure(3, 1, size=(1000, 1000), height_ratios=(2, 1, 1.5))
        ax = figure.ax(0, 0)
        for name, data, model, colors in (
            ("VV", self.data[0], res["model"]["vv"], ("b", "r")),
            ("VH", self.data[1], res["model"]["vh"], ((0.2, 0.6, 1.0), (1.0, 0.6, 0.0))),
        ):
            ax.line(t, np.clip(data, 1e-9, None), color=colors[0], label=name)
            ax.line(t[sl], np.clip(model, 1e-9, None), color=colors[1], label=f"{name} fit")
        ax.set_log(y=True)
        positive = self.data[0][self.data[0] > 0]
        if positive.size:
            ax.set_ylim(float(positive.min()) * 0.5, float(self.data[0].max()) * 2.0)
        ax.set_labels(x="Time (ns)", y="Counts")
        ax.legend()
        ax = figure.ax(1, 0)
        for data, model, color in (
            (self.data[0], res["model"]["vv"], "b"),
            (self.data[1], res["model"]["vh"], (0.2, 0.6, 1.0)),
        ):
            ax.line(
                t[sl],
                weighted_residuals(data[sl], np.asarray(model), self.noise_model),
                color=color,
            )
        ax.hline(0.0, color=(0, 0, 0, 0.5))
        ax.set_labels(x="Time (ns)", y="Weighted Residuals")
        ax = figure.ax(2, 0)
        ax.line(
            res["anisotropy"]["time"],
            res["anisotropy"]["data"],
            color=(0.5, 0.5, 0.5),
            label="r(t) data",
        )
        ax.line(res["anisotropy"]["time"], res["anisotropy"]["model"], color="r", label="r(t) fit")
        ax.set_ylim(-0.1, 0.5)
        ax.set_labels(x="Time (ns)", y="r(t)")
        ax.legend()
        figure.save(filename)
        return figure


def seed_notes(result: dict) -> list[str]:
    """What to say about the seed fit: only that it stopped early, and only when the joint fit converged.

    A joint fit that did not converge is reported by its own optimizer warning.
    """
    seed = result.get("seed_fit") or {}
    if seed and not seed.get("converged", True) and result.get("converged"):
        return [SEED_NOTE]
    return []


def fit_polarized(
    decay,
    irf,
    vh_decay=None,
    irf_vh=None,
    config: dict | None = None,
    g_factor: float | None = None,
    l1: float | None = None,
    l2: float | None = None,
    output_file: str | None = None,
    plot_file: str | None = None,
    verbose: bool = False,
) -> dict:
    """Joint VV/VH fit of a polarized decay with LLTF's rules.

    Parameters
    ----------
    decay : str, pathlib.Path, PolarizedData or DataCurveGroup
        The VV/VH pair (see :func:`read_polarized` for the file forms).
    irf : str or pathlib.Path
        IRF: one two-column file for both channels, or a pair like *decay*.
    vh_decay, irf_vh : str or pathlib.Path, optional
        The VH channel / VH IRF as separate two-column files.
    config : dict, optional
        LLTF configuration over the packaged defaults. ``lifetime_fit_parameter``
        (``find_optimal``, ``number_of_lifetimes``, ``maximum_number_of_lifetimes``,
        ``prob_threshold``, ``selection_mode``, ``noise_model``) and
        ``polarization_parameter`` (``g_factor``, ``l1``, ``l2``,
        ``number_of_rotations``, ``fit_r_infinity``, ``channel_width``) apply.
    g_factor, l1, l2 : float, optional
        Override the calibration; otherwise the data's, otherwise the settings'.
    output_file, plot_file : str, optional
        JSON result and PNG plot to write.
    verbose : bool
        Print the result summary.

    Returns
    -------
    dict
        The fit result (lifetimes, rotations, r0, r_inf, per-channel and joint
        chi-square, models, r(t) data and model, calibration and its sources).
    """
    import json

    settings = merged_settings(config)
    pol = settings["polarization_parameter"]
    if isinstance(decay, PolarizedData):
        data = decay
    elif hasattr(decay, "meta_data") and not isinstance(decay, (str, pathlib.Path)):
        data = from_data_group(decay)
    else:
        data = read_polarized(decay, vh_decay, pol["channel_width"])
    irf_vv, irf_vh_ = read_irf(irf, irf_vh, pol["channel_width"])
    cal = calibration(data, pol, {"g_factor": g_factor, "l1": l1, "l2": l2})
    fit_params = settings["lifetime_fit_parameter"]
    pd = PolarizedDecay(
        data.time,
        data.vv,
        data.vh,
        irf_vv,
        irf_vh_,
        cal["g_factor"],
        cal["l1"],
        cal["l2"],
        fit_params["noise_model"],
    )
    pd.setup(settings, verbose=verbose)
    n_rot = int(pol["number_of_rotations"])
    r_inf = bool(pol["fit_r_infinity"])
    if fit_params["find_optimal"]:
        result = pd.scan(
            fit_params["maximum_number_of_lifetimes"],
            n_rot,
            r_inf,
            fit_params["prob_threshold"],
            fit_params["selection_mode"],
            settings,
        )
    else:
        n = int(fit_params.get("number_of_lifetimes") or 1)
        result = pd.fit(n, n_rot, r_inf, settings=settings)
    result["calibration_source"] = {k: cal[f"{k}_source"] for k in ("g_factor", "l1", "l2")}
    result["notes"] = seed_notes(result)
    if verbose:
        for note in result["notes"]:
            print(note)
        for i, row in enumerate(result["lifetimes"], 1):
            print(f"Lifetime {i}: {row['lifetime']:.3f} ns, Amplitude: {row['amplitude']:.3f}")
        for i, row in enumerate(result["rotations"], 1):
            print(f"Rotation {i}: {row['rho']:.3f} ns, b: {row['b']:.3f}")
        print(f"r0: {result['r0']:.3f}" + (f", r_inf: {result['r_infinity']:.3f}" if r_inf else ""))
        print(
            f"g: {cal['g_factor']:.4g} ({cal['g_factor_source']}), l1: {cal['l1']:.4g}, l2: {cal['l2']:.4g}"
        )
        print(
            f"Reduced chi-square: {result['reduced_chi_square']:.2f} "
            f"(VV {result['reduced_chi_square_vv']:.2f}, VH {result['reduced_chi_square_vh']:.2f})"
        )
    if output_file:
        pathlib.Path(output_file).write_text(json.dumps(result, indent=2))
    if plot_file:
        pd.plot(plot_file)
    return result


# ── demo ──────────────────────────────────────────────────────────────────────
#: The simulated VV/VH pair of the demo / Load example, in one place so help,
#: guide and tests agree.
DEMO: dict[str, typing.Any] = {
    "lifetimes": [1.0, 4.0],
    "amplitudes": [0.3, 0.7],
    "rho": 1.5,
    "r0": 0.35,
    "g_factor": 1.2,
    "l1": 0.0,
    "l2": 0.0,
    "photons": 2.0e6,
    "seed": 7,
}


def simulate_vv_vh(
    irf: np.ndarray,
    channel_width: float,
    lifetimes=(4.0,),
    amplitudes=None,
    rotations=((0.35, 1.5),),
    g_factor: float = 1.0,
    l1: float = 0.0,
    l2: float = 0.0,
    photons: float = 2e6,
    seed: int | None = 0,
) -> PolarizedData:
    """Poisson-sampled VV/VH pair from ChiSurf's forward model (:func:`synthetic_aniso_decay`).

    Parameters
    ----------
    irf : numpy.ndarray
        Instrument response, one channel per bin.
    channel_width : float
        Bin width in ns.
    lifetimes, amplitudes : sequence of float
        The population decay.
    rotations : sequence of (b, rho)
        The anisotropy decay.
    g_factor, l1, l2 : float
        Calibration (``G`` divides VH).
    photons : float
        Total photons over both channels.
    seed : int, optional
        Poisson seed.

    Returns
    -------
    PolarizedData
        With the calibration recorded as if the data carried it.
    """
    from chisurf.core.fluorescence.decay import synthetic_aniso_decay

    irf = np.asarray(irf, float)
    vv, vh = synthetic_aniso_decay(
        irf.size,
        list(lifetimes),
        amplitudes=None if amplitudes is None else list(amplitudes),
        anisotropy_spectrum=np.asarray(rotations, float).ravel(),
        g_factor=g_factor,
        l1=l1,
        l2=l2,
        bin_width=channel_width,
        irf=irf,
        normalize=False,
        photon_count=photons,
        seed=seed,
    )
    return PolarizedData(
        np.arange(irf.size) * channel_width,
        np.asarray(vv, float),
        np.asarray(vh, float),
        {"g_factor": float(g_factor), "l1": float(l1), "l2": float(l2)},
    )


def write_demo(folder) -> tuple[pathlib.Path, pathlib.Path]:
    """Write the demo pair as a stacked ``vv_vh`` file (g in its footer) and the example IRF.

    Returns
    -------
    tuple of pathlib.Path
        ``(decay_file, irf_file)``.
    """
    from chisurf.core.fio.vv_vh import write_vv_vh

    folder = pathlib.Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    irf_file = pathlib.Path(__file__).resolve().parents[1] / "example" / "IRF_D0.dat"
    irf_data = np.loadtxt(irf_file)
    dt = float(irf_data[1, 0] - irf_data[0, 0])
    d = DEMO
    pair = simulate_vv_vh(
        irf_data[:, 1],
        dt,
        d["lifetimes"],
        d["amplitudes"],
        [(d["r0"], d["rho"])],
        d["g_factor"],
        d["l1"],
        d["l2"],
        d["photons"],
        d["seed"],
    )
    decay_file = folder / "lltf_vv_vh_demo.txt"
    write_vv_vh(
        decay_file,
        vv=pair.vv,
        vh=pair.vh,
        g_factor=d["g_factor"],
        metadata={"l1": d["l1"], "l2": d["l2"], "dt": dt},
    )
    return decay_file, irf_file
