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

The arithmetic -- the reference-sample estimators, the E-S fit, the posterior
of :func:`refine_calibration`, the light-path factor algebra -- is tttrlib's
(``tttrlib.global_es_correction``, ``tttrlib.refine_gamma``,
``tttrlib.lightpath_correction_factors``, ...), shared with ndXplorer; this
module holds the factors as fitting parameters and reads the light-path
payloads.
"""

from __future__ import annotations

import numpy as np
import tttrlib

from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fitting.priors import NormalPrior, TruncatedNormalPrior
from chisurf.core.support.labels import to_rich

__all__ = [
    "CalibrationParameters",
    "lightpath_correction_factors",
    "crosstalk_matrices_from_lightpath",
    "general_correction_from_lightpath",
    "set_priors_from_lightpath",
    "refine_calibration",
    "CalibrationFit",
    "register_calibration",
    "unregister_calibration",
    "link_to_calibration",
    "calibration_to_setup",
    "calibration_from_setup",
    "setup_calibration_values",
    "setup_calibration_uncertainties",
    "SETUP_CALIBRATION_KEYS",
    "SETUP_CALIBRATION_FIELD",
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

        def factor(name, label, **kwargs):
            """One calibration factor: a programmatic name and a typeset label.

            The ``name`` is what code, links and the ndxplorer mapping key on and
            must not change; the ``label`` is the plain spelling of what the
            reader should see, typeset by :func:`chisurf.core.support.labels.to_rich` so
            a parameter table shows γ and Φ<sub>A</sub> rather than ``gamma``
            and ``PhiA``.
            """
            return FittingParameter(name=name, label_text=to_rich(label), bounds_on=True, **kwargs)

        self._gamma = factor("gamma", "gamma", value=1.0, lb=0.05, ub=20.0)
        self._alpha = factor("alpha", "alpha", value=0.0, lb=0.0, ub=1.0)
        self._beta = factor("beta", "beta", value=1.0, lb=0.01, ub=100.0)
        self._delta = factor("delta", "delta", value=0.0, lb=0.0, ub=1.0)
        self._bg_dd = factor("Bg_DD", "Bg_DD", value=0.0, lb=0.0, ub=1e6)
        self._bg_da = factor("Bg_DA", "Bg_DA", value=0.0, lb=0.0, ub=1e6)
        self._bg_aa = factor("Bg_AA", "Bg_AA", value=0.0, lb=0.0, ub=1e6)
        self._r0 = factor("R0", "R_0", value=52.0, lb=1.0, ub=200.0)
        self._phi_a = factor("PhiA", "Phi_A", value=1.0, lb=0.0, ub=1.0)
        self._phi_d = factor("PhiD", "Phi_D", value=1.0, lb=0.0, ub=1.0)
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
            "gamma": self.gamma,
            "alpha": self.alpha,
            "beta": self.beta,
            "delta": self.delta,
            "Bg_DD": self.bg_dd,
            "Bg_DA": self.bg_da,
            "Bg_AA": self.bg_aa,
            "R0": self.r0,
            "PhiA": self.phi_a,
            "PhiD": self.phi_d,
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
    red_laser: str | None = None,
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
    red_laser : str, optional
        Acceptor-excitation (ALEX/PIE) laser label. Defaults to the first
        excitation row that is not ``green_laser``.
    gG, gR : float, optional
        Green / red detection efficiencies.
    qy_d, qy_a : float, optional
        Donor / acceptor quantum yields.

    Returns
    -------
    dict
        ``{"gamma", "alpha", "delta"}`` in the **Hellenkamp 2018** convention the
        rest of this module and ``tttrlib.corrected_es``
        consume — in particular ``alpha = I_DA/I_DD = (gR·cRD)/(gG·cGD)``, the donor
        leakage *relative to the green channel*, matching
        ``tttrlib.leakage_from_donor_only``. This is **not** the legacy MFD fraction
        ``R_D0/(G_D0 + R_D0)`` of ``pda/nusiance.py``. Likewise
        ``delta = I_DA/I_AA = ex[green, A]/ex[red, A]``, the direct acceptor
        excitation *relative to the acceptor-excitation channel*, matching
        ``tttrlib.direct_excitation_from_acceptor_only`` — not the ratio to the
        donor's own excitation, which differs from it by ``beta``. Without an
        acceptor-excitation laser there is no ``I_AA`` to subtract and ``delta``
        is 0.
    """
    exc = matrices.get("excitation", {}) if isinstance(matrices, dict) else {}
    emi = matrices.get("emission", {}) if isinstance(matrices, dict) else {}
    lasers = list(exc.get("rows", []) or [])
    laser = green_laser if green_laser is not None else (lasers[0] if lasers else None)
    if red_laser is None:
        red_laser = next((row for row in lasers if row != laser), None)

    c_gd = _cell(emi, donor, green_detector, 1.0)
    c_rd = _cell(emi, donor, red_detector, 0.0)
    c_ra = _cell(emi, acceptor, red_detector, 1.0)
    ex_ag = _cell(exc, laser, acceptor, 0.0) if laser is not None else 0.0
    ex_ar = _cell(exc, red_laser, acceptor, 0.0) if red_laser is not None else 0.0
    # the algebra is tttrlib's (lightpath_correction_factors); this reads the cells
    return tttrlib.lightpath_correction_factors(
        c_gd, c_rd, c_ra, ex_ag, ex_ar, gG=gG, gR=gR, qy_d=qy_d, qy_a=qy_a
    )


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
    correction (``tttrlib.corrected_es_general``)
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
    ``tttrlib.corrected_es_general``. This is the
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
    excitation, emission = crosstalk_matrices_from_lightpath(
        matrices,
        chromophores,
        lasers,
        detectors,
        quantum_yields=quantum_yields,
        detection_efficiencies=detection_efficiencies,
    )
    return tttrlib.corrected_es_general(
        intensity,
        excitation,
        emission,
        background=background,
        pairs=pairs,
        unmix=unmix,
        ridge=ridge,
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
    red_laser: str | None = None,
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
    donor, acceptor, green_detector, red_detector, green_laser, red_laser, gG, gR, qy_d, qy_a
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
        matrices,
        donor,
        acceptor,
        green_detector,
        red_detector,
        green_laser=green_laser,
        red_laser=red_laser,
        gG=gG,
        gR=gR,
        qy_d=qy_d,
        qy_a=qy_a,
    )
    calib._gamma.prior = NormalPrior(mu=factors["gamma"], sigma=gamma_sigma)
    calib._alpha.prior = TruncatedNormalPrior(
        mu=factors["alpha"], sigma=alpha_sigma, lb=0.0, ub=1.0
    )
    calib._delta.prior = TruncatedNormalPrior(
        mu=factors["delta"], sigma=delta_sigma, lb=0.0, ub=1.0
    )
    if r0 is not None:
        calib._r0.prior = NormalPrior(mu=float(r0), sigma=r0_sigma)
    if seed_values:
        calib.gamma = factors["gamma"]
        calib.alpha = factors["alpha"]
        calib.delta = factors["delta"]
        if r0 is not None:
            calib.r0 = float(r0)
    return factors


