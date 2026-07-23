r"""smFRET calibration parameters with light-path priors and data optimization.

The calibration factors that turn raw green/red/yellow burst counts into an
accurate FRET efficiency — the detection/quantum-yield ratio ``gamma``, the
donor spectral leakage ``alpha``, the direct acceptor excitation ``delta``, the
channel backgrounds and the Förster radius ``R0`` — are modelled here as real
:class:`~chisurf.core.fitting.parameter.FittingParameter`\\s in a
:class:`CalibrationParameters` group.

The design (see the calibration OKF concept):

* the **light-path calculator** supplies each factor's **prior** — a
  physically-motivated Gaussian centred on the value computed from the optics
  (spectra, filters, detector QE), with a width reflecting the model
  uncertainty (:func:`set_priors_from_lightpath`);
* **optimizing against the measured data** (a global E-S correction followed by
  a prior-regularized refinement) yields the **posterior** factors used for
  accurate FRET.

Because the priors are attached to ordinary ``FittingParameter``\\s, the standard
ChiSurf MAP (``_prior_residuals``) and MCMC (``lnprob``) machinery regularizes
the fit automatically. The module is Qt-free and array-based so it runs
head-less, in tests and from the CLI.
"""

from __future__ import annotations

import numpy as np

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fitting.priors import NormalPrior, TruncatedNormalPrior

__all__ = [
    "CalibrationParameters",
    "lightpath_correction_factors",
    "crosstalk_matrices_from_lightpath",
    "general_correction_from_lightpath",
    "set_priors_from_lightpath",
    "global_es_correction",
    "refine_calibration",
    "CalibrationFit",
    "register_calibration",
    "unregister_calibration",
    "link_to_calibration",
    "calibration_to_ndx_constants",
    "leakage_from_donor_only",
    "direct_excitation_from_acceptor_only",
    "calibrate_from_samples",
]


class CalibrationParameters(FittingParameterGroup):
    """Free smFRET calibration factors (gamma, alpha, delta, backgrounds, R0).

    Each factor is a bounded :class:`FittingParameter`; a light-path prior can
    be attached via :func:`set_priors_from_lightpath`, after which the factors
    are optimized against the data (they stay *free* — the light-path value is
    only the prior mean).

    Uses the Hellenkamp 2018 nomenclature (α leakage, β excitation-flux ratio,
    γ detection/QY, δ direct excitation; channels I_DD/I_DA/I_AA).

    Attributes (via properties)
    ---------------------------
    gamma : float
        Detection/quantum-yield ratio γ = ``(gR·ΦA)/(gG·ΦD)``.
    alpha : float
        Donor spectral leakage α into the acceptor (I_DA) channel.
    beta : float
        Excitation-flux ratio β (enters the stoichiometry).
    delta : float
        Direct acceptor excitation δ at the donor-excitation wavelength.
    bg_dd, bg_da, bg_aa : float
        Background count rates of the I_DD / I_DA / I_AA channels.
    r0 : float
        Förster radius R0 (Å).
    phi_a, phi_d : float
        Acceptor / donor fluorescence quantum yields (ΦA, ΦD).
    """

    def __init__(self, name: str = "calibration", **kwargs):
        """Create the calibration parameter group with weakly-bounded defaults.

        Parameters
        ----------
        name : str
            Name of the parameter group.
        **kwargs
            Forwarded to :class:`FittingParameterGroup`.
        """
        super().__init__(name=name, **kwargs)
        self._gamma = FittingParameter(value=1.0, name="gamma", lb=0.05, ub=20.0, bounds_on=True)
        self._alpha = FittingParameter(value=0.0, name="alpha", lb=0.0, ub=1.0, bounds_on=True)
        self._beta = FittingParameter(value=1.0, name="beta", lb=0.01, ub=100.0, bounds_on=True)
        self._delta = FittingParameter(value=0.0, name="delta", lb=0.0, ub=1.0, bounds_on=True)
        self._bg_dd = FittingParameter(value=0.0, name="Bg_DD", lb=0.0, ub=1e6, bounds_on=True)
        self._bg_da = FittingParameter(value=0.0, name="Bg_DA", lb=0.0, ub=1e6, bounds_on=True)
        self._bg_aa = FittingParameter(value=0.0, name="Bg_AA", lb=0.0, ub=1e6, bounds_on=True)
        self._r0 = FittingParameter(value=52.0, name="R0", lb=1.0, ub=200.0, bounds_on=True)
        self._phi_a = FittingParameter(value=1.0, name="PhiA", lb=0.0, ub=1.0, bounds_on=True)
        self._phi_d = FittingParameter(value=1.0, name="PhiD", lb=0.0, ub=1.0, bounds_on=True)
        self.find_parameters()

    # --- scalar accessors -------------------------------------------------
    @property
    def gamma(self) -> float:
        """Detection/quantum-yield ratio."""
        return float(self._gamma.value)

    @gamma.setter
    def gamma(self, v: float):
        self._gamma.value = float(v)

    @property
    def alpha(self) -> float:
        """Donor leakage into the acceptor channel (α)."""
        return float(self._alpha.value)

    @alpha.setter
    def alpha(self, v: float):
        self._alpha.value = float(v)

    @property
    def beta(self) -> float:
        """Excitation-flux ratio (β)."""
        return float(self._beta.value)

    @beta.setter
    def beta(self, v: float):
        self._beta.value = float(v)

    @property
    def delta(self) -> float:
        """Direct acceptor excitation (δ)."""
        return float(self._delta.value)

    @delta.setter
    def delta(self, v: float):
        self._delta.value = float(v)

    @property
    def bg_dd(self) -> float:
        """Background of the I_DD channel."""
        return float(self._bg_dd.value)

    @bg_dd.setter
    def bg_dd(self, v: float):
        self._bg_dd.value = float(v)

    @property
    def bg_da(self) -> float:
        """Background of the I_DA (FRET) channel."""
        return float(self._bg_da.value)

    @bg_da.setter
    def bg_da(self, v: float):
        self._bg_da.value = float(v)

    @property
    def bg_aa(self) -> float:
        """Background of the I_AA channel."""
        return float(self._bg_aa.value)

    @bg_aa.setter
    def bg_aa(self, v: float):
        self._bg_aa.value = float(v)

    @property
    def r0(self) -> float:
        """Förster radius (Å)."""
        return float(self._r0.value)

    @r0.setter
    def r0(self, v: float):
        self._r0.value = float(v)

    @property
    def phi_a(self) -> float:
        """Acceptor quantum yield."""
        return float(self._phi_a.value)

    @phi_a.setter
    def phi_a(self, v: float):
        self._phi_a.value = float(v)

    @property
    def phi_d(self) -> float:
        """Donor quantum yield."""
        return float(self._phi_d.value)

    @phi_d.setter
    def phi_d(self, v: float):
        self._phi_d.value = float(v)

    def as_dict(self) -> dict:
        """Return the current factor values as a plain dict."""
        return {
            "gamma": self.gamma, "alpha": self.alpha, "beta": self.beta, "delta": self.delta,
            "Bg_DD": self.bg_dd, "Bg_DA": self.bg_da, "Bg_AA": self.bg_aa,
            "R0": self.r0, "PhiA": self.phi_a, "PhiD": self.phi_d,
        }


