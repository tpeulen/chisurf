"""Whether a chain can be believed — the two plots that show it.

Convergence statistics are reported as numbers elsewhere; these are the pictures
that show *how* a chain failed, which a threshold cannot.

- **Rank plot** — draws ranked across all chains together, histogrammed per
  chain. Converged chains are flat; a chain that lingers somewhere the others do
  not shows as a slope or a spike. Recommended over a trace plot because a trace
  plot's resolution collapses as the chain lengthens, so it becomes unreadable
  exactly when there are finally enough draws to judge.
- **ESS evolution** — effective sample size against draws taken. Converged, it
  grows linearly: twice the effort buys twice the information. Flattening means
  the extra draws are telling you nothing new.
"""

from __future__ import annotations

import numpy as np

import chisurf.core.fitting
from chisurf import chiplot as cp
from chisurf.chiplot import style as S
from chisurf.core.fitting import diagnostics as dg
from chisurf.core.support.i18n import tr
from chisurf.emtk.fit_pages.pages import emtk_notes as N
from chisurf.emtk.fit_pages.pages.plotbase import Plot

#: One colour per chain, distinguishable and stable across both tabs.
CHAIN_COLOURS = (
    "#4c9be8",
    "#e8834c",
    "#5cc98a",
    "#c96ec9",
    "#e8c84c",
    "#7f7fe8",
    "#e85c7a",
    "#4cc9c9",
)


#: Above this many chains, overlaid histograms become a solid block of colour
#: and the rank plot switches to a heatmap. Differential evolution runs a
#: population, so this is the common case rather than the exotic one.
MAX_OVERLAID_CHAINS = 5


def _chain_colour(index: int) -> str:
    """Return the colour for chain ``index``."""
    return CHAIN_COLOURS[index % len(CHAIN_COLOURS)]


