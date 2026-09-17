"""An ebFRET session: what ``ebfret.ui.MainWindow`` does, without the window.

ebFRET keeps its whole state on the main window object -- ``series``,
``analysis`` and ``controls`` -- and every menu entry and button is a method on
it (``load_data``, ``remove_bleaching``, ``run_ebayes``, ``export_smd``...).
This class is those methods, ported one to one, with each MATLAB dialog
replaced by the arguments the dialog would have returned. The GUI asks the
questions; the session does what the answers say. That split is what lets the
analysis run on the backend while the window stays responsive, and what lets a
test walk the whole workflow with no window at all.

Method names follow the MATLAB file names (``load_data.m`` ->
:meth:`Session.load_data`), so the reference for any behaviour here is the file
of the same name under ``+ebfret/+ui/@MainWindow``.
"""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

import numpy as np

from .. import io as ebio
from . import ebayes as ebayes_core
from . import hmm
from .model import Analysis, Controls, Series

__all__ = [
    "Session",
    "FILE_TYPES",
    "SESSION",
    "RAW",
    "SF_TRACER",
    "SMD_MAT",
    "SMD_JSON",
    "SMD_JSON_GZ",
]

#: The ``uigetfile`` filter list of ``load_data.m``, in its order. The index of
#: the chosen filter *is* the file type -- two entries are ``*.mat``, and only
#: the filter tells a saved session from an SMD dataset.
FILE_TYPES = (
    ("ebFRET saved session (.mat)", ("*.mat",)),
    ("Raw donor-acceptor time series (.dat)", ("*.dat",)),
    ("SF-Tracer donor-acceptor time series (.tsv)", ("*.tsv",)),
    ("SMD time series (.mat)", ("*.mat",)),
    ("SMD time series (.json)", ("*.json",)),
    ("SMD time series (.json.gz)", ("*.json.gz",)),
)
SESSION, RAW, SF_TRACER, SMD_MAT, SMD_JSON, SMD_JSON_GZ = 1, 2, 3, 4, 5, 6


def _stem(path: str | Path) -> str:
    """MATLAB ``fileparts`` name: the base name without its *last* extension."""
    return Path(path).stem


