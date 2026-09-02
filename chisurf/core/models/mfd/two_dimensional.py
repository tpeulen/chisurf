"""Fitting kinetic models to the 2D MFD burst histogram.

The physics is in :mod:`chisurf.core.fluorescence.mfd`; this module is the fitting
surface over it — parameter groups, the model/view split, and the residual the
optimizer sees. Nothing here recomputes anything the compute layer already does.

Two models:

* :class:`Mfd2DModel` — states that do not exchange. This is what milestone 1a is
  fitted with, and the right starting point for any measurement: the static answer
  is what a dynamic one has to beat.
* :class:`Mfd2DKineticModel` — the same states with a fittable rate matrix, using
  the shared rate-matrix group rather than a private copy.

**Uncertainties are refused rather than quietly reported.** The histogram source
scores the same bursts through more than one marginal, so its summed deviance is an
M-estimator: the optimum is meaningful, the curvature is not. Asking this model for
parameter errors from the fit's covariance therefore raises, and points at the
burst-wise source or a bootstrap. That is enforced in code because the footnote
version of the rule is exactly the kind that goes unread, and confidently narrow
error bars look like success.
"""

from __future__ import annotations

import numpy as np

import chisurf as cs
from chisurf.core.fitting.kinetics import RateMatrixParameters
from chisurf.core.fitting.parameter import FittingParameter, FittingParameterGroup
from chisurf.core.fluorescence.mfd.fit import MfdKineticModel
from chisurf.core.fluorescence.mfd.patterns import FretState, Optics
from chisurf.core.fluorescence.mfd.seed import estimate_starting_values
from chisurf.core.fluorescence.mfd.sources import uncertainty_is_valid
from chisurf.core.models.model import ModelCurve

__all__ = [
    "Mfd2DModel",
    "MfdCalibration",
    "MfdStates",
    "MfdImageMixin",
    "get_mfd_residual_image",
]


def burst_payload(data):
    """Return the MFD objects a dataset carries, or ``None``.

    **Descends into a data group.** A reader returns an
    :class:`~chisurf.core.data.ExperimentDataCurveGroup`, and that is what the
    model combobox and the add-fit path hand to ``supports_data`` — not the curve
    inside it. A lookup that only inspected the object itself therefore found
    nothing, and the symptom was an *empty model list* for a dataset that had
    loaded perfectly well: no error, no warning, just no models to choose.

    A group holding an MFD curve is MFD data, so the payload of the first member
    that has one is the group's payload.

    Parameters
    ----------
    data : object
        A dataset, a data group, or ``None``.

    Returns
    -------
    chisurf.core.fluorescence.mfd.fit.MfdData or None
    """
    if data is None:
        return None
    payload = getattr(data, "mfd", None)
    if payload is not None:
        return payload
    meta = getattr(data, "meta_data", None) or {}
    payload = meta.get("mfd_data")
    if payload is not None:
        return payload
    # ``DataGroup`` subclasses ``list``, so this is the group case and only the
    # group case — a bare curve is not iterable over datasets.
    if isinstance(data, list):
        for member in data:
            payload = burst_payload(member)
            if payload is not None:
                return payload
    return None