def refine_calibration(
    calib: CalibrationParameters,
    i_dd,
    i_da,
    i_aa,
    labels,
    *,
    data_sigma: float | None = None,
    n_bootstrap: int = 60,
    seed: int = 0,
) -> dict:
    """Prior-regularized (Bayesian) refinement of ``gamma`` against E-S data.

    The data estimate of ``gamma`` comes from ``tttrlib.global_es_correction`` (the
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
        ``{**calib.as_dict(), "gamma_data", "gamma_prior", "data_sigma",
        "gamma_updated"}``. When the E-S fit does not identify a finite
        ``gamma`` (a degenerate population, e.g. one without signal),
        ``gamma_data``/``data_sigma`` are ``NaN``, ``gamma_updated`` is
        ``False`` and ``calib.gamma`` keeps its current (prior) value.
    """
    from chisurf.core.fitting.priors import as_prior

    labels = np.asarray(labels)
    prior = as_prior(calib._gamma.prior)
    has_prior = prior is not None and hasattr(prior, "sigma")
    # the resampling draws numpy's generator, as this function always did
    rng = np.random.default_rng(seed)
    n = labels.size
    indices = (
        np.stack([rng.integers(0, n, n) for _ in range(int(n_bootstrap))])
        if data_sigma is None and n_bootstrap
        else None
    )
    est = tttrlib.refine_gamma(
        i_dd,
        i_da,
        i_aa,
        labels,
        alpha=calib.alpha,
        delta=calib.delta,
        prior=(float(prior.mu), float(prior.sigma)) if has_prior else None,
        data_sigma=data_sigma,
        n_bootstrap=int(n_bootstrap) if indices is not None else 0,
        seed=seed,
        indices=indices,
    )
    gamma_data = est["gamma_data"]
    # beta (excitation-flux ratio) is also identified by the E-S fit.
    if np.isfinite(est["beta"]) and est["beta"] > 0:
        calib.beta = float(est["beta"])
    gamma_prior = float(getattr(prior, "mu", gamma_data))
    data_sigma = est["data_sigma"]
    gamma_post = est["gamma_posterior"]

    gamma_updated = bool(np.isfinite(gamma_post))
    if gamma_updated:
        calib.gamma = float(np.clip(gamma_post, 0.05, 20.0))
    out = calib.as_dict()
    out.update(
        {
            "gamma_data": gamma_data,
            "gamma_prior": gamma_prior,
            "data_sigma": data_sigma,
            "gamma_updated": gamma_updated,
        }
    )
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

    fit = (
        calibration
        if isinstance(calibration, CalibrationFit)
        else CalibrationFit(calibration, name)
    )
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


