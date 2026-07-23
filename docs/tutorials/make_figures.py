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


# --------------------------------------------------------------------------
# 8. Burst Variance Analysis (BVA)
# --------------------------------------------------------------------------
def fig_bva():
    import tttrlib
    rng = np.random.default_rng(8)
    n_slice = 5

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
        return d, np.asarray(rows, np.int64)

    static = [(rng.random(300) < 0.5).astype(int) for _ in range(80)]
    dynamic = []
    for _ in range(80):
        dynamic.append(np.concatenate(
            [(rng.random(60) < (0.15 if i % 2 else 0.85)).astype(int) for i in range(5)]))

    fig, ax = plt.subplots(figsize=(5.2, 4.0))
    for bursts, color, label in [(static, "#1f77b4", "static"), (dynamic, "#d62728", "dynamic")]:
        d, bounds = build(bursts)
        bva = tttrlib.BVA(d)
        bva.set_donor([0]); bva.set_acceptor([1])
        bva.compute(bounds, n_slice, 0.01)
        ax.scatter(bva.proximity_ratio_mean, bva.proximity_ratio_std,
                   s=12, alpha=0.5, color=color, label=label)
    grid = np.linspace(0.01, 0.99, 200)
    _, sd = tttrlib.BVA.compute_static_bva_line(grid, n_slice)
    ax.plot(grid, sd, "k-", lw=2, label="shot-noise limit")
    ax.set_xlabel("proximity ratio (mean)"); ax.set_ylabel("proximity ratio (std)")
    ax.set_title("Burst Variance Analysis"); ax.set_xlim(0, 1); ax.set_ylim(0, 0.6)
    ax.legend()
    save(fig, "bva.png")


# --------------------------------------------------------------------------
# 9. Diffusion FCS
# --------------------------------------------------------------------------
def fig_fcs_diffusion():
    tau = np.logspace(-6, 0, 300)          # seconds

    def g_3d_gauss(tau, N, td, s, trip_a=0.0, trip_t=1e-6):
        g = (1.0 / N) / (1 + tau / td) / np.sqrt(1 + (tau / td) / s ** 2)
        return g * (1 - trip_a + trip_a * np.exp(-tau / trip_t))

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    for td, c in [(3e-5, "#2ca02c"), (1e-4, "#1f77b4"), (5e-4, "#d62728")]:
        ax.semilogx(tau * 1e3, g_3d_gauss(tau, N=2.0, td=td, s=5.0),
                    color=c, label=f"τ_D = {td*1e3:.2g} ms")
    ax.semilogx(tau * 1e3, g_3d_gauss(tau, 2.0, 1e-4, 5.0, trip_a=0.2, trip_t=3e-6),
                "k--", lw=1, label="+ triplet")
    ax.set_xlabel("lag τ (ms)"); ax.set_ylabel("G(τ)")
    ax.set_title("3-D Gaussian diffusion FCS")
    ax.legend(fontsize=8)
    save(fig, "fcs_diffusion.png")


# --------------------------------------------------------------------------
# 10. Fluorescence lifetime and anisotropy decays
# --------------------------------------------------------------------------
def fig_lifetime_anisotropy():
    from chisurf.core.fluorescence.tcspc.convolve import convolve_lifetime_spectrum
    n = 4096
    dt = 0.016                              # ns/channel
    t = np.arange(n) * dt
    # Gaussian IRF
    irf = np.exp(-0.5 * ((t - 0.6) / 0.05) ** 2); irf /= irf.sum()

    def decay(spectrum):
        out = np.zeros(n)
        convolve_lifetime_spectrum(out, np.asarray(spectrum, float), irf, -1, t)
        return out

    d_mono = decay([1.0, 3.5])                      # tau = 3.5 ns
    d_bi = decay([0.6, 3.5, 0.4, 0.7])              # 3.5 ns + 0.7 ns (FRET)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.8))
    a1.semilogy(t, d_mono / d_mono.max(), color="#1f77b4", label="no FRET (τ=3.5 ns)")
    a1.semilogy(t, d_bi / d_bi.max(), color="#d62728", label="with FRET (3.5 & 0.7 ns)")
    a1.semilogy(t, irf / irf.max(), color="0.5", lw=1, label="IRF")
    a1.set_xlabel("time (ns)"); a1.set_ylabel("counts (norm.)")
    a1.set_ylim(1e-3, 1.5); a1.set_xlim(0, 20)
    a1.set_title("Fluorescence-lifetime decays"); a1.legend(fontsize=8)

    # Anisotropy decay r(t) = r0 exp(-t/rho)
    for rho, c in [(0.5, "#2ca02c"), (2.0, "#1f77b4"), (8.0, "#d62728")]:
        a2.plot(t, 0.4 * np.exp(-t / rho), color=c, label=f"ρ = {rho:g} ns")
    a2.set_xlabel("time (ns)"); a2.set_ylabel("anisotropy r(t)")
    a2.set_xlim(0, 20); a2.set_title("Anisotropy decays"); a2.legend(fontsize=8)
    save(fig, "lifetime_anisotropy.png")


# --------------------------------------------------------------------------
# 11. Photon Distribution Analysis (PDA)
# --------------------------------------------------------------------------
def fig_pda():
    import tttrlib
    pda = tttrlib.Pda(hist2d_nmax=60, hist2d_nmin=5)
    pda.background_ch1 = 0.0
    pda.background_ch2 = 0.0
    # Poisson-distributed burst sizes.
    pf = np.zeros(61); mu = 25.0
    from scipy.stats import poisson
    pf[:] = poisson.pmf(np.arange(61), mu)
    pda.setPF(pf)

    def e_hist(pch0, label):
        # single species with a given channel-1 probability p(ch0)
        pda.set_probability_spectrum_ch1([1.0, pch0])
        s1s2 = np.asarray(pda.get_S1S2_matrix()).reshape(61, 61)
        # collapse to proximity ratio histogram
        e_bins = np.linspace(0, 1, 41)
        e_hist = np.zeros(len(e_bins) - 1)
        for s1 in range(61):
            for s2 in range(61):
                tot = s1 + s2
                if tot < 5:
                    continue
                e = s2 / tot
                idx = min(int(e * (len(e_bins) - 1)), len(e_bins) - 2)
                e_hist[idx] += s1s2[s1, s2]
        c = 0.5 * (e_bins[:-1] + e_bins[1:])
        return c, e_hist / e_hist.sum(), label

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    try:
        for pch0, c in [(0.7, "#1f77b4"), (0.4, "#d62728")]:
            centers, h, _ = e_hist(pch0, f"p(ch0)={pch0}")
            ax.plot(centers, h, color=c, label=f"E ≈ {1-pch0:.1f}")
        ax.set_title("PDA: shot-noise-limited E histograms")
    except Exception as exc:   # pragma: no cover
        ax.text(0.5, 0.5, f"PDA demo unavailable:\n{exc}", ha="center", transform=ax.transAxes)
    ax.set_xlabel("proximity ratio E"); ax.set_ylabel("frequency")
    ax.legend(fontsize=8)
    save(fig, "pda.png")


if __name__ == "__main__":
    fig_2cde()
    fig_rasp()
    fig_polymer()
    fig_fida()
    fig_mdf()
    fig_g3()
    fig_rcm()
    fig_bva()
    fig_fcs_diffusion()
    fig_lifetime_anisotropy()
    fig_pda()
    print("all figures written to", FIG)
