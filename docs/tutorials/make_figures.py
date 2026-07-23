#!/usr/bin/env python
"""Generate the figures for the ChiSurf single-molecule tutorials (headless).

Runs the actual ChiSurf analysis functions on synthetic data and saves one PNG
per tutorial into ``docs/tutorials/figures/``.  Uses the Agg backend so it works
without a display::

    python docs/tutorials/make_figures.py
"""

from __future__ import annotations

import pathlib

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

FIG = pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)
plt.rcParams.update({"figure.dpi": 110, "font.size": 10, "axes.grid": True,
                     "grid.alpha": 0.3})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# --------------------------------------------------------------------------
# 1. FRET-2CDE burst dynamics
# --------------------------------------------------------------------------
def fig_2cde():
    import tttrlib
    rng = np.random.default_rng(1)

    def build(chan_per_burst, gap=1_000_000):
        macro, chan, rows = [], [], []
        t = 0
        for ch in chan_per_burst:
            start = len(macro)
            for c in ch:
                t += 1; macro.append(t); chan.append(int(c))
            t += gap
            rows.append((start, len(macro) - 1))
        d = tttrlib.TTTR()
        d.append_events(np.asarray(macro, np.uint64), np.zeros(len(macro), np.uint16),
                        np.asarray(chan, np.int8), np.zeros(len(macro), np.int8), False, 0)
        d.header.set_macro_time_resolution(1.0)
        return d, np.asarray(rows, np.int64), np.asarray(chan)

    static = [(rng.random(400) < p).astype(int) for p in rng.uniform(0.2, 0.8, 60)]
    dyn = []
    for _ in range(60):
        blocks = [(rng.random(80) < (0.2 if i % 2 else 0.8)).astype(int) for i in range(5)]
        dyn.append(np.concatenate(blocks))

    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    for bursts, color, label in [(static, "#1f77b4", "static"), (dyn, "#d62728", "dynamic")]:
        d, bounds, chan = build(bursts)
        eng = tttrlib.TwoCDE(d)
        eng.set_donor([0]); eng.set_acceptor([1])
        eng.compute(bounds, 40.0, tttrlib.TwoCDE.FRET_2CDE, tttrlib.TwoCDE.LAPLACE)
        cde = eng.two_cde
        E = np.array([b.mean() for b in bursts])  # acceptor fraction ~ proximity ratio
        ax.scatter(E, cde, s=10, alpha=0.5, color=color, label=label)
    ax.axhline(10, ls="--", color="k", lw=1, alpha=0.6)
    ax.set_xlabel("proximity ratio E"); ax.set_ylabel("FRET-2CDE")
    ax.set_title("FRET-2CDE separates static from dynamic bursts")
    ax.set_xlim(0, 1); ax.legend()
    save(fig, "2cde.png")


# --------------------------------------------------------------------------
# 2. Recurrence analysis (RASP)
# --------------------------------------------------------------------------
def fig_rasp():
    from chisurf.core.fluorescence.burst import recurrence as rec
    rng = np.random.default_rng(2)

    # Molecules that recur within ~30 ms, each inter-converting low<->high E.
    times, eff = [], []
    t = 0.0
    for _ in range(600):
        t += rng.exponential(0.4)
        times.append(t); eff.append(rng.normal(0.25, 0.04))
        t += rng.uniform(0.003, 0.03)
        times.append(t); eff.append(rng.normal(0.75, 0.04))
    times = np.asarray(times); eff = np.asarray(eff)

    tau, psame, _ = rec.same_molecule_probability(times, 1e-3, 1.0, n_bins=40)
    centers, rec_h, all_h = rec.recurrence_histogram(
        times, eff, e_range=(0.0, 0.4), dt_range_s=(1e-3, 0.05), bins=40)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.0, 3.8))
    a1.semilogx(tau * 1e3, psame, "o-", ms=3, color="#1f77b4")
    a1.set_xlabel("lag τ (ms)"); a1.set_ylabel(r"$P_{\rm same}(\tau)$")
    a1.set_title("Same-molecule probability")
    a2.bar(centers, all_h, width=centers[1]-centers[0], color="0.8", label="all bursts")
    a2.bar(centers, rec_h, width=centers[1]-centers[0], color="#1f77b4", alpha=0.7,
           label="recurrence of E∈[0,0.4]")
    a2.axvspan(0, 0.4, color="crimson", alpha=0.08)
    a2.set_xlabel("FRET efficiency E"); a2.set_ylabel("p.d.f.")
    a2.set_title("Initial low-E recurs as high-E"); a2.legend(fontsize=8)
    save(fig, "rasp.png")


# --------------------------------------------------------------------------
# 3. Polymer distance distributions (SAW-nu, Ising, Gaussian, WLC)
# --------------------------------------------------------------------------
def fig_polymer():
    from chisurf.core.math.functions import rdf
    r = np.linspace(1e-3, 160.0, 4000)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.0, 3.8))
    for nu, c in [(0.40, "#2ca02c"), (0.50, "#1f77b4"), (0.588, "#ff7f0e"), (0.70, "#d62728")]:
        a1.plot(r, rdf.saw_nu(r, 55.0, nu=nu), color=c, label=f"ν = {nu}")
    a1.set_xlabel("inter-dye distance R (Å)"); a1.set_ylabel("P(R)")
    a1.set_title("SAW-ν (same RMS, varying ν)"); a1.legend(fontsize=8)

    for h, c, lbl in [(-3.0, "#d62728", "unfolded (h<0)"), (0.0, "#1f77b4", "midpoint"),
                      (3.0, "#2ca02c", "folded (h>0)")]:
        p = rdf.ising_chain(r, 40, 4.0, 9.0, coupling=1.5, field=h)
        a2.plot(r, p, color=c, label=lbl)
    a2.set_xlabel("inter-dye distance R (Å)"); a2.set_ylabel("P(R)")
    a2.set_title("Ising two-state chain (varying field h)"); a2.legend(fontsize=8)
    save(fig, "polymer.png")