class MfdCalibration(FittingParameterGroup):
    """The instrument's correction factors and the dyes' constants.

    Deliberately a thin group over the *same* quantities the shared
    :class:`~chisurf.core.fluorescence.fret.calibration.CalibrationParameters`
    carries, so that a value fitted here can be linked to a calibration fit rather
    than being a second, independent copy of γ.

    ``sigma`` — the combined linker width — sits here rather than with the states
    because it is a property of the labelling, shared across every state. It is
    fixed by default: it is *not* a free broadening parameter, and freeing it under
    the histogram source alone lets it absorb width that belongs to the kinetics.
    Free it only with a prior, or under the pooled-decay source which can see the
    linker width in the decay *shape*.
    """

    def __init__(self, name: str = "calibration", **kwargs):
        """Create the calibration group.

        Parameters
        ----------
        name : str
            Group name.
        **kwargs
            Forwarded to :class:`FittingParameterGroup`.
        """
        super().__init__(name=name, **kwargs)
        self._r0 = FittingParameter(
            name="R0", value=52.0, lb=5.0, ub=200.0, bounds_on=True, fixed=True
        )
        self._tau_d0 = FittingParameter(
            name="tauD0", value=4.0, lb=0.05, ub=30.0, bounds_on=True
        )
        self._tau_a = FittingParameter(
            name="tauA", value=3.0, lb=0.05, ub=30.0, bounds_on=True, fixed=True
        )
        self._alpha = FittingParameter(
            name="alpha", value=0.0, lb=0.0, ub=1.0, bounds_on=True
        )
        self._delta = FittingParameter(
            name="delta", value=0.0, lb=0.0, ub=1.0, bounds_on=True, fixed=True
        )
        self._gamma = FittingParameter(
            name="gamma", value=1.0, lb=0.05, ub=20.0, bounds_on=True, fixed=True
        )
        self._sigma = FittingParameter(
            name="sigma", value=6.0, lb=0.0, ub=30.0, bounds_on=True, fixed=True
        )
        self.find_parameters()

    def _scalar(self, parameter) -> float:
        """Return a parameter's value as a plain float."""
        return float(parameter.value)

    @property
    def optics(self) -> Optics:
        """Return the plain-number view the compute layer takes."""
        return Optics(
            r0=self._scalar(self._r0),
            tau_d0=self._scalar(self._tau_d0),
            tau_a=self._scalar(self._tau_a),
            alpha=self._scalar(self._alpha),
            delta=self._scalar(self._delta),
            gamma=self._scalar(self._gamma),
            sigma=self._scalar(self._sigma),
        )


class MfdStates(FittingParameterGroup):
    """Mean donor–acceptor distances, their populations, and the donor-only fraction.

    The donor-only fraction is a first-class parameter rather than something to be
    cropped out of the data. Real single-molecule measurements always have some
    molecules whose acceptor is missing or bleached, and leaving them out of the
    model does not remove them from the histogram — it makes the fit drag a FRET
    state down to explain them.

    Distances live in a **list**, because
    :func:`chisurf.core.base.find_objects` recurses into lists only; a dict of them
    would be invisible to the optimizer.
    """

    def __init__(self, name: str = "states", n_states: int = 1, **kwargs):
        """Create the state group.

        Parameters
        ----------
        name : str
            Group name.
        n_states : int
            Number of FRET states.
        **kwargs
            Forwarded to :class:`FittingParameterGroup`.
        """
        super().__init__(name=name, **kwargs)
        self._distances: list[FittingParameter] = []
        self._fractions: list[FittingParameter] = []
        self._donor_only = FittingParameter(
            name="donorOnly", value=0.2, lb=0.0, ub=1.0, bounds_on=True
        )
        self.n_states = n_states

    @property
    def n_states(self) -> int:
        """Return the number of FRET states."""
        return len(self._distances)

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the state list, keeping the distances already set."""
        target = max(1, int(value))
        while len(self._distances) > target:
            self._distances.pop()
            self._fractions.pop()
        while len(self._distances) < target:
            index = len(self._distances) + 1
            self._distances.append(
                FittingParameter(
                    name=f"R{index}", value=50.0, lb=5.0, ub=250.0, bounds_on=True
                )
            )
            self._fractions.append(
                FittingParameter(
                    # A *relative* weight against the first state, which is held
                    # at 1 to fix the normalisation -- so the upper bound must
                    # allow a state to be more populated than the reference. At
                    # ub=1 no state could ever exceed half the population, and a
                    # fit that wanted more simply sat on the bound.
                    name=f"x{index}", value=1.0, lb=0.0, ub=100.0, bounds_on=True,
                    fixed=(index == 1),
                )
            )
        self.find_parameters()

    @property
    def states(self) -> list[FretState]:
        """Return the compute layer's view of the states."""
        return [
            FretState(distance=float(p.value), name=p.name) for p in self._distances
        ]

    @property
    def populations(self) -> np.ndarray:
        """Return the state populations, normalised."""
        values = np.array([float(p.value) for p in self._fractions], dtype=float)
        values = np.clip(values, 0.0, None)
        total = values.sum()
        return values / total if total > 0 else np.full(values.size, 1.0 / values.size)

    @property
    def donor_only(self) -> float:
        """Return the fraction of molecules with no active acceptor."""
        return float(np.clip(self._donor_only.value, 0.0, 1.0))

    def distance_rows(self):
        """Return the per-state parameters an editor renders, interleaved.

        **Flat, not nested.** A ``dynamic_group``'s ``rows_source`` yields one
        list of parameters which the section itself chunks ``row_width`` at a
        time; returning a list of rows made it call ``__dict__`` on a ``list``,
        the section failed to build, and the states got no per-state editor at
        all -- reported once in the log and invisible in the panel.

        Returns
        -------
        list
            ``[distance_1, fraction_1, distance_2, fraction_2, ...]``.
        """
        rows = []
        for distance, fraction in zip(self._distances, self._fractions):
            rows.append(distance)
            rows.append(fraction)
        return rows

    def append(self) -> None:
        """Add a state."""
        self.n_states = self.n_states + 1

    def pop(self) -> None:
        """Remove the last state."""
        if self.n_states > 1:
            self.n_states = self.n_states - 1