class Session:
    """The state and the actions of one ebFRET main window.

    Parameters
    ----------
    seed : int, optional
        Seed of the random draws the VBEM restarts use. ebFRET draws from
        MATLAB's global generator; a seed makes a run repeatable.

    Attributes
    ----------
    series : list of Series
        The loaded time series.
    analysis : dict of int to Analysis
        One model per number of states.
    controls : Controls
        The values of the window's controls.
    revision : int
        Incremented on every change a view has to redraw for.
    message : str
        The last informational message (a MATLAB ``msgbox``).
    log : list of str
        The lines ebFRET prints to the command window during a run.
    """

    def __init__(self, seed: int | None = None) -> None:
        self.series: list[Series] = []
        self.analysis: dict[int, Analysis] = {}
        self.controls = Controls()
        self.rng = np.random.default_rng(seed)
        self.revision = 0
        self.message = ""
        self.log: list[str] = []
        #: Guards every mutation; the analysis loop holds it one batch at a time.
        self.lock = threading.RLock()
        self._last_series_redraw = 0.0

    # -- helpers ----------------------------------------------------------- #
    def touch(self) -> None:
        """Mark the session changed, so a view redraws."""
        self.revision += 1

    def state_range(self) -> list[int]:
        """``min_states:max_states``, as MATLAB writes it."""
        return list(range(int(self.controls.min_states), int(self.controls.max_states) + 1))

    def run_targets(self) -> list[int]:
        """The analyses *All* / *Current* in the analysis popup refer to."""
        if self.controls.run_all:
            return self.state_range()
        return [int(self.controls.ensemble_value)]

    def groups(self) -> list[str]:
        """The distinct group labels, sorted as ``unique`` sorts them."""
        return sorted({s.group for s in self.series})

    def get_signal(self, series_index: list[int] | None = None) -> list[np.ndarray]:
        """``get_signal.m``: cropped and clipped signals; empty when excluded.

        Parameters
        ----------
        series_index : list of int, optional
            0-based series indices; all series by default.

        Returns
        -------
        list of numpy.ndarray
            One array per requested series, of length zero for an excluded one.
        """
        indices = range(len(self.series)) if series_index is None else series_index
        out = []
        for n in indices:
            s = self.series[n]
            if s.exclude:
                out.append(np.zeros(0))
                continue
            x = np.array(s.signal[s.crop_min - 1 : s.crop_max], dtype=float)
            if self.controls.clip_min < math.inf:
                x[x < self.controls.clip_min] = self.controls.clip_min
            if self.controls.clip_max < math.inf:
                x[x > self.controls.clip_max] = self.controls.clip_max
            out.append(x)
        return out

    def _signals_for_run(self) -> list[np.ndarray | None]:
        """Signals as the analysis loop takes them: ``None`` for excluded."""
        return [x if x.size else None for x in self.get_signal()]

    # -- analysis bookkeeping ---------------------------------------------- #
    def init_analysis(self, num_states: list[int] | None = None) -> None:
        """``init_analysis.m``: create the analyses that do not exist yet.

        Parameters
        ----------
        num_states : list of int, optional
            Defaults to ``min_states:max_states``.
        """
        targets = self.state_range() if num_states is None else num_states
        for k in targets:
            if k > 0 and k not in self.analysis:
                self.reset_analysis([k])

    def reset_analysis(self, num_states: list[int] | None = None) -> None:
        """``reset_analysis.m``: a fresh guessed prior and reset posteriors.

        Parameters
        ----------
        num_states : list of int, optional
            Defaults to the analyses *All* / *Current* refers to.
        """
        targets = self.run_targets() if num_states is None else num_states
        for k in targets:
            if k <= 0:
                continue
            self.analysis[k] = Analysis(states=k)
            if self.series:
                self.analysis[k].prior = hmm.guess_prior(self.get_signal(), k)
                self.reset_posterior([k])
        self.touch()

    def reset_posterior(
        self, analysis_index: list[int] | None = None, series_index: list[int] | None = None
    ) -> None:
        """``reset_posterior.m``: posterior back to the prior, results cleared.

        The posterior is reset *to the prior*, not emptied, so the next run's
        first restart starts from it -- exactly as the reference does.

        Parameters
        ----------
        analysis_index : list of int, optional
            State counts; defaults to the analyses *All* / *Current* refers to.
        series_index : list of int, optional
            0-based series; all by default.
        """
        targets = self.run_targets() if analysis_index is None else analysis_index
        indices = range(len(self.series)) if series_index is None else series_index
        n_series = len(self.series)
        for k in targets:
            a = self.analysis.get(k)
            if a is None:
                continue
            _grow(a, n_series)
            for n in indices:
                s = self.series[n]
                a.posterior[n] = a.prior.copy() if a.prior is not None else None
                a.expect[n] = None
                if s.exclude or s.crop_max == s.crop_min:
                    a.posterior[n] = None
                a.lowerbound[n] = 0.0
                a.viterbi[n] = None
        self.touch()

    # -- set_control.m ----------------------------------------------------- #
    def set_series(
        self, value: int | None = None, vmin: int | None = None, vmax: int | None = None
    ) -> None:
        """The *Select Series* index control (``IndexControl.set_prop``).

        Parameters
        ----------
        value, vmin, vmax : int, optional
            New value and limits; the value is clamped into the limits.
        """
        c = self.controls
        if vmin is not None:
            c.series_min = int(round(vmin))
            c.series_value = max(c.series_value, c.series_min)
        if vmax is not None:
            c.series_max = int(round(vmax))
            c.series_value = min(c.series_value, c.series_max)
        if value is not None:
            c.series_value = int(max(min(round(value), c.series_max), c.series_min))
        self.touch()

    def set_ensemble(
        self, value: int | None = None, vmin: int | None = None, vmax: int | None = None
    ) -> None:
        """The *Select States* index control; its limits follow min/max states.

        Parameters
        ----------
        value, vmin, vmax : int, optional
            New value and limits.
        """
        c = self.controls
        if vmin is not None and int(round(vmin)) != c.ensemble_min:
            c.ensemble_min = int(round(vmin))
            c.ensemble_value = max(c.ensemble_value, c.ensemble_min)
            self.set_min_states(c.ensemble_min)
        if vmax is not None and int(round(vmax)) != c.ensemble_max:
            c.ensemble_max = int(round(vmax))
            c.ensemble_value = min(c.ensemble_value, c.ensemble_max)
            self.set_max_states(c.ensemble_max)
        if value is not None:
            c.ensemble_value = int(max(min(round(value), c.ensemble_max), c.ensemble_min))
        self.touch()

    def set_min_states(self, value: int) -> None:
        """The *States* panel's *Min* field.

        Parameters
        ----------
        value : int
            Smallest number of states to analyse.
        """
        value = int(round(value))
        if value != self.controls.min_states:
            self.controls.min_states = value
            self.set_ensemble(vmin=value)
            self.init_analysis()
        self.touch()

    def set_max_states(self, value: int) -> None:
        """The *States* panel's *Max* field.

        Parameters
        ----------
        value : int
            Largest number of states to analyse.
        """
        value = int(round(value))
        if value != self.controls.max_states:
            self.controls.max_states = value
            self.set_ensemble(vmax=value)
            self.init_analysis()
        self.touch()

    def set_crop(self, crop_min: int | None = None, crop_max: int | None = None) -> None:
        """The *Crop* panel: change the range of the current series.

        Parameters
        ----------
        crop_min, crop_max : int, optional
            New inclusive 1-based limits; ``None`` keeps the current one.
        """
        if not self.series:
            return
        n = self.controls.series_value - 1
        s = self.series[n]
        lo = s.crop_min if crop_min is None else int(round(crop_min))
        hi = s.crop_max if crop_max is None else int(round(crop_max))
        lo = max(1, lo)
        hi = max(lo, min(s.length, hi))
        if lo != s.crop_min or hi != s.crop_max:
            s.crop_min, s.crop_max = lo, hi
            self.reset_posterior(self.state_range(), [n])
        self.touch()

    def set_exclude(self, exclude: bool) -> None:
        """The *Crop* panel's *Exclude* checkbox for the current series.

        Parameters
        ----------
        exclude : bool
            Leave the series out of the analysis.
        """
        if not self.series:
            return
        n = self.controls.series_value - 1
        if bool(exclude) != self.series[n].exclude:
            self.series[n].exclude = bool(exclude)
            self.reset_posterior(self.state_range(), [n])
        self.touch()

    def set_controls(self, **values: Any) -> None:
        """Set plain controls (``restarts``, ``run_all``, ``run_precision``,
        ``scale_plots``, ``show_*``, ``clip_*``, ``crop_margin``).

        Parameters
        ----------
        **values
            ``Controls`` field names and values.

        Raises
        ------
        KeyError
            For a name that is not a plain control -- ``set_control.m`` raises
            ``UnknownControl`` the same way.
        """
        plain = {
            "restarts",
            "run_all",
            "run_precision",
            "scale_plots",
            "show_viterbi",
            "show_prior",
            "show_posterior",
            "clip_min",
            "clip_max",
            "crop_margin",
        }
        for name, value in values.items():
            if name not in plain:
                raise KeyError(f"Unknown control {name!r}")
            kind = type(getattr(Controls(), name))
            setattr(self.controls, name, kind(value))
        self.touch()

    # -- File menu --------------------------------------------------------- #
    def load_data(
        self,
        files: list[str],
        ftype: int,
        append: bool = False,
        smd_channels: Callable[[list[str]], dict | None] | dict | None = None,
    ) -> str:
        """``load_data.m``: read files of one type into the session.

        Parameters
        ----------
        files : list of str
            Paths; only the first is used for a saved session.
        ftype : int
            Index of the file-dialog filter, :data:`FILE_TYPES` (1-based).
        append : bool
            *Keep* the loaded series (a new group) rather than *Replace* them.
            Ignored for a session, which always replaces.
        smd_channels : dict or callable, optional
            The *Assign Channels* dialog: a ``{donor, acceptor, fret}`` dict of
            1-based columns (``None`` where not selected), or a callable taking
            an SMD's column labels and returning one (``None`` cancels).

        Returns
        -------
        str
            ``"Read N time series from M files"`` -- the waitbar's last text.
        """
        with self.lock:
            message = ""
            if ftype == SESSION:
                series, analysis, controls = ebio.load_session(files[0])
                self.series, self.analysis = series, analysis
                run_analysis = False
                self.controls = replace(controls, run_analysis=run_analysis)
                message = f"Loaded session {Path(files[0]).name}"
            elif ftype in (RAW, SF_TRACER, SMD_MAT, SMD_JSON, SMD_JSON_GZ):
                append = bool(append) and bool(self.series)
                group = f"group {len(self.groups()) + 1}" if append else "group 1"
                loaded: list[Series] = []
                for path in files:
                    if ftype == RAW:
                        donors, acceptors, labels = ebio.load_raw(path, has_labels=True)
                        loaded += ebio.series_from_raw(path, donors, acceptors, labels, group)
                    elif ftype == SF_TRACER:
                        donors, acceptors = ebio.load_sf_tracer(path)
                        labels = list(range(1, len(donors) + 1))
                        loaded += ebio.series_from_raw(path, donors, acceptors, labels, group)
                    else:
                        smd = ebio.load_smd(path)
                        channels = (
                            smd_channels(list(smd["columns"]))
                            if callable(smd_channels)
                            else smd_channels
                        )
                        if channels is None:
                            continue
                        loaded += ebio.series_from_smd(path, smd, channels, group)
                message = f"Read {len(loaded)} time series from {len(files)} files"
                self.series = (self.series + loaded) if append else loaded
                if not append:
                    self.analysis = {}
                self.reset_analysis(self.state_range())
                self.set_series(vmin=1, vmax=len(self.series), value=1)
                self.set_ensemble(value=self.controls.min_states)
            self.controls.run_analysis = False
            self.message = message
            self.touch()
            return message

    def save_data(self, path: str) -> None:
        """``save_data.m``: write the session ``.mat``.

        Parameters
        ----------
        path : str
            Output file.
        """
        with self.lock:
            ebio.save_session(path, self.series, self.analysis, self.controls)

    # -- Analysis menu ----------------------------------------------------- #
    def remove_bleaching(self, method: int, thresholds: dict | None = None) -> str:
        """``remove_bleaching.m``: crop each series at its photobleaching point.

        Parameters
        ----------
        method : int
            1 *Manual* thresholds, 2 *Auto* (``photobleach_index``); anything
            else is the dialog's Cancel and does nothing.
        thresholds : dict, optional
            ``don``, ``acc``, ``sum``, ``fret``, ``pad`` -- ``NaN`` (or
            ``None``) where the dialog's checkbox is off.

        Returns
        -------
        str
            The message box text, or ``""`` when nothing was done.
        """
        if not self.series or method not in (1, 2):
            return ""
        with self.lock:
            th = {k: _nan(v) for k, v in (thresholds or {}).items()}
            for key in ("don", "acc", "sum", "fret", "pad"):
                th.setdefault(key, math.nan)
            excluded = 0
            if method == 1:
                width = 7
                half = width // 2
                kernel = np.exp(-(np.linspace(-1.5, 1.5, width) ** 2))
                kernel = kernel / kernel.sum()
                for s in self.series:
                    start = s.crop_min - 1
                    crop_max = s.length - s.crop_min
                    donor = acceptor = None
                    if not math.isnan(th["fret"]):
                        smooth = np.convolve(s.signal[start:], kernel, mode="valid")
                        crop_max = min(crop_max, _first_below(smooth, th["fret"], half))
                    if not math.isnan(th["acc"]) or not math.isnan(th["sum"]):
                        acceptor = np.convolve(s.acceptor[start:], kernel, mode="valid")
                        crop_max = min(crop_max, _first_below(acceptor, th["acc"], half))
                    if not math.isnan(th["don"]) or not math.isnan(th["sum"]):
                        donor = np.convolve(s.donor[start:], kernel, mode="valid")
                        crop_max = min(crop_max, _first_below(donor, th["don"], half))
                    if not math.isnan(th["sum"]):
                        crop_max = min(crop_max, _first_below(donor + acceptor, th["sum"], half))
                    if not math.isnan(th["pad"]):
                        crop_max = crop_max - th["pad"]
                    if crop_max > 0:
                        s.crop_max = int(crop_max + s.crop_min)
                        s.exclude = False
                    else:
                        s.exclude = True
                        excluded += 1
            else:
                for s in self.series:
                    if s.donor.size and s.acceptor.size:
                        index_d, _ = hmm.photobleach_index(np.asarray(s.donor, dtype=float))
                        index_a, _ = hmm.photobleach_index(np.asarray(s.acceptor, dtype=float))
                        s.crop_max = int(min(index_d, index_a))
                        if s.crop_max <= s.crop_min:
                            s.exclude = True
                            excluded += 1
            lengths = np.array([s.crop_max - s.crop_min + 1 for s in self.series])
            message = (
                f"Total length: {int(lengths.sum())}. "
                f"Median length: {float(np.median(lengths)):.1f}.\n\n"
                f"Excluded {excluded} out of {len(self.series)} time series from "
                "analysis."
            )
            self.message = message
            self.touch()
            return message

    def clip_outliers(
        self, x_lim: tuple[float, float] = (-0.2, 1.2), max_outliers: int = 10
    ) -> str:
        """``clip_outliers.m``: clip the signal and exclude outlier-heavy series.

        Parameters
        ----------
        x_lim : tuple of float
            *Clip at Minimum* / *Clip at Maximum* (dialog defaults -0.2, 1.2).
        max_outliers : int
            *Exclude when number of Outliers exceeds* (default 10).

        Returns
        -------
        str
            The message box text.
        """
        with self.lock:
            total_points = total_out = removed = 0
            lo, hi = float(x_lim[0]), float(x_lim[1])
            for s in self.series:
                self.controls.clip_min, self.controls.clip_max = lo, hi
                x = s.signal[s.crop_min - 1 : s.crop_max]
                out = int(np.sum(x <= lo) + np.sum(x >= hi))
                if out > max_outliers:
                    s.exclude = True
                    removed += 1
                total_points += x.size
                total_out += out
            share = 100.0 * total_out / total_points if total_points else math.nan
            message = (
                f"Found {total_out} outlier points ({share:.3f}% of total).\n\n"
                f"Excluded {removed} out of {len(self.series)} time series from "
                "analysis."
            )
            self.reset_posterior(self.state_range())
            self.message = message
            self.touch()
            return message

    def update_priors(self, choice: str) -> None:
        """``update_priors.m``, after its question: *Auto*, *Manual*, *Keep Current*.

        *Manual* is the *Set Priors* dialog; the caller shows it and calls
        :meth:`init_priors` with its values.

        Parameters
        ----------
        choice : str
            ``"auto"``, ``"manual"`` or ``"keep current"`` (any case).
        """
        if choice.lower() != "auto":
            return
        with self.lock:
            for k in self.state_range():
                if k > 0:
                    self.analysis.setdefault(k, Analysis(states=k))
                    self.analysis[k].prior = hmm.guess_prior(self.get_signal(), k)
                    self.reset_posterior([k])
            self.touch()

    def init_priors(self, theta0: dict, counts0: dict, status: int) -> None:
        """``init_priors.m`` with the values of the *Set Priors* dialog.

        Parameters
        ----------
        theta0 : dict
            ``mu_min``, ``mu_max``, ``sigma``, ``tau`` (*Expected Parameters*).
        counts0 : dict
            ``mu``, ``sigma``, ``tau`` (*Prior Strength*).
        status : int
            The dialog's popup: 1 *All*, 2 *Current*; 0 is Cancel.
        """
        if status not in (1, 2):
            return
        with self.lock:
            targets = self.state_range() if status == 1 else [self.controls.ensemble_value]
            mu = (float(theta0["mu_min"]), float(theta0["mu_max"]))
            lam = float(theta0["sigma"]) ** -2
            for k in targets:
                theta = {
                    "mu": np.linspace(mu[0], mu[1], k),
                    "lambda": np.full(k, lam),
                    "tau": np.full(k, float(theta0["tau"])),
                }
                counts = {
                    "mu": np.full(k, float(counts0["mu"])),
                    "lambda": np.full(k, float(counts0["sigma"])),
                    "tau": np.full(k, float(counts0["tau"])),
                }
                self.analysis.setdefault(k, Analysis(states=k))
                self.analysis[k].prior = hmm.init_prior(theta, counts)
                self.reset_posterior([k])
            self.touch()

    # -- Analysis panel ---------------------------------------------------- #
    def reset(self) -> None:
        """The *Reset* button: ``reset_analysis`` for *All* / *Current*."""
        with self.lock:
            self.reset_analysis()

    def run_ebayes(self, should_stop: Callable[[], bool] | None = None) -> Iterator[dict]:
        """``run_ebayes.m``: the empirical-Bayes loop over the selected analyses.

        A generator, so a caller can hand the lock back between batches and a
        view can redraw; the reference does the same with ``drawnow``. It moves
        *Select States* to the analysis being run, and *Select Series* to the
        last series of a batch at most once a second, as the reference's redraw
        intervals do.

        Parameters
        ----------
        should_stop : callable, optional
            Returns ``True`` once *Stop* was pressed.

        Yields
        ------
        dict
            The core loop's events, each with ``"states"`` added.
        """
        stop = should_stop or (lambda: not self.controls.run_analysis)
        if not self.series:
            return
        self.controls.run_analysis = True
        try:
            for k in self.run_targets():
                with self.lock:
                    if k not in self.analysis or self.analysis[k].prior is None:
                        self.init_analysis([k])
                        if self.analysis[k].prior is None:
                            self.reset_analysis([k])
                    self.set_ensemble(value=k)
                    signals = self._signals_for_run()
                    _grow(self.analysis[k], len(self.series))
                events = ebayes_core.run_ebayes(
                    self.analysis[k],
                    signals,
                    restarts=int(self.controls.restarts),
                    precision=float(self.controls.run_precision),
                    rng=self.rng,
                    should_stop=stop,
                )
                while True:
                    with self.lock:
                        try:
                            event = next(events)
                        except StopIteration:
                            break
                        event = dict(event, states=k)
                        if event.get("kind") == "batch" and event.get("series"):
                            now = time.monotonic()
                            if now - self._last_series_redraw > 1.0:
                                self.set_series(value=int(event["series"][-1]) + 1)
                                self._last_series_redraw = now
                        elif event.get("kind") == "iteration":
                            line = f"it {event['it']:02d}   L {event['L']:.5e}"
                            if event.get("dL") is not None and math.isfinite(event["dL"]):
                                line += f"    dL {event['dL']:.2e}"
                            self.log.append(f"K{k:02d}    {line}")
                        self.touch()
                    yield event
                if stop():
                    return
        finally:
            self.controls.run_analysis = False
            self.touch()

    # -- Export ------------------------------------------------------------ #
    def select_analysis(self, states: int, group: str = "all") -> tuple[list[Series], Analysis]:
        """``select_analysis.m``: the series and model an export is made of.

        Parameters
        ----------
        states : int
            *Number of States*.
        group : str
            *Time Series Group*; ``"all"`` for every series. For a single group
            the prior is re-estimated from that group's posteriors (``h_step``).

        Returns
        -------
        tuple
            ``(series, analysis)`` restricted to the group.
        """
        analysis = self.analysis[int(states)]
        if group.lower() == "all":
            return list(self.series), analysis
        ns = [n for n, s in enumerate(self.series) if s.group.lower() == group.lower()]
        sub = Analysis(
            states=analysis.states,
            posterior=[analysis.posterior[n] for n in ns],
            expect=[analysis.expect[n] for n in ns],
            viterbi=[analysis.viterbi[n] for n in ns],
            lowerbound=np.asarray(analysis.lowerbound)[ns],
            restart=np.asarray(analysis.restart)[ns],
        )
        posteriors = [w for w in sub.posterior if w is not None]
        sub.prior = hmm.h_step(posteriors, analysis.prior) if posteriors else analysis.prior
        return [self.series[n] for n in ns], sub

    def export_summary(self, path: str) -> None:
        """``export_summary.m``: the analysis-summary CSV for every state count.

        Parameters
        ----------
        path : str
            Output ``.csv``.
        """
        with self.lock:
            groups = self.groups()
            splits = [list(range(len(self.series)))]
            labels = ["all"]
            if len(groups) > 1:
                splits += [[n for n, s in enumerate(self.series) if s.group == g] for g in groups]
                labels += groups
            report: list = []
            signal = self.get_signal()
            first = True
            for k in range(self.controls.ensemble_min, self.controls.ensemble_max + 1):
                a = self.analysis.get(k)
                if a is None or a.prior is None:
                    continue
                rep = hmm.report(
                    signal,
                    a.prior,
                    list(a.expect),
                    lowerbound=a.lowerbound,
                    splits=splits,
                    labels=labels,
                )
                if not first:
                    for entry in rep:
                        entry["Series"] = np.zeros((0, 0))
                report += rep
                first = False
            ebio.write_report(path, report)

    def export_traces(
        self, path: str, channels: dict, states: int, group: str = "all", fmt: str | None = None
    ) -> None:
        """``export_traces.m``: the selected columns of every included series.

        Parameters
        ----------
        path : str
            Output ``.dat`` or ``.mat``.
        channels : dict
            The *Channels* dialog: ``donor``, ``acceptor``, ``fret``,
            ``viterbi_state``, ``viterbi_mean`` booleans.
        states, group
            The *Select* dialog (:meth:`select_analysis`).
        fmt : str, optional
            ``"dat"`` or ``"mat"``; from the extension by default.
        """
        if not any(channels.values()):
            return
        with self.lock:
            series, analysis = self.select_analysis(states, group)
            fmt = fmt or Path(path).suffix.lstrip(".")
            ebio.export_traces(path, series, analysis, channels, fmt=fmt)

    def export_smd(
        self, path: str, states: int, group: str = "all", fmt: str | None = None
    ) -> None:
        """``export_smd.m``: the single-molecule dataset of one analysis.

        Parameters
        ----------
        path : str
            Output ``.mat``, ``.json`` or ``.json.gz``.
        states, group
            The *Select* dialog (:meth:`select_analysis`).
        fmt : str, optional
            ``"mat"``, ``"json"`` or ``"gz"``; from the extension by default.
        """
        with self.lock:
            series, analysis = self.select_analysis(states, group)
            ebio.write_smd(path, series, analysis, fmt=fmt)

    # -- summaries for a view ---------------------------------------------- #
    def controls_dict(self) -> dict:
        """The controls as a plain dict (for a view, or a JSON transport)."""
        return {f.name: getattr(self.controls, f.name) for f in fields(Controls)}