def _cell(payload, row, column, default=0.0) -> float:
    """Return a single labelled cell of a light-path matrix payload."""
    from chisurf.core.fluorescence.crosstalk import matrix_from_payload

    if not payload:
        return float(default)
    matrix, _, _ = matrix_from_payload(payload, rows=[row], columns=[column])
    return float(matrix[0, 0])


def lightpath_correction_factors(
    matrices: dict,
    donor: str,
    acceptor: str,
    green_detector: str,
    red_detector: str,
    *,
    green_laser: str | None = None,
    gG: float = 1.0,
    gR: float = 1.0,
    qy_d: float = 1.0,
    qy_a: float = 1.0,
) -> dict:
    """Compute gamma/alpha/delta from a light-path crosstalk payload.

    Reuses the standard MFD correction algebra (as in
    ``pda/nusiance.py``) on the excitation (laser×dye) and emission
    (dye×detector) matrices produced by the light-path calculator's
    ``get_crosstalk_matrices()``.

    Parameters
    ----------
    matrices : dict
        ``{"excitation": payload, "emission": payload, ...}`` with each payload
        a ``{"rows", "columns", "values"}`` matrix.
    donor, acceptor : str
        Dye labels.
    green_detector, red_detector : str
        Detector labels for the donor (green) and acceptor (red) channels.
    green_laser : str, optional
        Donor-excitation laser label. Defaults to the first excitation row.
    gG, gR : float, optional
        Green / red detection efficiencies.
    qy_d, qy_a : float, optional
        Donor / acceptor quantum yields.

    Returns
    -------
    dict
        ``{"gamma", "alpha", "delta"}``.
    """
    exc = matrices.get("excitation", {}) if isinstance(matrices, dict) else {}
    emi = matrices.get("emission", {}) if isinstance(matrices, dict) else {}
    laser = green_laser if green_laser is not None else (exc.get("rows", [None]) or [None])[0]

    c_gd = _cell(emi, donor, green_detector, 1.0)
    c_rd = _cell(emi, donor, red_detector, 0.0)
    c_ra = _cell(emi, acceptor, red_detector, 1.0)
    ex_dg = _cell(exc, laser, donor, 1.0) if laser is not None else 1.0
    ex_ag = _cell(exc, laser, acceptor, 0.0) if laser is not None else 0.0

    eps = 1e-12
    den_g = gG * c_gd * qy_d
    gamma = (gR * c_ra * qy_a) / den_g if den_g > eps else float("nan")
    den_a = gG * c_gd + gR * c_rd
    alpha = (gR * c_rd) / den_a if den_a > eps else 0.0
    delta = ex_ag / ex_dg if abs(ex_dg) > eps else 0.0
    return {"gamma": float(gamma), "alpha": float(alpha), "delta": float(delta)}