def get_mfd_residual_image(fit_group, weighted: bool = True, **kwargs):
    """Return the 2D residual image of an MFD fit, for the residual plot.

    The generic ``residual2d`` plot is model-agnostic and asks the model for a
    matrix and its two axes. Without this accessor the panel renders empty — which
    is what it did, silently, because a missing accessor is not an error.

    Parameters
    ----------
    fit_group : chisurf.core.fitting.fit.FitGroup or Fit
        The fit whose residuals are wanted.
    weighted : bool
        Return Poisson deviance residuals rather than raw differences. Deviance is
        the right choice on a burst histogram, where most bins hold single-digit
        counts and a raw difference would make the few crowded bins the only ones
        visible.
    **kwargs
        Ignored; present for the accessor signature.

    Returns
    -------
    image, x_axis, y_axis : numpy.ndarray
        ``Residual2DPlot`` draws with ``axis_order="col-major"``, so axis 0 of the
        array is **x**. The histogram is already stored ``(ratio, micro)``, which is
        exactly that — transposing here would swap the axes against the two axis
        vectors returned alongside, and the picture would be a plausible-looking
        transpose of the truth.
    """
    from chisurf.core.fitting import deviance_residuals

    fit = getattr(fit_group, "fits", None)
    fit = fit[0] if fit else fit_group
    data = burst_payload(getattr(fit, "data", None))
    model = getattr(fit, "model", None)
    if data is None or model is None:
        return np.zeros((1, 1)), np.zeros(1), np.zeros(1)

    observed = np.asarray(data.observed.counts, dtype=float)
    flat = np.asarray(getattr(model, "y", np.zeros(observed.size)), dtype=float)
    if flat.size != observed.size:
        return np.zeros((1, 1)), np.zeros(1), np.zeros(1)
    predicted = flat.reshape(observed.shape, order="C")

    if weighted:
        residual = np.zeros_like(observed)
        usable = predicted > 0
        residual[usable] = deviance_residuals(observed[usable], predicted[usable])
    else:
        residual = observed - predicted

    axes = data.axes
    ratio = 0.5 * (axes.ratio_edges[:-1] + axes.ratio_edges[1:])
    micro = 0.5 * (axes.micro_time_edges[:-1] + axes.micro_time_edges[1:])
    return residual, ratio, micro


#: The maps the image dock can show. Kept as one list so the selector, the
#: accessor and the documentation cannot drift apart.
IMAGE_CHANNELS = ("measured", "model", "residual", "difference")