def _grow(analysis: Analysis, n_series: int) -> None:
    """Pad an analysis' per-series lists to ``n_series`` entries."""
    for name in ("posterior", "expect", "viterbi"):
        values = getattr(analysis, name)
        values.extend([None] * (n_series - len(values)))
    lb = np.zeros(n_series)
    lb[: min(n_series, len(analysis.lowerbound))] = analysis.lowerbound[:n_series]
    analysis.lowerbound = lb
    rs = np.zeros(n_series, dtype=int)
    rs[: min(n_series, len(analysis.restart))] = analysis.restart[:n_series]
    analysis.restart = rs


def _nan(value: Any) -> float:
    """A dialog value as float, ``None`` meaning an unticked box (NaN)."""
    return math.nan if value is None else float(value)


def _first_below(values: np.ndarray, threshold: float, offset: int) -> float:
    """``min([find(values < threshold, 1, 'first') + offset, inf])``.

    Parameters
    ----------
    values : numpy.ndarray
        Smoothed signal.
    threshold : float
        NaN finds nothing, as MATLAB's comparison with NaN is false.
    offset : int
        Half the smoothing window.

    Returns
    -------
    float
        1-based index plus offset, or ``inf``.
    """
    if math.isnan(threshold):
        return math.inf
    hits = np.flatnonzero(values < threshold)
    return float(hits[0] + 1 + offset) if hits.size else math.inf