def crosstalk_matrices_from_lightpath(
    matrices: dict,
    chromophores: list[str],
    lasers: list[str],
    detectors: list[str],
    *,
    quantum_yields: dict | None = None,
    detection_efficiencies: dict | None = None,
) -> tuple:
    """Build the ``(excitation, emission)`` matrices for the general correction.

    The scalar Hellenkamp factors are only a two-colour summary; the general
    correction (:func:`chisurf.core.fluorescence.burst.es.corrected_es_general`)
    consumes the light-path matrices themselves. This assembles them, ordered, and
    folds the per-chromophore quantum yields and per-detector detection
    efficiencies into the **emission** matrix so its diagonal carries the
    detection/quantum-yield weighting that reduces to ``gamma``.

    Parameters
    ----------
    matrices : dict
        Light-path payload ``{"excitation": {...}, "emission": {...}}`` as returned
        by ``get_crosstalk_matrices()``.
    chromophores : list of str
        Chromophore (dye) labels in order (donor first, then acceptors).
    lasers : list of str
        Excitation-laser labels in order (aligned with the chromophores they
        primarily excite).
    detectors : list of str
        Detection-channel labels in order.
    quantum_yields : dict, optional
        ``{chromophore: QY}``; missing entries default to ``1.0``.
    detection_efficiencies : dict, optional
        ``{detector: g}``; missing entries default to ``1.0``.

    Returns
    -------
    excitation : numpy.ndarray
        ``(len(lasers), len(chromophores))`` excitation crosstalk matrix.
    emission : numpy.ndarray
        ``(len(chromophores), len(detectors))`` detected-brightness matrix
        (spectral overlap × quantum yield × detection efficiency).
    """
    import numpy as np

    from chisurf.core.fluorescence.crosstalk import matrix_from_payload

    exc_payload = matrices.get("excitation", {}) if isinstance(matrices, dict) else {}
    emi_payload = matrices.get("emission", {}) if isinstance(matrices, dict) else {}

    excitation, _, _ = matrix_from_payload(exc_payload, rows=lasers, columns=chromophores)
    emission, _, _ = matrix_from_payload(emi_payload, rows=chromophores, columns=detectors)

    qy = quantum_yields or {}
    det = detection_efficiencies or {}
    qy_vec = np.array([float(qy.get(c, 1.0)) for c in chromophores])
    det_vec = np.array([float(det.get(d, 1.0)) for d in detectors])
    # detected brightness = spectral overlap * QY (per chromophore) * g (per detector)
    emission = emission * qy_vec[:, None] * det_vec[None, :]
    return excitation, emission


def general_correction_from_lightpath(
    intensity,
    matrices: dict,
    chromophores: list[str],
    lasers: list[str],
    detectors: list[str],
    *,
    quantum_yields: dict | None = None,
    detection_efficiencies: dict | None = None,
    background=None,
    pairs=None,
    unmix="naive",
    ridge=0.0,
) -> dict:
    """Accurate pairwise FRET from measured intensities and the light-path matrices.

    Convenience wrapper: build the excitation/emission matrices with
    :func:`crosstalk_matrices_from_lightpath` and run the general correction
    :func:`chisurf.core.fluorescence.burst.es.corrected_es_general`. This is the
    general (any number of chromophores, arbitrary inter-channel bleed) counterpart
    of the scalar :func:`lightpath_correction_factors` + ``corrected_es`` path.

    Parameters
    ----------
    intensity : array_like
        Measured ``I[laser, detector]`` matrix (see ``corrected_es_general``).
    matrices, chromophores, lasers, detectors, quantum_yields, detection_efficiencies
        Passed to :func:`crosstalk_matrices_from_lightpath`.
    background, pairs, unmix, ridge
        Passed to ``corrected_es_general`` (``unmix="stable"`` selects the
        non-negative, ill-conditioning-robust un-mixing; ``ridge`` adds Tikhonov
        damping).

    Returns
    -------
    dict
        ``{(donor, acceptor): {"E", "fc"}}`` per pair.
    """
    from chisurf.core.fluorescence.burst.es import corrected_es_general

    excitation, emission = crosstalk_matrices_from_lightpath(
        matrices, chromophores, lasers, detectors,
        quantum_yields=quantum_yields, detection_efficiencies=detection_efficiencies,
    )
    return corrected_es_general(
        intensity, excitation, emission, background=background, pairs=pairs,
        unmix=unmix, ridge=ridge,
    )


