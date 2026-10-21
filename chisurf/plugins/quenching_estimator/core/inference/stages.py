"""The stages of a quenching analysis: which data sets are fitted together, and what is reported.

This is the headless entry of the inverse analysis (the API, RPC, CLI and GUI call it). It
loads the measurements and their statistics once (:func:`load_analysis_data`), solves the
declared graphs on demand (:class:`Analysis`) and turns each declared stage into a
:class:`StageResult` with declared tables, plot data and a plain-language text.

The MalE stages (``settings/analysis/stages.yaml``):

- **A** — AF488 and Cy3B in normal water (blocks of the ``joint`` graph).
- **B** — Atto655 in heavy water alone (its own ``heavy_water`` graph).
- **naive_h2o** — B's result predicts normal water with the free dye's tau0 and no water
  term; expected to fail (it shows that water quenching on the protein must be modelled).
- **C** — Atto655 in heavy and normal water at once (the ``joint`` graph's third block), with
  water = kq_w,free x exposure and no new parameter; the water access per site, measured
  against the model, and the time-weighted exposure of declared sites.
- **summary** — one line per dye and the estimates of every stage.

A and C are views of one graph: Cy3B and Atto655 read the reference dye's titration slopes, so
the stored analysis solved them together. Running stage A therefore solves the whole
``joint`` graph, and C then costs nothing more.

Long runs report ``progress(percent, message)`` and stop at the next checkpoint when
``cancel()`` returns true (raising :class:`~..tasks.CancelledError`), the callback shapes of
:class:`~..tasks.JobManager`'s ``reporter``/``canceller``. Theory:
``docs/concepts/quenching_inference.md``.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from ..tasks import CancelledError
from . import columns as _columns
from . import graph_fit as _gf
from . import lifetime_errors as _lifetime_errors
from . import measurements as _measurements
from . import report as _report
from . import sampler_check as _sampler_check
from . import site_model as _site_model
from . import site_table as _site_table
from . import titration as _titration

__all__ = [
    "STAGES",
    "AnalysisData",
    "TableFiles",
    "load_analysis_data",
    "stage_settings",
    "stage_names",
    "Analysis",
    "AnalysisResult",
    "StageResult",
    "run_stage",
    "run_analysis",
    "CancelledError",
]

#: The stage declaration.
STAGES = _columns.ANALYSIS_SETTINGS_DIR / "stages.yaml"


def stage_settings(path=STAGES):
    """The declared graphs, stages and order.

    Parameters
    ----------
    path : str or pathlib.Path, optional

    Returns
    -------
    dict
        A fresh copy.
    """
    return _gf._deep_copy(_columns.settings(path))


def stage_names(path=STAGES):
    """The declared stages in run order.

    Parameters
    ----------
    path : str or pathlib.Path, optional

    Returns
    -------
    list of str
    """
    return list(stage_settings(path)["order"])


# --------------------------------------------------------------------------------------------
# inputs


class TableFiles:
    """Site models from stored site-table files (for example the MalE prototype's cache).

    Parameters
    ----------
    files : dict
        ``{(state, site, linker_length): path}``.
    settings_ : dict, optional
        Site-model settings.
    """

    def __init__(self, files, settings_=None):
        self.settings = settings_ or _site_table.settings()
        self.files = {(str(k[0]), int(k[1]), round(float(k[2]), 6)): Path(v)
                      for k, v in files.items()}
        self._sites = {}

    def site(self, state, site, linker_length):
        """The site model of one stored table (kept in memory).

        Parameters
        ----------
        state : str
        site : int
        linker_length : float

        Returns
        -------
        Site
        """
        key = (str(state), int(site), round(float(linker_length), 6))
        if key not in self._sites:
            if key not in self.files:
                raise KeyError(f"no stored site table for {key}")
            self._sites[key] = _site_model.Site(self.files[key], self.settings)
        return self._sites[key]


@dataclass
class AnalysisData:
    """Measurements and everything chapters 1-3 derive from them.

    Attributes
    ----------
    measurements : Measurements
    per_day : numpy.ndarray
        Table ``titration_days``.
    posterior : TitrationPosterior
    errors : LifetimeErrors
    context : graph_fit.TitrationContext
    library : SiteLibrary or TableFiles
        Anything with ``.site(state, site, linker_length) -> Site``.
    site_settings : dict
        Site-model settings (linker lengths per dye).
    """

    measurements: object
    per_day: np.ndarray
    posterior: object
    errors: object
    context: object
    library: object
    site_settings: dict

    @property
    def titrated(self):
        """Every titrated ``(dye, amino_acid)`` with a line."""
        return sorted({(str(r["dye"]), str(r["amino_acid"])) for r in self.per_day})

    def rows(self, dye, solvent):
        """Measured site lifetimes of one dye and solvent.

        Parameters
        ----------
        dye, solvent : str

        Returns
        -------
        numpy.ndarray
            Rows of the ``site_lifetimes`` table (dye, solvent, state, site order).
        """
        d = self.errors.data
        return d[(d["dye"] == dye) & (d["solvent"] == solvent)]

    def tau0(self, dye, solvent):
        """Free-dye lifetime (ns).

        Parameters
        ----------
        dye, solvent : str

        Returns
        -------
        float
        """
        return float(self.errors.tau0[(dye, solvent)])

    def water_rate(self, name):
        """A declared water term.

        Parameters
        ----------
        name : str or float or None
            ``"free_dye"`` (kq_w,free), a number, or none (0).

        Returns
        -------
        float
            1/ns.
        """
        if name is None:
            return 0.0
        if name == "free_dye":
            return float(self.errors.kqw_free)
        return float(name)

    def points(self, dye, rows, water=0.0):
        """``(Site, water)`` per row, at the dye's declared linker length.

        Parameters
        ----------
        dye : str
        rows : numpy.ndarray
        water : float, optional

        Returns
        -------
        list of (Site, float)
        """
        length = float(self.site_settings["linker_lengths"][dye])
        return [(self.library.site(str(r["state"]), int(r["site"]), length), float(water))
                for r in rows]


def load_analysis_data(folder=None, library=None, structures=None, cache_dir=None):
    """Read the measurements and derive the titration posterior and the lifetime errors.

    Parameters
    ----------
    folder : str or pathlib.Path, optional
        Measurement folder (the shipped MalE data by default).
    library : object, optional
        Site models (``.site(state, site, linker_length)``); a :class:`SiteLibrary` on
        *structures* by default (site tables are built on first use and cached).
    structures : dict, optional
        ``{state: structure path}`` for the default library.
    cache_dir : str or pathlib.Path, optional
        Site-table cache folder of the default library.

    Returns
    -------
    AnalysisData
    """
    m = _measurements.load_measurements(folder)
    per_day, posterior = _titration.analyse_titrations(m.titration_points)
    errors = _lifetime_errors.analyse_lifetimes(m.lifetimes, m.titration_summary)
    site_settings = _site_table.settings()
    if library is None:
        library = _site_model.SiteLibrary(structures=structures, settings_=site_settings,
                                          cache_dir=cache_dir)
    return AnalysisData(
        measurements=m, per_day=per_day, posterior=posterior, errors=errors,
        context=_gf.TitrationContext.from_posterior(posterior), library=library,
        site_settings=site_settings,
    )


# --------------------------------------------------------------------------------------------
# results


@dataclass
class StageResult:
    """What one stage reports.

    Attributes
    ----------
    name : str
        Declared stage name (``A``, ``B``, ``naive_h2o``, ``C``, ``summary``).
    title : str
    views : list of graph_fit.BlockResult
        The data sets the stage reports (empty for a test or the summary).
    tables : dict
        ``{table name: numpy record array}``, declared in ``result_columns.yaml`` (or
        ``site_model.yaml`` for ``site_exposure``).
    plots : dict
        Plot data (plain numbers and lists; see :meth:`Analysis.run`).
    numbers : dict
        JSON-able key numbers (estimates, stats, test results).
    text : str
        Plain-language explanation written from the numbers.
    """

    name: str
    title: str
    views: list = field(default_factory=list)
    tables: dict = field(default_factory=dict)
    plots: dict = field(default_factory=dict)
    numbers: dict = field(default_factory=dict)
    text: str = ""


@dataclass
class AnalysisResult:
    """Every stage run so far, and the solved graphs.

    Attributes
    ----------
    stages : dict
        ``{stage name: StageResult}`` in run order.
    graphs : dict
        ``{graph name: graph_fit.GraphResult}``.
    preset : str or None
    fit_settings : dict
    """

    stages: dict = field(default_factory=dict)
    graphs: dict = field(default_factory=dict)
    preset: object = None
    fit_settings: dict = field(default_factory=dict)

    def tables(self):
        """Every table of every stage.

        Returns
        -------
        dict
            ``{"<stage>.<table>": numpy record array}``.
        """
        return {f"{s}.{name}": t for s, r in self.stages.items() for name, t in r.tables.items()}

    def view(self, label):
        """The view of a data set, from whichever graph holds it.

        Parameters
        ----------
        label : str

        Returns
        -------
        graph_fit.BlockResult
        """
        for g in self.graphs.values():
            for v in g.views:
                if v.label == label:
                    return v
        raise KeyError(f"no solved data set {label!r}")

    def to_dict(self):
        """A JSON-able summary: per stage its numbers, text and tables as row lists.

        Returns
        -------
        dict
        """
        out = dict(preset=self.preset, stages={}, graphs={})
        for name, r in self.stages.items():
            out["stages"][name] = dict(
                title=r.title, numbers=_jsonable(r.numbers), text=r.text,
                tables={k: table_rows(t) for k, t in r.tables.items()},
            )
        for name, g in self.graphs.items():
            s = dict(g.structure or {})
            s.pop("factor_graph", None)
            out["graphs"][name] = dict(
                blocks=[v.label for v in g.views], n_parameters=g.graph.n_parameters,
                n_slopes=len(g.graph.k_keys), structure=_jsonable(s),
            )
        return out

    def write(self, folder):
        """Write every table as CSV, the summary as JSON and the text as markdown.

        Parameters
        ----------
        folder : str or pathlib.Path

        Returns
        -------
        list of pathlib.Path
            The files written.
        """
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        written = []
        for name, table in self.tables().items():
            path = folder / f"{name}.csv"
            write_csv(table, path)
            written.append(path)
        path = folder / "summary.json"
        path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        written.append(path)
        path = folder / "report.md"
        path.write_text("\n\n".join(f"## {r.title}\n\n{r.text}" for r in self.stages.values()),
                        encoding="utf-8")
        written.append(path)
        return written


def table_rows(table):
    """A record array as a list of plain dicts.

    Parameters
    ----------
    table : numpy.ndarray

    Returns
    -------
    list of dict
    """
    return [{n: _jsonable(r[n].item() if hasattr(r[n], "item") else r[n])
             for n in table.dtype.names} for r in table]


def write_csv(table, path):
    """Write a record array as CSV (header = the declared columns).

    Parameters
    ----------
    table : numpy.ndarray
    path : str or pathlib.Path
    """
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(table.dtype.names)
        for r in table:
            w.writerow([repr(float(v)) if isinstance(v, (float, np.floating)) else v
                        for v in r.tolist()])


def _jsonable(value):
    """Plain JSON types of numpy values (NaN becomes None).

    Parameters
    ----------
    value : object

    Returns
    -------
    object
    """
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        v = float(value)
        return None if not np.isfinite(v) else v
    return value


# --------------------------------------------------------------------------------------------
# the analysis


class Analysis:
    """A quenching analysis: solves the declared graphs on demand and runs the stages.

    Parameters
    ----------
    data : AnalysisData, optional
        :func:`load_analysis_data` on the shipped MalE data by default.
    preset : str, optional
        Fit preset (``"full"``, ``"quick"``).
    fit_overrides : dict, optional
        Fit settings to replace (``{"n_starts": 16}``).
    workers : int, optional
        Worker processes for the searches and Jacobians (1 = in process; the CPU count by
        default).
    profile : bool, optional
        Compute the declared profile likelihoods (default True; they cost about a joint fit
        of the block's sub-graph per point).
    sampler_check : bool or dict, optional
        The optional MCMC check of the Laplace error bars (:mod:`.sampler_check`, the
        prototype's cell 40). None follows the declared ``sampler_check`` setting (off by
        default); True forces it on with the declared numbers; a dict adds options over the
        declared ones (``{"steps": 500}``). It runs for the blocks a stage declares under
        ``sampler_check:`` (stage A: the AF488 data set, as in cell 49).
    stage_path : str or pathlib.Path, optional
        Stage declaration.

    Attributes
    ----------
    result : AnalysisResult
        Everything run so far.
    """

    def __init__(self, data=None, preset=None, fit_overrides=None, workers=None, profile=True,
                 sampler_check=None, stage_path=STAGES):
        self.data = data if data is not None else load_analysis_data()
        self.preset = preset
        self.fit_settings = _gf.settings(preset, fit_overrides)
        self.workers = workers
        self.profile = bool(profile)
        self.sampler_check = _sampler_check.resolve(sampler_check,
                                                    self.fit_settings.get("sampler_check"))
        self.declaration = stage_settings(stage_path)
        groups = list(self.data.site_settings["groups"])
        declared = [p.label[2:] for p in _gf.parameter_specs(self.fit_settings)
                    if p.label.startswith("s_") and p.label != "s_common"]
        if declared != groups:
            raise ValueError(f"fit parameters declare groups {declared}, site model {groups}")
        self.groups = groups
        self.result = AnalysisResult(preset=preset, fit_settings=self.fit_settings)
        self._profiles = {}
        self._sampler_checks = {}

    # ---- graphs

    def blocks(self, graph_name, progress=None, cancel=None):
        """Fresh (unsearched) blocks of a declared graph.

        The site models are loaded (built and cached on first use) before the blocks are
        made, one table at a time, so a first run reports where it is.

        Parameters
        ----------
        graph_name : str
        progress : callable, optional
            ``progress(done, total, message)`` after each site table.
        cancel : callable, optional
            Checked between site tables.

        Returns
        -------
        list of graph_fit.Block
        """
        spec = self.declaration["graphs"][graph_name]
        lengths = self.data.site_settings["linker_lengths"]
        keys = []
        for entry in spec["blocks"]:
            for solvent in entry["solvents"]:
                for r in self.data.rows(entry["dye"], solvent):
                    key = (str(r["state"]), int(r["site"]), float(lengths[entry["dye"]]))
                    if key not in keys:
                        keys.append(key)
        for k, key in enumerate(keys):
            _gf._check(cancel)
            self.data.library.site(*key)
            if progress:
                progress(k + 1, len(keys), f"site table {key[0]} {key[1]} L {key[2]:g} "
                                           f"({k + 1}/{len(keys)})")
        out = []
        for entry in spec["blocks"]:
            dye = entry["dye"]
            water = entry.get("water") or {}
            parts, points = [], []
            for solvent in entry["solvents"]:
                rows = self.data.rows(dye, solvent)
                parts.append(rows)
                points += self.data.points(dye, rows, self.data.water_rate(water.get(solvent)))
            rows = np.concatenate(parts) if len(parts) > 1 else parts[0]
            block = _gf.Block(entry["label"], dye, rows, points,
                              self.data.tau0(dye, entry["tau0"]), self.data.context,
                              self.fit_settings, self.groups)
            if self.fit_settings.get("use_declared_starts", True):
                for start in entry.get("starts") or []:
                    block.add_start(start)
            out.append(block)
        return out

    def graph(self, name, progress=None, cancel=None):
        """A solved graph (solved once, then kept).

        Parameters
        ----------
        name : str
            Declared graph.
        progress : callable, optional
            ``progress(fraction, message)``.
        cancel : callable, optional

        Returns
        -------
        graph_fit.GraphResult
        """
        if name not in self.result.graphs:
            share = float(self.declaration["progress_weights"].get("site_tables", 0.1))

            def loading(done, total, message):
                if progress:
                    progress(share * done / total, message)

            def fitting(fraction, message):
                if progress:
                    progress(share + (1 - share) * fraction, message)

            blocks = self.blocks(name, progress=loading, cancel=cancel)
            self.result.graphs[name] = _gf.fit_graph(
                blocks, fit_settings=self.fit_settings, workers=self.workers,
                progress=fitting, cancel=cancel, name=name, titrated=self.data.titrated,
            )
        return self.result.graphs[name]

    def replay(self, name, values, slopes, progress=None, cancel=None):
        """Re-evaluate a stored optimum: settle at *values*, polish from them, no search.

        The joint fit starts at the given block parameters and titration slopes and is only
        polished (no MINPACK stage), so the Laplace intervals, leave one out and notes are
        taken at the stored run's optimum. Model errors come from ``values[label]
        ["model_error"]`` when given.

        Parameters
        ----------
        name : str
            Declared graph.
        values : dict
            ``{block label: {internal name: value}}``.
        slopes : dict
            ``{(dye, amino_acid): K_SV}``.
        progress, cancel : callable, optional

        Returns
        -------
        graph_fit.GraphResult
        """
        blocks = self.blocks(name, cancel=cancel)
        for block in blocks:
            _gf.adopt(block, values[block.label], self.fit_settings)
        graph = _gf.Graph(blocks, self.fit_settings)
        v = [slopes[key] if b is None else blocks[b].best_x[i] for b, key, i in graph.layout]
        _gf.joint_fit(graph, workers=self.workers, cancel=cancel, start=graph.to_u(np.array(v)),
                      minpack=False)
        self.result.graphs[name] = _gf.GraphResult(
            name=name, graph=graph, views=_gf.block_views(graph, name),
            k_table=_gf.k_table(graph, name),
            structure=_gf.describe_graph(graph, self.data.titrated))
        if progress:
            progress(1.0, f"{name} replayed")
        return self.result.graphs[name]

    def solve_from(self, name, values, progress=None, cancel=None):
        """Solve a graph starting from given block parameters instead of searching.

        Each block is settled at its values (model error and inliers by the search's rule,
        :func:`graph_fit.adopt`), then the joint fit, Laplace and leave one out run as usual.
        This replays a stored run's searches (e.g. the MalE prototype's printed estimates).

        Parameters
        ----------
        name : str
            Declared graph.
        values : dict
            ``{block label: {internal name: value}}``; a block missing here is searched.
        progress, cancel : callable, optional

        Returns
        -------
        graph_fit.GraphResult
        """
        blocks = self.blocks(name)
        for block in blocks:
            if block.label in values:
                _gf.adopt(block, values[block.label], self.fit_settings)
        self.result.graphs[name] = _gf.fit_graph(
            blocks, fit_settings=self.fit_settings, workers=self.workers, progress=progress,
            cancel=cancel, name=name, titrated=self.data.titrated,
        )
        return self.result.graphs[name]

    def profile_of(self, graph_name, label, progress=None, cancel=None):
        """The quench-scale profile likelihood of one data set (computed once).

        Parameters
        ----------
        graph_name, label : str
        progress : callable, optional
            ``progress(done, total, label)``.
        cancel : callable, optional

        Returns
        -------
        dict
            :func:`graph_fit.profile_likelihood`.
        """
        key = (graph_name, label)
        if key not in self._profiles:
            view = self.graph(graph_name).view(label)
            self._profiles[key] = _gf.profile_likelihood(view, "ln_scale", cancel=cancel,
                                                         progress=progress, workers=self.workers)
        return self._profiles[key]

    def sampler_check_of(self, graph_name, label, progress=None, cancel=None):
        """The MCMC-vs-Laplace comparison of one data set (computed once).

        Runs only when the check is enabled (:attr:`sampler_check`); the numbers are the
        declared ``sampler_check`` setting's, unless the :class:`Analysis` was given others.

        Parameters
        ----------
        graph_name, label : str
        progress : callable, optional
            ``progress(done, total, label)``.
        cancel : callable, optional

        Returns
        -------
        dict
            :func:`sampler_check.sampler_check`.
        """
        if self.sampler_check is None:
            raise ValueError("the sampler check is off (enable it with sampler_check=True, "
                             "a dict of options, or the declared sampler_check setting)")
        key = (graph_name, label)
        if key not in self._sampler_checks:
            view = self.graph(graph_name).view(label)
            o = self.sampler_check
            self._sampler_checks[key] = _sampler_check.sampler_check(
                view, steps=o.get("steps"), runs=o.get("runs"), walkers=o.get("walkers"),
                start_spread=o.get("start_spread"), first_seed=o.get("first_seed"),
                cancel=cancel, progress=progress)
        return self._sampler_checks[key]

    # ---- running

    def _plan(self, names):
        """Steps (graphs, profiles, stages) still to do for *names*, with their weights.

        Parameters
        ----------
        names : list of str

        Returns
        -------
        list of tuple
        """
        weights = self.declaration["progress_weights"]
        stages = self.declaration["stages"]
        steps, seen = [], set()

        def need_graph(graph, profiles=(), checks=()):
            if graph not in self.result.graphs and ("graph", graph) not in seen:
                seen.add(("graph", graph))
                steps.append(("graph", graph, float(weights.get(graph, weights["other"]))))
            if self.profile:
                for label in profiles:
                    key = (graph, label)
                    if key not in self._profiles and ("profile", key) not in seen:
                        seen.add(("profile", key))
                        steps.append(("profile", key, float(weights["profile"])))
            if self.sampler_check is not None:
                for label in checks:
                    key = (graph, label)
                    if key not in self._sampler_checks and ("sampler", key) not in seen:
                        seen.add(("sampler", key))
                        steps.append(("sampler", key,
                                      float(weights.get("sampler_check", weights["other"]))))

        def need(name):
            spec = stages[name]
            if spec["kind"] == "transfer":
                need(spec["source"]["stage"])
            if spec["kind"] == "summary":
                for s in spec["estimates"]:
                    need(s)
            if "compare_scale" in spec:
                other = spec["compare_scale"]["with"]
                need_graph(other["graph"], [other["block"]])
            if spec.get("graph"):
                need_graph(spec["graph"], spec.get("profile", []),
                           spec.get("sampler_check", []))
            if name not in self.result.stages and ("stage", name) not in seen:
                seen.add(("stage", name))
                steps.append(("stage", name, float(weights["other"])))

        for name in names:
            need(name)
        return steps

    def run(self, stages="all", progress=None, cancel=None):
        """Run stages (and everything they need).

        Parameters
        ----------
        stages : str or sequence of str, optional
            ``"all"`` (the declared order), one stage name, or several.
        progress : callable, optional
            ``progress(percent: int, message: str)``.
        cancel : callable, optional
            ``cancel() -> bool``; raises :class:`CancelledError` at the next checkpoint (between
            searches, at every joint-fit evaluation, between profile points).

        Returns
        -------
        AnalysisResult
            :attr:`result`, with the requested stages in it.

        Notes
        -----
        Plot data of a ``blocks`` stage, per data set ``<label>``: ``parity:<label>``
        (``measured``, ``predicted``, ``sigma_total``, ``pred_sd``, ``state``, ``site``,
        ``solvent``, ``outlier``, ``tau0``), ``estimates:<label>`` (rows), ``loo:<label>``
        (``site``, ``max_abs_z``, ``limit``), ``profile:<label>`` (``laplace`` samples and
        summary, ``profile`` values and deviance); stage A also ``k_graph`` (rows of
        ``graph_titration_slopes``); stage C ``water_access`` and ``exposure`` (per site the
        histogram data). ``summary``: ``scale`` and ``stickiness`` per dye.

        With the sampler check enabled (:attr:`Analysis.sampler_check`), a ``blocks`` stage
        also carries ``sampler_check:<label>`` (``rows``, ``n_samples``, ``acceptance``,
        ``verdict``) and the comparison in ``numbers`` and ``text``.
        """
        names = self.declaration["order"] if stages == "all" else (
            [stages] if isinstance(stages, str) else list(stages))
        for name in names:
            if name not in self.declaration["stages"]:
                raise KeyError(f"no stage {name!r}; declared {self.declaration['order']}")
        steps = self._plan(names)
        total = sum(w for *_, w in steps) or 1.0
        done = 0.0

        def say(fraction, message, weight):
            if progress:
                progress(int(100 * min(1.0, (done + weight * fraction) / total)), message)

        for kind, what, weight in steps:
            _gf._check(cancel)
            if kind == "graph":
                self.graph(what, progress=lambda f, m, w=weight: say(f, m, w), cancel=cancel)
            elif kind == "profile":
                self.profile_of(*what, cancel=cancel,
                                progress=lambda d, t, m, w=weight: say(d / t, m, w))
            elif kind == "sampler":
                self.sampler_check_of(*what, cancel=cancel,
                                      progress=lambda d, t, m, w=weight: say(d / t, m, w))
            else:
                self.result.stages[what] = self._stage(what)
            done += weight
            say(0.0, f"{kind} {what if isinstance(what, str) else what[1]} done", 0.0)
        if progress:
            progress(100, "done")
        return self.result

    # ---- stages

    def _stage(self, name):
        """Build one stage's result (its graphs are solved).

        Parameters
        ----------
        name : str

        Returns
        -------
        StageResult
        """
        spec = self.declaration["stages"][name]
        kind = spec["kind"]
        if kind == "blocks":
            return self._blocks_stage(name, spec)
        if kind == "transfer":
            return self._transfer_stage(name, spec)
        if kind == "summary":
            return self._summary_stage(name, spec)
        raise ValueError(f"stage {name!r}: unknown kind {kind!r}")

    def _blocks_stage(self, name, spec):
        """A stage that reports blocks of a solved graph.

        Parameters
        ----------
        name : str
        spec : dict

        Returns
        -------
        StageResult
        """
        g = self.graph(spec["graph"])
        views = [g.view(label) for label in spec["blocks"]]
        tables = dict(
            predictions=np.concatenate([v.table for v in views]),
            estimates=np.concatenate([v.estimates for v in views]),
            leave_one_out=np.concatenate([v.loo for v in views]),
            site_ranking=np.concatenate([_gf.site_ranking_table(v, g.name) for v in views]),
            searches=np.concatenate([_gf.searches_table(v, g.name) for v in views]),
            titration_slopes=g.k_table,
        )
        plots, numbers = {}, dict(graph=g.name, blocks={})
        intervals, profile_rows = [], []
        for v in views:
            samples = _gf.laplace_samples(v)
            laplace = _gf.sample_summary(samples)
            intervals.append(dict(graph=g.name, block=v.label, parameter="scale",
                                  method="laplace", value=laplace["median"],
                                  low_68=laplace["low"], high_68=laplace["high"]))
            prof = None
            if self.profile and v.label in spec.get("profile", []):
                prof = self.profile_of(g.name, v.label)
                intervals.append(dict(graph=g.name, block=v.label, parameter="scale",
                                      method="profile", value=prof["best"], low_68=prof["low"],
                                      high_68=prof["high"]))
                profile_rows += [dict(graph=g.name, block=v.label, parameter="scale",
                                      value=float(x), deviance=float(d))
                                 for x, d in zip(prof["values"], prof["deviance"])]
            t = v.table
            plots[f"parity:{v.label}"] = dict(
                measured=t["tau_x"].tolist(), predicted=t["tau_pred"].tolist(),
                sigma_total=t["sigma_total"].tolist(), pred_sd=t["pred_sd"].tolist(),
                state=t["state"].tolist(), site=t["site"].tolist(),
                solvent=t["solvent"].tolist(), outlier=t["outlier"].tolist(),
                tau0={s: self.data.tau0(v.dye, s) for s in sorted(set(t["solvent"].tolist()))
                      if (v.dye, s) in self.data.errors.tau0},
            )
            plots[f"estimates:{v.label}"] = table_rows(v.estimates)
            plots[f"loo:{v.label}"] = dict(site=[s for s, _ in v.worst],
                                           max_abs_z=[z for _, z in v.worst],
                                           limit=float(self.fit_settings["outlier_limit"]))
            plots[f"profile:{v.label}"] = dict(
                laplace=samples.tolist(), laplace_summary=laplace,
                profile=None if prof is None else dict(
                    values=np.asarray(prof["values"]).tolist(),
                    deviance=np.asarray(prof["deviance"]).tolist(),
                    best=prof["best"], low=prof["low"], high=prof["high"]),
            )
            numbers["blocks"][v.label] = dict(
                dye=v.dye, model_error=v.model_error, stats=v.stats,
                worst=[[int(s), float(z)] for s, z in v.worst],
                estimates={r["parameter"]: dict(value=float(r["value"]),
                                                low=float(r["low_68"]),
                                                high=float(r["high_68"]), note=str(r["note"]))
                           for r in v.estimates},
                scale_laplace=laplace,
                scale_profile=None if prof is None else dict(best=prof["best"], low=prof["low"],
                                                             high=prof["high"]),
            )
        tables["intervals"] = _gf.make_result_table("interval_summary", intervals)
        if profile_rows:
            tables["scale_profile"] = _gf.make_result_table("scale_profile", profile_rows)
        plots["k_graph"] = table_rows(g.k_table)
        if g.structure:
            s = dict(g.structure)
            s.pop("factor_graph", None)
            numbers["graph_structure"] = s
        numbers["graph_size"] = dict(blocks=len(g.views), parameters=g.graph.n_parameters,
                                     slopes=len(g.graph.k_keys))
        text = [_report.explain(v, self.groups) for v in views]
        if "water_access" in spec:
            access, extra = self._water_access(g, spec["water_access"])
            tables["water_access"] = access
            numbers["water_access"] = extra
            plots["water_access"] = dict(rows=table_rows(access), **extra)
            text.append(_report.water_access_text(extra))
        if "exposure" in spec:
            exposure, hist = self._exposure(g, spec["exposure"])
            tables["exposure"] = exposure
            numbers["exposure"] = table_rows(exposure)
            plots["exposure"] = hist
        for v in views:
            if (v.label in spec.get("profile", []) and self.profile):
                text.append(_report.profile_text(v.label, numbers["blocks"][v.label]))
        check_labels = spec.get("sampler_check", [])
        if self.sampler_check is not None and check_labels:
            numbers["sampler_check"] = {}
            for v in views:
                if v.label not in check_labels:
                    continue
                check = self.sampler_check_of(g.name, v.label)
                numbers["sampler_check"][v.label] = check
                numbers["blocks"][v.label]["sampler_check"] = check
                plots[f"sampler_check:{v.label}"] = dict(
                    rows=check["parameters"], n_samples=check["n_samples"],
                    acceptance=check["acceptance"], verdict=check["verdict"])
                text.append(_sampler_check.text(check))
        if "compare_scale" in spec:
            cmp = spec["compare_scale"]
            other = self.graph(cmp["with"]["graph"]).view(cmp["with"]["block"])
            here = numbers["blocks"][cmp["block"]]
            there = _gf.sample_summary(_gf.laplace_samples(other))
            comparison = dict(laplace=dict(first=there, second=here["scale_laplace"]))
            text.append("Laplace: " + _report.compare_profiles(
                there, here["scale_laplace"], (other.label, cmp["block"])))
            key = (cmp["with"]["graph"], cmp["with"]["block"])
            if self.profile and here.get("scale_profile") and key in self._profiles:
                p = self._profiles[key]
                comparison["profile"] = dict(first=dict(low=p["low"], high=p["high"]),
                                             second=here["scale_profile"])
                text.append("Profile likelihood: " + _report.compare_profiles(
                    comparison["profile"]["first"], here["scale_profile"],
                    (other.label, cmp["block"])))
            numbers["compare_scale"] = comparison
            plots["profiles"] = {other.label: there, cmp["block"]: here["scale_laplace"]}
        return StageResult(name=name, title=spec["title"], views=views, tables=tables,
                           plots=plots, numbers=_jsonable(numbers), text="\n\n".join(text))

    def _water_access(self, g, spec):
        """Measured against model water access per site (Stage C).

        Parameters
        ----------
        g : graph_fit.GraphResult
        spec : dict

        Returns
        -------
        tuple
            ``(water_access_model table, {"r_all", "r_without", "without"})``.
        """
        view = g.view(spec["block"])
        rows = view.block.rows
        solvent = np.asarray(rows["solvent"])
        d2o = np.flatnonzero(solvent == "D2O")
        h2o = np.flatnonzero(solvent == "H2O")
        pairs = []
        for j_h in h2o:
            match = [j for j in d2o if rows["site"][j] == rows["site"][j_h]
                     and rows["state"][j] == rows["state"][j_h]]
            if match:
                pairs.append((int(j_h), int(match[0])))
        kqw = float(self.data.errors.kqw_free)
        points = view.block.points

        def access(th):
            p = _site_model.predict(points, th, np.exp(th["ln_tau0"]))
            return [(1 / p[j_h] - 1 / p[j_d]) / kqw for j_h, j_d in pairs]

        model, model_err = _gf.propagate(view, access)
        measured = {(int(r["site"]), str(r["state"])): r for r in self.data.errors.access}
        out = []
        for (j_h, _), m, e in zip(pairs, model, model_err):
            key = (int(rows["site"][j_h]), str(rows["state"][j_h]))
            r = measured[key]
            out.append(dict(site=key[0], state=key[1], measured=float(r["measured"]),
                            measured_err=float(r["measured_err"]), model=float(m),
                            model_err=float(e)))
        table = _gf.make_result_table("water_access_model", out)
        without = [int(s) for s in spec.get("also_without", [])]
        keep = ~np.isin(table["site"], without)
        r_all = float(np.corrcoef(table["measured"], table["model"])[0, 1])
        r_without = float(np.corrcoef(table["measured"][keep], table["model"][keep])[0, 1])
        return table, dict(r_all=r_all, r_without=r_without, without=without)

    def _exposure(self, g, spec):
        """Time-weighted water exposure of declared sites (Stage C).

        Parameters
        ----------
        g : graph_fit.GraphResult
        spec : dict

        Returns
        -------
        tuple
            ``(site_exposure table, histogram data per site)``.
        """
        view = g.view(spec["block"])
        rows = view.block.rows
        tau0 = self.data.tau0(view.dye, spec["solvent"])
        out, hist = [], {}
        for site in spec["sites"]:
            j = [k for k in range(len(rows)) if int(rows["site"][k]) == int(site)
                 and str(rows["state"][k]) == spec["state"]
                 and str(rows["solvent"][k]) == spec["solvent"]][0]
            here = view.block.points[j][0]
            e = here.exposure_profile(view.theta, tau0)
            out.append(dict(site=int(site), state=spec["state"], reachable=e["reachable"],
                            visible=e["visible"], dark_fraction=e["dark_fraction"]))
            hist[str(site)] = dict(exposure=e["exposure"].tolist(), weight=e["weight"].tolist(),
                                   visible=e["visible"], reachable=e["reachable"],
                                   dark_fraction=e["dark_fraction"])
        return _site_model.exposure_table(out), hist

    def _transfer_stage(self, name, spec):
        """A test: one stage's parameters predict another solvent (naive H2O transfer).

        Parameters
        ----------
        name : str
        spec : dict

        Returns
        -------
        StageResult
        """
        source = self.declaration["stages"][spec["source"]["stage"]]
        g = self.graph(source["graph"])
        view = g.view(spec["source"]["block"])
        dye, solvent = spec["dye"], spec["solvent"]
        rows = self.data.rows(dye, solvent)
        points = self.data.points(dye, rows)
        tau0 = self.data.tau0(dye, spec["tau0"])
        value, error = _gf.propagate(
            view, lambda th: [site.lifetime(th, tau0)[0] for site, _ in points])
        tau_x = np.asarray(rows["tau_x"], float)
        label = f"{dye} in {solvent} from {view.label}"
        table = _gf.make_result_table("fit_predictions", [
            dict(graph=g.name, block=label, dye=dye, solvent=solvent, state=str(r["state"]),
                 site=int(r["site"]), tau_x=float(r["tau_x"]),
                 sigma_meas=float(r["sigma_meas"]), sigma_total=float(r["sigma_meas"]),
                 tau_pred=float(v), pred_sd=float(e), pred_low=float(v - e),
                 pred_high=float(v + e), dark_fraction=float(site.lifetime(view.theta, tau0)[1]),
                 loo_z=float("nan"), outlier=False, used=False)
            for r, v, e, (site, _) in zip(rows, value, error, points)
        ])
        numbers = dict(
            source=view.label, tau0=tau0, n=int(len(rows)),
            median_abs_dev=float(np.median(np.abs(value - tau_x))),
            sites_above_free_tau0=int((tau_x > tau0).sum()),
        )
        plots = {f"parity:{label}": dict(
            measured=tau_x.tolist(), predicted=value.tolist(),
            sigma_total=table["sigma_total"].tolist(), pred_sd=error.tolist(),
            state=table["state"].tolist(), site=table["site"].tolist(),
            solvent=table["solvent"].tolist(), outlier=[False] * len(rows),
            tau0={solvent: tau0})}
        return StageResult(name=name, title=spec["title"], tables=dict(predictions=table),
                           plots=plots, numbers=numbers,
                           text=_report.transfer_text(numbers, dye, solvent))

    def _summary_stage(self, name, spec):
        """One line per dye and the estimates of every stage.

        Parameters
        ----------
        name : str
        spec : dict

        Returns
        -------
        StageResult
        """
        lines, final = [], {}
        for dye, label in spec["final"].items():
            v = self.result.view(label)
            final[dye] = v
            lines.append(_report.dye_line(v, self.groups))
        table = _gf.make_result_table("dye_summary", [
            dict(dye=dye, block=v.label, scale=line["scale"], scale_low=line["scale_low"],
                 scale_high=line["scale_high"], scale_note=line["scale_note"],
                 stickiest_group=line["stickiest_group"],
                 outlier_sites=" ".join(str(s) for s in line["outliers"]))
            for (dye, v), line in zip(final.items(), lines)
        ])
        estimates = np.concatenate([self.result.stages[s].tables["estimates"]
                                    for s in spec["estimates"]])
        slopes = np.concatenate([self.graph(g).k_table for g in self.result.graphs])
        plots = dict(
            scale={dye: v.estimate("scale") for dye, v in final.items()},
            stickiness={dye: {g: v.estimate(f"s_{g}") for g in self.groups}
                        for dye, v in final.items()},
        )
        return StageResult(name=name, title=spec["title"],
                           tables=dict(dyes=table, estimates=estimates, titration_slopes=slopes),
                           plots=plots, numbers=dict(dyes=_jsonable(lines)),
                           text=_report.summary_text(lines))


def run_stage(stage, data=None, preset=None, fit_overrides=None, workers=None, progress=None,
              cancel=None, profile=True, sampler_check=None, analysis=None):
    """Run one stage (and what it needs) headless.

    Parameters
    ----------
    stage : str
        Declared stage (:func:`stage_names`), or ``"all"``.
    data : AnalysisData, optional
        The shipped MalE data by default.
    preset : str, optional
        ``"full"`` or ``"quick"``.
    fit_overrides : dict, optional
    workers : int, optional
    progress : callable, optional
        ``progress(percent, message)``.
    cancel : callable, optional
        ``cancel() -> bool``; raises :class:`CancelledError` at the next checkpoint.
    profile : bool, optional
        Compute the profile likelihoods.
    sampler_check : bool or dict, optional
        The optional MCMC check of the Laplace error bars (see :class:`Analysis`).
    analysis : Analysis, optional
        Continue an analysis (its solved graphs are reused); the other arguments except
        *progress*/*cancel* are then ignored.

    Returns
    -------
    AnalysisResult
    """
    analysis = analysis or Analysis(data, preset=preset, fit_overrides=fit_overrides,
                                    workers=workers, profile=profile,
                                    sampler_check=sampler_check)
    return analysis.run(stage, progress=progress, cancel=cancel)


def run_analysis(data=None, preset=None, **kwargs):
    """Run every declared stage.

    Parameters
    ----------
    data : AnalysisData, optional
    preset : str, optional
    **kwargs
        As :func:`run_stage`.

    Returns
    -------
    AnalysisResult
    """
    return run_stage("all", data=data, preset=preset, **kwargs)
