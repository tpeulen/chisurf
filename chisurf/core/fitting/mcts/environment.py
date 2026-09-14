"""Model-selection environment for TCSPC fits: the discrete action space is
the fix/free mask of an existing ChiSurf ``LifetimeModel``.

Nothing here re-implements fitting. A :class:`FitEnv` owns one chisurf
:class:`~chisurf.core.fitting.fit.Fit` — built by the existing
:func:`~chisurf.core.fluorescence.decay_fit_model.build_lifetime_fit`, or the
live fit of the fitting window — and the agent's structural actions are
manipulations of that model:

- ``ADD_LIFETIME_COMPONENT`` / ``REMOVE_LIFETIME_COMPONENT``: free or
  zero-and-fix one of the lifetime/amplitude parameter pairs. All pairs exist
  from the start (``max_components`` of them, appended by the existing
  :meth:`~chisurf.core.models.tcspc.lifetime.Lifetime.append` with its bounds
  and spacing); "removed" components are not deleted but fixed at zero
  amplitude, so they leave the model sum exactly.
- ``TOGGLE_IRF_SHIFT`` / ``TOGGLE_SCATTER`` / ``TOGGLE_BACKGROUND``: free or
  fix the existing nuisance parameters ``convolve.ts`` / ``generic.sc`` /
  ``generic.bg``.
- ``TERMINATE_FIT``: accept the current model.

Every action is followed by the existing inner loop — :meth:`Fit.run`, the
same least-squares optimiser the Fit button uses — which refines all free
parameters (lifetimes *and* amplitudes *and* the nuisances) at once. The
state's statistics are likewise read off the fit: ``chi2r``,
``durbin_watson``, ``weighted_residuals``, ``model.parameters`` (the free
parameter count ``k``) and ``generic.n_ph_exp`` (the photon count).

The only quantity that does not exist in ChiSurf is the Poisson
log-likelihood of the reward, so it is computed here (three lines of
``gammaln``) together with the reward formula

.. math::

    R = \\ln L_{\\text{Poisson}} - \\tfrac{k}{2}\\ln(N_{\\text{photons}})
        - \\gamma\\,|2 - DW|.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.special import gammaln

from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

logger = logging.getLogger(__name__)

#: Evaluation budget the environment grants each inner-loop least-squares
#: run. The user settings default (``maxfev: 0`` → MINPACK's auto ~1000–1600)
#: aborts mid-Jacobian on the small fits the tree explores, and MINPACK does
#: not restore the best point on abort — the parameters end at a
#: finite-difference probe while the model cache still holds the last good
#: evaluation, a stale-model illusion that mis-scores perfectly good
#: structures. The budget is raised only around the environment's own runs
#: and restored immediately after.
_INNER_LOOP_MAXFEV = 2500

#: Floor for expected counts inside the Poisson log-likelihood. Below it the
#: log-likelihood is linearised in the model value, which keeps the gradient
#: finite without rewarding a model for predicting ~zero where photons were seen.
_MODEL_FLOOR = 1e-10


class DiscreteAction(enum.IntEnum):
    """The structural moves the agent can make.

    The numbering is stable — it indexes the policy head of
    :class:`~chisurf.core.fitting.mcts.network.TCSPCNet` and stored training
    examples — so new actions must be appended, never inserted. The
    FRET-specific actions (6–9) are masked out on plain lifetime fits.
    """

    ADD_LIFETIME_COMPONENT = 0
    REMOVE_LIFETIME_COMPONENT = 1
    TOGGLE_IRF_SHIFT = 2
    TOGGLE_SCATTER = 3
    TOGGLE_BACKGROUND = 4
    TERMINATE_FIT = 5
    ADD_FRET_STATE = 6
    REMOVE_FRET_STATE = 7
    TOGGLE_DONOR_ONLY = 8
    TOGGLE_DONOR_LIFETIME = 9
    TOGGLE_STATE_WIDTH = 10
    # Generic parameter toggles occupy 11..34. New semantic actions are
    # appended after that reserved range so saved policy targets stay aligned.
    ADD_ROTATION_COMPONENT = 35
    REMOVE_ROTATION_COMPONENT = 36

    def __str__(self) -> str:
        return self.name


#: Width of the generic toggle-slot family: one slot per nuisance parameter
#: the model actually carries (IRF width/skew, lamp background, pile-up
#: correction, anisotropy g/l1/l2, kappa2, measurement times, …) — discovered
#: from the live model, so the agent can reach **every** parameter without a
#: hand-written action per name.
N_TOGGLE_SLOTS = 24

#: Action id of the first generic toggle slot. Slot actions are plain ints
#: (``TOGGLE_PARAMETER_BASE + i``), not enum members — the environment maps
#: them to its registry and names them via :meth:`FitEnv.action_name`.
TOGGLE_PARAMETER_BASE = 11

#: Total action width (the policy head's width).
N_ACTIONS = 37

#: Type of the optional user-dialogue callback. It receives an
#: :class:`AgentQuestion` and returns the index of the chosen option, or
#: ``None`` when the interaction was cancelled.
QueryUser = Callable[["AgentQuestion"], Optional[int]]


@dataclass(frozen=True)
class AgentQuestion:
    """One question the agent would like to ask a human.

    Model selection sometimes needs information the data cannot provide —
    the canonical case: a FRET fit wants the donor-only reference
    measurement to link against, and guessing wrong silently biases every
    distance. Instead of assuming, the environment formulates the question;
    the headless default answers "proceed without" (and logs it), while the
    GUI shows a message box.

    Attributes
    ----------
    kind : str
        Machine-readable question type (``"donor_reference"``, …).
    prompt : str
        The question as shown to the user.
    choices : list of str
        Option labels, in order; the answer is the chosen index.
    datasets : list, optional
        Payload per choice — for ``donor_reference``, tuples of
        ``(decay, irf, bin_width)`` in the same order as the dataset
        choices, so the caller does not have to know how candidates were
        found.
    """

    kind: str
    prompt: str
    choices: List[str]
    datasets: List[Any] = field(default_factory=list)


@dataclass(frozen=True)
class EnvConfig:
    """All tunable ranges and constants of the environment.

    Nothing numeric is hardcoded in the environment body; every bound lives
    here so a caller can tighten the search for a specific instrument
    (e.g. fast TCSPC with 0.005 ns channels) without touching code. The
    bounds are applied to the model's own parameters (``tau_bounds`` reach
    :meth:`Lifetime.append <chisurf.core.models.tcspc.lifetime.Lifetime.
    append>`, ``irf_shift_bounds`` reach ``convolve.ts``).

    Parameters
    ----------
    tau_bounds : (float, float)
        Lower and upper lifetime bounds in ns (the default 0.01–50 ns spans
        everything from ultra-fast rise components to phosphorescence tails).
    irf_shift_bounds : (float, float)
        IRF time-shift limits in channels (colour-shift of the IRF relative
        to the decay; a fraction of the IRF width is the physical regime).
    max_components : int
        Number of lifetime/amplitude pairs the model carries; the search may
        free any subset of them.
    gamma_autocorr : float
        Weight of the Durbin-Watson autocorrelation penalty in the reward.
    obs_length : int
        Length the decay/IRF/residual channels are resampled to for the
        network input (the convolutional trunk needs a fixed receptive field).
    component_spacing : float
        Ratio between a newly freed component's starting lifetime and the
        shortest active one (the existing
        :attr:`Lifetime.COMPONENT_SPACING
        <chisurf.core.models.tcspc.lifetime.Lifetime.COMPONENT_SPACING>`
        rationale: two equal lifetimes are a degenerate, unseparable start).
    default_lifetime : float
        Starting lifetime of the first component, in ns.
    protected_parameters : tuple of str
        Instrument/calibration parameters whose initial fixed/free state is
        authoritative. MCTS never toggles these: if the user made one free it
        remains free and participates in every inner fit; if it started fixed
        it remains fixed. ``n0`` is intentionally not protected.
    """

    tau_bounds: Tuple[float, float] = (0.01, 50.0)
    irf_shift_bounds: Tuple[float, float] = (-8.0, 8.0)
    max_components: int = 4
    max_rotation_components: int = 3
    gamma_autocorr: float = 10.0
    obs_length: int = 128
    component_spacing: float = 3.0
    default_lifetime: float = 4.0
    protected_parameters: Tuple[str, ...] = (
        "dt", "rep", "g", "l1", "l2", "R0(F)"
    )
    # Compatibility for callers that used the earlier name. Extra names are
    # protected with the same preserve-initial-state semantics.
    frozen_parameters: Tuple[str, ...] = ()
    chi2_acceptance_z: float = 2.0

    def __post_init__(self) -> None:
        lo, hi = self.tau_bounds
        if not 0.0 < lo < hi:
            raise ValueError(f"tau_bounds must satisfy 0 < lower < upper, got {self.tau_bounds}")
        slo, shi = self.irf_shift_bounds
        if not slo < shi:
            raise ValueError(
                f"irf_shift_bounds must satisfy lower < upper, got {self.irf_shift_bounds}"
            )
        if int(self.max_components) < 1:
            raise ValueError("max_components must be at least 1")
        if int(self.max_rotation_components) < 0:
            raise ValueError("max_rotation_components cannot be negative")
        if int(self.obs_length) < 8:
            raise ValueError("obs_length must be at least 8")


@dataclass(frozen=True)
class ModelStructure:
    """The discrete part of the model: which existing parameters are free.

    ``active`` marks, per lifetime/amplitude pair (in model order), whether
    the pair is fitted; the three booleans are the nuisance toggles. This is
    exactly the fix/free mask of the underlying ``LifetimeModel``. FRET fits
    add ``fret_states`` (per Gaussian distance state) and the donor-only /
    donor-lifetime toggles; on lifetime fits these carry their defaults and
    the corresponding actions are masked out.
    """

    active: Tuple[bool, ...] = (True,)
    fit_irf_shift: bool = False
    fit_scatter: bool = False
    fit_background: bool = False
    fret_states: Tuple[bool, ...] = ()
    fit_donor_only: bool = False
    fit_donor_lifetime: bool = False
    fit_state_width: bool = False
    toggles: Tuple[bool, ...] = ()
    # Appended to preserve the positional constructor used by existing FRET
    # callers; older nine-field structures therefore still mean the same.
    rotations: Tuple[bool, ...] = ()

    @property
    def n_components(self) -> int:
        """Number of active (fitted) lifetime components."""
        return sum(bool(a) for a in self.active)

    @property
    def n_fret_states(self) -> int:
        """Number of active (fitted) Gaussian distance states."""
        return sum(bool(a) for a in self.fret_states)

    @property
    def n_rotations(self) -> int:
        """Number of active anisotropy rotation components."""
        return sum(bool(a) for a in self.rotations)

    def as_tuple(self) -> Tuple[Any, ...]:
        """Hashable identity of the structure (states are compared by it)."""
        return (tuple(bool(a) for a in self.active),
                bool(self.fit_irf_shift), bool(self.fit_scatter),
                bool(self.fit_background),
                tuple(bool(a) for a in self.fret_states),
                bool(self.fit_donor_only), bool(self.fit_donor_lifetime),
                bool(self.fit_state_width),
                tuple(bool(a) for a in self.toggles),
                tuple(bool(a) for a in self.rotations))

    def __str__(self) -> str:
        toggles = [
            name for name, on in (
                ("shift", self.fit_irf_shift),
                ("scatter", self.fit_scatter),
                ("background", self.fit_background),
                ("donor-only", self.fit_donor_only),
                ("donor lifetime", self.fit_donor_lifetime),
            ) if on
        ]
        base = f"{self.n_components} component(s)"
        if self.fret_states:
            base += f", {self.n_fret_states} FRET state(s)"
        if self.rotations:
            base += f", {self.n_rotations} rotation(s)"
        return base + (f" + {', '.join(toggles)}" if toggles else "")


@dataclass
class FitStats:
    """Goodness-of-fit metrics of one optimised state.

    Attributes
    ----------
    chi2_reduced : float
        The fit's own reduced chi-square.
    log_likelihood : float
        Poisson log-likelihood ``ln L = Σ [y·ln m − m − ln(y!)]`` over the
        fit window (the one quantity ChiSurf does not carry itself).
    durbin_watson : float
        The fit's own Durbin-Watson statistic; 2.0 means white noise.
    autocorr_score : float
        ``|2 − DW|`` — the penalty term of the reward.
    n_photons : float
        Total counts (``generic.n_ph_exp``).
    n_free_parameters : int
        ``len(model.parameters)`` — the free-parameter count ``k``.
    dof : int
        Residual degrees of freedom (bins − k).
    chi2_acceptable : bool
        Whether χ²ᵣ is consistent with 1 within the configured z-score —
        the gate on ``TERMINATE_FIT``. Close to 1 or it is not done.
    reward : float
        ``ln L − (k/2)·ln(N) − γ·|2 − DW|``.
    """

    chi2_reduced: float = float("nan")
    log_likelihood: float = float("-inf")
    durbin_watson: float = float("nan")
    autocorr_score: float = float("nan")
    n_photons: float = 0.0
    n_free_parameters: int = 0
    dof: int = 0
    chi2_acceptable: bool = False
    reward: float = float("-inf")


@dataclass
class FitState:
    """A fully specified model: structure (the free mask) and its values."""

    structure: ModelStructure
    lifetimes: np.ndarray
    amplitudes: np.ndarray
    irf_shift: float = 0.0
    scatter: float = 0.0
    background: float = 0.0
    prediction: np.ndarray = field(default_factory=lambda: np.zeros(0))
    residuals: np.ndarray = field(default_factory=lambda: np.zeros(0))
    stats: FitStats = field(default_factory=FitStats)
    #: FRET states (Gaussian distances), filled by the FRET environment.
    distances: np.ndarray = field(default_factory=lambda: np.zeros(0))
    sigmas: np.ndarray = field(default_factory=lambda: np.zeros(0))
    fractions: np.ndarray = field(default_factory=lambda: np.zeros(0))
    donor_only_fraction: float = 0.0
    rotation_times: np.ndarray = field(default_factory=lambda: np.zeros(0))
    rotation_amplitudes: np.ndarray = field(default_factory=lambda: np.zeros(0))
    # Exact parameter payload for every member of a grouped fit. This is the
    # general restore mechanism; model-specific fields above are retained for
    # reporting, feature construction, and backwards compatibility.
    model_parameter_values: Tuple[Tuple[float, ...], ...] = ()
    model_parameter_fixed: Tuple[Tuple[bool, ...], ...] = ()
    #: Generic nuisance registry payload (aligned with the environment's
    #: registry order): parameter names, values and free flags.
    toggle_names: Tuple[str, ...] = ()
    toggle_values: np.ndarray = field(default_factory=lambda: np.zeros(0))
    toggles: Tuple[bool, ...] = ()

    @property
    def intensity_fractions(self) -> np.ndarray:
        """Photon fractions ``f_i = a_i·τ_i / Σ a_j·τ_j`` of the active pairs.

        The model's amplitudes are pre-exponential (the ``Lifetime`` group
        normalises them), so the intensity fraction weighs each by its
        lifetime — the quantity a spectroscopist reads off a decay table.
        """
        weights = self.amplitudes * self.lifetimes
        total = float(np.abs(weights).sum())
        if not np.isfinite(total) or total <= 0.0:
            return np.full_like(weights, np.nan)
        return weights / total

    def describe(self) -> str:
        """Human-readable multi-line summary of the model and its quality.

        Components are reported sorted from large to small — lifetimes by
        their value, FRET states by distance, rotation times by theirs —
        which is how decay tables are read, independent of the order the
        optimiser happened to leave them in.
        """
        lines = [f"model: {self.structure}"]
        pairs = sorted(
            zip(self.lifetimes, self.amplitudes, self.intensity_fractions),
            key=lambda row: row[0], reverse=True,
        )
        for i, (tau, amp, frac) in enumerate(pairs):
            lines.append(
                f"  component {i + 1}: tau = {tau:.4f} ns, "
                f"a = {amp:.4f}, f = {frac:.3f}"
            )
        states = sorted(
            zip(self.distances, self.sigmas, self.fractions),
            key=lambda row: row[0], reverse=True,
        )
        for i, (r, w, x) in enumerate(states):
            lines.append(
                f"  FRET state {i + 1}: R = {r:.1f} A, w = {w:.1f} A, x = {x:.3f}"
            )
        rotations = sorted(
            zip(self.rotation_times, self.rotation_amplitudes),
            key=lambda row: row[0], reverse=True,
        )
        for i, (rho, b) in enumerate(rotations):
            lines.append(
                f"  rotation {i + 1}: rho = {rho:.3f} ns, b = {b:.3f}"
            )
        if self.structure.fit_donor_only and self.distances.size:
            lines.append(f"  donor-only fraction: {self.donor_only_fraction:.3f}")
        if self.structure.fit_irf_shift:
            lines.append(f"  irf shift: {self.irf_shift:+.3f} channels")
        if self.structure.fit_scatter:
            lines.append(f"  scatter: {self.scatter:.4f}")
        if self.structure.fit_background:
            lines.append(f"  background: {self.background:.4f} counts/channel")
        s = self.stats
        lines.append(
            f"  chi2_r = {s.chi2_reduced:.3f}  lnL = {s.log_likelihood:.1f}  "
            f"DW = {s.durbin_watson:.3f}  k = {s.n_free_parameters}  "
            f"reward = {s.reward:.1f}"
        )
        return "\n".join(lines)



def nuisance_registry_for_model(
    model: Any,
    lifetime_group: Any,
    frozen_names: Tuple[str, ...] = (),
    limit: int = N_TOGGLE_SLOTS,
) -> List[Tuple[str, Any]]:
    """Every reachable parameter of a model, in a stable order.

    Shared by the environments (their action slots) and the state transfer
    (applying the searched free/fixed decisions to a live fit), so both walk
    the same parameter set the same way. Excludes the lifetime pairs, the
    semantic nuisance parameters (``ts``/``sc``/``bg``, plus ``xDonly``/
    ``tauD0``/``R0`` and the Gaussian rows on FRET models), linked and
    frozen parameters. **No inertness pruning here** — the transfer must be
    able to address every parameter the search freed, inert or not.
    """
    excluded: set = set()
    for tau_p, amp_p in zip(lifetime_group._lifetimes, lifetime_group._amplitudes):
        excluded.add(id(tau_p))
        excluded.add(id(amp_p))
    for group, names in ((getattr(model, "convolve", None), ("_ts",)),
                         (getattr(model, "generic", None), ("_sc", "_bg")),
                         (getattr(model, "fret_parameters", None),
                          ("_xDonly", "_tauD0", "_forster_radius", "_kappa2"))):
        for name in names:
            parameter = getattr(group, name, None) if group is not None else None
            if parameter is not None:
                excluded.add(id(parameter))
    for container in ("_gaussianMeans", "_gaussianSigma",
                      "_gaussianAmplitudes", "_gaussianShape"):
        for parameter in getattr(getattr(model, "gaussians", None), container, []) or []:
            excluded.add(id(parameter))

    frozen = set(frozen_names)
    registry: List[Tuple[str, Any]] = []
    try:
        parameters = model.parameters_all
    except Exception:
        parameters = []
    for parameter in parameters:
        if id(parameter) in excluded or parameter.is_linked:
            continue
        if parameter.name in frozen:
            continue
        registry.append((str(parameter.name), parameter))
    registry.sort(key=lambda entry: entry[0])
    return registry[:limit]


class _Discrete:
    """Minimal stand-in for ``gymnasium.spaces.Discrete``.

    Gymnasium is deliberately not a dependency of the core; the environment
    keeps its API shape (``.n``, sampling) so it drops into Gymnasium-based
    tooling unchanged when the package happens to be installed.
    """

    def __init__(self, n: int):
        self.n = int(n)
        self._rng = np.random.default_rng()

    def sample(self) -> int:
        return int(self._rng.integers(self.n))


class _Box:
    """Minimal stand-in for ``gymnasium.spaces.Box`` (shape/bounds only)."""

    def __init__(self, shape: Tuple[int, ...], low: float = -np.inf, high: float = np.inf):
        self.shape = tuple(int(s) for s in shape)
        self.low = low
        self.high = high


class FitEnv:
    """Model-selection environment over one ChiSurf lifetime fit.

    The environment is a thin adapter: it never computes a model, a residual
    or a statistic itself — it flips the fix/free mask of the model's own
    parameters, runs the fit's own optimiser and reads the fit's own
    statistics. It is functional where the tree needs it to be:
    :meth:`apply_action` restores a state, mutates the mask, optimises and
    returns the *new* state, so nodes can be revisited safely.

    Parameters
    ----------
    decay : array_like, optional
        Measured decay in counts. Either ``decay``/``irf``/``bin_width`` or
        ``fit`` must be given; the former are handed to the existing
        :func:`~chisurf.core.fluorescence.decay_fit_model.build_lifetime_fit`.
    irf : array_like, optional
        Measured instrument response (any positive scaling).
    bin_width : float, optional
        Micro-time channel width in ns (the "timing bin resolution").
    fit : chisurf.core.fitting.fit.Fit, optional
        An existing lifetime fit to operate on (used by the GUI path); the
        model must expose the ``lifetimes``/``convolve``/``generic`` groups.
        Its data window (``xmin``/``xmax``) is respected.
    config : EnvConfig, optional
        Bounds and constants; defaults to :class:`EnvConfig` defaults.
    period : float, optional
        Laser repetition period in ns for a periodic convolution.
    initial_irf_shift : float, optional
        The live fit's current IRF colour shift in channels. The environment
        is built from the *unshifted* IRF, so this seeds ``ts`` — without it,
        a live fit that carries a real shift would be analysed (and
        transferred back) as if the data were shift-free.
    """

    metadata: Dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        decay: Optional[Sequence[float]] = None,
        irf: Optional[Sequence[float]] = None,
        bin_width: Optional[float] = None,
        *,
        fit: Any = None,
        config: Optional[EnvConfig] = None,
        period: Optional[float] = None,
        initial_irf_shift: float = 0.0,
    ):
        self.config = config if config is not None else EnvConfig()
        if fit is not None:
            self.fit = fit
            for group in ("lifetimes", "convolve", "generic"):
                if getattr(self.fit.model, group, None) is None:
                    raise ValueError(
                        f"the fit's model has no '{group}' group; the MCTS "
                        "environment drives lifetime models"
                    )
        elif decay is not None and irf is not None and bin_width is not None:
            self.fit = build_lifetime_fit(
                np.asarray(decay, dtype=float),
                bin_width=float(bin_width),
                irf=np.asarray(irf, dtype=float),
                n_components=int(self.config.max_components),
                tau_bounds=tuple(self.config.tau_bounds),
                period=period,
            )
        else:
            raise ValueError("pass either an existing fit or decay/irf/bin_width")
        if bin_width is None:
            bin_width = float(self.fit.model.convolve.dt)
        self.bin_width = float(bin_width)
        self._setup_from_fit()
        try:
            slo, shi = self.config.irf_shift_bounds
            self._model.convolve._ts.value = float(
                np.clip(initial_irf_shift, slo, shi))
        except Exception:
            logger.debug("could not seed the initial IRF shift")

    def _setup_from_fit(self) -> None:
        """Bind to ``self.fit``: the groups, the pair bookkeeping, the
        Poisson constants and the observation/action spaces. Split from
        :meth:`__init__` so a subclass (the FRET environment) can build its
        own fits first and skip the lifetime fit it would otherwise throw
        away."""
        self._fits = list(getattr(self.fit, "grouped_fits", []) or []) or [self.fit]
        self._model = self._fits[0].model
        self._lifetime_groups = [f.model.lifetimes for f in self._fits]
        self._lifetimes = self._lifetime_groups[0]
        for group in self._lifetime_groups:
            while len(group) < int(self.config.max_components):
                group.append(
                    lower_bound_lifetime=self.config.tau_bounds[0],
                    upper_bound_lifetime=self.config.tau_bounds[1],
                )
        #: Every fit whose parameter table the environment owns. The state
        #: captures and restores them wholesale (``FitState.
        #: model_parameter_values``), which is what makes the selector
        #: model-agnostic: anything the model carries is covered without a
        #: per-model restore path.
        self._parameter_fits = list(self._fits)

        y = np.asarray(self.fit.data.y, dtype=float)
        self.y = y
        self.n_channels = int(y.size)
        self.n_photons = float(sum(
            np.asarray(f.data.y, dtype=float).sum() for f in self._fits
        ))
        self._i0, self._i1 = int(self.fit.xmin), int(self.fit.xmax) + 1
        self._ln_factorial = float(gammaln(y + 1.0).sum())

        # Apply the configured shift bounds to the existing timeshift
        # parameter. The configuration is in channels, which means the *time*
        # reach shrinks with the bin width — ±8 channels is 0.38 ns on a
        # 48-ps/bins decay and a useless 0.11 ns on a 4096-channel TAC. The
        # bound must at least span the prompt itself: a synthetic IRF is
        # seeded at the rising edge (≈1σ left of the true centre), and if the
        # optimiser cannot reach the true centre it trades the position error
        # for a wrong width and junk lifetimes.
        try:
            ts = self._model.convolve._ts
            reach = max(abs(float(b)) for b in self.config.irf_shift_bounds)
            if getattr(self._model.convolve, "_irf", None) is None:
                y = np.asarray(self.fit.data.y, dtype=float)[self._i0:self._i1]
                peak = int(np.argmax(y)) if y.size and y.max() > 0 else 0
                half = 0.5 * float(y[peak]) if y.size and y.max() > 0 else 0.0
                left = peak
                while left > 0 and y[left] > half:
                    left -= 1
                fwhm_channels = max(peak - left, 1)
                reach = max(reach, 2.0 * fwhm_channels)
            ts.bounds = (-float(reach), float(reach))
            ts.bounds_on = True
        except Exception:
            logger.debug("could not apply irf shift bounds to convolve.ts")
        #: Gymnasium-style space descriptors (duck-typed; no gymnasium needed).
        self.action_space = _Discrete(N_ACTIONS)
        self.observation_space = _Box(
            (self.config.obs_length, 3 + self.n_structure_features), low=-1.0, high=1.0
        )
        #: Every remaining parameter of the model, in a stable order (see
        #: :meth:`_nuisance_registry`); slot ``i`` of the generic toggle
        #: actions addresses ``self._registry[i]``.
        self._registry = self._nuisance_registry()

        self.state: Optional[FitState] = None

    #: Number of scalar structure features (signal planes stay 3): the four
    #: lifetime features plus the padded generic-toggle bits.
    n_structure_features = 7 + N_TOGGLE_SLOTS

    @property
    def n_actions(self) -> int:
        """Action width of this environment (the policy head's width)."""
        return N_ACTIONS

    def action_name(self, action: "DiscreteAction | int") -> str:
        """Human-readable action label, including the generic slots."""
        if int(action) in (int(DiscreteAction.ADD_ROTATION_COMPONENT),
                           int(DiscreteAction.REMOVE_ROTATION_COMPONENT)):
            return str(DiscreteAction(action))
        if isinstance(action, int) and action >= TOGGLE_PARAMETER_BASE:
            slot = action - TOGGLE_PARAMETER_BASE
            if slot < len(self._registry):
                return f"TOGGLE {self._registry[slot][0]}"
            return f"TOGGLE_SLOT_{slot}"
        return str(DiscreteAction(action))

    def _semantic_parameter_ids(self) -> set:
        """Parameters with their own named action or structural role — they
        are *not* duplicated into the generic registry."""
        ids = set()
        for tau_p, amp_p in zip(self._lifetimes._lifetimes,
                                self._lifetimes._amplitudes):
            ids.add(id(tau_p))
            ids.add(id(amp_p))
        for name in ("_ts", "_sc", "_bg"):
            group = {"_ts": self._model.convolve, "_sc": self._model.generic,
                     "_bg": self._model.generic}[name]
            p = getattr(group, name, None)
            if p is not None:
                ids.add(id(p))
        anisotropy = getattr(self._model, "anisotropy", None)
        if anisotropy is not None:
            for p in (list(getattr(anisotropy, "_bs", []))
                      + list(getattr(anisotropy, "_rhos", []))):
                ids.add(id(p))
        return ids

    def _nuisance_registry(self) -> List[Tuple[str, Any]]:
        """Discover every remaining parameter of the live model.

        Walks ``model.parameters_all`` (the same discovery the fit's own
        optimiser uses) and keeps what is neither structurally managed
        (lifetime pairs, Gaussian rows), semantically actioned (``ts``,
        ``sc``, ``bg``, ``xDonly``, ``tauD0``), linked, nor protected by
        ``config.protected_parameters``. Sorted by name, so the registry — and
        with it the meaning of every toggle slot — is stable.
        """
        excluded = self._semantic_parameter_ids()
        frozen = set(self.config.protected_parameters) | set(
            self.config.frozen_parameters
        )
        registry: List[Tuple[str, Any]] = []
        seen: set = set()
        try:
            parameters = self._model.parameters_all
        except Exception:
            parameters = []
        for parameter in parameters:
            if id(parameter) in excluded or id(parameter) in seen:
                continue
            if parameter.is_linked:
                continue
            if parameter.name in frozen:
                continue
            # A parameter fixed by the user is a calibration/assumption until
            # they say otherwise. `n0` and the synthetic-IRF shape pair are
            # deliberate exceptions: they are model fit parameters, and an
            # incorrect synthetic prompt must be allowed to recover.
            if parameter.fixed and parameter.name not in ("n0", "iw", "ik"):
                continue
            seen.add(id(parameter))
            registry.append((str(parameter.name), parameter))
        registry.sort(key=lambda entry: entry[0])
        # Inertness probe: a parameter the data cannot see — an anisotropy
        # rotation time on a single-channel decay, an IRF width when the IRF
        # is measured, a pile-up window with the correction off — is pruned.
        # Perturb, update, compare: one model evaluation per candidate, no
        # fitting. Keeping inert slots would only dilute the search; each
        # costs a visit to learn it is useless, and the BIC term of the
        # reward refuses them anyway if they are freed.
        self._model.update()
        reference = np.asarray(self._model.y, dtype=float).copy()
        live: List[Tuple[str, Any]] = []
        for name, parameter in registry:
            original = float(parameter.value)
            scale = max(abs(original), 1e-6)
            parameter.value = original * 1.01 + 1e-3 * scale
            try:
                self._model.update()
                moved = float(np.max(np.abs(
                    np.asarray(self._model.y, dtype=float) - reference
                ))) > 1e-9
            except Exception:
                moved = True  # cannot evaluate -> keep it reachable
            parameter.value = original
            if moved:
                live.append((name, parameter))
        self._model.update()
        return live[:N_TOGGLE_SLOTS]

    # ------------------------------------------------------------------ #
    # Anisotropy (VV/VH) rotation components                             #
    # ------------------------------------------------------------------ #

    def _anisotropy_groups(self) -> list:
        """Live, polarisation-aware anisotropy groups of every member fit.

        Magic-angle groups contribute no anisotropy (the model short-circuits
        the rotation spectrum), so they are excluded: rotation components
        would be invisible parameters there, and invisible ones stay fixed.
        """
        groups = []
        for f in self._fits:
            anisotropy = getattr(f.model, "anisotropy", None)
            if anisotropy is None:
                continue
            if str(getattr(anisotropy, "polarization_type", "vm")).lower() == "vm":
                continue
            groups.append(anisotropy)
        return groups

    def _rotation_components(self, rho: float = None, amplitude: float = None):
        """Make every member's anisotropy carry exactly the state's rotations.

        The last component is (re)seeded with ``rho``/``amplitude`` so a
        freshly added rotation starts from a physical value instead of the
        constructor default.
        """
        groups = self._anisotropy_groups()
        if not groups:
            return
        target = len(self.state.structure.rotations) if (
            self.state is not None and self.state.structure.rotations
        ) else None
        for anisotropy in groups:
            while len(anisotropy) < len(self.state.structure.rotations):
                anisotropy.add_rotation(
                    b=0.2 if amplitude is None else float(amplitude),
                    rho=1.0 if rho is None else float(rho),
                )
            while len(anisotropy) > len(self.state.structure.rotations):
                anisotropy.remove_rotation()
        if rho is not None and target:
            for anisotropy in groups:
                if anisotropy._rhos:
                    anisotropy._rhos[-1].value = float(rho)
                if anisotropy._bs:
                    anisotropy._bs[-1].value = float(
                        0.2 if amplitude is None else amplitude
                    )

    # ------------------------------------------------------------------ #
    # Reading state off the live fit                                     #
    # ------------------------------------------------------------------ #

    def _structure_of_fit(self) -> ModelStructure:
        """The current fix/free mask, read off the model's parameters."""
        active = []
        for tau, amp in zip(self._lifetimes._lifetimes, self._lifetimes._amplitudes):
            free = not (tau.fixed and amp.fixed) and abs(amp.value) > 0.0
            active.append(bool(free))
        anisotropy_groups = self._anisotropy_groups()
        rotations = tuple(
            True for _ in range(len(anisotropy_groups[0]))
        ) if anisotropy_groups else ()
        return ModelStructure(
            active=tuple(active),
            fit_irf_shift=not self._model.convolve._ts.fixed,
            fit_scatter=not self._model.generic._sc.fixed,
            fit_background=not self._model.generic._bg.fixed,
            rotations=rotations,
            toggles=tuple(not p.fixed for _name, p in self._registry),
        )

    def _poisson_log_likelihood(self) -> float:
        """``ln L = Σ [y·ln m − m − ln(y!)]`` over every member fit window."""
        ln_l = 0.0
        for fit in self._fits:
            y = np.asarray(fit.data.y, dtype=float)[self._i0:self._i1]
            m = np.asarray(fit.model.y, dtype=float)[self._i0:self._i1]
            expected = np.maximum(m, _MODEL_FLOOR)
            with np.errstate(divide="ignore", invalid="ignore"):
                terms = y * np.log(expected) - expected
            ln_l += float(np.sum(np.where(np.isfinite(terms), terms, 0.0)))
            ln_l -= float(gammaln(y + 1.0).sum())
        return ln_l

    def _seed_synthetic_irf_width(self) -> None:
        """Seed ``iw`` from the data's own prompt, fit-free.

        A synthetic IRF whose width is a wild guess (the model default) puts
        every candidate model against a mis-shaped instrument response, and
        the joint (τ, ts, iw) surface has basins that trade a wrong width for
        junk lifetimes — the search then reports a confident 4-component
        model instead of noticing its prompt is wrong. The prompt's
        half-maximum width is directly measurable: the rising side of the
        peak is instrument response, not sample decay, so twice the distance
        from peak to half-max on the left estimates the FWHM for any
        symmetric-ish response, contamination-free.
        """
        y = np.asarray(self.fit.data.y, dtype=float)[self._i0:self._i1]
        if y.size < 8 or float(y.max()) <= 0.0:
            return
        peak = int(np.argmax(y))
        half = 0.5 * float(y[peak])
        left = peak
        while left > 0 and y[left] > half:
            left -= 1
        fwhm = 2.0 * (peak - left) * self.bin_width
        iw = self._model.convolve._iw
        lo, hi = (iw.lb, iw.ub) if iw.bounds_on else (0.005, 5.0)
        iw.value = float(np.clip(fwhm, lo, hi))

    def _chi2_acceptable(self, chi2_reduced: float, k: int) -> bool:
        """χ²ᵣ consistent with 1 within ``z`` standard errors of the χ² law."""
        if not np.isfinite(chi2_reduced):
            return False
        dof = max(self.n_channels - int(k), 1)
        limit = 1.0 + self.config.chi2_acceptance_z * np.sqrt(2.0 / dof)
        return chi2_reduced <= limit

    def _combined_chi2(self) -> float:
        """Unreduced chi² summed over every member fit of the environment.

        A VV/VH anisotropy fit is one analysis spread over two fits; the
        reward has to see the combined misfit, not one channel's.
        """
        chi2 = 0.0
        for f in self._fits:
            try:
                chi2 += float(f.chi2)
            except Exception:
                chi2 += float("nan")
        return chi2

    def _combined_points(self) -> int:
        n = 0
        for f in self._fits:
            try:
                n += int(getattr(f.model, "n_points", 0))
            except Exception:
                pass
        return max(n, 1)

    def _stats_of_fit(self) -> FitStats:
        """The reward ingredients, read off the fit (plus the Poisson lnL)."""
        try:
            dw = float(self.fit.durbin_watson)
        except Exception:
            dw = float("nan")
        if not np.isfinite(dw):
            dw = 2.0
        k = len(self._model.parameters)
        ln_l = self._poisson_log_likelihood()
        reward = (
            ln_l
            - 0.5 * k * math.log(max(self.n_photons, 1.0))
            - self.config.gamma_autocorr * abs(2.0 - dw)
        )
        chi2 = self._combined_chi2()
        dof = max(self._combined_points() - k, 1)
        chi2_reduced = chi2 / dof
        return FitStats(
            chi2_reduced=chi2_reduced,
            log_likelihood=ln_l,
            durbin_watson=dw,
            autocorr_score=abs(2.0 - dw),
            n_photons=self.n_photons,
            n_free_parameters=int(k),
            dof=dof,
            chi2_acceptable=chi2_reduced <= (
                1.0 + self.config.chi2_acceptance_z * np.sqrt(2.0 / dof)
            ),
            reward=reward,
        )

    def _snapshot(self) -> FitState:
        """Copy the model's current values and statistics into a state."""
        structure = self._structure_of_fit()
        active = [i for i, on in enumerate(structure.active) if on]
        lifetimes = np.array(
            [self._lifetimes._lifetimes[i].value for i in active], dtype=float
        )
        amplitudes = np.array(
            [self._lifetimes._amplitudes[i].value for i in active], dtype=float
        )
        residuals = np.asarray(
            self.fit.weighted_residuals.y, dtype=float
        ) if self.fit.weighted_residuals is not None else np.zeros(0)
        prediction = np.asarray(self._model.y, dtype=float)[self._i0:self._i1]
        anisotropy_groups = self._anisotropy_groups()
        rotation_times = np.zeros(0)
        rotation_amplitudes = np.zeros(0)
        if anisotropy_groups:
            times = np.asarray(
                [p.value for p in anisotropy_groups[0]._rhos], dtype=float)
            amplitudes_r = np.asarray(
                [p.value for p in anisotropy_groups[0]._bs], dtype=float)
            order = np.argsort(times)[::-1]  # report large -> small
            rotation_times = times[order]
            rotation_amplitudes = amplitudes_r[order]
        return FitState(
            # One generic payload per member fit: values and fix/free state of
            # the *whole* parameter table. This is what makes one network and
            # one restore path cover every model ChiSurf can build — no
            # per-model field is load-bearing.
            model_parameter_values=tuple(
                tuple(float(p.value) for p in f.model.parameters_all)
                for f in self._parameter_fits
            ),
            model_parameter_fixed=tuple(
                tuple(bool(p.fixed) for p in f.model.parameters_all)
                for f in self._parameter_fits
            ),
            toggle_names=tuple(name for name, _p in self._registry),
            toggle_values=np.array(
                [p.value for _name, p in self._registry], dtype=float),
            toggles=tuple(not p.fixed for _name, p in self._registry),
            structure=structure,
            lifetimes=lifetimes,
            amplitudes=amplitudes,
            irf_shift=float(self._model.convolve.timeshift)
            if structure.fit_irf_shift else 0.0,
            scatter=float(self._model.generic.scatter)
            if structure.fit_scatter else 0.0,
            background=float(self._model.generic.background)
            if structure.fit_background else 0.0,
            prediction=prediction,
            residuals=residuals,
            stats=self._stats_of_fit(),
            rotation_times=rotation_times,
            rotation_amplitudes=rotation_amplitudes,
        )

    def _restore(self, state: FitState) -> None:
        """Write a state's values and fix/free mask back into the model."""
        # 1. The generic payload: every parameter of every member fit, by
        #    position. This restores anything model-specific (rotations,
        #    corrections, …) without a per-model code path.
        if state.model_parameter_values and len(
            state.model_parameter_values
        ) == len(self._parameter_fits):
            for fit, values, fixed in zip(
                self._parameter_fits,
                state.model_parameter_values,
                state.model_parameter_fixed,
            ):
                parameters = getattr(fit.model, "parameters_all", [])
                if len(parameters) != len(values) or len(values) != len(fixed):
                    continue
                for parameter, value, is_fixed in zip(
                    parameters, values, fixed
                ):
                    if getattr(parameter, "is_linked", False):
                        continue
                    parameter.value = float(value)
                    parameter.fixed = bool(is_fixed)

        # 2. The structural mask: which lifetime/rotation components exist
        #    and which nuisances are fitted, applied consistently to every
        #    member fit of the group.
        structure = state.structure
        for group in self._lifetime_groups:
            active = list(structure.active)
            while len(active) < len(group._lifetimes):
                active.append(False)
            k = 0
            lo, hi = self.config.tau_bounds
            for i, (tau_p, amp_p) in enumerate(
                zip(group._lifetimes, group._amplitudes)
            ):
                if active[i]:
                    tau_p.value = float(np.clip(state.lifetimes[k], lo, hi))
                    amp_p.value = float(state.amplitudes[k])
                    tau_p.fixed = False
                    amp_p.fixed = False
                    k += 1
                else:
                    amp_p.value = 0.0
                    tau_p.fixed = True
                    amp_p.fixed = True
        anisotropy_groups = self._anisotropy_groups()
        if anisotropy_groups:
            times = np.sort(np.asarray(state.rotation_times, dtype=float))[::-1] \
                if state.rotation_times.size else np.zeros(
                    len(structure.rotations))
            amplitudes = np.sort(np.asarray(state.rotation_amplitudes, dtype=float))[::-1] \
                if state.rotation_amplitudes.size else None
            for anisotropy in anisotropy_groups:
                while len(anisotropy) < len(structure.rotations):
                    anisotropy.add_rotation(b=0.2, rho=1.0)
                while len(anisotropy) > len(structure.rotations):
                    anisotropy._rhos.pop()
                    anisotropy._bs.pop()
                for i, (rho_p, b_p) in enumerate(
                    zip(anisotropy._rhos, anisotropy._bs)
                ):
                    if i < times.size:
                        rho_p.value = float(max(times[i], 1e-6))
                    if amplitudes is not None and i < amplitudes.size:
                        b_p.value = float(amplitudes[i])
        ts = self._model.convolve._ts
        sc = self._model.generic._sc
        bg = self._model.generic._bg
        ts.value = float(state.irf_shift) if structure.fit_irf_shift else 0.0
        ts.fixed = not structure.fit_irf_shift
        sc.value = float(state.scatter) if structure.fit_scatter else 0.0
        sc.fixed = not structure.fit_scatter
        bg.value = float(state.background) if structure.fit_background else 0.0
        bg.fixed = not structure.fit_background
        for i, (name, parameter) in enumerate(self._registry):
            if i < len(state.structure.toggles):
                parameter.fixed = not state.structure.toggles[i]
                if i < len(state.toggle_values):
                    parameter.value = float(state.toggle_values[i])
            else:
                parameter.fixed = True
        self._model.update()

    # ------------------------------------------------------------------ #
    # Observations                                                       #
    # ------------------------------------------------------------------ #

    def _resample(self, vector: np.ndarray) -> np.ndarray:
        length = self.config.obs_length
        if vector.size == length:
            return vector.astype(np.float32)
        src = np.linspace(0.0, 1.0, vector.size)
        grid = np.linspace(0.0, 1.0, length)
        return np.interp(grid, src, vector).astype(np.float32)

    def observation(self, state: FitState) -> np.ndarray:
        """Render one state as the fixed-length network input.

        Seven channels, resampled to ``config.obs_length``:

        1. the decay, normalised to its maximum;
        2. the IRF the model is convolved with;
        3. the fit's weighted residuals clipped to a sane range;
        4.–7. constant planes carrying the structure features (component
           count and the three toggles). The planes exist because a TOGGLE
           action means the *opposite* thing depending on the current mask —
           a policy that cannot read the mask from its input learns only the
           average "toggles are useful" and ping-pongs them; a constant plane
           per feature hands the convolutional trunk the mask at every
           position.
        """
        y = np.asarray(self.fit.data.y, dtype=float)[self._i0:self._i1]
        peak = float(y.max())
        decay_channel = self._resample(y / (peak if peak > 0 else 1.0))
        irf = np.asarray(self._model.convolve.irf.y, dtype=float)
        irf_channel = self._resample(irf / (irf.max() if irf.max() > 0 else 1.0))
        residual_channel = self._resample(
            np.clip(state.residuals / 8.0, -1.0, 1.0)
        )
        length = self.config.obs_length
        planes = np.tile(
            self.structure_features(state.structure)[None, :], (length, 1)
        )
        return np.stack(
            [decay_channel, irf_channel, residual_channel, *planes.T],
            axis=1,
        ).astype(np.float32)

    def structure_features(self, structure: ModelStructure) -> np.ndarray:
        """Auxiliary scalar features describing the discrete structure.

        The policy must know the current structure to act on it; the decay
        channels alone do not encode it, so the heads receive the semantic
        feature block alongside the pooled convolutional features. The
        layout is fixed and shared by every adapter — one network for all
        models.
        """
        toggles = np.zeros(N_TOGGLE_SLOTS, dtype=np.float32)
        for i, on in enumerate(structure.toggles[:N_TOGGLE_SLOTS]):
            toggles[i] = float(on)
        return np.concatenate(
            [
                np.array(
                    [
                        structure.n_components / max(self.config.max_components, 1),
                        float(structure.fit_irf_shift),
                        float(structure.fit_scatter),
                        float(structure.fit_background),
                        0.0,  # FRET: state count (0 on lifetime fits)
                        0.0,  # FRET: donor-only present
                        float(structure.n_rotations)
                        / max(self.config.max_rotation_components, 1),
                    ],
                    dtype=np.float32,
                ),
                toggles,
            ],
        ).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Actions: flips of the fix/free mask + the existing optimiser       #
    # ------------------------------------------------------------------ #

    def _run_fit(self, fit) -> None:
        """One inner-loop least-squares run with an honest final state.

        Raises the evaluation budget for the duration (see
        :data:`_INNER_LOOP_MAXFEV`) and re-updates the model afterwards, so
        the cached model, the statistics and the parameters always describe
        the same point — never a mid-Jacobian probe.
        """
        import chisurf.core.settings

        options = chisurf.core.settings.cs_settings["optimization"]["leastsq"]
        previous = options.get("maxfev")
        options["maxfev"] = _INNER_LOOP_MAXFEV
        try:
            fit.run(
                record_result=False,
                estimate_errors=False,
                finalize=False,
                notify=False,
            )
            fit.model.update()
        except Exception:
            logger.exception("inner-loop Fit.run failed; keeping unoptimised state")
        finally:
            options["maxfev"] = previous

    def valid_actions(
        self,
        structure: Optional[ModelStructure] = None,
        state: Optional[FitState] = None,
    ) -> List[DiscreteAction]:
        """Structural moves that are legal from a structure.

        ``TERMINATE_FIT`` is only legal once the state's reduced χ² is
        statistically consistent with 1 — close to 1 or it is not done, and
        accepting a χ²ᵣ of 2 is exactly the mistake the gate exists for.
        ``state`` supplies the statistics; when it is omitted (a structure
        alone), the gate cannot apply and TERMINATE is offered.
        """
        s = structure if structure is not None else self.state.structure
        acceptable = True
        if state is not None:
            acceptable = bool(state.stats.chi2_acceptable)
        actions: List[DiscreteAction] = []
        if acceptable:
            actions.append(DiscreteAction.TERMINATE_FIT)
        if s.n_components < self.config.max_components:
            actions.append(DiscreteAction.ADD_LIFETIME_COMPONENT)
        if s.n_components > 1:
            actions.append(DiscreteAction.REMOVE_LIFETIME_COMPONENT)
        if self._anisotropy_groups():
            n_rot = s.n_rotations
            if n_rot < self.config.max_rotation_components:
                actions.append(DiscreteAction.ADD_ROTATION_COMPONENT)
            if n_rot >= 1:
                actions.append(DiscreteAction.REMOVE_ROTATION_COMPONENT)
        actions.append(DiscreteAction.TOGGLE_IRF_SHIFT)
        actions.append(DiscreteAction.TOGGLE_SCATTER)
        actions.append(DiscreteAction.TOGGLE_BACKGROUND)
        actions.extend(
            TOGGLE_PARAMETER_BASE + i for i in range(len(self._registry))
        )
        return actions

    def _drop_index(self, state: FitState) -> int:
        """Model-order index of the active pair contributing least intensity.

        ``f_i ∝ a_i·τ_i``; the least pair is what REMOVE_LIFETIME_COMPONENT
        retires. Used both to compute a next structure without fitting and by
        the action itself, so the two can never disagree.
        """
        active = [i for i, on in enumerate(state.structure.active) if on]
        contributions = [
            abs(state.amplitudes[k]) * abs(state.lifetimes[k])
            for k in range(state.structure.n_components)
        ]
        return active[int(np.argmin(contributions))]

    def next_structure(self, state: FitState, action: DiscreteAction) -> ModelStructure:
        """The structural result of an action, computed from the mask alone.

        No fitting happens here — the tree uses it to refuse actions that
        would recreate a structure already on the current path (cycle
        prevention), because a toggle that is flipped back is a wasted
        simulation, and a prior that keeps flipping it can spend a whole
        search budget going in circles.
        """
        s = state.structure
        if action == DiscreteAction.ADD_LIFETIME_COMPONENT:
            active = list(s.active)
            active[active.index(False)] = True
            return ModelStructure(tuple(active), s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width, s.toggles)
        if action == DiscreteAction.REMOVE_LIFETIME_COMPONENT:
            active = list(s.active)
            active[self._drop_index(state)] = False
            return ModelStructure(tuple(active), s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width, s.toggles)
        if action == DiscreteAction.TOGGLE_IRF_SHIFT:
            return ModelStructure(s.active, not s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width, s.toggles)
        if action == DiscreteAction.TOGGLE_SCATTER:
            return ModelStructure(s.active, s.fit_irf_shift, not s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width, s.toggles)
        if action == DiscreteAction.TOGGLE_BACKGROUND:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  not s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width, s.toggles)
        if action == DiscreteAction.ADD_ROTATION_COMPONENT:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width,
                                  s.toggles, s.rotations + (True,))
        if action == DiscreteAction.REMOVE_ROTATION_COMPONENT:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width,
                                  s.toggles, s.rotations[:-1])
        if isinstance(action, int) and action >= TOGGLE_PARAMETER_BASE:
            slot = action - TOGGLE_PARAMETER_BASE
            toggles = list(s.toggles)
            if slot >= len(toggles):
                return s
            toggles[slot] = not toggles[slot]
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, s.fit_state_width,
                                  tuple(toggles))
        if action == DiscreteAction.TOGGLE_STATE_WIDTH:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states, s.fit_donor_only,
                                  s.fit_donor_lifetime, not s.fit_state_width,
                                  s.toggles)
        if action == DiscreteAction.TERMINATE_FIT:
            return s
        raise ValueError(f"unknown action: {action!r}")

    def apply_best(self, state: FitState) -> FitState:
        """Leave the environment's fit — the user's fit — in a given state.

        The search explores by mutating the fit and restoring; this is the
        final restore: parameters, fix/free mask, one inner-loop
        optimisation, and a *compaction* — components the winning model does
        not use are removed from the model entirely (not zero-and-fixed), so
        the parameter table, the exports and the plot legends show exactly
        the winning model, with its components sorted from large to small.
        """
        self._restore(state)
        self._compact_lifetimes(state)
        self.state = self._finish()
        return self.state

    def _compact_lifetimes(self, state: FitState) -> None:
        """Physically drop unused lifetime pairs; order survivors large→small.

        Sorting is order-invariant for a sum of exponentials (each amplitude
        travels with its lifetime), so reporting large → small costs nothing
        and is what a decay table should read like.
        """
        for group in self._lifetime_groups:
            # Keep the values that the final *member* optimisation found.
            # A grouped VV/VH fit has distinct parameter objects per channel;
            # copying the selected member into all of them here destroyed the
            # joint optimum immediately before it reached the UI.
            keep = sorted(
                (
                    (float(tau.value), float(amp.value))
                    for tau, amp in zip(group._lifetimes, group._amplitudes)
                    if not (tau.fixed and amp.fixed) and abs(float(amp.value)) > 0.0
                ),
                key=lambda row: row[0],
                reverse=True,
            )
            while len(group) > 0:
                group.pop()
            for tau, amp in keep:
                group.append(
                    amplitude=abs(amp),
                    lifetime=tau,
                    lower_bound_lifetime=self.config.tau_bounds[0],
                    upper_bound_lifetime=self.config.tau_bounds[1],
                    bound_on_lifetime=True,
                )

    def _sort_rotation_groups(self) -> None:
        """Present rotational correlation pairs in descending time order."""
        for anisotropy in self._anisotropy_groups():
            rows = sorted(
                [(float(rho.value), float(b.value), bool(rho.fixed), bool(b.fixed))
                 for rho, b in zip(anisotropy._rhos, anisotropy._bs)],
                key=lambda row: row[0], reverse=True,
            )
            for rho_p, b_p, (rho, b, rho_fixed, b_fixed) in zip(
                anisotropy._rhos, anisotropy._bs, rows
            ):
                rho_p.value, b_p.value = rho, b
                rho_p.fixed, b_p.fixed = rho_fixed, b_fixed

    def apply_action(self, state: FitState, action: DiscreteAction) -> FitState:
        """Functional transition: restore, flip the mask, optimise, snapshot.

        The embedded inner loop is the fit's own :meth:`Fit.run
        <chisurf.core.fitting.fit.Fit.run>` — one call, every free parameter
        (lifetimes, amplitudes, shift, scatter, background) refined together,
        exactly as the Fit button does.
        """
        if action not in self.valid_actions(state.structure):
            raise ValueError(f"action {action} is not valid from {state.structure}")
        if action == DiscreteAction.TERMINATE_FIT:
            return state

        self._restore(state)

        if action == DiscreteAction.ADD_LIFETIME_COMPONENT:
            return self._apply_add(state)
        elif action == DiscreteAction.REMOVE_LIFETIME_COMPONENT:
            drop = self._drop_index(state)
            self._lifetimes._amplitudes[drop].value = 0.0
            self._lifetimes._amplitudes[drop].fixed = True
            self._lifetimes._lifetimes[drop].fixed = True
        elif action == DiscreteAction.TOGGLE_IRF_SHIFT:
            self._model.convolve._ts.fixed = not self._model.convolve._ts.fixed
        elif action == DiscreteAction.TOGGLE_SCATTER:
            self._model.generic._sc.fixed = not self._model.generic._sc.fixed
        elif action == DiscreteAction.TOGGLE_BACKGROUND:
            self._model.generic._bg.fixed = not self._model.generic._bg.fixed
        elif action == DiscreteAction.ADD_ROTATION_COMPONENT:
            return self._apply_rotation_add(state)
        elif action == DiscreteAction.REMOVE_ROTATION_COMPONENT:
            for anisotropy in self._anisotropy_groups():
                if len(anisotropy) > 0:
                    anisotropy._rhos.pop()
                    anisotropy._bs.pop()
        elif isinstance(action, int) and action >= TOGGLE_PARAMETER_BASE:
            slot = action - TOGGLE_PARAMETER_BASE
            if slot < len(self._registry):
                self._registry[slot][1].fixed = not self._registry[slot][1].fixed

        return self._finish()

    def _apply_rotation_add(self, state: FitState) -> FitState:
        """ADD a rotation component with a multi-start on its correlation time.

        Rotational correlation times span decades (sub-ns side chains to
        >10 ns whole-body tumbling), and the anisotropy amplitude trades
        against r0, so one warm start is exactly how a good branch gets
        scored as useless. A handful of spread starts, best kept.
        """
        anisotropy_groups = self._anisotropy_groups()
        n_target = state.structure.n_rotations + 1
        best_state: Optional[FitState] = None
        best_rho: Optional[float] = None
        for rho0 in (0.5, 2.0, 10.0):
            self._restore(state)
            for anisotropy in anisotropy_groups:
                while len(anisotropy) < n_target:
                    anisotropy.add_rotation(b=0.2, rho=rho0)
                if anisotropy._rhos:
                    anisotropy._rhos[-1].value = rho0
                if anisotropy._bs:
                    anisotropy._bs[-1].value = 0.2
            candidate = self._finish()
            if best_state is None or \
                    candidate.stats.reward > best_state.stats.reward:
                best_state = candidate
                best_rho = rho0
        # Leave the fit in the best candidate's configuration: the state the
        # caller receives must describe the model the fit actually holds.
        self._restore(state)
        for anisotropy in anisotropy_groups:
            while len(anisotropy) < n_target:
                anisotropy.add_rotation(b=0.2, rho=best_rho or 2.0)
            if anisotropy._rhos:
                anisotropy._rhos[-1].value = best_rho or 2.0
        return self._finish()

    def _finish(self) -> FitState:
        """The end of every action: refresh, optimise, sort, snapshot."""
        self._model.update()
        self._optimize_runs()
        self._sort_lifetime_groups()
        self._sort_rotation_groups()
        return self._snapshot()

    def _sort_lifetime_groups(self) -> None:
        """Order every lifetime group's components from large to small.

        The model sum is order-invariant, so this is a pure re-assignment of
        values — each amplitude travels with its lifetime, bounds and error
        estimates travel with their parameter — and it is what makes the
        outputs the user reads (parameter table, logs) sorted from large to
        small no matter which order the optimiser left them in.
        """
        for group in self._lifetime_groups:
            rows = []
            for tau_p, amp_p in zip(group._lifetimes, group._amplitudes):
                rows.append((
                    float(tau_p.value), float(amp_p.value),
                    bool(tau_p.fixed), bool(amp_p.fixed),
                    (tuple(tau_p.bounds) if tau_p.bounds_on else None),
                    bool(tau_p.bounds_on),
                    getattr(tau_p, "error_estimate", None),
                    getattr(amp_p, "error_estimate", None),
                ))
            rows.sort(key=lambda row: row[0], reverse=True)
            for i, (tau, amp, tau_fixed, amp_fixed, bounds, bounds_on,
                    tau_ee, amp_ee) in enumerate(rows):
                group._lifetimes[i].value = tau
                group._lifetimes[i].fixed = tau_fixed
                group._amplitudes[i].value = amp
                group._amplitudes[i].fixed = amp_fixed
                if bounds is not None:
                    group._lifetimes[i].bounds = bounds
                    group._lifetimes[i].bounds_on = True
                if tau_ee is not None:
                    group._lifetimes[i].error_estimate = tau_ee
                if amp_ee is not None:
                    group._amplitudes[i].error_estimate = amp_ee

    def _optimize_runs(self) -> None:
        """The inner loop proper. The FRET environment overrides this to
        run the donor reference first and frozen (see
        :meth:`FretEnv._run_inner`)."""
        self._run_fit(self.fit)

    def _apply_add(self, state: FitState) -> FitState:
        """ADD with a multi-start on the new component's lifetime.

        A single warm start (shortest existing tau / spacing) can land the
        joint fit in a poor local optimum, which makes the ADD branch *look*
        bad to the tree and the search never returns to it. A handful of
        cheap fits from spread starting values — the same philosophy as the
        model's own non-degenerate seeding — makes the branch's value
        trustworthy. The other actions keep their single fit: they move in a
        much smaller space.
        """
        lo, hi = self.config.tau_bounds
        active_taus = [t for t, on in
                       zip(state.lifetimes, state.structure.active) if on and t > 0]
        if active_taus:
            shortest, longest = min(active_taus), max(active_taus)
            candidates = [
                shortest / self.config.component_spacing,
                float(np.sqrt(min(active_taus) * max(active_taus))),
                longest * self.config.component_spacing,
                float(np.clip(self.config.default_lifetime, lo, hi)),
            ]
        else:
            candidates = [self.config.default_lifetime]
        # Deduplicate against the resolution of the bounds; drop near-duplicates.
        unique: List[float] = []
        for tau in candidates:
            tau = float(np.clip(tau, lo, hi))
            if all(abs(tau - other) > 0.05 * other for other in unique):
                unique.append(tau)

        best_state: Optional[FitState] = None
        for tau0 in unique:
            self._restore(state)
            index = list(state.structure.active).index(False)
            tau_p = self._lifetimes._lifetimes[index]
            amp_p = self._lifetimes._amplitudes[index]
            tau_p.value = tau0
            amp_p.value = 1.0 / max(state.structure.n_components, 1)
            tau_p.fixed = False
            amp_p.fixed = False
            self._model.update()
            self._optimize_runs()
            candidate = self._snapshot()
            if best_state is None or \
                    candidate.stats.reward > best_state.stats.reward:
                best_state = candidate
        assert best_state is not None
        return best_state

    # ------------------------------------------------------------------ #
    # Gymnasium-style API                                                #
    # ------------------------------------------------------------------ #

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Start an episode from the minimal model: one component, no nuisances.

        Returns the observation and an info dict with the initial state, in
        the Gymnasium convention. All pairs beyond the first are fixed at
        zero amplitude; the first is freed with a log-spaced starting
        lifetime and optimised.

        One nuisance starts *on*: when the model's IRF is synthetic (no
        measured curve), its width and skew are model parameters — the
        builder's own convention frees them — and a search that starts with
        them pinned analyses every candidate against a wrong prompt. That is
        the "simulator with a non-matching initial IRF" trap: nothing
        structural can repair a mis-shaped instrument response, and the tree
        wastes its budget inventing lifetime components to imitate it.
        """
        if seed is not None:
            np.random.default_rng(seed)
        options = dict(options or {})
        n0 = max(1, int(options.get("n_components", 1)))
        n0 = min(n0, int(self.config.max_components))

        synthetic_irf = getattr(self._model.convolve, "_irf", None) is None
        if synthetic_irf:
            self._seed_synthetic_irf_width()
        shape_on = tuple(
            synthetic_irf and name in ("iw", "ik")
            for name, _p in self._registry
        )

        lo, hi = self.config.tau_bounds
        taus0 = np.exp(
            np.linspace(math.log(lo * 3.0), math.log(hi / 3.0), n0)
        )
        active = tuple(i < n0 for i in range(len(self._lifetimes._lifetimes)))
        state = FitState(
            structure=ModelStructure(
                active=active,
                fit_irf_shift=bool(options.get("fit_irf_shift", False)),
                fit_scatter=bool(options.get("fit_scatter", False)),
                fit_background=bool(options.get("fit_background", False)),
                toggles=shape_on,
            ),
            lifetimes=taus0,
            amplitudes=np.full(n0, 1.0 / n0),
        )
        # Optimise the starting structure through the same single path.
        self._restore(state)
        self.state = self._finish()
        return self.observation(self.state), {"state": self.state}

    def step(
        self, action: DiscreteAction | int
    ) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Apply one structural action to the current state.

        Returns the ``(observation, reward, terminated, truncated, info)``
        quintuple. The reward of every step is the information-theoretic score
        of the resulting state; ``TERMINATE_FIT`` ends the episode with the
        unchanged state's score.
        """
        if self.state is None:
            raise RuntimeError("call reset() before step()")
        action_id = int(action)
        if action_id < TOGGLE_PARAMETER_BASE:
            action_id = DiscreteAction(action_id)
        self.state = self.apply_action(self.state, action_id)
        reward = float(self.state.stats.reward)
        terminated = action == DiscreteAction.TERMINATE_FIT
        truncated = False
        return (
            self.observation(self.state),
            reward,
            terminated,
            truncated,
            {"state": self.state},
        )