# --------------------------------------------------------------------------
# 4. FIDA photon-counting histogram
# --------------------------------------------------------------------------
def fig_fida():
    from chisurf.core.models.pch import fida
    k = np.arange(0, 41)
    p1 = fida.fida_pch(40, [(3.0, 2.0)])
    p2 = fida.fida_pch(40, [(1.0, 4.0), (6.0, 0.3)])
    from scipy.stats import poisson
    pois = poisson.pmf(k, (np.arange(p1.size) * p1).sum())

    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    ax.semilogy(k, pois, "k--", lw=1, label="Poisson (same mean)")
    ax.semilogy(k, p1, "o-", ms=3, color="#1f77b4", label="1 species (q=3, N=2)")
    ax.semilogy(k, p2, "s-", ms=3, color="#d62728", label="2 species")
    ax.set_xlabel("photons per bin, k"); ax.set_ylabel("P(k)")
    ax.set_ylim(1e-5, 1); ax.set_title("FIDA: brightness broadens the PCH")
    ax.legend(fontsize=8)
    save(fig, "fida.png")


# --------------------------------------------------------------------------
# 5. Enderlein MDF and two-focus FCS
# --------------------------------------------------------------------------
def fig_mdf():
    from chisurf.core.fluorescence.fcs import enderlein as en
    tau = np.logspace(-6, -1, 120)
    auto = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.0)
    cross = en.g_diff(tau, 0.25, 0.25, diffusion=300.0, separation=0.5)

    # MDF profile U(rho, z)
    rho = np.linspace(-0.8, 0.8, 120)
    z = np.linspace(-2.5, 2.5, 120)
    RHO, Z = np.meshgrid(rho, z)
    U = en.mdf(np.abs(RHO), Z, 0.25, 0.25)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.8))
    im = a1.pcolormesh(rho, z, U, shading="auto", cmap="viridis")
    a1.set_xlabel("ρ (µm)"); a1.set_ylabel("z (µm)")
    a1.set_title("Gauss–Lorentz MDF  U(ρ,z)"); fig.colorbar(im, ax=a1, shrink=0.85)
    a2.semilogx(tau * 1e3, auto, color="#1f77b4", label="auto (single focus)")
    a2.semilogx(tau * 1e3, cross, color="#d62728", label="cross (d=0.5 µm)")
    a2.set_xlabel("lag τ (ms)"); a2.set_ylabel("G(τ) (norm.)")
    a2.set_title("Two-focus FCS → absolute D"); a2.legend(fontsize=8)
    save(fig, "mdf.png")


# --------------------------------------------------------------------------
# 6. ns-FCS second-order correlation g^(3)
# --------------------------------------------------------------------------
def fig_g3():
    from chisurf.core.fluorescence.fcs.correlate import second_order_correlation
    rng = np.random.default_rng(6)
    n = 200_000
    trace = rng.poisson(1.0, n).astype(float)
    for t in rng.integers(0, n - 5, size=4000):        # correlated bursts
        trace[t:t + 5] += 12.0
    tau = np.arange(1, 25)
    g3 = second_order_correlation(trace, tau, tau)

    fig, ax = plt.subplots(figsize=(5.4, 4.2))
    im = ax.imshow(g3, origin="lower", aspect="auto", cmap="magma",
                   extent=[tau[0], tau[-1], tau[0], tau[-1]])
    ax.set_xlabel("τ₂ (bins)"); ax.set_ylabel("τ₁ (bins)")
    ax.set_title("Second-order correlation g⁽³⁾(τ₁,τ₂)")
    fig.colorbar(im, ax=ax, shrink=0.85, label="g⁽³⁾")
    save(fig, "g3.png")


# --------------------------------------------------------------------------
# 7. RCM detection-correction matrix
# --------------------------------------------------------------------------
def fig_rcm():
    from chisurf.core.fluorescence.fret.calibration import rcm_from_dye_solutions
    assignment = [("A", "P"), ("D", "P"), ("A", "S"), ("D", "S")]
    donor = [0.06, 1.0, 0.05, 0.95]      # donor solution: mostly D channels + leak
    acceptor = [1.0, 0.04, 0.9, 0.03]    # acceptor solution: mostly A channels + leak
    rcm = rcm_from_dye_solutions(donor, acceptor, 1.15, assignment, anisotropy=(0.2, 0.15))

    fig, ax = plt.subplots(figsize=(4.6, 4.0))
    im = ax.imshow(rcm, cmap="coolwarm", vmin=-abs(rcm).max(), vmax=abs(rcm).max())
    labels = [f"{s}·{p}" for s, p in assignment]
    ax.set_xticks(range(4)); ax.set_yticks(range(4))
    ax.set_xticklabels(labels); ax.set_yticklabels(labels)
    for i in range(4):
        for j in range(4):
            ax.text(j, i, f"{rcm[i, j]:.2f}", ha="center", va="center", fontsize=8)
    ax.set_title("Routing-correction matrix (from dye solutions)")
    fig.colorbar(im, ax=ax, shrink=0.85)
    save(fig, "rcm.png")


if __name__ == "__main__":
    fig_2cde()
    fig_rasp()
    fig_polymer()
    fig_fida()
    fig_mdf()
    fig_g3()
    fig_rcm()
    print("all figures written to", FIG)
