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
from qtpy import QtWidgets

import chisurf.core.fitting
from chisurf.core.fitting import diagnostics as dg
from chisurf.gui.chiplot import Plot as ChiPlot
from chisurf.gui.chiplot import style as S
from chisurf.gui.plots.plotbase import Plot

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
        """Build the tabs and the parameter selector."""
        super().__init__(fit)
        self.fit = fit

        self.tabs = QtWidgets.QTabWidget()
        self.layout.addWidget(self.tabs)

        # -- rank tab, one parameter at a time -------------------------------
        rank_page = QtWidgets.QWidget()
        rank_layout = QtWidgets.QVBoxLayout(rank_page)
        rank_layout.setContentsMargins(4, 4, 4, 4)
        chooser = QtWidgets.QHBoxLayout()
        chooser.addWidget(QtWidgets.QLabel("Parameter"))
        self.parameter_box = QtWidgets.QComboBox()
        self.parameter_box.currentIndexChanged.connect(self._draw_rank)
        chooser.addWidget(self.parameter_box, 1)
        rank_layout.addLayout(chooser)
        self.rank_plot = ChiPlot()
        self.rank_plot.set_labels(bottom="rank (pooled over chains)", left="draws")
        rank_layout.addWidget(self.rank_plot.canvas.widget(), 1)
        self.rank_notes = QtWidgets.QLabel("")
        self.rank_notes.setWordWrap(True)
        self.rank_notes.setTextFormat(1)
        rank_layout.addWidget(self.rank_notes, 0)
        self.tabs.addTab(rank_page, "Rank")

        # -- ESS tab ---------------------------------------------------------
        ess_page = QtWidgets.QWidget()
        ess_layout = QtWidgets.QVBoxLayout(ess_page)
        ess_layout.setContentsMargins(4, 4, 4, 4)
        self.ess_plot = ChiPlot()
        self.ess_plot.set_labels(bottom="draws per chain", left="effective sample size")
        ess_layout.addWidget(self.ess_plot.canvas.widget(), 1)
        self.ess_notes = QtWidgets.QLabel("")
        self.ess_notes.setWordWrap(True)
        self.ess_notes.setTextFormat(1)
        ess_layout.addWidget(self.ess_notes, 0)
        self.tabs.addTab(ess_page, "ESS growth")

        self._chains = None
        self._names = []

    # -- data ---------------------------------------------------------------

    def _load(self) -> bool:
        """Pull the stored chain off the fit. Return whether there is one."""
        chain = getattr(self.fit, "sampling_chain", None)
        if not isinstance(chain, dict) or chain.get("chains") is None:
            self._chains, self._names = None, []
            return False
        chains = np.asarray(chain["chains"], dtype=float)
        if chains.ndim != 3 or chains.shape[1] < 8:
            self._chains, self._names = None, []
            return False
        self._chains = chains
        self._names = [str(n).split(":")[-1] for n in chain.get("parameter_names", [])]
        while len(self._names) < chains.shape[2]:
            self._names.append(f"p{len(self._names)}")
        return True

    def update(self, *args, **kwargs) -> None:
        """Reload the chain and redraw both tabs."""
        super().update(*args, **kwargs)
        if not self._load():
            for plot, notes in ((self.rank_plot, self.rank_notes), (self.ess_plot, self.ess_notes)):
                plot.clear()
                notes.setText(
                    "<i>no chain stored for this fit — run a sampling job "
                    "(<b>Chain diagnostics</b> describes what it produced, it "
                    "does not sample)</i>"
                )
            self.parameter_box.clear()
            return

        current = self.parameter_box.currentText()
        self.parameter_box.blockSignals(True)
        self.parameter_box.clear()
        self.parameter_box.addItems(self._names)
        if current in self._names:
            self.parameter_box.setCurrentIndex(self._names.index(current))
        self.parameter_box.blockSignals(False)

        self._draw_rank()
        self._draw_ess()

    # -- drawing ------------------------------------------------------------

    def _draw_rank(self, *args) -> None:
        """Draw per-chain rank histograms for the selected parameter."""
        if self._chains is None:
            return
        index = max(0, self.parameter_box.currentIndex())
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
        self.rank_notes.setText(
            "<span style='color:#888'>each chain's share of the pooled ranks; "
            "flat = converged</span><br>"
            f"worst bin {z_max:.1f}&sigma; from flat, against {z_null:.1f}&sigma; "
            f"expected by chance at &tau;={tau:.0f} — {verdict}"
        )

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
            self.ess_notes.setText("<i>too few draws to estimate</i>")
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
        self.ess_notes.setText(
            "<span style='color:#888'>a converged sampler's ESS grows linearly; "
            "flattening means the extra draws add nothing</span><br>"
            f"lowest ESS {worst:.0f} from "
            f"{draws[-1] * self._chains.shape[0]} draws ({ratio:.1%} efficiency)"
            + (
                ""
                if worst >= dg.ESS_THRESHOLD
                else f" — below the usual {dg.ESS_THRESHOLD:.0f} needed to quote a "
                f"credible interval"
            )
        )