def set_priors_from_lightpath(
    calib: CalibrationParameters,
    matrices: dict,
    donor: str,
    acceptor: str,
    green_detector: str,
    red_detector: str,
    *,
    green_laser: str | None = None,
    gG: float = 1.0,
    gR: float = 1.0,
    qy_d: float = 1.0,
    qy_a: float = 1.0,
    gamma_sigma: float = 0.1,
    alpha_sigma: float = 0.02,
    delta_sigma: float = 0.02,
    r0: float | None = None,
    r0_sigma: float = 2.0,
    seed_values: bool = True,
) -> dict:
    """Attach light-path-derived Gaussian priors to the calibration factors.

    The light-path value becomes the **prior mean** (a `NormalPrior`, or a
    `TruncatedNormalPrior` for the bounded leakage/direct-excitation factors);
    the parameters stay free and are subsequently optimized against the data.

    Parameters
    ----------
    calib : CalibrationParameters
        The group whose parameters receive the priors.
    matrices : dict
        Light-path crosstalk matrices (see
        :func:`lightpath_correction_factors`).
    donor, acceptor, green_detector, red_detector, green_laser, gG, gR, qy_d, qy_a
        Forwarded to :func:`lightpath_correction_factors`.
    gamma_sigma, alpha_sigma, delta_sigma : float, optional
        Prior standard deviations (the light-path model uncertainty).
    r0 : float, optional
        Förster radius prior mean (Å). If given, an `R0` prior is attached.
    r0_sigma : float, optional
        Förster-radius prior width.
    seed_values : bool, optional
        If True (default), also set each parameter's current *value* to the
        prior mean, so the optimizer starts at the light-path estimate.

    Returns
    -------
    dict
        The computed ``{"gamma", "alpha", "delta"}`` light-path factors.
    """
    factors = lightpath_correction_factors(
        matrices, donor, acceptor, green_detector, red_detector,
        green_laser=green_laser, gG=gG, gR=gR, qy_d=qy_d, qy_a=qy_a,
    )
    calib._gamma.prior = NormalPrior(mu=factors["gamma"], sigma=gamma_sigma)
    calib._alpha.prior = TruncatedNormalPrior(mu=factors["alpha"], sigma=alpha_sigma, lb=0.0, ub=1.0)
    calib._delta.prior = TruncatedNormalPrior(mu=factors["delta"], sigma=delta_sigma, lb=0.0, ub=1.0)
    if r0 is not None:
        calib._r0.prior = NormalPrior(mu=float(r0), sigma=r0_sigma)
    if seed_values:
        calib.gamma = factors["gamma"]
        calib.alpha = factors["alpha"]
        calib.delta = factors["delta"]
        if r0 is not None:
            calib.r0 = float(r0)
    return factors


def global_es_correction(i_dd, i_da, i_aa, labels, *, alpha=0.0, delta=0.0) -> dict:
    """Recover gamma (and beta) from an E-S population plot (Lee 2005 / Hellenkamp 2018).

    After removing donor leakage (``alpha``) and direct acceptor excitation
    (``delta``), the apparent stoichiometry and proximity ratio of a doubly
    labelled sample obey the linear relation ``1/S = Omega + Sigma * E`` across
    FRET populations; the detection factor is
    ``gamma = (Omega - 1) / (Omega + Sigma - 1)`` and ``beta = Omega + Sigma - 1``.

    Parameters
    ----------
    i_dd, i_da, i_aa : array_like
        Per-burst ``I_DD`` / ``I_DA`` / ``I_AA`` counts (donor|donor,
        acceptor|donor, acceptor|acceptor excitation).
    labels : array_like
        Population label per burst (>= 2 distinct populations required).
    alpha, delta : float, optional
        Donor-leakage (α) and direct-excitation (δ) coefficients (e.g. from the
        light-path prior or donor-only/acceptor-only samples).

    Returns
    -------
    dict
        ``{"gamma", "beta", "Omega", "Sigma"}`` (Hellenkamp β = Ω+Σ−1).
    """
    g = np.asarray(i_dd, dtype=float)
    r = np.asarray(i_da, dtype=float)
    y = np.asarray(i_aa, dtype=float)
    labels = np.asarray(labels)

    f_da = r - alpha * g - delta * y  # leakage + direct-excitation corrected
    gf = g + f_da
    with np.errstate(divide="ignore", invalid="ignore"):
        e_pr = np.where(gf != 0, f_da / gf, 0.0)
        s_pr = np.where((gf + y) != 0, gf / (gf + y), 0.0)

    uniq = [u for u in np.unique(labels)]
    if len(uniq) < 2:
        raise ValueError("global_es_correction needs >= 2 populations")
    e_mean = np.array([e_pr[labels == u].mean() for u in uniq])
    inv_s = np.array([1.0 / s_pr[labels == u].mean() for u in uniq])

    # Linear fit 1/S = Omega + Sigma * E.
    sigma, omega = np.polyfit(e_mean, inv_s, 1)
    denom = omega + sigma - 1.0
    gamma = (omega - 1.0) / denom if abs(denom) > 1e-12 else float("nan")
    beta = denom
    return {"gamma": float(gamma), "beta": float(beta),
            "Omega": float(omega), "Sigma": float(sigma)}