def _mfd_maps(model):
    """Return ``(measured, predicted, axes)`` for a model, or ``None``."""
    data = burst_payload(getattr(model.fit, "data", None))
    if data is None:
        return None
    observed = np.asarray(data.observed.counts, dtype=float)
    flat = np.asarray(getattr(model, "y", None), dtype=float)
    if flat is None or flat.size != observed.size:
        predicted = np.zeros_like(observed)
    else:
        predicted = flat.reshape(observed.shape, order="C")
    return observed, predicted, data.axes


class MfdImageMixin:
    """The 2D maps, exposed for the shared AutoForm ``image`` section.

    Reusing that section rather than writing another image widget is what gets the
    colormap selector, the channel selector, real-world axes, click-picking and the
    rectangle gate for free — and keeps one image dock behaving the same way
    everywhere in the application.

    The channel selector is what replaces a side-by-side pair: flipping *in place*
    between the measured map, the model and the residual compares them on the same
    axes and the same colour scale, which side-by-side panels at 40% width each
    cannot do.
    """

    #: Which map the dock is showing.
    image_channel: str = "measured"

    #: Colormap of the image dock, so the choice persists across refreshes and is
    #: shared if a tool ever shows two of these.
    image_colormap: str = "inferno"

    def mfd_image_channels(self) -> list[str]:
        """Return the maps the dock can switch between."""
        return list(IMAGE_CHANNELS)

    def set_mfd_image_channel(self, name: str = "") -> None:
        """Select the map to show.

        Parameters
        ----------
        name : str
            One of :data:`IMAGE_CHANNELS`.
        """
        if name in IMAGE_CHANNELS:
            self.image_channel = name

    def mfd_image_extent(self):
        """Return ``(x0, x1, y0, y1)`` — the axes the map really spans.

        Without it the dock would show pixel indices, and a rectangle drawn on the
        plane would be in bins rather than in proximity ratio and nanoseconds.
        """
        maps = _mfd_maps(self)
        if maps is None:
            return (0.0, 1.0, 0.0, 1.0)
        _, _, axes = maps
        return (
            float(axes.ratio_edges[0]),
            float(axes.ratio_edges[-1]),
            float(axes.micro_time_edges[0]),
            float(axes.micro_time_edges[-1]),
        )

    def mfd_image(self):
        """Return the selected map, oriented ``(⟨t⟩, proximity ratio)``.

        Counts are shown as their **square root**. A burst histogram is dominated by
        its donor-only spike — one bin can hold twenty times what the FRET
        population's brightest bin does — so a linear scale renders everything that
        matters as near-black. The residual and difference maps are signed and are
        *not* transformed.
        """
        maps = _mfd_maps(self)
        if maps is None:
            return np.zeros((1, 1))
        observed, predicted, _ = maps
        channel = getattr(self, "image_channel", "measured")
        if channel == "model":
            return np.sqrt(np.clip(predicted, 0.0, None)).T
        if channel == "residual":
            # ``get_mfd_residual_image`` is written for ``Residual2DPlot``, which
            # draws col-major (axis 0 is x). This dock is row-major, so the same
            # array has to be transposed — the two consumers genuinely want
            # opposite orientations, and an untransposed residual here renders as a
            # thin strip that looks like a failed fit rather than a wrong axis.
            return get_mfd_residual_image(self.fit, weighted=True)[0].T
        if channel == "difference":
            return (observed - predicted).T
        return np.sqrt(np.clip(observed, 0.0, None)).T