class SamplingDiagnosticsPlot(Plot):
    """Rank plots and ESS evolution for a fit's stored chain."""

    name = "Chain diagnostics"

    def __init__(self, fit: chisurf.core.fitting.fit.Fit, **kwargs):
        """The rank and ESS panels with their notes, and the parameter choice."""
        from chisurf.emtk.fit_pages.pages.emtk_page import PanelItem

        super().__init__(fit)
        self.fit = fit
        self.tabs = N.Tabs(("Rank", "ESS growth"))
        #: Index into :attr:`parameters` of the parameter the rank tab shows.
        self.parameter = 0

        self.rank_plot = cp.Panel()
        self.rank_plot.set_labels(bottom="rank (pooled over chains)", left="draws")
        self.rank_notes = []
        self.ess_plot = cp.Panel()
        self.ess_plot.set_labels(bottom="draws per chain", left="effective sample size")
        self.ess_notes = []
        self.panel_items = [
            PanelItem(self.rank_plot, self.rank_plot.control()),
            PanelItem(self.ess_plot, self.ess_plot.control()),
        ]
        # The fit window's right-click menu offers a panel's own entries.
        self._extra_menu_actions = [(tr("Open in ndX"), self._open_in_ndx)]
        for plot in (self.rank_plot, self.ess_plot):
            plot.add_menu_action(*self._extra_menu_actions[0])

        self._chains = None
        self._names = []
        self._draws = 0
        #: What the last :meth:`update` found (see :meth:`_load`).
        self.state = "none"

    @property
    def parameters(self) -> list:
        """The parameter names the rank tab offers."""
        return list(self._names)

    def set_parameter(self, index: int) -> None:
        """Show parameter *index* on the rank tab."""
        self.parameter = int(index)
        self._draw_rank()

    def emtk_draw(self, box) -> None:
        """The tab bar; the rank tab carries the parameter choice above its plot."""
        from emtk import im

        for item in self.panel_items:
            item.box = None  # a hidden tab's panel must not answer a right click

        def body(index: int) -> None:
            if index == 0:
                if self._names:
                    im.text(tr("Parameter"))
                    im.same_line()
                    im.set_next_item_width(-1.0)
                    changed, picked = im.combo("##chain-parameter", self.parameter, self._names)
                    im.set_item_tooltip(tr("The parameter whose per-chain ranks are drawn."))
                    if changed:
                        self.set_parameter(picked)
                N.panel_and_notes("chain-rank", self.panel_items[0], self.rank_notes)
            else:
                N.panel_and_notes("chain-ess", self.panel_items[1], self.ess_notes)

        self.tabs.draw("chain-tabs", body)

    # -- data ---------------------------------------------------------------

    #: Number of draws per chain below which neither panel means anything.
    MIN_DRAWS = 8

    def _owner(self):
        """The fit holding the run: the fit, else a group's selected member.

        ``sample_fit`` leaves the run on both; a restored project keeps it on the
        member that owns it.
        """
        fit = self.fit
        if getattr(fit, "sampling_chain", None) is None and not getattr(
            fit, "sampling_diagnostics", None
        ):
            selected = getattr(fit, "selected_fit", None) if hasattr(fit, "grouped_fits") else None
            if selected is not None:
                return selected
        return fit

    def _load(self) -> str:
        """Pull the stored chain off the fit and say what was found.

        Returns
        -------
        str
            ``"ok"`` (a chain to draw), ``"none"`` (neither a chain nor a
            report), ``"external"`` (a report but no draws: the run happened in
            another process and only its summary reached this fit) or
            ``"short"`` (fewer than :attr:`MIN_DRAWS` draws per chain).
        """
        owner = self._owner()
        chain = getattr(owner, "sampling_chain", None)
        report = getattr(owner, "sampling_diagnostics", None)
        self._chains, self._names, self._draws = None, [], 0
        if not isinstance(chain, dict) or chain.get("chains") is None:
            return "external" if isinstance(report, dict) else "none"
        chains = np.asarray(chain["chains"], dtype=float)
        if chains.ndim != 3 or chains.shape[1] < self.MIN_DRAWS:
            self._draws = int(chains.shape[1]) if chains.ndim == 3 else 0
            return "short"
        self._chains = chains
        self._names = [str(n).split(":")[-1] for n in chain.get("parameter_names", [])]
        while len(self._names) < chains.shape[2]:
            self._names.append(f"p{len(self._names)}")
        return "ok"

    def reason(self, state: str) -> str:
        """The line a page shows when there is nothing to draw, for a ``_load`` state."""
        if state == "short":
            return tr("chain has {n} draws; at least {m} are needed").format(
                n=self._draws, m=self.MIN_DRAWS
            )
        if state == "external":
            return tr("chain was produced in another process — open its folder in ndX")
        return tr(
            "no chain stored for this fit — run a sampling job (Chain "
            "diagnostics describes what it produced, it does not sample)"
        )

    def update(self, *args, **kwargs) -> None:
        """Reload the chain and redraw both tabs."""
        super().update(*args, **kwargs)
        previous = self._names[self.parameter] if self.parameter < len(self._names) else None
        self.state = self._load()
        if self.state != "ok":
            message = [N.Line(self.reason(self.state), N.MUTED)]
            for plot in (self.rank_plot, self.ess_plot):
                plot.clear()
            self.rank_notes, self.ess_notes = list(message), list(message)
            self.parameter = 0
            return

        # The same parameter stays selected when the chain is reloaded.
        self.parameter = self._names.index(previous) if previous in self._names else 0
        self._draw_rank()
        self._draw_ess()

    # -- ndX ------------------------------------------------------------------

    def _open_in_ndx(self) -> None:
        """Open the project's stored chain in ndX.

        The saved document is opened when it holds what is on screen; otherwise
        the live project is written to a scratch ``.cs.pto`` first, so ndX sees
        the run that was just made.
        """
        try:
            path = project_path_for_ndx()
            from chisurf.plugins.ndxplorer.gui.app import open_in_ndx

            open_in_ndx(path)
        except Exception as exc:
            chisurf.logging.warning(f"Open in ndX: {exc}")

    # -- drawing ------------------------------------------------------------

    def _draw_rank(self, *args) -> None:
        """Draw per-chain rank histograms for the selected parameter."""
        if self._chains is None:
            return
        index = max(0, self.parameter)
        counts, edges, expected = dg.rank_histogram(self._chains, bins=20)
        if index >= counts.shape[0]:
            return
        per_chain = counts[index]

        plot = self.rank_plot
        plot.clear()
        plot.set_title(f"Rank plot — {self._names[index]}")
        n_chains = per_chain.shape[0]

        if n_chains <= MAX_OVERLAID_CHAINS:
            # Few enough chains to overlay as step outlines, which is the
            # familiar form and reads exactly.
            for c in range(n_chains):
                xs, ys = [], []
                for i in range(per_chain.shape[1]):
                    xs.extend([edges[i], edges[i + 1]])
                    ys.extend([per_chain[c, i], per_chain[c, i]])
                plot.line(xs, ys, pen=S.to_pen(_chain_colour(c), width=1.6), name=f"chain {c + 1}")
            plot.line(
                [0.0, 1.0],
                [expected, expected],
                pen=S.to_pen("#909090", width=1.2, style="dash"),
                name="expected",
            )
            top = max(float(per_chain.max()), expected) * 1.15
            plot.set_range(x=(0.0, 1.0), y=(0.0, top), padding=0.0)
            plot.set_labels(left="draws")
            plot.grid(x=False, y=True, alpha=0.15)
        else:
            # Differential evolution runs a *population* -- ten or twenty chains
            # routinely -- and twenty overlaid histograms are a solid block of
            # colour in which nothing can be read. As a heatmap the same data
            # scales to any number of chains: one row each, colour the departure
            # from flat, so a chain favouring one end of the range is a bright
            # band and convergence is an even field.
            deviation = (per_chain - expected) / max(expected, 1e-12)
            limit = max(0.35, float(np.abs(deviation).max()))
            plot.image(
                deviation,
                colormap="coolwarm",
                levels=(-limit, limit),
                rect=(0.0, 0.5, 1.0, float(n_chains)),
            )
            plot.set_range(x=(0.0, 1.0), y=(0.5, n_chains + 0.5), padding=0.0)
            plot.set_labels(left="chain")
            plot.grid(x=False, y=False)

        # The picture shows *where* a chain is over-represented; this says
        # whether it means anything. Measured against what noise alone produces
        # for a histogram of this size, not against a fixed percentage -- a
        # converged run's worst bin is routinely tens of percent off, so a fixed
        # threshold fires on healthy chains and teaches the reader to ignore it.
        tau = float(dg.within_chain_tau(self._chains)[index])
        z_max, z_null = dg.rank_uniformity(per_chain, int(self._chains.shape[1]), 20, tau=tau)
        ratio = z_max / max(z_null, 1e-12)
        verdict = (
            "consistent with noise — the chains cover the same distribution"
            if ratio < 1.5
            else "more structure than noise explains — worth a longer run"
            if ratio < 2.5
            else "far beyond noise — the chains are not sampling the same distribution"
        )
        self.rank_notes = [
            N.Line("each chain's share of the pooled ranks; flat = converged", N.MUTED),
            N.Line(
                f"worst bin {z_max:.1f}σ from flat, against {z_null:.1f}σ "
                f"expected by chance at τ={tau:.0f} — {verdict}"
            ),
        ]

    def _draw_ess(self) -> None:
        """Draw effective sample size against draws, for every parameter."""
        if self._chains is None:
            return
        draws, ess = dg.ess_evolution(self._chains, points=12)
        plot = self.ess_plot
        plot.clear()
        plot.set_title("Effective sample size vs draws")
        # The legend has to exist before the curves it describes, or it is
        # created empty and the parameters cannot be told apart.
        plot.legend()
        if draws.size == 0:
            self.ess_notes = [N.Line("too few draws to estimate", N.MUTED)]
            return

        for k in range(ess.shape[1]):
            plot.line(
                draws, ess[:, k], pen=S.to_pen(_chain_colour(k), width=1.6), name=self._names[k]
            )
        # Linear growth is what a converged sampler does; the reference makes
        # "flattening" a comparison rather than a judgement call.
        final = float(np.nanmax(ess[-1])) if ess.size else 0.0
        if final > 0:
            slope = final / float(draws[-1])
            plot.line(
                draws,
                slope * draws,
                pen=S.to_pen("#909090", width=1.2, style="dash"),
                name="linear growth",
            )
        plot.grid(x=True, y=True, alpha=0.15)

        worst = float(np.nanmin(ess[-1]))
        ratio = worst / float(draws[-1] * self._chains.shape[0])
        self.ess_notes = [
            N.Line(
                "a converged sampler's ESS grows linearly; flattening means the extra "
                "draws add nothing",
                N.MUTED,
            ),
            N.Line(
                f"lowest ESS {worst:.0f} from "
                f"{draws[-1] * self._chains.shape[0]} draws ({ratio:.1%} efficiency)"
                + (
                    ""
                    if worst >= dg.ESS_THRESHOLD
                    else f" — below the usual {dg.ESS_THRESHOLD:.0f} needed to quote a "
                    f"credible interval"
                )
            ),
        ]


def project_path_for_ndx() -> str:
    """A ``.cs.pto`` holding the live project, for ndX to open.

    The window's saved document when it is unmodified; else the live project
    saved to a scratch folder.

    Returns
    -------
    str
        Path of the project file.
    """
    import tempfile
    from pathlib import Path

    import chisurf as cs
    from chisurf.core.project import storage
    from chisurf.macros.core_fit import get_project_payload

    window = getattr(cs, "cs", None)
    document = window._get_project_document() if window is not None else None
    name = str(getattr(document, "name", "") or "chisurf_project")
    project = get_project_payload(name)
    if document is not None and document.path is not None and not document.is_modified(project):
        return str(document.path)
    stem = Path(name).name
    stem = stem[:-7] if stem.lower().endswith(".cs.pto") else stem
    target = Path(tempfile.mkdtemp(prefix="chisurf-ndx-")) / f"{stem or 'chisurf_project'}.cs.pto"
    return str(storage.save_file(project, target))
