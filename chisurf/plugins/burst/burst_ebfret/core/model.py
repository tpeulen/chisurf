"""The data an ebFRET session holds: time series, analyses and controls.

These are the fields of ebFRET's ``ebfret.ui.MainWindow`` -- ``series``,
``analysis`` and ``controls`` -- as plain dataclasses, so the algorithms, the
file formats, the backend service and the GUI all speak about the same objects
under the same names.

Conventions carried over from the reference unchanged, because the file
formats depend on them:

* **Indices are 1-based where ebFRET's are.** ``Series.crop_min`` /
  ``crop_max`` are inclusive 1-based frame numbers, ``Series.time`` runs
  ``1..T``, and ``Viterbi.state`` holds state numbers ``1..K``. They are
  written to ``.dat``/SMD/session files as they are, so converting them to
  0-based here would move every exported number by one.
* **Analyses are keyed by their number of states**, as ``analysis(k)`` is in
  MATLAB: ``Session.analysis[3]`` is the three-state model.
* **Hyperparameters use the Normal-Wishart names** ``mu, beta, W, nu, A, pi``
  (with ``D = 1``), not the Normal-Gamma ``m, beta, a, b`` -- the reference
  converts with ``a = nu / 2`` and ``b = 1 / (2 W)`` wherever it needs them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

__all__ = [
    "HmmParams",
    "Expect",
    "Viterbi",
    "Series",
    "Analysis",
    "Controls",
    "DEFAULT_CONTROLS",
]


@dataclass
class HmmParams:
    """Prior or posterior hyperparameters of a ``K``-state Gaussian HMM.

    Attributes
    ----------
    mu : numpy.ndarray
        Normal-Wishart state means, shape ``(K,)``.
    beta : numpy.ndarray
        Normal-Wishart occupation counts, shape ``(K,)``.
    W : numpy.ndarray
        Normal-Wishart precision scales, shape ``(K,)``.
    nu : numpy.ndarray
        Normal-Wishart degrees of freedom, shape ``(K,)``.
    A : numpy.ndarray
        Dirichlet parameters of each transition-matrix row, shape ``(K, K)``.
    pi : numpy.ndarray
        Dirichlet parameters of the initial-state distribution, shape ``(K,)``.
    """

    mu: np.ndarray
    beta: np.ndarray
    W: np.ndarray
    nu: np.ndarray
    A: np.ndarray
    pi: np.ndarray

    @property
    def n_states(self) -> int:
        """Number of hidden states ``K``."""
        return int(np.asarray(self.mu).shape[0])

    def copy(self) -> HmmParams:
        """Return a deep copy with freshly allocated float arrays."""
        return HmmParams(
            **{
                name: np.array(getattr(self, name), dtype=float)
                for name in ("mu", "beta", "W", "nu", "A", "pi")
            }
        )


@dataclass
class Expect:
    """Expected sufficient statistics of one trace under ``q(z)``.

    The ``expect(n)`` struct ebFRET's ``run_vbayes`` stores, and what the
    empirical-Bayes ``h_step`` re-uses. Shapes are for ``K`` states.

    Attributes
    ----------
    z : numpy.ndarray
        ``sum_{t>=2} gamma(t, k)``, shape ``(K,)``.
    z1 : numpy.ndarray
        ``gamma(1, k)``, shape ``(K,)``.
    zz : numpy.ndarray
        ``sum_t xi(t, k, l)``, shape ``(K, K)``.
    x : numpy.ndarray
        Occupancy-weighted mean observation per state, shape ``(K,)``.
    xx : numpy.ndarray
        Occupancy-weighted second moment per state, shape ``(K,)``.
    """

    z: np.ndarray
    z1: np.ndarray
    zz: np.ndarray
    x: np.ndarray
    xx: np.ndarray


@dataclass
class Viterbi:
    """The most likely state path of one trace.

    Attributes
    ----------
    state : numpy.ndarray
        State number ``1..K`` per frame of the cropped trace, shape ``(T,)``.
    mean : numpy.ndarray
        Posterior mean ``mu`` of that state per frame, shape ``(T,)``.
    """

    state: np.ndarray
    mean: np.ndarray


@dataclass
class Series:
    """One donor/acceptor time series, as ebFRET's ``series(n)``.

    Attributes
    ----------
    file : str
        Base name of the file it was read from (no directory, no extension).
    label : str
        The label the file gave it.
    group : str
        ``"group 1"``, ``"group 2"``... -- one group per load that appended.
    time : numpy.ndarray
        Frame index, ``1..T`` for raw data (an SMD ``index`` otherwise).
    signal : numpy.ndarray
        The analysed signal, ``(acceptor + eps) / (acceptor + donor + eps)``.
    donor, acceptor : numpy.ndarray
        Raw intensities; zeros when an SMD was loaded as a FRET signal.
    crop_min, crop_max : int
        Inclusive 1-based range of frames that enter the analysis.
    exclude : bool
        Leave this series out of the analysis entirely.
    """

    file: str
    label: str
    group: str
    time: np.ndarray
    signal: np.ndarray
    donor: np.ndarray
    acceptor: np.ndarray
    crop_min: int
    crop_max: int
    exclude: bool = False

    @property
    def length(self) -> int:
        """Number of frames in the uncropped series."""
        return int(np.asarray(self.signal).shape[0])


@dataclass
class Analysis:
    """The ``K``-state model of a session, as ebFRET's ``analysis(k)``.

    Per-series lists are indexed like ``Session.series``; an entry is ``None``
    where ebFRET stores an empty struct (the series is excluded, or has not
    been analysed yet).

    Attributes
    ----------
    states : int
        Number of states ``K`` (``analysis(k).dim.states``).
    prior : HmmParams or None
        The shared empirical-Bayes prior.
    posterior : list of HmmParams or None
        Per-series variational posterior.
    expect : list of Expect or None
        Per-series expected sufficient statistics.
    viterbi : list of Viterbi or None
        Per-series most likely state path.
    lowerbound : numpy.ndarray
        Per-series variational lower bound, shape ``(N,)``.
    restart : numpy.ndarray
        Per-series index of the restart that won, shape ``(N,)``; ``-1`` where
        no valid posterior was found.
    """

    states: int
    prior: HmmParams | None = None
    posterior: list = field(default_factory=list)
    expect: list = field(default_factory=list)
    viterbi: list = field(default_factory=list)
    lowerbound: np.ndarray = field(default_factory=lambda: np.zeros(0))
    restart: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))


@dataclass
class Controls:
    """The values of the main window's controls, as ``self.controls``.

    Defaults are the ones ``MainWindow``'s constructor passes to
    ``set_control``.

    Attributes
    ----------
    series_min, series_max, series_value : int
        The *Select Series* index control.
    ensemble_min, ensemble_max, ensemble_value : int
        The *Select States* index control.
    clip_min, clip_max : float
        Signal values are clipped to this range before analysis.
    min_states, max_states : int
        The *States* panel.
    restarts : int
        VBEM restarts per series (*Analysis* panel).
    run_analysis : bool
        The analysis loop is running.
    run_all : bool
        *All* (every state count) versus *Current* in the analysis popup.
    run_precision : float
        Relative lower-bound convergence threshold (*Precision*).
    scale_plots : bool
        View > *Normalize by Occupancy*.
    crop_margin : int
        Frames shown past ``crop_max`` in the time-series plots.
    show_viterbi, show_prior, show_posterior : bool
        The View menu checkmarks.
    """

    series_min: int = 0
    series_max: int = 0
    series_value: int = 0
    ensemble_min: int = 2
    ensemble_max: int = 6
    ensemble_value: int = 2
    clip_min: float = -0.5
    clip_max: float = 1.5
    min_states: int = 2
    max_states: int = 6
    restarts: int = 2
    run_analysis: bool = False
    run_all: bool = True
    run_precision: float = 1e-3
    scale_plots: bool = True
    crop_margin: int = 20
    show_viterbi: bool = True
    show_prior: bool = True
    show_posterior: bool = True


#: The constructor's defaults, for code that wants to compare against them.
DEFAULT_CONTROLS = Controls()

#: Default time-series colours, ``self.controls.colors`` (RGB in 0..1).
COLORS = {
    "obs": (0.4, 0.4, 0.4),
    "viterbi": (0.66, 0.33, 0.33),
    "donor": (0.33, 0.66, 0.33),
    "acceptor": (0.66, 0.33, 0.33),
}