@dataclass(frozen=True)
class FretEnvConfig(EnvConfig):
    """Bounds of the FRET search on top of :class:`EnvConfig`.

    Parameters
    ----------
    max_fret_states : int
        Number of Gaussian distance states the model carries; the search may
        free any subset.
    distance_bounds : (float, float)
        Mean-distance bounds in Å, applied to every state.
    gaussian_sigma : float
        Starting width of a newly freed state (Å). The width is a fitted
        parameter once the state is active; this is only its seed.
    """

    max_fret_states: int = 3
    distance_bounds: Tuple[float, float] = (10.0, 120.0)
    gaussian_sigma: float = 6.0

    def __post_init__(self) -> None:
        super().__post_init__()
        lo, hi = self.distance_bounds
        if not 0.0 < lo < hi:
            raise ValueError(
                f"distance_bounds must satisfy 0 < lower < upper, got {self.distance_bounds}"
            )
        if int(self.max_fret_states) < 1:
            raise ValueError("max_fret_states must be at least 1")


class FretEnv(FitEnv):
    """Model-selection environment over a Gaussian-distance FRET fit.

    Same contract as :class:`FitEnv`, one level richer: the fix/free mask now
    spans the donor decay's lifetime pairs (shared with a donor-only
    reference fit when one is given — the classic *linked donor* analysis),
    the Gaussian distance states, and the FRET nuisance parameters
    (``xDOnly``, ``tauD0``, IRF shift, scatter, background). Everything is
    again an existing parameter of the existing
    :class:`~chisurf.core.models.tcspc.fret.GaussianModel`, refined by the
    fit's own ``run()``.

    Parameters
    ----------
    decay, irf, bin_width
        The donor-in-presence-of-acceptor measurement.
    donor_decay, donor_irf : array_like, optional
        The donor-only reference measurement. When given, the reference is
        fitted simultaneously (its own lifetime fit) and the FRET model's
        donor spectrum is linked to it (:attr:`Lifetime.link
        <chisurf.core.models.tcspc.lifetime.Lifetime.link>`), so structural
        actions on the donor components act on the shared spectrum.
    forster_radius : float
        R₀ in Å — calibration, held fixed (the existing builder's stance).
    donor_lifetime : float
        τ_D0 seed in ns.
    donor_reference_candidates : list of dict, optional
        ``[{"label": str, "data": (decay, irf, bin_width)}]`` — the datasets
        the caller (GUI) considers plausible references. Used only when no
        explicit reference was given.
    query_user : callable, optional
        See :class:`AgentQuestion`. When no donor reference is supplied and
        candidates exist, the environment asks which to link against — the
        user knows which dataset it is; the data does not. Without a
        callback the environment proceeds unlinked and logs that.
    config, period
        As for :class:`FitEnv`; ``config`` should be a :class:`FretEnvConfig`.
    """

    def __init__(
        self,
        decay: Optional[Sequence[float]] = None,
        irf: Optional[Sequence[float]] = None,
        bin_width: Optional[float] = None,
        *,
        donor_decay: Optional[Sequence[float]] = None,
        donor_irf: Optional[Sequence[float]] = None,
        fit: Any = None,
        donor_fit: Any = None,
        config: Optional[FretEnvConfig] = None,
        forster_radius: float = 52.0,
        donor_lifetime: float = 4.0,
        period: Optional[float] = None,
        initial_irf_shift: float = 0.0,
        donor_reference_candidates: Optional[List[Dict[str, Any]]] = None,
        query_user: Optional[QueryUser] = None,
    ):
        self.config = config if config is not None else FretEnvConfig()
        if fit is not None:
            # Operate on the user's own FRET fit — no private copy, no
            # transfer. The donor reference is the user's linked fit
            # (``donor.link``), a fit handed in explicitly, or one chosen
            # through ``query_user`` from the candidates.
            if getattr(fit.model, "fret_parameters", None) is None:
                raise ValueError("the fit's model is not a FRET model")
            self.fit = fit
            self.bin_width = float(fit.model.convolve.dt)
            linked_group = getattr(fit.model.donor, "_link", None)
            if donor_fit is None and linked_group is not None:
                self.donor_fit = getattr(linked_group, "_owning_fit", None)
                if self.donor_fit is None:
                    self.donor_fit = self._find_donor_fit(linked_group)
            elif donor_fit is not None:
                self.donor_fit = donor_fit
                fit.model.donor.link = donor_fit.model.lifetimes
            else:
                self.donor_fit = self._resolve_donor_fit(
                    donor_reference_candidates, query_user, fit
                )
            self.linked = self.donor_fit is not None
            self._setup_from_fit()
            for tau_p, amp_p in zip(self._model.donor._lifetimes,
                                    self._model.donor._amplitudes):
                if self.linked:
                    tau_p.fixed = True
                    amp_p.value = 0.0
                    amp_p.fixed = True
            # Unlinked: the user's own donor group carries the spectrum; grow
            # it so the donor-component actions have pairs to act on.
            if not self.linked:
                self._lifetimes = self._model.donor
                while len(self._lifetimes) < int(self.config.max_components):
                    self._lifetimes.append(
                        lower_bound_lifetime=self.config.tau_bounds[0],
                        upper_bound_lifetime=self.config.tau_bounds[1],
                    )
            else:
                self._lifetimes = self.donor_fit.model.lifetimes
            # Structural lifetime actions drive the linked reference's group
            # (linked mode) or the FRET fit's own donor group (unlinked).
            self._lifetime_groups = [self._lifetimes]
            self._fret = self._model.fret_parameters
            self._gaussians = self._model.gaussians
            self._link_donor_accounting()
            return
        if decay is None or irf is None or bin_width is None:
            raise ValueError("pass a fit or decay/irf/bin_width")
        donor_decay, donor_irf = self._resolve_donor_reference(
            donor_decay, donor_irf, donor_reference_candidates, query_user
        )
        self.linked = donor_decay is not None

        # Build the FRET fit (and the linked reference fit) directly — the
        # base class's lifetime fit would be thrown straight away.
        self.bin_width = float(bin_width)
        from chisurf.core.fluorescence.decay_fit_model import build_fret_fit

        self.fit = build_fret_fit(
            np.asarray(decay, dtype=float),
            bin_width=self.bin_width,
            n_states=int(self.config.max_fret_states),
            forster_radius=float(forster_radius),
            donor_lifetime=float(donor_lifetime),
            sigma=float(self.config.gaussian_sigma),
            distance_bounds=tuple(self.config.distance_bounds),
            irf=np.asarray(irf, dtype=float),
            period=period,
        )
        self._setup_from_fit()
        try:
            slo, shi = self.config.irf_shift_bounds
            self._model.convolve._ts.value = float(
                np.clip(initial_irf_shift, slo, shi))
        except Exception:
            logger.debug("could not seed the initial IRF shift")
        self._fret = self._model.fret_parameters
        self._gaussians = self._model.gaussians
        # The donor decay's lifetime group: the reference's (linked) or the
        # FRET model's own. Structural actions on donor components act here.
        if self.linked:
            from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit

            self.donor_fit = build_lifetime_fit(
                np.asarray(donor_decay, dtype=float),
                bin_width=self.bin_width,
                irf=np.asarray(donor_irf, dtype=float),
                n_components=int(self.config.max_components),
                tau_bounds=tuple(self.config.tau_bounds),
                period=period,
            )
            self._lifetimes = self.donor_fit.model.lifetimes
            self._model.donor.link = self._lifetimes
            for tau_p, amp_p in zip(self._model.donor._lifetimes,
                                    self._model.donor._amplitudes):
                tau_p.fixed = True
                amp_p.value = 0.0
                amp_p.fixed = True
        else:
            self.donor_fit = None
            self._lifetimes = self._model.donor
            # The FRET builder configures the donor group with a single pair;
            # grow it with its own append machinery so the ADD/REMOVE actions
            # have pairs to act on, exactly like the lifetime environment.
            while len(self._lifetimes) < int(self.config.max_components):
                self._lifetimes.append(
                    lower_bound_lifetime=self.config.tau_bounds[0],
                    upper_bound_lifetime=self.config.tau_bounds[1],
                )
        # Structural lifetime groups follow the linked reference in linked
        # mode; the FRET fit's own donor group otherwise.
        self._lifetime_groups = [self._lifetimes]
        self._link_donor_accounting()

    def _link_donor_accounting(self) -> None:
        """The reference's Poisson constants (its reward contribution)."""
        self._ln_factorial_donor = 0.0
        self._n_photons_donor = 0.0
        if self.donor_fit is not None:
            y_d = np.asarray(self.donor_fit.data.y, dtype=float)
            self._n_photons_donor = float(y_d.sum())
            self._ln_factorial_donor = float(gammaln(y_d + 1.0).sum())
        # The linked reference's parameter table joins the generic payload:
        # its lifetimes are part of the searched state.
        self._parameter_fits = (
            ([self.donor_fit] if self.donor_fit is not None else [])
            + list(self._fits)
        )
        self.state = None

    @staticmethod
    def _find_donor_fit(lifetime_group: Any) -> Any:
        """The fit whose lifetimes group a link points at, from the open fits."""
        import chisurf as cs

        for candidate in cs.fits:
            if getattr(candidate, "model", None) is not None and \
                    getattr(candidate.model, "lifetimes", None) is lifetime_group:
                return candidate
        return None

    def _resolve_donor_fit(self, candidates, query_user, fit) -> Any:
        """Ask for the donor-only reference fit when none is attached.

        The candidates are *fits* (the user's own objects); a remote fitting
        server never enters the picture, because whatever the user picks is
        linked and refined in-process.
        """
        if not candidates or query_user is None:
            logger.info(
                "FRET model selection: no donor reference attached; fitting "
                "without a linked donor decay."
            )
            return None
        question = AgentQuestion(
            kind="donor_reference",
            prompt=(
                "Link a donor-only reference decay to this FRET fit?\n"
                "The reference fixes the donor lifetime spectrum the "
                "distances are measured against."
            ),
            choices=[str(c["label"]) for c in candidates]
            + ["Fit without donor reference", "Cancel"],
            datasets=[c["fit"] for c in candidates],
        )
        answer = query_user(question)
        if answer is None or answer >= len(question.datasets) + 1:
            raise RuntimeError("MCTS model selection cancelled by the user")
        if answer == len(question.datasets):
            return None
        return question.datasets[answer]

    # ------------------------------------------------------------------ #
    # The donor reference question                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_donor_reference(
        donor_decay, donor_irf, candidates, query_user
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Ask for the donor reference when it is missing.

        With a callback the question goes to the user (message box in the
        GUI); the answer selects a dataset, declines linking, or cancels the
        search. Without a callback the analysis proceeds unlinked and the
        choice is logged — silently guessing a reference would bias every
        fitted distance.
        """
        if donor_decay is not None or not candidates or query_user is None:
            if donor_decay is None:
                logger.info(
                    "FRET model selection: no donor reference given; fitting "
                    "without a linked donor decay."
                )
            return donor_decay, donor_irf
        question = AgentQuestion(
            kind="donor_reference",
            prompt=(
                "Link a donor-only reference decay to this FRET fit?\n"
                "The reference fixes the donor lifetime spectrum the "
                "distances are measured against."
            ),
            choices=[str(c["label"]) for c in candidates]
            + ["Fit without donor reference", "Cancel"],
            datasets=[c["data"] for c in candidates],
        )
        answer = query_user(question)
        if answer is None or answer >= len(question.datasets) + 1:
            raise RuntimeError("MCTS model selection cancelled by the user")
        if answer == len(question.datasets):
            logger.info("FRET model selection: user chose to fit without a reference.")
            return None, None
        decay_ref, irf_ref, _dt = question.datasets[answer]
        return (
            np.asarray(decay_ref, dtype=float),
            np.asarray(irf_ref, dtype=float),
        )

    # ------------------------------------------------------------------ #
    # Structure: the extended fix/free mask                               #
    # ------------------------------------------------------------------ #

    def _semantic_parameter_ids(self) -> set:
        ids = super()._semantic_parameter_ids()
        for name in ("_xDonly", "_tauD0", "_forster_radius", "_kappa2"):
            p = getattr(self._model.fret_parameters, name, None)
            if p is not None:
                ids.add(id(p))
        for container in ("_gaussianMeans", "_gaussianSigma",
                          "_gaussianAmplitudes", "_gaussianShape"):
            for p in getattr(self._model.gaussians, container, []):
                ids.add(id(p))
        return ids

    #: Same fixed-width semantic block as the lifetime adapter (the aniso
    #: slot carries the rotation count here).
    n_structure_features = 7 + N_TOGGLE_SLOTS

    def _structure_of_fit(self) -> ModelStructure:
        base = super()._structure_of_fit()
        fret_states = tuple(
            not (m.fixed and x.fixed) and abs(x.value) > 0.0
            for m, x in zip(self._gaussians._gaussianMeans,
                            self._gaussians._gaussianAmplitudes)
        )
        return ModelStructure(
            active=base.active,
            fit_irf_shift=base.fit_irf_shift,
            fit_scatter=base.fit_scatter,
            fit_background=base.fit_background,
            fret_states=fret_states,
            fit_donor_only=not self._fret._xDonly.fixed,
            # In linked mode the donor lifetime is the reference's business;
            # freeing tauD0 against a linked spectrum is not identifiable.
            fit_donor_lifetime=(not self._fret._tauD0.fixed)
            and not self.linked,
            fit_state_width=any(
                not s.fixed for s in self._gaussians._gaussianSigma[:len(fret_states)]
            ) and any(fret_states),
            toggles=base.toggles,
            rotations=base.rotations,
        )

    def structure_features(self, structure: ModelStructure) -> np.ndarray:
        """Six semantic features plus the padded generic-toggle bits."""
        toggles = np.zeros(N_TOGGLE_SLOTS, dtype=np.float32)
        for i, on in enumerate(structure.toggles[:N_TOGGLE_SLOTS]):
            toggles[i] = float(on)
        return np.concatenate(
            [
                np.array(
                    [
                        structure.n_components / max(self.config.max_components, 1),
                        float(structure.fit_irf_shift),
                        float(structure.fit_scatter),
                        float(structure.fit_background),
                        structure.n_fret_states / max(self.config.max_fret_states, 1),
                        float(structure.fit_donor_only),
                        structure.n_rotations
                        / max(self.config.max_rotation_components, 1),
                    ],
                    dtype=np.float32,
                ),
                toggles,
            ],
        ).astype(np.float32)

    def valid_actions(self, structure: Optional[ModelStructure] = None,
                     state: Optional[FitState] = None) -> List[DiscreteAction]:
        actions = super().valid_actions(structure, state)
        s = structure if structure is not None else self.state.structure
        if s.n_fret_states < self.config.max_fret_states:
            actions.append(DiscreteAction.ADD_FRET_STATE)
        if s.n_fret_states > 1:
            actions.append(DiscreteAction.REMOVE_FRET_STATE)
        actions.append(DiscreteAction.TOGGLE_DONOR_ONLY)
        if not self.linked:
            actions.append(DiscreteAction.TOGGLE_DONOR_LIFETIME)
        actions.append(DiscreteAction.TOGGLE_STATE_WIDTH)
        anisotropy_groups = self._anisotropy_groups()
        if anisotropy_groups:
            if s.n_rotations < self.config.max_rotation_components:
                actions.append(DiscreteAction.ADD_ROTATION_COMPONENT)
            if s.n_rotations >= 1:
                actions.append(DiscreteAction.REMOVE_ROTATION_COMPONENT)
        return actions

    def next_structure(self, state: FitState, action: DiscreteAction) -> ModelStructure:
        s = state.structure
        tail = (s.fit_donor_only, s.fit_donor_lifetime, s.fit_state_width,
                s.toggles, s.rotations)
        if action == DiscreteAction.ADD_FRET_STATE:
            states = list(s.fret_states)
            states[states.index(False)] = True
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, tuple(states), *tail)
        if action == DiscreteAction.REMOVE_FRET_STATE:
            states = list(s.fret_states)
            active = [i for i, on in enumerate(states) if on]
            drop = active[int(np.argmin([
                abs(state.fractions[k]) for k in range(s.n_fret_states)]))]
            states[drop] = False
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, tuple(states), *tail)
        if action == DiscreteAction.TOGGLE_DONOR_ONLY:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states,
                                  not s.fit_donor_only, s.fit_donor_lifetime,
                                  s.fit_state_width, s.toggles)
        if action == DiscreteAction.TOGGLE_DONOR_LIFETIME:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states,
                                  s.fit_donor_only, not s.fit_donor_lifetime,
                                  s.fit_state_width, s.toggles, s.rotations)
        if action == DiscreteAction.ADD_ROTATION_COMPONENT:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states,
                                  s.fit_donor_only, s.fit_donor_lifetime,
                                  s.fit_state_width, s.toggles,
                                  s.rotations + (True,))
        if action == DiscreteAction.REMOVE_ROTATION_COMPONENT:
            return ModelStructure(s.active, s.fit_irf_shift, s.fit_scatter,
                                  s.fit_background, s.fret_states,
                                  s.fit_donor_only, s.fit_donor_lifetime,
                                  s.fit_state_width, s.toggles,
                                  s.rotations[:-1])
        return super().next_structure(state, action)

    # ------------------------------------------------------------------ #
    # Restore, mutate, optimise — the existing fitters do the work        #
    # ------------------------------------------------------------------ #

    def _restore(self, state: FitState) -> None:
        super()._restore(state)
        lo, hi = self.config.distance_bounds
        k = 0
        for mean_p, sigma_p, amp_p in zip(
            self._gaussians._gaussianMeans, self._gaussians._gaussianSigma,
            self._gaussians._gaussianAmplitudes,
        ):
            if k < len(state.structure.fret_states) and state.structure.fret_states[k]:
                mean_p.value = float(np.clip(state.distances[k], lo, hi))
                sigma_p.value = float(state.sigmas[k])
                amp_p.value = float(state.fractions[k])
                mean_p.fixed = False
                amp_p.fixed = False
                sigma_p.fixed = not state.structure.fit_state_width
                k += 1
            else:
                amp_p.value = 0.0
                mean_p.fixed = True
                amp_p.fixed = True
                sigma_p.fixed = True
        self._fret._xDonly.value = float(state.donor_only_fraction) \
            if state.structure.fit_donor_only else 0.0
        self._fret._xDonly.fixed = not state.structure.fit_donor_only
        self._fret._tauD0.fixed = not (state.structure.fit_donor_lifetime
                                       and not self.linked)

    def _optimize_runs(self) -> None:
        """Linked donor analysis: reference first, then the FRET fit.

        The two runs are strictly ordered and the reference's parameters are
        frozen during the FRET run: the FRET model's parameter discovery sees
        through ``donor.link``, and without freezing, the FRET fit would
        re-fit the donor spectrum against the FRET measurement — the
        reference would stop being a reference and the τ_D0/distance
        degeneracy would come straight back.
        """
        if self.donor_fit is not None:
            self._run_fit(self.donor_fit)
            frozen = []
            for p in self._lifetimes.parameters_all:
                if not p.fixed:
                    p.fixed = True
                    frozen.append(p)
            try:
                self._run_fit(self.fit)
            finally:
                for p in frozen:
                    p.fixed = False
        else:
            self._run_fit(self.fit)

    def apply_action(self, state: FitState, action: DiscreteAction) -> FitState:
        if action not in self.valid_actions(state.structure):
            raise ValueError(f"action {action} is not valid from {state.structure}")
        if action == DiscreteAction.TERMINATE_FIT:
            return state
        if action == DiscreteAction.ADD_FRET_STATE:
            return self._apply_fret_add(state)
        self._restore(state)
        if action == DiscreteAction.REMOVE_FRET_STATE:
            states = list(state.structure.fret_states)
            active = [i for i, on in enumerate(states) if on]
            drop = active[int(np.argmin([
                abs(state.fractions[k]) for k in range(state.structure.n_fret_states)]))]
            self._gaussians._gaussianAmplitudes[drop].value = 0.0
            self._gaussians._gaussianAmplitudes[drop].fixed = True
            self._gaussians._gaussianMeans[drop].fixed = True
        elif action == DiscreteAction.TOGGLE_DONOR_ONLY:
            self._fret._xDonly.fixed = not self._fret._xDonly.fixed
        elif action == DiscreteAction.TOGGLE_DONOR_LIFETIME:
            self._fret._tauD0.fixed = not self._fret._tauD0.fixed
            self._model.donor._lifetimes[0].fixed = self._fret._tauD0.fixed
        elif action == DiscreteAction.TOGGLE_STATE_WIDTH:
            free = not state.structure.fit_state_width
            for i, on in enumerate(state.structure.fret_states):
                if on:
                    self._gaussians._gaussianSigma[i].fixed = not free
        elif action == DiscreteAction.ADD_ROTATION_COMPONENT:
            return self._apply_rotation_add(state)
        elif action == DiscreteAction.REMOVE_ROTATION_COMPONENT:
            for anisotropy in self._anisotropy_groups():
                if len(anisotropy) > 0:
                    anisotropy._rhos.pop()
                    anisotropy._bs.pop()
        else:
            return super().apply_action(state, action)
        return self._finish()

    def _apply_fret_add(self, state: FitState) -> FitState:
        """ADD_FRET_STATE with a multi-start on the new state's mean.

        Distance is the parameter a FRET fit is most sensitive to and least
        linear in, so — like the lifetime ADD — the branch is evaluated from
        several spread starting means and keeps the best.
        """
        lo, hi = self.config.distance_bounds
        active_r = [r for r, on in zip(state.distances, state.structure.fret_states)
                    if on]
        r0 = float(self._fret._forster_radius.value)
        candidates = [0.7 * r0, r0, 1.3 * r0]
        if active_r:
            candidates.append(min(active_r) - 10.0)
            candidates.append(max(active_r) + 10.0)
        unique: List[float] = []
        for r in candidates:
            r = float(np.clip(r, lo, hi))
            if all(abs(r - other) > 0.05 * other for other in unique):
                unique.append(r)

        best_state: Optional[FitState] = None
        for r0_candidate in unique:
            self._restore(state)
            index = list(state.structure.fret_states).index(False)
            mean_p = self._gaussians._gaussianMeans[index]
            amp_p = self._gaussians._gaussianAmplitudes[index]
            self._gaussians._gaussianSigma[index].value = self.config.gaussian_sigma
            mean_p.value = r0_candidate
            amp_p.value = 1.0 / max(state.structure.n_fret_states, 1)
            mean_p.fixed = False
            amp_p.fixed = False
            self._model.update()
            self._optimize_runs()
            candidate = self._snapshot()
            if best_state is None or candidate.stats.reward > best_state.stats.reward:
                best_state = candidate
        assert best_state is not None
        return best_state

    # ------------------------------------------------------------------ #
    # Statistics: the FRET decay plus the linked reference                #
    # ------------------------------------------------------------------ #

    def _poisson_log_likelihood(self) -> float:
        ln_l = super()._poisson_log_likelihood()
        if self.donor_fit is not None:
            y = np.asarray(self.donor_fit.data.y, dtype=float)
            m = np.asarray(self.donor_fit.model.y, dtype=float)
            expected = np.maximum(m, _MODEL_FLOOR)
            with np.errstate(divide="ignore", invalid="ignore"):
                terms = y * np.log(expected) - expected
            ln_l += float(np.sum(np.where(np.isfinite(terms), terms, 0.0)))
            ln_l -= self._ln_factorial_donor
        return ln_l

    def _free_parameter_ids(self) -> set:
        ids = {id(p) for p in self._model.parameters}
        if self.donor_fit is not None:
            ids.update(id(p) for p in self.donor_fit.model.parameters)
        return ids

    def _stats_of_fit(self) -> FitStats:
        """Reward over the combined evidence; DW and χ²ᵣ from the FRET fit."""
        base = super()._stats_of_fit()
        k = len(self._free_parameter_ids())
        ln_l = self._poisson_log_likelihood()
        n_photons = self.n_photons + self._n_photons_donor
        reward = (
            ln_l
            - 0.5 * k * math.log(max(n_photons, 1.0))
            - self.config.gamma_autocorr * base.autocorr_score
        )
        return FitStats(
            chi2_reduced=base.chi2_reduced,
            log_likelihood=ln_l,
            durbin_watson=base.durbin_watson,
            autocorr_score=base.autocorr_score,
            n_photons=n_photons,
            n_free_parameters=k,
            dof=max(self.n_channels + int(self._n_photons_donor > 0) * self.n_channels - int(k), 1),
            chi2_acceptable=self._chi2_acceptable(base.chi2_reduced, k),
            reward=reward,
        )

    def _snapshot(self) -> FitState:
        state = super()._snapshot()
        structure = state.structure
        active = [i for i, on in enumerate(structure.fret_states) if on]
        return FitState(
            structure=structure,
            lifetimes=state.lifetimes,
            amplitudes=state.amplitudes,
            irf_shift=state.irf_shift,
            scatter=state.scatter,
            background=state.background,
            prediction=state.prediction,
            residuals=state.residuals,
            stats=state.stats,
            distances=np.array(
                [self._gaussians._gaussianMeans[i].value for i in active], dtype=float),
            sigmas=np.array(
                [self._gaussians._gaussianSigma[i].value for i in active], dtype=float),
            fractions=np.array(
                [self._gaussians._gaussianAmplitudes[i].value for i in active], dtype=float),
            donor_only_fraction=float(self._fret.xDOnly),
            rotation_times=state.rotation_times,
            rotation_amplitudes=state.rotation_amplitudes,
            model_parameter_values=state.model_parameter_values,
            model_parameter_fixed=state.model_parameter_fixed,
        )

    def reset(
        self,
        *,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Start from the minimal FRET model: one donor component, one state."""
        options = dict(options or {})
        options.setdefault("n_components", 1)
        obs, info = super().reset(seed=seed, options=options)
        # Free exactly one distance state at a sensible mean; fix the rest.
        structure = self._structure_of_fit()
        self._restore(FitState(
            structure=ModelStructure(
                active=structure.active,
                fit_irf_shift=structure.fit_irf_shift,
                fit_scatter=structure.fit_scatter,
                fit_background=structure.fit_background,
                fret_states=tuple(i == 0 for i in range(len(structure.fret_states))),
                fit_donor_only=structure.fit_donor_only,
                fit_donor_lifetime=structure.fit_donor_lifetime,
            ),
            lifetimes=self.state.lifetimes,
            amplitudes=self.state.amplitudes,
            model_parameter_values=self.state.model_parameter_values,
            model_parameter_fixed=self.state.model_parameter_fixed,
            distances=np.array([float(self._fret.forster_radius)]),
            sigmas=np.array([self.config.gaussian_sigma]),
            fractions=np.array([1.0]),
            donor_only_fraction=0.1,
        ))
        self.state = self._finish()
        return self.observation(self.state), {"state": self.state}