def refine_calibration(calib: CalibrationParameters, i_dd, i_da, i_aa, labels,
                       *, data_sigma: float | None = None, n_bootstrap: int = 60,
                       seed: int = 0) -> dict:
    """Prior-regularized (Bayesian) refinement of ``gamma`` against E-S data.

    The data estimate of ``gamma`` comes from :func:`global_es_correction` (the
    E-S population linear fit — the only quantity the E-S data identifies); its
    uncertainty is estimated by bootstrapping bursts. The **posterior** ``gamma``
    is the precision-weighted combination of that data estimate and the
    (light-path) Gaussian prior on ``gamma``:

        gamma_post = (gamma_data/sigma_data^2 + mu_prior/sigma_prior^2)
                     / (1/sigma_data^2 + 1/sigma_prior^2)

    so strong data (many bursts) → posterior ≈ data; weak data → posterior ≈
    the light-path prior. ``alpha``/``delta`` are not identifiable from a pure
    FRET-population E-S set (they need donor-only/acceptor-only samples), so they
    keep their prior/current values. The result is written back into ``calib``.

    Parameters
    ----------
    calib : CalibrationParameters
        Group refined in place; its ``alpha``/``delta`` are used for the leakage/
        direct-excitation correction and its ``gamma`` prior regularizes the fit.
    i_dd, i_da, i_aa : array_like
        Per-burst ``I_DD`` / ``I_DA`` / ``I_AA`` counts.
    labels : array_like
        Population label per burst (>= 2 FRET populations).
    data_sigma : float, optional
        Uncertainty of the data ``gamma`` estimate; bootstrapped if omitted.
    n_bootstrap : int, optional
        Bootstrap resamples used to estimate ``data_sigma``.
    seed : int, optional
        Bootstrap RNG seed.

    Returns
    -------
    dict
        ``{**calib.as_dict(), "gamma_data", "gamma_prior", "data_sigma"}``.
    """
    from chisurf.core.fitting.priors import as_prior

    g = np.asarray(i_dd, dtype=float)
    r = np.asarray(i_da, dtype=float)
    y = np.asarray(i_aa, dtype=float)
    labels = np.asarray(labels)

    est = global_es_correction(g, r, y, labels, alpha=calib.alpha, delta=calib.delta)
    gamma_data = est["gamma"]
    # beta (excitation-flux ratio) is also identified by the E-S fit.
    if np.isfinite(est["beta"]) and est["beta"] > 0:
        calib.beta = float(est["beta"])

    if data_sigma is None:
        rng = np.random.default_rng(seed)
        n = labels.size
        boot = []
        for _ in range(int(n_bootstrap)):
            idx = rng.integers(0, n, n)
            try:
                gb = global_es_correction(
                    g[idx], r[idx], y[idx], labels[idx], alpha=calib.alpha, delta=calib.delta
                )["gamma"]
                if np.isfinite(gb):
                    boot.append(gb)
            except Exception:
                continue
        data_sigma = float(np.std(boot)) if len(boot) > 2 else abs(gamma_data) * 0.1
    data_sigma = max(float(data_sigma), 1e-6)

    prior = as_prior(calib._gamma.prior)
    gamma_prior = float(getattr(prior, "mu", gamma_data))
    if prior is not None and hasattr(prior, "sigma"):
        w_d = 1.0 / data_sigma ** 2
        w_p = 1.0 / float(prior.sigma) ** 2
        gamma_post = (gamma_data * w_d + gamma_prior * w_p) / (w_d + w_p)
    else:
        gamma_post = gamma_data

    calib.gamma = float(np.clip(gamma_post, 0.05, 20.0))
    out = calib.as_dict()
    out.update({"gamma_data": gamma_data, "gamma_prior": gamma_prior, "data_sigma": data_sigma})
    return out


