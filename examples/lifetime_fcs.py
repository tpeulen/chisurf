"""Lifetime-FCS (FLCS) worked example: simulate, filter, correlate.

Fluorescence-lifetime correlation spectroscopy separates species that overlap in
space and colour but differ in fluorescence lifetime. Each photon is weighted by a
statistical filter built from the species' TCSPC decays, and the weighted stream is
correlated — yielding one correlation curve per species from a single measurement.

This script uses chisurf's Qt-free FCS core end to end:

* :func:`chisurf.core.fluorescence.fcs.simulate.simulate_lifetime_fcs` simulates
  diffusing species (via ``tttrlib.SimEngine``) with distinct lifetimes and optional
  interconversion,
* :func:`chisurf.core.fluorescence.fcs.filtered.calc_ffcs_filters` builds the
  lifetime filters, and
* :func:`chisurf.core.fluorescence.fcs.filtered.species_filtered_correlation`
  computes the species auto-/cross-correlations.

Two scenarios are shown:

1. **Static mixture** — a fast/short-lifetime species and a slow/long-lifetime
   species. Lifetime filtering pulls the two diffusion times apart.
2. **Interconverting states** — two states with the *same* diffusion but exchanging
   while they cross the focus. The species cross-correlation grows an exchange peak.

Run with a display to see the plots (``python examples/lifetime_fcs.py``); without a
display it prints the recovered amplitudes.
"""

import numpy as np

from chisurf.core.fluorescence.fcs.filtered import (
    calc_ffcs_filters,
    filter_condition_number,
    species_filtered_correlation,
)
from chisurf.core.fluorescence.fcs.simulate import simulate_lifetime_fcs


def run_static(n_photons=1_000_000):
    """Fast/short-lifetime + slow/long-lifetime species diffusing independently."""
    sim = simulate_lifetime_fcs(
        lifetimes_ns=(1.0, 4.0), diffusion_um2_ms=(8.0, 0.5),
        n_photons=n_photons, seed=1,
    )
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    res = species_filtered_correlation(
        sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
        n_bins=8, n_casc=25, labels=["fast (tau=1 ns)", "slow (tau=4 ns)"],
    )
    return sim, filters, res


def run_kinetics(n_photons=1_000_000):
    """Two lifetime states with equal diffusion, interconverting at 5 ms^-1."""
    sim = simulate_lifetime_fcs(
        lifetimes_ns=(1.0, 4.0), diffusion_um2_ms=(0.15, 0.15),
        exchange_rate_ms=5.0, n_photons=n_photons, seed=2,
    )
    filters, _, _ = calc_ffcs_filters(sim.total_decay, sim.reference_decays)
    res = species_filtered_correlation(
        sim.macro_times, sim.micro_times, filters, sim.macro_time_resolution_s,
        n_bins=8, n_casc=25, labels=["state 0", "state 1"],
    )
    return sim, filters, res


def _report(title, res):
    lag = res.lag_s

    def at(g, t):
        return g[np.argmin(np.abs(lag - t))]

    print(f"\n{title}")
    for i, g in res.auto.items():
        print(f"  auto  {res.labels[i]:18s} G(10us)={at(g, 1e-5):6.2f}  G(500us)={at(g, 5e-4):6.2f}")
    for (i, j), g in res.cross.items():
        band = (lag > 1e-5) & (lag < 1e-3)
        print(f"  cross {res.labels[i]} x {res.labels[j]}: mid-lag max={np.nanmax(g[band]):.2f}")


def plot(static, kinetics):
    """Plot reference decays, filters, and the two correlation scenarios."""
    import matplotlib.pyplot as plt

    sim_s, filt_s, res_s = static
    sim_k, _, res_k = kinetics
    t_ns = np.arange(sim_s.n_microtime_channels) * sim_s.micro_time_resolution_ns

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    ax = axes[0, 0]
    for d, c, lab in zip(sim_s.reference_decays, ("tab:blue", "tab:red"),
                         ("species 0 (1 ns)", "species 1 (4 ns)")):
        ax.semilogy(t_ns, d / d.max(), color=c, label=lab)
    ax.set(xlabel="micro-time (ns)", ylabel="norm. counts", xlim=(0, 20),
           ylim=(1e-3, 2), title="Reference decays")
    ax.legend(frameon=False)

    ax = axes[0, 1]
    for row, c in zip(filt_s, ("tab:blue", "tab:red")):
        ax.plot(t_ns, row, color=c)
    ax.axhline(0, color="0.7", lw=0.8)
    ax.set(xlabel="micro-time (ns)", ylabel="filter weight", xlim=(0, 20),
           title="Lifetime filters")

    ax = axes[1, 0]
    ax.semilogx(res_s.lag_s, res_s.auto[0], color="tab:blue", label="fast (filtered)")
    ax.semilogx(res_s.lag_s, res_s.auto[1], color="tab:red", label="slow (filtered)")
    ax.semilogx(res_s.lag_s, res_s.cross[(0, 1)], color="tab:green", label="cross")
    ax.set(xlabel="lag (s)", ylabel="G(tau)", xlim=(1e-6, 1e-2),
           title="Static mixture: diffusion times separate")
    ax.legend(frameon=False)

    ax = axes[1, 1]
    ax.semilogx(res_k.lag_s, res_k.auto[0], color="tab:blue", label="state 0 (auto)")
    ax.semilogx(res_k.lag_s, res_k.auto[1], color="tab:red", label="state 1 (auto)")
    ax.semilogx(res_k.lag_s, res_k.cross[(0, 1)], color="tab:green", lw=2, label="cross")
    ax.axhline(1.0, color="0.7", lw=0.8)
    ax.set(xlabel="lag (s)", ylabel="G(tau)", xlim=(1e-6, 1e-2),
           title="Interconversion: cross-correlation peak")
    ax.legend(frameon=False)

    fig.tight_layout()
    return fig


if __name__ == "__main__":
    static = run_static()
    kinetics = run_kinetics()
    print("Lifetime-FCS simulation summary")
    print("  filter condition number (static): "
          f"{filter_condition_number(static[0].total_decay, static[0].reference_decays):.2f}")
    _report("Static mixture", static[2])
    _report("Interconverting states", kinetics[2])
    try:
        import matplotlib.pyplot as plt

        plot(static, kinetics)
        plt.show()
    except Exception as exc:  # pragma: no cover - display/backends optional
        print(f"\n(Plotting skipped: {exc})")