#: The calibration factors stored on a detector setup, and the group attribute
#: each maps to. Deliberately a plain ``{name: float}`` payload rather than a
#: pickled parameter group: it is written to the setups file and read by tools
#: that have no reason to import the fitting stack.
SETUP_CALIBRATION_KEYS = (
    "gamma",
    "alpha",
    "beta",
    "delta",
    "bg_dd",
    "bg_da",
    "bg_aa",
    "r0",
    "phi_a",
    "phi_d",
)

#: Key under which the calibration payload lives inside a detector-setup dict.
SETUP_CALIBRATION_FIELD = "fret_calibration"


def calibration_to_setup(calibration, *, uncertainties: dict | None = None) -> dict:
    """Reduce a calibration to the payload stored on a detector setup.

    A correction factor is a property of the *instrument*, not of one burst
    file: γ is set by the detection efficiencies and quantum yields, α by the
    filters, δ by the excitation. Determining it once and hanging it on the
    detector setup is what lets every other tool that already picks a setup —
    burst analysis, PDA, the filter calculator — start from a measured
    calibration instead of typed-in defaults.

    Parameters
    ----------
    calibration : CalibrationParameters or CalibrationFit
        The calibration to store.
    uncertainties : dict, optional
        ``{factor: sigma}`` as returned by the automatic calibration; kept
        alongside the values so a consumer can weight or display them.

    Returns
    -------
    dict
        ``{"values": {...}, "uncertainties": {...}}``, JSON-serializable.

    See Also
    --------
    calibration_from_setup : the inverse.
    """
    calib = calibration.model if isinstance(calibration, CalibrationFit) else calibration
    values = {key: float(getattr(calib, key)) for key in SETUP_CALIBRATION_KEYS}
    payload: dict = {"values": values}
    if uncertainties:
        payload["uncertainties"] = {
            str(k): float(v)
            for k, v in dict(uncertainties).items()
            if v is not None and np.isfinite(float(v))
        }
    return payload


def calibration_from_setup(setup: dict | None, calib=None):
    """Read a stored calibration back out of a detector-setup dict.

    Parameters
    ----------
    setup : dict or None
        A detector setup as stored in the setups file. A setup without a stored
        calibration (the normal case for a fresh setup) yields the defaults.
    calib : CalibrationParameters, optional
        Group to fill in place; a fresh one is created when omitted.

    Returns
    -------
    CalibrationParameters
        The calibration group, unchanged where the setup says nothing.
    """
    calib = calib if calib is not None else CalibrationParameters()
    payload = (setup or {}).get(SETUP_CALIBRATION_FIELD) or {}
    values = payload.get("values") if isinstance(payload, dict) else None
    if not isinstance(values, dict):
        return calib
    for key in SETUP_CALIBRATION_KEYS:
        value = values.get(key)
        if value is None:
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            setattr(calib, key, value)
    return calib