class CalibrationFit:
    """Dataset-free pseudo-fit exposing a calibration group for global analysis.

    Wrapping a :class:`CalibrationParameters` group as an object with the
    minimal fit contract (``model`` + ``unique_identifier`` + ``name``, no
    dataset and no optimiser contribution) lets its factors appear as
    session-wide **link targets**: any fit's correction parameter can link to,
    e.g., the calibration ``gamma`` so one calibration is shared across many
    datasets. Register it with :func:`register_calibration`.
    """

    def __init__(self, calibration: CalibrationParameters, name: str = "Calibration"):
        """Wrap a calibration group as a link-target pseudo-fit.

        Parameters
        ----------
        calibration : CalibrationParameters
            The parameter group exposed as this pseudo-fit's ``model``.
        name : str
            Display name in the fit/parameter-link lists.
        """
        import uuid

        self.model = calibration
        self.name = name
        self.data = None
        uid = getattr(calibration, "unique_identifier", None)
        self.unique_identifier = str(uid) if uid else str(uuid.uuid4())

    @property
    def calibration(self) -> CalibrationParameters:
        """The wrapped :class:`CalibrationParameters` group."""
        return self.model


def register_calibration(calibration, name: str = "Calibration") -> CalibrationFit:
    """Register a calibration group as a session-wide link target.

    Adds a :class:`CalibrationFit` to ``chisurf.fits`` (and the project
    registry) so its factors are discoverable by the parameter-link UI and by
    the fitting client, enabling cross-dataset global analysis.

    Parameters
    ----------
    calibration : CalibrationParameters or CalibrationFit
        The calibration group (or an already-wrapped pseudo-fit).
    name : str
        Display name.

    Returns
    -------
    CalibrationFit
        The registered pseudo-fit.
    """
    import chisurf as cs

    fit = calibration if isinstance(calibration, CalibrationFit) else CalibrationFit(calibration, name)
    if fit not in cs.fits:
        cs.fits.append(fit)
    try:
        from chisurf.core.project import registry

        registry.register_fit(str(fit.unique_identifier), fit)
    except Exception:
        pass
    return fit


def unregister_calibration(fit: CalibrationFit) -> None:
    """Remove a registered calibration pseudo-fit from the session.

    Parameters
    ----------
    fit : CalibrationFit
        The pseudo-fit returned by :func:`register_calibration`.
    """
    import chisurf as cs

    if fit in cs.fits:
        cs.fits.remove(fit)
    try:
        from chisurf.core.project import registry

        registry.unregister_fit(str(fit.unique_identifier))
    except Exception:
        pass


def link_to_calibration(parameter, calibration, factor: str) -> None:
    """Link a fitting parameter to a shared calibration factor.

    After linking, ``parameter`` reads its value from the calibration factor
    (chinet-port identity), so refining the calibration once updates every
    linked fit — the mechanism behind calibration-shared global analysis.

    Parameters
    ----------
    parameter : FittingParameter
        The consumer parameter (e.g. a fit's ``gamma``).
    calibration : CalibrationParameters or CalibrationFit
        The shared calibration group.
    factor : str
        Name of the calibration factor to link to (e.g. ``"gamma"``).
    """
    group = calibration.model if isinstance(calibration, CalibrationFit) else calibration
    parameter.link = group.parameters_all_dict[factor]


def calibration_to_ndx_constants(calibration) -> dict:
    """Map calibration factors onto ndxplorer's MFD constant names.

    ndxplorer's derived-FRET equations use ``gG/gR``, ``alpha`` (leakage),
    ``beta`` (direct excitation), ``Bg``/``Br``/``By``, ``PhiA``/``PhiD`` and
    ``forster_radius``; its effective detection factor is
    ``gamma = (PhiA/PhiD) / (gG/gR)``. This inverts that so the ndx effective
    gamma equals the calibration ``gamma``:

        gG/gR = (PhiA/PhiD) / gamma

    Parameters
    ----------
    calibration : CalibrationParameters or CalibrationFit
        Source of the (posterior) calibration factors.

    Returns
    -------
    dict
        ndxplorer constant name → value, ready to merge into ``ndx.constants``.
    """
    calib = calibration.model if isinstance(calibration, CalibrationFit) else calibration
    phi_a = float(calib.phi_a)
    phi_d = float(calib.phi_d)
    gamma = float(calib.gamma)
    gg_gr = (phi_a / phi_d) / gamma if gamma != 0 else 1.0
    # ndxplorer's constant it calls "beta" is the direct-excitation coefficient
    # (Hellenkamp delta); its equations have no slot for the excitation-flux ratio.
    return {
        "gG/gR": gg_gr,
        "alpha": float(calib.alpha),
        "beta": float(calib.delta),
        "Bg": float(calib.bg_dd),
        "Br": float(calib.bg_da),
        "By": float(calib.bg_aa),
        "PhiA": phi_a,
        "PhiD": phi_d,
        "forster_radius": float(calib.r0),
    }