class Mfd2DModel(MfdImageMixin, ModelCurve):
    """States fitted to the 2D MFD histogram, with or without exchange.

    **One model, not two.** A static analysis is the special case of a kinetic one
    with no exchange, and splitting them into separate models made the user choose
    up front — before the data has told them which it is — and left two code paths
    that could disagree. Here the rate matrix is simply all-zero until it is not:
    the same states, the same corrections, the same statistic throughout.
    """

    name = "MFD 2D"
    view_spec_file = "two_dimensional.view.json"

    def __init__(self, fit, n_states: int = 2, **kwargs):
        """Create the model.

        Parameters
        ----------
        fit : chisurf.core.fitting.fit.Fit
            The fit this model belongs to.
        n_states : int
            Number of conformational states.
        **kwargs
            Forwarded to :class:`ModelCurve`.
        """
        super().__init__(fit, **kwargs)
        self.calibration = MfdCalibration()
        self.state_group = MfdStates(n_states=n_states)
        self.kinetics = RateMatrixParameters(name="kinetics", n_states=n_states)
        # Start with an *empty* scheme, so a fresh model is the static analysis.
        # The shared group defaults its rates to 100 Hz, which would mean every MFD
        # fit began with exchange nobody asked for — and at a rate that is neither
        # slow nor fast for a typical burst, so it would visibly move the answer.
        self.kinetics.default_rate = 0.0
        self.kinetics.set_rate_matrix(np.zeros((n_states, n_states)))
        self._last_summary: dict = {}
        self.find_parameters()
        self.seed_from_data()

    def seed_from_data(self) -> dict:
        """Set the free parameters to values read off this fit's measurement.

        A six-parameter fit of a strongly multi-modal objective ends where its
        start point's basin takes it, and the generic defaults were a bad basin:
        every state at the *same* distance (two states that are literally one
        species, so the first step is rank-deficient), ``alpha`` sitting on its
        lower bound, and a donor lifetime unrelated to the measured decay. On a
        real measurement that converged to a crosstalk of 0.31, putting the
        model's donor-only population at a proximity ratio of 0.24 while the
        data's sat at 0.012.

        Only *free* parameters are touched: a value the user has fixed is a
        decision, not a starting point.

        Returns
        -------
        dict
            What the estimate was read off, or ``{}`` when there is no dataset to
            read (a model built before its data, which is a legal state).
        """
        data = burst_payload(self.fit.data)
        if data is None:
            return {}
        try:
            start = estimate_starting_values(
                data,
                n_states=self.n_states,
                r0=float(self.calibration._r0.value),
                gamma=float(self.calibration._gamma.value),
            )
        except Exception as exc:
            # Seeding is an optimisation of the *start*; failing to seed must
            # leave a usable model rather than an unopenable dataset.
            cs.logging.warning("MFD starting values could not be estimated: %s", exc)
            return {}

        def _set(parameter, value) -> None:
            if not parameter.fixed:
                parameter.value = float(value)

        _set(self.calibration._alpha, start.alpha)
        _set(self.calibration._tau_d0, start.tau_d0)
        _set(self.state_group._donor_only, start.donor_only)
        for parameter, value in zip(self.state_group._distances, start.distances):
            _set(parameter, value)
        for parameter, value in zip(self.state_group._fractions, start.populations):
            _set(parameter, value)
        return dict(start.diagnostics)

    @property
    def n_states(self) -> int:
        """Return the number of conformational states."""
        return self.state_group.n_states

    @n_states.setter
    def n_states(self, value: int) -> None:
        """Resize the states and the rate matrix together.

        They must move as one: a rate matrix that disagrees with the state count is
        the kind of mismatch that reads as a broadcasting error three layers down.
        """
        target = max(1, int(value))
        self.state_group.n_states = target
        # Keep the empty-scheme default across a resize too: a new state should not
        # arrive already exchanging.
        self.kinetics.default_rate = 0.0
        self.kinetics.n_states = target
        self.find_parameters()

    @property
    def state_names(self) -> list[str]:
        """Return state labels for the rate-matrix editor."""
        return [f"R{i + 1}" for i in range(self.n_states)]

    @property
    def rate_values(self):
        """Return the flat rate matrix the AutoForm grid binds to."""
        return self.kinetics.rate_values

    @rate_values.setter
    def rate_values(self, values) -> None:
        """Set the flat rate matrix from the editor."""
        self.kinetics.rate_values = values

    def exchange_rate_matrix(self):
        """Return the rate matrix, or ``None`` when the scheme is empty.

        **An all-zero matrix means "no exchange", not "a scheme whose rates are
        zero".** The distinction matters: fed to the occupation-time law, an
        all-zero generator has no well-defined equilibrium, so the populations
        would come back uniform and silently override the fitted ones. Mapping it
        to ``None`` instead selects the static path, where the state populations
        are the parameters they are meant to be.

        This is the same convention the shared rate-matrix group already uses
        elsewhere in the tree, so one model covers static and kinetic analysis and
        the user never has to pick between two of them.

        Returns
        -------
        numpy.ndarray or None
        """
        matrix = np.asarray(self.kinetics.rate_matrix(), dtype=float)
        if matrix.size == 0 or not np.any(matrix > 0.0):
            return None
        return matrix

    @classmethod
    def supports_data(cls, data) -> bool:
        """Return whether this model applies to a dataset.

        Parameters
        ----------
        data : object
            A dataset, or ``None`` for "list everything".

        Returns
        -------
        bool
        """
        if data is None:
            return True
        return burst_payload(data) is not None

    def _compute_model(self):
        """Return the compute-layer model this fitting model describes.

        Always the kinetic one: with no exchange it reduces exactly to the static
        model, so there is no second class to choose between and no way to fit a
        static answer with machinery that quietly differs from the dynamic one.
        """
        return MfdKineticModel(
            optics=self.calibration.optics,
            states=self.state_group.states,
            populations=self.state_group.populations,
            donor_only=self.state_group.donor_only,
            rate_matrix=self.exchange_rate_matrix(),
        )

    def _update_model(self, **kwargs):
        """Recompute the predicted histogram and store it flattened.

        **A missing payload is a loud no-op, not a silent one.** A model built
        before its data is attached (a legal state -- see
        :meth:`seed_from_data`) leaves the curve at ``ModelCurve``'s zeroed
        placeholder, which is fine while nothing has asked for a fit yet. What
        must not happen is that placeholder reading as "computed and correct"
        later -- the census (``imp.bff/test/minimizer/census_models.py``)
        checks exactly this, and without the warning below its row for this
        model would say nothing beyond "no dataset", which is the same thing
        a genuinely-fitted-but-flat model would say.

        Parameters
        ----------
        **kwargs
            Ignored; present for the base-class signature.
        """
        data = burst_payload(self.fit.data)
        if data is None:
            cs.logging.warning(
                "Mfd2DModel.update_model: no MFD burst payload on this fit's "
                "data; the curve is left at its last (or zeroed) value -- "
                "nothing was fitted."
            )
            return
        try:
            predicted = self._compute_model().histogram(data)
        except Exception as exc:  # pragma: no cover - surfaced, never swallowed
            cs.logging.error("MFD model evaluation failed: %s", exc)
            raise
        observed = np.asarray(self.fit.data.y, dtype=float)
        flat = predicted.ravel(order="C")
        total = flat.sum()
        if total > 0:
            flat = flat * (observed.sum() / total)
        self.y = flat
        self.d = np.vstack((self.x, self.y))

    #: Why this fit's covariance must not be read as an uncertainty.
    _COVARIANCE_CAVEAT = (
        "Uncertainties from this fit's covariance are not valid: the histogram "
        "source scores the same bursts through more than one marginal, so its "
        "curvature is not a likelihood's. Use the burst-wise source or a "
        "bootstrap over bursts."
    )

    def summary_rows(self) -> list[tuple[str, str]]:
        """Return what the fit is being asked to explain, and what it excluded.

        One source of truth for both renderings below, so the plain-text and the
        HTML views cannot drift apart.
        """
        data = burst_payload(self.fit.data)
        if data is None:
            return []
        summary = data.observed.summary
        rows = [
            ("Bursts in the folder", f"{summary['n_input']}"),
            ("In the histogram", f"{summary['n_used']}"),
            ("Excluded", f"{summary['excluded_fraction']:.1%}"),
            ("Donor-photon cut", f"{summary['min_green_photons']}"),
        ]
        for name, response in data.responses.items():
            rows.append(
                (f"{name} background", f"{response.background_rate * 1e-3:.3f} kHz")
            )
        return rows

    def summary_text(self) -> str:
        """Return the summary as plain text, for the Info tab's report.

        The Info tab is one continuous plain-text account of the fit, and a
        second widget floating above it -- with its own scrollbar and its own
        idea of how tall it should be -- reads as a thing bolted on rather than
        part of the report. So the model offers text and the tab merges it.
        """
        rows = self.summary_rows()
        if not rows:
            return "No MFD dataset."
        width = max(len(k) for k, _ in rows)
        body = "\n".join(f"  {k:<{width}}  {v}" for k, v in rows)
        return f"{body}\n\n{self._COVARIANCE_CAVEAT}"

    def summary_html(self) -> str:
        """Return the same summary as HTML, for an AutoForm ``info`` section.

        A **method**, deliberately. An ``info`` section resolves its ``source`` by
        calling it; a property is read at class level, returns a ``property``
        object rather than a string, and the section renders as a large blank
        block with no error anywhere — which is exactly what it did.
        """
        rows = self.summary_rows()
        if not rows:
            return "<i>No MFD dataset.</i>"
        body = "".join(f"<tr><td>{k}</td><td><b>{v}</b></td></tr>" for k, v in rows)
        return (
            "<table cellspacing='4'>" + body + "</table>"
            f"<p><i>{self._COVARIANCE_CAVEAT}</i></p>"
        )

    def burstwise_score(self, max_bursts: int | None = 800, seed: int = 0):
        """Score this model photon by photon, as the maximum-likelihood reference.

        The histogram source compresses each burst to two numbers; this one keeps
        every photon's micro time. Agreement between the two is a test of both — a
        rate they disagree on is a rate nobody should report — and unlike the
        histogram this source touches each burst once, so its curvature *is* a
        likelihood's.

        Parameters
        ----------
        max_bursts : int, optional
            Score a random subset of this many bursts; ``None`` scores all of them.
        seed : int
            Seed for that subsample, so the objective stays deterministic.

        Returns
        -------
        chisurf.core.fluorescence.mfd.sources.ScoreResult
        """
        from chisurf.core.fluorescence.mfd.fit import burstwise_log_probabilities
        from chisurf.core.fluorescence.mfd.sources import burstwise_log_likelihood

        data = burst_payload(self.fit.data)
        if data is None:
            raise ValueError("this fit has no MFD dataset")
        return burstwise_log_likelihood(
            burstwise_log_probabilities(
                self._compute_model(), data, max_bursts=max_bursts, seed=seed
            )
        )

    def bootstrap(self, refit, n_resamples: int = 40, seed: int = 0) -> dict:
        """Estimate parameter uncertainties by resampling bursts.

        The sanctioned route, because the histogram source's own curvature is not
        one: it scores the same bursts through more than one marginal. Resampling
        bursts perturbs the thing that actually varies between repeats of an
        experiment — which bursts you happened to catch.

        Parameters
        ----------
        refit : callable
            ``refit(MfdData) -> dict`` returning fitted parameters for one resample.
        n_resamples : int
            Bootstrap replicates.
        seed : int
            Random seed.

        Returns
        -------
        dict
            Per parameter, ``{"mean", "std", "values"}``.
        """
        from chisurf.core.fluorescence.mfd.fit import bootstrap_uncertainties

        data = burst_payload(self.fit.data)
        if data is None:
            raise ValueError("this fit has no MFD dataset")
        return bootstrap_uncertainties(
            refit, data, n_resamples=n_resamples, seed=seed
        )

    def parameter_uncertainties(self):
        """Refuse to report uncertainties the histogram source cannot support.

        Raises
        ------
        RuntimeError
            Always, for the histogram source. The optimum from a summed deviance
            over marginals is meaningful; its curvature is not, because the same
            bursts enter every marginal and the score double-counts them.
        """
        if not uncertainty_is_valid(["histogram"]):
            raise RuntimeError(
                "the marginal-histogram score is an M-estimator, not a likelihood: "
                "the same bursts appear in every marginal, so its curvature reports "
                "uncertainties that are too small. Use this model's burstwise_score() "
                "or bootstrap() instead — both are valid, and both are here."
            )
        return None  # pragma: no cover - unreachable while only this source exists