def setup_calibration_values(setup: dict | None) -> dict:
    """Flat ``{name: value}`` seed for a tool that has a detector setup in hand.

    :func:`calibration_from_setup` is the right reader for anything that owns a
    :class:`CalibrationParameters` group. Most consumers do not: the filter
    calculator, the FRET-species editor and the burst tools each keep plain
    scalar fields, and only want to *start* from the measured instrument values
    instead of the typed-in defaults. This is that reader.

    The Förster radius is returned under **both** spellings — ``r0`` as stored,
    and ``forster_radius`` as almost every GUI field is named — so a caller can
    seed by attribute name without a lookup table of its own.

    Legacy ``"calibration"`` / ``"crosstalk"`` dicts on the setup are read too
    and may carry keys the calibration proper has no notion of (``g_factor``,
    ``l1``, ``l2``, ``period_ns``); the canonical field wins where both speak.

    Parameters
    ----------
    setup : dict or None
        A detector setup as stored in the setups file.

    Returns
    -------
    dict
        Possibly empty mapping of factor name to float. Non-finite and
        unparsable entries are dropped rather than propagated into a GUI field.
    """
    seed: dict[str, float] = {}

    def take(source) -> None:
        if not isinstance(source, dict):
            return
        for key, value in source.items():
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                seed[str(key)] = value

    setup = setup or {}
    take(setup.get("calibration"))
    take(setup.get("crosstalk"))
    payload = setup.get(SETUP_CALIBRATION_FIELD)
    if isinstance(payload, dict):
        take(payload.get("values"))
    if "r0" in seed:
        seed["forster_radius"] = seed["r0"]
    elif "forster_radius" in seed:
        seed["r0"] = seed["forster_radius"]
    return seed


def setup_calibration_uncertainties(setup: dict | None) -> dict:
    """Return the stored ``{factor: sigma}`` of a setup's calibration, if any.

    Parameters
    ----------
    setup : dict or None
        A detector setup as stored in the setups file.

    Returns
    -------
    dict
        Possibly empty mapping of factor name to standard deviation.
    """
    payload = (setup or {}).get(SETUP_CALIBRATION_FIELD) or {}
    found = payload.get("uncertainties") if isinstance(payload, dict) else None
    return dict(found) if isinstance(found, dict) else {}


def calibrate_from_samples(
    calib: CalibrationParameters, fret, *, donor_only=None, acceptor_only=None, refine: bool = True
) -> dict:
    """Full data-driven calibration from FRET + reference samples (Hellenkamp).

    The complete layered procedure:

    1. ``alpha`` from the **donor-only** sample (``tttrlib.leakage_from_donor_only``),
    2. ``delta`` from the **acceptor-only** sample
       (``tttrlib.direct_excitation_from_acceptor_only``, using the estimated α),
    3. ``gamma``/``beta`` from the multi-population FRET E-S fit
       (``tttrlib.global_es_correction``) and, if ``refine``, the prior-regularized
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
        calib.alpha = tttrlib.leakage_from_donor_only(
            *donor_only[:2], bg_dd=calib.bg_dd, bg_da=calib.bg_da
        )
    if acceptor_only is not None:
        i_da_ao = acceptor_only[0]
        i_aa_ao = acceptor_only[1]
        i_dd_ao = acceptor_only[2] if len(acceptor_only) > 2 else None
        calib.delta = tttrlib.direct_excitation_from_acceptor_only(
            i_da_ao,
            i_aa_ao,
            i_dd_ao,
            alpha=calib.alpha,
            bg_dd=calib.bg_dd,
            bg_da=calib.bg_da,
            bg_aa=calib.bg_aa,
        )

    i_dd, i_da, i_aa, labels = fret
    if refine:
        return refine_calibration(calib, i_dd, i_da, i_aa, labels)
    est = tttrlib.global_es_correction(
        i_dd, i_da, i_aa, labels, alpha=calib.alpha, delta=calib.delta
    )
    if np.isfinite(est["gamma"]):
        calib.gamma = float(np.clip(est["gamma"], 0.05, 20.0))
    if np.isfinite(est["beta"]) and est["beta"] > 0:
        calib.beta = float(est["beta"])
    out = calib.as_dict()
    out.update(est)
    return out