def leakage_from_donor_only(i_dd, i_da, *, bg_dd=0.0, bg_da=0.0) -> float:
    """Estimate donor leakage ``alpha`` from a donor-only reference sample.

    For a donor-only sample the acceptor (``i_da``) channel under donor
    excitation contains only donor spectral bleed-through, so

        alpha = <i_da - Bg_da> / <i_dd - Bg_dd>

    (Hellenkamp 2018). Averages are taken over the donor-only bursts.

    Parameters
    ----------
    i_dd, i_da : array_like
        Per-burst donor and acceptor counts under donor excitation for the
        **donor-only** population.
    bg_dd, bg_da : float, optional
        Channel backgrounds.

    Returns
    -------
    float
        Donor leakage ``alpha`` (α).
    """
    f_dd = np.asarray(i_dd, dtype=float) - bg_dd
    f_da = np.asarray(i_da, dtype=float) - bg_da
    denom = float(np.mean(f_dd))
    return float(np.mean(f_da) / denom) if denom != 0 else 0.0


def direct_excitation_from_acceptor_only(i_da, i_aa, i_dd=None, *, alpha=0.0,
                                         bg_dd=0.0, bg_da=0.0, bg_aa=0.0) -> float:
    """Estimate direct excitation ``delta`` from an acceptor-only reference sample.

    For an acceptor-only sample the acceptor (``i_da``) channel under donor
    excitation contains only directly-excited acceptor emission, so

        delta = <i_da - Bg_da - alpha*(i_dd - Bg_dd)> / <i_aa - Bg_aa>

    (Hellenkamp 2018). The optional ``alpha`` term removes any residual leakage.

    Parameters
    ----------
    i_da, i_aa : array_like
        Per-burst acceptor counts under donor and acceptor excitation for the
        **acceptor-only** population.
    i_dd : array_like, optional
        Donor-channel counts (for the residual-leakage correction).
    alpha : float, optional
        Donor leakage (from :func:`leakage_from_donor_only`).
    bg_dd, bg_da, bg_aa : float, optional
        Channel backgrounds.

    Returns
    -------
    float
        Direct acceptor excitation ``delta`` (δ).
    """
    f_da = np.asarray(i_da, dtype=float) - bg_da
    f_aa = np.asarray(i_aa, dtype=float) - bg_aa
    if i_dd is not None and alpha:
        f_da = f_da - alpha * (np.asarray(i_dd, dtype=float) - bg_dd)
    denom = float(np.mean(f_aa))
    return float(np.mean(f_da) / denom) if denom != 0 else 0.0


def calibrate_from_samples(calib: CalibrationParameters, fret, *, donor_only=None,
                           acceptor_only=None, refine: bool = True) -> dict:
    """Full data-driven calibration from FRET + reference samples (Hellenkamp).

    The complete layered procedure:

    1. ``alpha`` from the **donor-only** sample (:func:`leakage_from_donor_only`),
    2. ``delta`` from the **acceptor-only** sample
       (:func:`direct_excitation_from_acceptor_only`, using the estimated α),
    3. ``gamma``/``beta`` from the multi-population FRET E-S fit
       (:func:`global_es_correction`) and, if ``refine``, the prior-regularized
       posterior (:func:`refine_calibration`).

    Each provided estimate is written into ``calib``. When a reference sample is
    omitted the corresponding factor keeps its current value (e.g. the light-path
    prior mean).

    Parameters
    ----------
    calib : CalibrationParameters
        Calibration refined in place (seed its priors first, e.g. via
        :func:`set_priors_from_lightpath`).
    fret : tuple
        ``(i_dd, i_da, i_aa, labels)`` for the FRET populations (>= 2).
    donor_only : tuple, optional
        ``(i_dd, i_da)`` for the donor-only sample.
    acceptor_only : tuple, optional
        ``(i_da, i_aa[, i_dd])`` for the acceptor-only sample.
    refine : bool, optional
        If True, run the prior-regularized ``gamma`` refinement.

    Returns
    -------
    dict
        The calibration values plus refinement diagnostics.
    """
    if donor_only is not None:
        calib.alpha = leakage_from_donor_only(
            *donor_only[:2], bg_dd=calib.bg_dd, bg_da=calib.bg_da
        )
    if acceptor_only is not None:
        i_da_ao = acceptor_only[0]
        i_aa_ao = acceptor_only[1]
        i_dd_ao = acceptor_only[2] if len(acceptor_only) > 2 else None
        calib.delta = direct_excitation_from_acceptor_only(
            i_da_ao, i_aa_ao, i_dd_ao, alpha=calib.alpha,
            bg_dd=calib.bg_dd, bg_da=calib.bg_da, bg_aa=calib.bg_aa,
        )

    i_dd, i_da, i_aa, labels = fret
    if refine:
        return refine_calibration(calib, i_dd, i_da, i_aa, labels)
    est = global_es_correction(i_dd, i_da, i_aa, labels, alpha=calib.alpha, delta=calib.delta)
    if np.isfinite(est["gamma"]):
        calib.gamma = float(np.clip(est["gamma"], 0.05, 20.0))
    if np.isfinite(est["beta"]) and est["beta"] > 0:
        calib.beta = float(est["beta"])
    out = calib.as_dict()
    out.update(est)
    return out


def rcm_from_dye_solutions(
    donor_sample_rates,
    acceptor_sample_rates,
    absorbance_ratio: float,
    detector_assignment,
    anisotropy=(0.0, 0.0),
):
    """Routing/detection-correction matrix (RCM) from dye-solution measurements.

    Port of Fretica ``FRCMCalibrationFromDyeSolutions``.  From per-channel count
    rates of a **donor-only** and an **acceptor-only** dye solution, the relative
    absorbance ``AbsorbanceA / AbsorbanceD`` and the detector layout, it solves
    for the matrix that corrects measured channel rates for detection
    efficiencies and cross-talk between the spectral (and, with a polarising
    beam-splitter, polarisation) channels — a per-setup calibration that removes
    the need to hand-enter correction factors.

    Parameters
    ----------
    donor_sample_rates, acceptor_sample_rates : array_like
        Background-corrected count rate in every channel for the donor-only and
        acceptor-only dye solution (length = number of channels).
    absorbance_ratio : float
        ``AbsorbanceA / AbsorbanceD`` of the two calibration solutions (relative
        excitation/concentration).
    detector_assignment : sequence of (str, str)
        Per channel ``(species, polarisation)`` with ``species in {"A", "D"}``
        and ``polarisation in {"P", "S"}`` (polarisation ignored for a 2-channel
        setup).  Must have an equal number of A and D channels (1 or 2 each).
    anisotropy : (float, float)
        ``(r_donor, r_acceptor)`` steady-state anisotropies (used only for a
        4-channel polarising-beam-splitter setup; ``(0, 0)`` for a 50/50 split).

    Returns
    -------
    numpy.ndarray
        The ``nchtot x nchtot`` correction matrix (identity on unused channels,
        normalised so its first ordered element is 1).
    """
    donor_sample_rates = np.asarray(donor_sample_rates, dtype=float)
    acceptor_sample_rates = np.asarray(acceptor_sample_rates, dtype=float)
    nchtot = len(detector_assignment)
    if donor_sample_rates.size != nchtot or acceptor_sample_rates.size != nchtot:
        raise ValueError("rate vectors must match the number of detector channels")

    species = [d[0] for d in detector_assignment]
    pol = [d[1] if len(d) > 1 else None for d in detector_assignment]
    nchA = species.count("A")
    nchD = species.count("D")
    if nchA != nchD or nchA == 0 or nchA > 2:
        raise ValueError("need an equal number of A and D channels (1 or 2 each)")
    nch = nchA + nchD
    alpha = float(absorbance_ratio)
    rd, ra = anisotropy

    a_idx = [i for i, s in enumerate(species) if s == "A"]
    d_idx = [i for i, s in enumerate(species) if s == "D"]

    if nch == 2:
        order = [a_idx[0], d_idx[0]]
        pa = pd = 0.0
    else:
        def _find(sp, pl):
            return [i for i, d in enumerate(detector_assignment) if d == (sp, pl)]
        polarized = all(len(_find(sp, pl)) == 1
                        for sp, pl in [("A", "P"), ("D", "P"), ("A", "S"), ("D", "S")])
        if polarized:
            order = [_find("A", "P")[0], _find("D", "P")[0],
                     _find("A", "S")[0], _find("D", "S")[0]]
            pa = (3.0 * ra) / (2.0 + ra)
            pd = (3.0 * rd) / (2.0 + rd)
        else:  # 50/50 beam splitter, polarisation not resolved
            order = [a_idx[0], d_idx[0], a_idx[1], d_idx[1]]
            pa = pd = 0.0

    nd = donor_sample_rates[order]
    na = acceptor_sample_rates[order]

    if nch == 2:
        amat = np.array([[na[0], alpha * nd[0]],
                         [na[1], alpha * nd[1]]], dtype=float)
    else:
        amat = np.array([
            [na[0] / (1 + pa), alpha * nd[0] / (1 + pd), 0.0, 0.0],
            [na[1] / (1 + pa), alpha * nd[1] / (1 + pd), 0.0, 0.0],
            [0.0, 0.0, na[2] / (1 - pa), alpha * nd[2] / (1 - pd)],
            [0.0, 0.0, na[3] / (1 - pa), alpha * nd[3] / (1 - pd)],
        ], dtype=float)

    rcm_sub = np.linalg.inv(amat)
    rcm_sub /= rcm_sub[0, 0]

    # Scatter the nch x nch block back into full channel space (identity elsewhere).
    perm = np.zeros((nch, nchtot), dtype=float)
    for i, o in enumerate(order):
        perm[i, o] = 1.0
    rcm = perm.T @ rcm_sub @ perm
    for i in range(nchtot):
        if i not in order:
            rcm[i, i] = 1.0
    return rcm
