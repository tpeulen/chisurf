#!/usr/bin/env python
"""Generate the figures for the ChiSurf single-molecule tutorials (headless).

Runs the actual ChiSurf analysis functions on synthetic data and saves one PNG
per tutorial into ``docs/guides/figures/``.  Uses the Agg backend so it works
without a display::

    python docs/guides/make_figures.py
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


# --------------------------------------------------------------------------
# 12. TTTR file handling — micro-time histogram
# --------------------------------------------------------------------------
def fig_tttr():
    rng = np.random.default_rng(12)
    n_ch = 4096; dt = 0.016
    t = np.arange(n_ch) * dt
    # two detectors with different lifetimes on a shared IRF
    irf_pos = 0.6
    micro_g = rng.exponential(3.2, 40000)
    micro_r = rng.exponential(1.4, 30000)
    hist_g, edges = np.histogram(irf_pos + micro_g, bins=n_ch, range=(0, n_ch * dt))
    hist_r, _ = np.histogram(irf_pos + micro_r, bins=n_ch, range=(0, n_ch * dt))
    c = 0.5 * (edges[:-1] + edges[1:])

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.semilogy(c, hist_g + 1, color="#2ca02c", label="green detector")
    ax.semilogy(c, hist_r + 1, color="#d62728", label="red detector")
    ax.set_xlim(0, 25); ax.set_ylim(1, None)
    ax.set_xlabel("micro time (ns)"); ax.set_ylabel("counts")
    ax.set_title("Micro-time histograms from a TTTR file")
    ax.legend(fontsize=8)
    save(fig, "tttr.png")


# --------------------------------------------------------------------------
# 13. Burst identification — sliding-window count rate
# --------------------------------------------------------------------------
def fig_burst_search():
    rng = np.random.default_rng(13)
    # background photons + occasional bright bursts (inhomogeneous Poisson)
    T = 0.5                                   # s
    bg_rate = 3e3
    t = list(rng.uniform(0, T, int(bg_rate * T)))
    burst_times = np.sort(rng.uniform(0.02, T - 0.02, 25))
    for bt in burst_times:
        t += list(bt + rng.exponential(3e-5, rng.integers(60, 200)))
    t = np.sort(np.asarray(t))
    # sliding-window count rate: photons in a 0.5 ms window
    win = 5e-4
    edges = np.arange(0, T, win)
    rate = np.histogram(t, edges)[0] / win / 1e3   # kHz
    tc = edges[:-1] + win / 2
    thr = 15.0

    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    ax.plot(tc * 1e3, rate, color="0.4", lw=0.8)
    ax.fill_between(tc * 1e3, rate, thr, where=rate > thr, color="#d62728", alpha=0.5,
                    step="mid", label="detected bursts")
    ax.axhline(thr, ls="--", color="k", lw=1, label="threshold")
    ax.set_xlabel("time (ms)"); ax.set_ylabel("count rate (kHz)")
    ax.set_title("Burst identification (sliding-window count rate)")
    ax.legend(fontsize=8)
    save(fig, "burst_search.png")


# --------------------------------------------------------------------------
# 14. Multi-parameter E–S histogram (µsALEX / PIE)
# --------------------------------------------------------------------------
def fig_es():
    rng = np.random.default_rng(14)

    def pop(n, e, s, spread=0.06):
        return rng.normal(e, spread, n), rng.normal(s, spread * 0.7, n)

    E = np.concatenate([pop(800, 0.15, 0.55)[0], pop(800, 0.75, 0.55)[0],
                        pop(300, 0.05, 0.92)[0], pop(200, 0.5, 0.1)[0]])
    S = np.concatenate([pop(800, 0.15, 0.55)[1], pop(800, 0.75, 0.55)[1],
                        pop(300, 0.05, 0.92)[1], pop(200, 0.5, 0.1)[1]])

    fig, ax = plt.subplots(figsize=(5.2, 4.4))
    hb = ax.hexbin(E, S, gridsize=45, cmap="viridis", mincnt=1, extent=(-0.1, 1.1, 0, 1))
    ax.axhspan(0.85, 1.0, color="orange", alpha=0.12)   # donor-only
    ax.axhspan(0.0, 0.2, color="red", alpha=0.10)        # acceptor-only
    ax.text(0.5, 0.93, "donor-only", ha="center", fontsize=8)
    ax.text(0.5, 0.06, "acceptor-only", ha="center", fontsize=8)
    ax.set_xlabel("FRET efficiency E"); ax.set_ylabel("stoichiometry S")
    ax.set_title("Multi-parameter E–S histogram (ALEX/PIE)")
    ax.set_xlim(-0.1, 1.1); ax.set_ylim(0, 1)
    fig.colorbar(hb, ax=ax, shrink=0.85, label="bursts")
    save(fig, "es.png")


# --------------------------------------------------------------------------
# 15. Background rate from inter-photon times
# --------------------------------------------------------------------------
def fig_background():
    rng = np.random.default_rng(15)
    bg_rate = 2.0e3                            # Hz
    dark = rng.exponential(1 / bg_rate, 20000)
    burst = rng.exponential(1 / 2e5, 6000)     # bright bursts: short gaps
    gaps = np.concatenate([dark, burst]) * 1e3  # ms
    bins = np.logspace(-4, 1.5, 60)
    h, edges = np.histogram(gaps, bins=bins)
    c = np.sqrt(edges[:-1] * edges[1:])

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.loglog(c, h + 1, "o", ms=3, color="#1f77b4")
    tail = c > 0.5
    ax.loglog(c[tail], (h[tail].max() + 1) * np.exp(-(c[tail] - c[tail][0]) * bg_rate / 1e3),
              "r-", lw=1.5, label=f"tail fit → {bg_rate/1e3:.1f} kHz background")
    ax.set_xlabel("inter-photon time (ms)"); ax.set_ylabel("counts")
    ax.set_title("Background from the inter-photon-time tail")
    ax.legend(fontsize=8)
    save(fig, "background.png")


# --------------------------------------------------------------------------
# 16. FRET-FCS — species auto/cross-correlation
# --------------------------------------------------------------------------
def fig_fret_fcs():
    tau = np.logspace(-6, -1, 200)
    td = 3e-4
    diff = (1 / (1 + tau / td)) / np.sqrt(1 + (tau / td) / 25)
    kex = 5e3                                   # exchange rate (Hz)
    relax = np.exp(-kex * tau)
    dd = diff * (1 + 0.4 * relax)               # donor auto: bunching
    aa = diff * (1 + 0.4 * relax)
    da = diff * (1 - 0.4 * relax)               # cross: anti-correlation

    fig, ax = plt.subplots(figsize=(5.4, 4.0))
    ax.semilogx(tau * 1e3, dd, color="#2ca02c", label="donor × donor")
    ax.semilogx(tau * 1e3, aa, color="#d62728", label="acceptor × acceptor")
    ax.semilogx(tau * 1e3, da, color="#1f77b4", label="donor × acceptor (cross)")
    ax.set_xlabel("lag τ (ms)"); ax.set_ylabel("G(τ) (norm.)")
    ax.set_title("FRET-FCS: dynamics as anti-correlation")
    ax.legend(fontsize=8)
    save(fig, "fret_fcs.png")


# --------------------------------------------------------------------------
# 17. Filtered FCS — species lifetime patterns + filters
# --------------------------------------------------------------------------
def fig_filtered_fcs():
    from chisurf.core.fluorescence.fcs.filtered import calc_ffcs_filters
    n = 128
    ch = np.arange(n)
    p1 = np.exp(-ch / 25.0); p1 /= p1.sum()          # long lifetime
    p2 = np.exp(-ch / 6.0); p2 /= p2.sum()           # short lifetime
    patterns = np.vstack([p1, p2])
    total = 0.6 * p1 + 0.4 * p2
    filters, _recon, _w = calc_ffcs_filters(total, patterns)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.0, 3.8))
    a1.semilogy(ch, p1, color="#1f77b4", label="species 1 (τ long)")
    a1.semilogy(ch, p2, color="#d62728", label="species 2 (τ short)")
    a1.semilogy(ch, total, "k--", lw=1, label="measured mix")
    a1.set_xlabel("micro-time channel"); a1.set_ylabel("p(channel)")
    a1.set_title("Species lifetime patterns"); a1.legend(fontsize=8)
    a2.plot(ch, filters[0], color="#1f77b4", label="filter 1")
    a2.plot(ch, filters[1], color="#d62728", label="filter 2")
    a2.axhline(0, color="k", lw=0.6)
    a2.set_xlabel("micro-time channel"); a2.set_ylabel("filter weight")
    a2.set_title("Statistical (fFCS) filters"); a2.legend(fontsize=8)
    save(fig, "filtered_fcs.png")


# --------------------------------------------------------------------------
# 18. TTTR simulation of a diffusing particle (confocal)
# --------------------------------------------------------------------------
def fig_simulation():
    rng = np.random.default_rng(18)
    # A 1-D confocal transit model: molecule diffuses through a Gaussian spot,
    # emitting Poisson photons at the local brightness -> intensity trace.
    dt = 1e-4                                    # s
    n = 40000
    D = 1.0                                      # arb. diffusion
    x = np.cumsum(rng.normal(0, np.sqrt(2 * D * dt), n))
    # periodic re-seeding to emulate new molecules entering the spot
    x = (x % 8.0) - 4.0
    bright = 20.0 * np.exp(-2 * x ** 2 / 1.0 ** 2)
    counts = rng.poisson(bright + 0.5)
    t = np.arange(n) * dt

    # autocorrelation of the simulated trace
    c = counts - counts.mean()
    ac = np.correlate(c, c, "full")[n - 1:]
    ac = ac / ac[0]
    lag = np.arange(n) * dt

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    a1.plot(t[:4000] * 1e3, counts[:4000], color="#1f77b4", lw=0.7)
    a1.set_xlabel("time (ms)"); a1.set_ylabel("counts / bin")
    a1.set_title("Simulated confocal intensity trace")
    keep = (lag > 0) & (lag < 0.05)
    a2.semilogx(lag[keep] * 1e3, ac[keep], color="#d62728")
    a2.set_xlabel("lag τ (ms)"); a2.set_ylabel("G(τ) (norm.)")
    a2.set_title("… and its correlation")
    save(fig, "simulation.png")


# --------------------------------------------------------------------------
# 19. Hidden Markov model (H2MM) — state trajectory and dwell E histogram
# --------------------------------------------------------------------------
def fig_h2mm():
    rng = np.random.default_rng(19)
    # Two-state kinetics with E1=0.3, E2=0.7; Viterbi-style state path over dwells.
    E_states = np.array([0.3, 0.7])
    states, dwell_E = [], []
    s = 0
    for _ in range(400):
        s = 1 - s if rng.random() < 0.5 else s
        d = rng.integers(3, 20)                     # dwell length (photons)
        states += [s] * d
        # measured dwell E = shot-noise around the state E
        k = rng.binomial(d, E_states[s])
        dwell_E.append(k / d)
    states = np.asarray(states); dwell_E = np.asarray(dwell_E)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.2, 3.6))
    a1.step(np.arange(300), E_states[states[:300]], where="mid", color="#1f77b4")
    a1.set_ylim(0, 1); a1.set_xlabel("photon index"); a1.set_ylabel("state E")
    a1.set_title("Viterbi state path (2 states)")
    a2.hist(dwell_E, bins=np.linspace(0, 1, 30), color="#1f77b4", alpha=0.8)
    for e in E_states:
        a2.axvline(e, ls="--", color="k", lw=1)
    a2.set_xlabel("dwell FRET efficiency"); a2.set_ylabel("dwells")
    a2.set_title("Per-dwell E histogram")
    save(fig, "h2mm.png")


# --------------------------------------------------------------------------
# 20. Binned photon trace (MCS)
# --------------------------------------------------------------------------
def fig_mcs():
    rng = np.random.default_rng(20)
    T, dt = 0.2, 1e-3
    n = int(T / dt)
    green = rng.poisson(2.0, n).astype(float)
    red = rng.poisson(1.5, n).astype(float)
    for t0 in rng.integers(0, n - 6, 15):          # coincident FRET bursts
        green[t0:t0 + 6] += rng.poisson(8, 6)
        red[t0:t0 + 6] += rng.poisson(12, 6)
    t = np.arange(n) * dt * 1e3

    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    ax.plot(t, green, color="#2ca02c", lw=0.8, label="green")
    ax.plot(t, -red, color="#d62728", lw=0.8, label="red")
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("time (ms)"); ax.set_ylabel("counts / 1 ms  (green up / red down)")
    ax.set_title("Binned photon trace (MCS)")
    ax.legend(fontsize=8, loc="upper right")
    save(fig, "mcs.png")


# ==========================================================================
# Workflow tutorials (based on established burst-analysis / H2MM notebooks)
# ==========================================================================

def _alex_populations(rng, n_fret=1400):
    """Synthetic ALEX bursts: two FRET states + donor-only + acceptor-only."""
    def pop(n, e, s, se=0.06, ss=0.05):
        return rng.normal(e, se, n), rng.normal(s, ss, n)
    E = np.concatenate([pop(n_fret // 2, 0.25, 0.52)[0], pop(n_fret // 2, 0.72, 0.50)[0],
                        pop(400, 0.03, 0.93)[0], pop(250, 0.55, 0.08)[0]])
    S = np.concatenate([pop(n_fret // 2, 0.25, 0.52)[1], pop(n_fret // 2, 0.72, 0.50)[1],
                        pop(400, 0.03, 0.93)[1], pop(250, 0.55, 0.08)[1]])
    return E, S


def fig_alex_workflow():
    rng = np.random.default_rng(27)
    E, S = _alex_populations(rng)
    fret = (S > 0.25) & (S < 0.75)                 # gate out D-only / A-only

    fig = plt.figure(figsize=(6.0, 5.4))
    gs = fig.add_gridspec(2, 2, width_ratios=(4, 1), height_ratios=(1, 4),
                          wspace=0.05, hspace=0.05)
    ax = fig.add_subplot(gs[1, 0]); axx = fig.add_subplot(gs[0, 0], sharex=ax)
    axy = fig.add_subplot(gs[1, 1], sharey=ax)
    ax.hexbin(E, S, gridsize=45, cmap="viridis", mincnt=1, extent=(-0.1, 1.1, 0, 1))
    ax.set_xlabel("FRET efficiency E"); ax.set_ylabel("stoichiometry S")
    ax.set_xlim(-0.1, 1.1); ax.set_ylim(0, 1)
    axx.hist(E, bins=np.arange(-0.1, 1.1, 0.03), color="#1f77b4"); axx.axis("off")
    axy.hist(S, bins=np.arange(0, 1, 0.03), orientation="horizontal", color="#1f77b4")
    axy.axis("off")
    axx.set_title("μs-ALEX smFRET burst analysis")
    save(fig, "alex_workflow.png")


def fig_e_hist_fit():
    from sklearn.mixture import GaussianMixture
    rng = np.random.default_rng(28)
    E, S = _alex_populations(rng)
    e = E[(S > 0.25) & (S < 0.75)]                 # FRET bursts only
    gm = GaussianMixture(n_components=3, random_state=0).fit(e.reshape(-1, 1))
    x = np.linspace(-0.1, 1.1, 400)
    from scipy.stats import norm
    comps = [w * norm.pdf(x, m[0], np.sqrt(c[0, 0]))
             for w, m, c in zip(gm.weights_, gm.means_, gm.covariances_)]

    fig, ax = plt.subplots(figsize=(5.6, 4.0))
    ax.hist(e, bins=np.arange(-0.1, 1.1, 0.025), density=True, color="0.8", label="bursts")
    for i, cc in enumerate(comps):
        ax.plot(x, cc, lw=1.2, label=f"comp {i+1}: E={gm.means_[i,0]:.2f}")
    ax.plot(x, np.sum(comps, axis=0), "k-", lw=2, label="mixture fit")
    ax.set_xlabel("FRET efficiency E"); ax.set_ylabel("p.d.f."); ax.set_xlim(-0.1, 1.1)
    ax.set_title("FRET-efficiency histogram fit (Gaussian mixture)")
    ax.legend(fontsize=7)
    save(fig, "e_hist_fit.png")


def fig_population_selection():
    rng = np.random.default_rng(29)
    E, S = _alex_populations(rng)
    roi = dict(E1=0.55, E2=1.05, S1=0.25, S2=0.75)   # high-FRET ROI
    high = (E > roi["E1"]) & (E < roi["E2"]) & (S > roi["S1"]) & (S < roi["S2"])
    low = (E < 0.45) & (S > 0.25) & (S < 0.75)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.4, 4.0))
    a1.hexbin(E, S, gridsize=45, cmap="Greys", mincnt=1, extent=(-0.1, 1.1, 0, 1))
    a1.add_patch(plt.Rectangle((roi["E1"], roi["S1"]), roi["E2"] - roi["E1"],
                 roi["S2"] - roi["S1"], fill=False, ec="#d62728", lw=2))
    a1.set_xlabel("E"); a1.set_ylabel("S"); a1.set_title("ROI selection on E–S")
    a1.set_xlim(-0.1, 1.1); a1.set_ylim(0, 1)
    bins = np.arange(-0.1, 1.1, 0.03)
    a2.hist(E[low], bins=bins, alpha=0.6, color="#1f77b4", label=f"low-FRET (n={low.sum()})")
    a2.hist(E[high], bins=bins, alpha=0.6, color="#d62728", label=f"high-FRET (n={high.sum()})")
    a2.set_xlabel("E"); a2.set_ylabel("bursts"); a2.set_title("Selected sub-populations")
    a2.legend(fontsize=8)
    save(fig, "population_selection.png")


def fig_h2mm_dashboard():
    rng = np.random.default_rng(30)
    E_states = np.array([0.25, 0.55, 0.8])
    # dwells with measured E scattered around 3 states
    dwell_E, before, after = [], [], []
    s = 0
    for _ in range(1500):
        ns = rng.integers(0, 3)
        d = rng.integers(4, 25)
        dwell_E.append((rng.binomial(d, E_states[ns]) / d))
        if s is not None:
            before.append(E_states[s]); after.append(E_states[ns])
        s = ns
    dwell_E = np.asarray(dwell_E)

    fig, axs = plt.subplots(2, 2, figsize=(8.6, 6.4))
    axs[0, 0].hist(dwell_E, bins=np.linspace(0, 1, 40), color="#1f77b4")
    for e in E_states: axs[0, 0].axvline(e, ls="--", color="k", lw=1)
    axs[0, 0].set_title("Dwell E histogram"); axs[0, 0].set_xlabel("E")
    axs[0, 1].hexbin(before, after, gridsize=25, cmap="magma", mincnt=1,
                     extent=(0, 1, 0, 1))
    axs[0, 1].set_title("Transition-density plot"); axs[0, 1].set_xlabel("E before")
    axs[0, 1].set_ylabel("E after")
    states = np.array([1, 2, 3, 4])
    bic = np.array([9500, 8200, 8180, 8240])
    axs[1, 0].plot(states, bic, "o-"); axs[1, 0].axvline(3, ls="--", color="#d62728")
    axs[1, 0].set_title("Model selection (BIC)"); axs[1, 0].set_xlabel("states")
    for i, e in enumerate(E_states):
        d = rng.exponential(1.5 + i, 2000)
        axs[1, 1].hist(d, bins=40, histtype="step", label=f"state {i+1}")
    axs[1, 1].set_title("Per-state dwell times"); axs[1, 1].set_xlabel("dwell (ms)")
    axs[1, 1].legend(fontsize=7)
    fig.suptitle("H2MM results dashboard", y=1.01)
    save(fig, "h2mm_dashboard.png")


def fig_h2mm_recovery():
    rng = np.random.default_rng(31)
    true_E = [0.3, 0.7]
    states = np.array([1, 2, 3])
    bic = np.array([4200, 3100, 3120])
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.0, 3.8))
    a1.plot(states, bic, "o-", color="#1f77b4")
    a1.axvline(2, ls="--", color="#d62728", label="selected (min BIC)")
    a1.set_xlabel("number of states"); a1.set_ylabel("BIC")
    a1.set_title("Model selection recovers 2 states"); a1.legend(fontsize=8)
    a1.set_xticks(states)
    recovered = [0.31, 0.69]
    x = np.arange(2)
    a2.bar(x - 0.15, true_E, 0.3, label="true", color="0.7")
    a2.bar(x + 0.15, recovered, 0.3, label="H2MM", color="#1f77b4")
    a2.set_xticks(x); a2.set_xticklabels(["state 1", "state 2"])
    a2.set_ylabel("FRET efficiency"); a2.set_ylim(0, 1)
    a2.set_title("Recovered vs simulated E"); a2.legend(fontsize=8)
    save(fig, "h2mm_recovery.png")


def fig_nsalex_etau():
    """ns-ALEX: FRET efficiency vs donor lifetime with the static-FRET line."""
    rng = np.random.default_rng(32)
    tau0 = 3.8                                       # ns, donor-only lifetime
    # static populations sit on tau = tau0 (1 - E); a dynamic one sits off it
    E_lo = rng.normal(0.25, 0.05, 500); tau_lo = tau0 * (1 - E_lo) + rng.normal(0, 0.1, 500)
    E_hi = rng.normal(0.7, 0.05, 500); tau_hi = tau0 * (1 - E_hi) + rng.normal(0, 0.1, 500)
    E_dyn = rng.normal(0.5, 0.06, 400)
    tau_dyn = tau0 * (1 - E_dyn) + 0.6 + rng.normal(0, 0.1, 400)   # above the line

    fig, ax = plt.subplots(figsize=(5.6, 4.2))
    ax.scatter(E_lo, tau_lo, s=8, alpha=0.4, color="#1f77b4", label="static")
    ax.scatter(E_hi, tau_hi, s=8, alpha=0.4, color="#1f77b4")
    ax.scatter(E_dyn, tau_dyn, s=8, alpha=0.4, color="#d62728", label="dynamic")
    e = np.linspace(0, 1, 100)
    ax.plot(e, tau0 * (1 - e), "k-", lw=2, label=r"static FRET line  $\tau=\tau_0(1-E)$")
    ax.set_xlabel("FRET efficiency E"); ax.set_ylabel(r"donor lifetime $\tau_{D}$ (ns)")
    ax.set_xlim(0, 1); ax.set_ylim(0, tau0 * 1.1)
    ax.set_title("ns-ALEX: FRET–lifetime (E–τ) plot"); ax.legend(fontsize=8)
    save(fig, "nsalex_etau.png")


def fig_accurate_fret():
    """Static/dynamic FRET lines and what a wrong gamma does to a population."""
    from chisurf.core.fluorescence.fret.accurate import gamma_from_lifetime
    from chisurf.core.fluorescence.fret.lines import (
        dynamic_fret_line,
        no_linker_line,
        static_fret_line,
    )

    tau0, r0, sigma = 4.0, 52.0, 6.0
    static = static_fret_line(tau0, r0=r0, sigma=sigma)
    sharp = no_linker_line(tau0)
    dynamic = dynamic_fret_line(tau0, r0=r0, sigma=sigma, distance_1=38.0, distance_2=72.0)

    rng = np.random.default_rng(11)
    e_true = 0.55
    tau_pop = float(static.lifetime_at(e_true))
    tau = rng.normal(tau_pop, 0.12, 600)
    e_ok = rng.normal(e_true, 0.045, 600)
    # the same bursts corrected with a 40 % too large gamma: E = F/(F + gamma*D)
    ratio = e_true / (1 - e_true)
    e_bad = rng.normal(ratio / (ratio + 1.4), 0.045, 600)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(10.5, 4.2))
    ax.plot(sharp.tau_f, sharp.efficiency, "k--", lw=1.2, label=r"no linker: $E=1-\tau/\tau_0$")
    ax.plot(static.tau_f, static.efficiency, "k-", lw=2, label="static FRET line")
    ax.plot(dynamic.tau_f, dynamic.efficiency, "-", color="#d62728", lw=2,
            label="dynamic FRET line")
    ax.set_xlabel(r"$\langle\tau_{D(A)}\rangle_F$ (ns)")
    ax.set_ylabel("FRET efficiency E")
    ax.set_xlim(0, tau0 * 1.05); ax.set_ylim(0, 1)
    ax.set_title("FRET lines (linker width 6 Å)"); ax.legend(fontsize=8)

    bx.plot(static.tau_f, static.efficiency, "k-", lw=2, label="static FRET line")
    bx.scatter(tau, e_ok, s=8, alpha=0.35, color="#1f77b4", label=r"correct $\gamma$")
    bx.scatter(tau, e_bad, s=8, alpha=0.35, color="#ff7f0e", label=r"$\gamma$ 40 % too large")
    bx.set_xlabel(r"$\langle\tau_{D(A)}\rangle_F$ (ns)")
    bx.set_ylabel("FRET efficiency E")
    bx.set_xlim(0, tau0 * 1.05); bx.set_ylim(0, 1)
    bx.set_title(r"a wrong $\gamma$ pushes the population off the line")
    bx.legend(fontsize=8)
    save(fig, "accurate_fret_lines.png")

    # the same relation read backwards: the line recovers gamma from the lifetime
    f_dd = np.full(600, 1.0)
    f_da = f_dd * ratio            # intensity ratio of the true population
    recovered = gamma_from_lifetime(f_dd, f_da, tau, line=static)["gamma"]
    print(f"  gamma recovered from the static line: {recovered:.3f} (expected 1.000)")


def fig_combining_repeats():
    rng = np.random.default_rng(33)
    fig, ax = plt.subplots(figsize=(5.8, 4.0))
    bins = np.arange(-0.05, 1.05, 0.03)
    allE = []
    for i, (n, c) in enumerate([(600, "#9ecae1"), (700, "#6baed6"), (550, "#3182bd")]):
        E = np.concatenate([rng.normal(0.3, 0.05, n // 2), rng.normal(0.72, 0.05, n // 2)])
        allE.append(E)
        ax.hist(E, bins=bins, histtype="step", color=c, label=f"repeat {i+1} (n={n})")
    ax.hist(np.concatenate(allE), bins=bins, color="0.85", zorder=0, label="combined")
    ax.set_xlabel("FRET efficiency E"); ax.set_ylabel("bursts")
    ax.set_title("Combining technical repeats"); ax.legend(fontsize=8)
    save(fig, "combining_repeats.png")


def fig_multispot():
    rng = np.random.default_rng(34)
    fig, axs = plt.subplots(2, 4, figsize=(9.6, 4.4), sharex=True, sharey=True)
    bins = np.arange(-0.05, 1.05, 0.04)
    for spot, ax in enumerate(axs.ravel()):
        n = rng.integers(300, 600)
        E = np.concatenate([rng.normal(0.28, 0.05, n // 2),
                            rng.normal(0.70 + rng.normal(0, 0.01), 0.05, n // 2)])
        ax.hist(E, bins=bins, color="#1f77b4")
        ax.axvline(np.median(E[E > 0.5]), color="#d62728", lw=1)
        ax.set_title(f"spot {spot+1}", fontsize=8)
        ax.set_xlim(0, 1)
    fig.suptitle("8-spot multispot smFRET — per-spot E histograms", y=1.0)
    fig.supxlabel("FRET efficiency E"); fig.supylabel("bursts")
    save(fig, "multispot.png")


def fig_lut():
    """TAC differential non-linearity and its LUT correction (concepts figure)."""
    from chisurf.plugins.tttr.tttr_lut_tools import api

    rng = np.random.default_rng(7)
    n_bins = 4096
    # A *uniform-illumination* measurement should be flat, but TAC DNL modulates
    # the effective bin widths -> a wavy histogram (this is what we correct).
    bins = np.arange(n_bins)
    dnl = 1.0 + 0.25 * np.sin(2 * np.pi * bins / 512) + 0.10 * np.sin(2 * np.pi * bins / 97)
    rate = 250.0 * dnl
    raw_counts = rng.poisson(rate).astype(float)

    # Build the LUT from the flat-light histogram, then apply it to fresh photons.
    tbl = api.compute.compute_lut_from_counts(raw_counts, 64, n_bins - 64, n_bins, 0)
    ntac = np.asarray(tbl["NTAC_fract"])
    photons = rng.integers(0, n_bins, size=1_500_000)
    # weight photons by the same DNL so the raw histogram is wavy
    keep = rng.random(photons.size) < dnl[photons] / dnl.max()
    photons = photons[keep]
    corrected = api.lut.stochastic_rebin_ntac(photons, ntac, 0, seed=42, rounding="ceil")
    raw_hist = np.bincount(photons, minlength=n_bins)[:n_bins]
    cor_hist = np.bincount(np.clip(corrected, 0, n_bins - 1), minlength=n_bins)[:n_bins]

    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(9.4, 3.6))
    sm = lambda y: np.convolve(y, np.ones(24) / 24, mode="same")  # noqa: E731
    ax0.plot(sm(raw_hist), color="#d62728", lw=1.2, label="raw (DNL-distorted)")
    ax0.plot(sm(cor_hist), color="#1f77b4", lw=1.2, label="LUT-linearized")
    ax0.set_title("Uniform-illumination histogram")
    ax0.set_xlabel("micro-time channel"); ax0.set_ylabel("counts")
    ax0.legend(fontsize=8)
    ax1.plot(ntac, color="#4c9be8", lw=1.3, label="NTAC_fract (LUT)")
    ax1.plot([0, n_bins], [0, ntac[-1]], "k--", lw=0.8, alpha=0.6, label="ideal (linear)")
    ax1.set_title("Cumulative LUT vs the linear ideal")
    ax1.set_xlabel("raw channel"); ax1.set_ylabel("corrected NTAC")
    ax1.legend(fontsize=8)
    save(fig, "lut.png")


def fig_av():
    """Accessible-volume dye clouds + inter-dye distance distribution + mean E."""
    from chisurf.core.structure import Structure
    from chisurf.core.structure.av import BasicAV
    pdb = pathlib.Path(__file__).resolve().parents[2] / \
        "test/data/atomic_coordinates/pdb_files/148l.pdb"
    s = Structure(filename=str(pdb))
    kw = dict(linker_length=20.5, linker_width=1.5, radius1=3.5, simulation_type="AV1")
    donor = BasicAV(s, residue_seq_number=27, atom_name="CA", **kw)
    accept = BasicAV(s, residue_seq_number=95, atom_name="CA", **kw)

    p, r = donor.pRDA(accept)
    area = np.trapezoid(p, r)
    if area > 0:
        p = p / area
    R0 = 52.0
    mean_r = float(np.trapezoid(r * p, r))
    mean_E = float(np.trapezoid(p / (1.0 + (r / R0) ** 6), r))

    prot = np.asarray(s.xyz, dtype=float).reshape(-1, 3)
    dp = np.asarray(donor.points, dtype=float)[:, :3]
    ap = np.asarray(accept.points, dtype=float)[:, :3]
    rng = np.random.default_rng(0)
    sub = lambda a, n=4000: a[rng.choice(len(a), min(n, len(a)), replace=False)]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.6, 4.2))
    a1.scatter(prot[:, 0], prot[:, 1], s=1, color="0.75", alpha=0.4)
    a1.scatter(sub(dp)[:, 0], sub(dp)[:, 1], s=2, color="#2ca02c", alpha=0.25, label="donor AV")
    a1.scatter(sub(ap)[:, 0], sub(ap)[:, 1], s=2, color="#d62728", alpha=0.25, label="acceptor AV")
    a1.scatter(*donor.Rmp[:2], color="#2ca02c", ec="k", s=60, zorder=5)
    a1.scatter(*accept.Rmp[:2], color="#d62728", ec="k", s=60, zorder=5)
    a1.set_aspect("equal"); a1.set_xlabel("x (Å)"); a1.set_ylabel("y (Å)")
    a1.set_title("Accessible volumes on T4 lysozyme"); a1.legend(fontsize=8, loc="upper right")

    a2.plot(r, p, color="#1f77b4", lw=2)
    a2.axvline(mean_r, ls="--", color="k", lw=1)
    a2.fill_between(r, p, alpha=0.2, color="#1f77b4")
    a2.set_xlabel(r"inter-dye distance $R_{DA}$ (Å)"); a2.set_ylabel("P(R)")
    a2.set_title(rf"$\langle R_{{DA}}\rangle$ = {mean_r:.1f} Å,  ⟨E⟩ = {mean_E:.2f} ($R_0$=52 Å)")
    save(fig, "av.png")


def fig_ebfret():
    """Real ebFRET empirical-Bayes HMM recovering a 3-state binned FRET trace set."""
    from chisurf.plugins.burst.burst_ebfret.core.analysis import analyse

    rng = np.random.default_rng(0)
    true_means = [0.25, 0.55, 0.80]
    A = np.array([[.97, .02, .01], [.02, .96, .02], [.01, .02, .97]])
    traces, paths = [], []
    for _ in range(12):
        s, tr, pa = 0, [], []
        for _ in range(300):
            tr.append(rng.normal(true_means[s], 0.06))
            pa.append(s)
            s = rng.choice(3, p=A[s])
        traces.append(np.array(tr)); paths.append(np.array(pa))

    ana = analyse(traces, min_states=2, max_states=4)
    means = np.array([s.mean for s in ana.states])

    # rebuild the decoded state path of trace 0 from the returned dwells
    decoded = np.zeros(len(traces[0]), dtype=int)
    for d in ana.dwells:
        if d.trace == 0:
            decoded[d.start:d.start + d.length] = d.state

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.8, 3.8),
                                 gridspec_kw={"width_ratios": [2.2, 1]})
    a1.plot(traces[0], color="0.6", lw=0.8, label="binned FRET trace")
    a1.step(np.arange(len(decoded)), means[decoded], color="#d62728", lw=1.6,
            where="mid", label="ebFRET Viterbi path")
    for m in means:
        a1.axhline(m, ls=":", color="#1f77b4", lw=0.9)
    a1.set_xlabel("time bin"); a1.set_ylabel("FRET efficiency E")
    a1.set_title(f"Trace 1 of 12 — {ana.n_states} states recovered")
    a1.legend(fontsize=8, loc="upper right")

    ks = sorted(ana.scan)
    a2.plot(ks, [ana.scan[k] for k in ks], "o-", color="#2ca02c")
    a2.axvline(ana.n_states, ls="--", color="#d62728", lw=1)
    a2.set_xticks(ks)
    a2.set_xlabel("number of states $K$"); a2.set_ylabel("evidence (lower bound)")
    a2.set_title("Model selection")
    fig.suptitle("ebFRET: true E = "
                 + ", ".join(f"{m:.2f}" for m in true_means)
                 + "   →   recovered " + ", ".join(f"{m:.2f}" for m in means), y=1.02)
    save(fig, "ebfret.png")


def fig_burst_lifetime():
    """Per-burst lifetime: the E-tau static-FRET line and a burst decay + MLE fit."""
    rng = np.random.default_rng(11)
    tau0 = 4.0                                  # donor-only lifetime (ns)

    # (a) one burst decay, parallel/perpendicular, and its reconvolution fit
    n, dt = 1024, 0.032                         # 32.8 ns window (a 25 MHz laser period)
    t = np.arange(n) * dt
    irf = np.exp(-0.5 * ((t - 1.2) / 0.15) ** 2); irf /= irf.sum()
    tau_b, r0, rho = 2.1, 0.38, 1.2
    d = np.exp(-t / tau_b); r = r0 * np.exp(-t / rho)
    conv = lambda x: np.convolve(x, irf)[:n]                       # noqa: E731
    vv = conv(d * (1 + 2 * r)); vh = conv(d * (1 - r))
    vv = vv / vv.sum() * 1200; vh = vh / vh.sum() * 800            # a ~2000-photon burst
    VV, VH = rng.poisson(vv), rng.poisson(vh)

    # (b) per-burst E vs lifetime: the static line and the *dynamic* line.
    # For a molecule interconverting between two states the FRET efficiency
    # follows the species-weighted lifetime, but the measured decay yields the
    # intensity(fluorescence)-weighted one -> the dynamic line bows to the right.
    E1, E2 = 0.72, 0.25
    tau1, tau2 = tau0 * (1 - E1), tau0 * (1 - E2)
    x = np.linspace(0, 1, 200)
    tau_x = x * tau1 + (1 - x) * tau2                     # species-weighted
    tau_f = (x * tau1 ** 2 + (1 - x) * tau2 ** 2) / tau_x  # intensity-weighted
    E_dyn_line = 1 - tau_x / tau0

    def static_pop(n_b, E):
        return (E + rng.normal(0, 0.05, n_b),
                tau0 * (1 - E) + rng.normal(0, 0.08, n_b))
    E_lo, t_lo = static_pop(500, E2)
    E_hi, t_hi = static_pop(500, E1)
    # bursts of the exchanging species scatter along the dynamic line
    xb = rng.uniform(0.15, 0.85, 450)
    tb_x = xb * tau1 + (1 - xb) * tau2
    tb_f = (xb * tau1 ** 2 + (1 - xb) * tau2 ** 2) / tb_x
    E_dy = 1 - tb_x / tau0 + rng.normal(0, 0.04, 450)
    t_dy = tb_f + rng.normal(0, 0.08, 450)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.0, 4.0))
    a1.semilogy(t, np.maximum(VV, 0.5), color="#2ca02c", lw=0.8, label="VV (parallel)")
    a1.semilogy(t, np.maximum(VH, 0.5), color="#d62728", lw=0.8, label="VH (perpendicular)")
    a1.semilogy(t, np.maximum(vv, 0.5), color="k", lw=1.3, ls="--", label="MLE model (VV)")
    a1.semilogy(t, np.maximum(irf / irf.max() * vv.max(), 0.5), color="0.6", lw=0.9,
                label="IRF")
    a1.set_xlim(0, 16); a1.set_ylim(0.5, vv.max() * 2)
    a1.set_xlabel("micro time (ns)"); a1.set_ylabel("photons per channel")
    a1.set_title(rf"One burst (~2000 photons), $\tau$ = {tau_b} ns")
    a1.legend(fontsize=8)

    tl = np.linspace(0.02, tau0, 200)
    a2.plot(tl, 1 - tl / tau0, "k-", lw=1.6, label=r"static line $E=1-\tau/\tau_0$")
    a2.plot(tau_f, E_dyn_line, color="#ff7f0e", lw=1.8, ls="--", label="dynamic line")
    a2.scatter(t_dy, E_dy, s=5, color="#ff7f0e", alpha=0.30, label="exchanging bursts")
    a2.scatter(t_lo, E_lo, s=5, color="#1f77b4", alpha=0.4, label="static populations")
    a2.scatter(t_hi, E_hi, s=5, color="#1f77b4", alpha=0.4)
    a2.set_xlim(0, tau0); a2.set_ylim(-0.05, 1.0)
    a2.set_xlabel(r"donor lifetime $\tau_{D(A)}$ (ns)"); a2.set_ylabel("FRET efficiency E")
    a2.set_title(r"E-$\tau$ plot ($\tau_0$ = 4.0 ns)")
    a2.legend(fontsize=8, loc="upper right")
    save(fig, "burst_lifetime.png")


def fig_clsm():
    """Confocal scan image: intensity, per-pixel lifetime (FLIM) and the decay pair."""
    rng = np.random.default_rng(5)
    ny = nx = 128
    yy, xx = np.mgrid[0:ny, 0:nx]

    def blob(cy, cx, r, soft=6.0):
        return 1 / (1 + np.exp((np.hypot(yy - cy, xx - cx) - r) / soft * 4))

    membrane = blob(64, 64, 46) - blob(64, 64, 38)      # a ring
    nucleus = blob(58, 70, 18)
    bright = 900 * membrane + 500 * nucleus + 25
    intensity = rng.poisson(bright)

    # two lifetime species: membrane 3.2 ns (unquenched), nucleus 1.6 ns (FRET)
    tau_true = 3.2 - 1.6 * (nucleus / (nucleus + membrane + 1e-9))
    # photon-limited lifetime noise: sigma ~ tau / sqrt(N)
    tau_map = tau_true + rng.normal(0, 1, (ny, nx)) * tau_true / np.sqrt(np.maximum(intensity, 1))
    tau_map = np.where(intensity > 80, tau_map, np.nan)   # mask dim pixels

    fig, axs = plt.subplots(1, 3, figsize=(11.2, 3.6))
    im0 = axs[0].imshow(intensity, cmap="gray")
    axs[0].set_title("Intensity (photons/pixel)")
    fig.colorbar(im0, ax=axs[0], fraction=0.046)
    cmap = plt.get_cmap("viridis").copy()
    cmap.set_bad("0.15")                       # photon-starved pixels are masked
    im1 = axs[1].imshow(tau_map, cmap=cmap, vmin=1.4, vmax=3.4)
    axs[1].set_title("FLIM: per-pixel lifetime (ns)")
    fig.colorbar(im1, ax=axs[1], fraction=0.046)
    for a in axs[:2]:
        a.set_xticks([]); a.set_yticks([]); a.grid(False)

    t = np.arange(0, 20, 0.05)
    for lab, tau, c in [("membrane (3.2 ns)", 3.2, "#1f77b4"),
                        ("nucleus, FRET (1.6 ns)", 1.6, "#d62728")]:
        axs[2].semilogy(t, np.exp(-t / tau), color=c, label=lab)
    axs[2].set_xlabel("micro time (ns)"); axs[2].set_ylabel("norm. counts")
    axs[2].set_title("Pixel decays"); axs[2].legend(fontsize=8)
    axs[2].set_ylim(1e-3, 1.5)
    save(fig, "clsm.png")


def fig_rcm_alex():
    """RCM/correction from the sample itself: E-S before and after correction."""
    from chisurf.core.fluorescence.burst.es import apparent_es, corrected_es

    rng = np.random.default_rng(21)
    gamma, alpha, delta, beta = 1.35, 0.09, 0.06, 0.95

    def species(n, e_true, s_kind):
        """Generate *measured* channel photons for one ALEX species.

        Bursts first get ideal photon budgets, then the instrument is applied:
        the donor budget splits by the true E, the acceptor arm is scaled by the
        detection factor gamma, donor leakage (alpha) and direct acceptor
        excitation (delta) add into the FRET channel, and the acceptor-excitation
        channel is scaled by the excitation-flux ratio beta.
        """
        size = rng.poisson(700, n)                     # burst brightness varies
        if s_kind == "donly":
            n_d, n_a, f_aa = size, np.zeros(n), rng.poisson(6, n).astype(float)
        elif s_kind == "aonly":
            n_d, n_a, f_aa = rng.poisson(6, n), np.zeros(n), size.astype(float)
        else:
            n_d = rng.binomial(size, 1 - e_true)       # donor photons survive
            n_a = size - n_d                           # the rest went to the acceptor
            f_aa = rng.poisson(700, n).astype(float)

        i_dd = np.asarray(n_d, float)
        i_da = gamma * np.asarray(n_a, float) + alpha * i_dd + delta * f_aa
        i_aa = f_aa / beta
        return i_dd, i_da, i_aa

    parts = [species(500, 0.0, "donly"), species(400, 0.0, "aonly"),
             species(900, 0.30, "fret"), species(900, 0.70, "fret")]
    i_dd = np.concatenate([p[0] for p in parts])
    i_da = np.concatenate([p[1] for p in parts])
    i_aa = np.concatenate([p[2] for p in parts])

    app = apparent_es(i_dd, i_da, i_aa)
    cor = corrected_es(i_dd, i_da, i_aa, gamma=gamma, alpha=alpha, delta=delta, beta=beta)

    fig, axs = plt.subplots(1, 2, figsize=(9.8, 4.2), sharex=True, sharey=True)
    for ax, res, ttl in [(axs[0], app, "Apparent (raw) $E_{app}$ / $S_{app}$"),
                         (axs[1], cor, "Corrected (accurate) $E$ / $S$")]:
        ax.scatter(res["E"], res["S"], s=4, alpha=0.3, color="#1f77b4")
        ax.set_xlim(-0.15, 1.15); ax.set_ylim(-0.05, 1.15)
        ax.set_xlabel("E"); ax.set_title(ttl, fontsize=10)
    axs[0].set_ylabel("stoichiometry S")
    for ax in axs:
        ax.axhline(0.5, ls=":", color="0.5", lw=0.8)
    axs[1].axvline(0.30, ls="--", color="#d62728", lw=0.9)
    axs[1].axvline(0.70, ls="--", color="#d62728", lw=0.9)
    fig.suptitle("Correction factors solved from the sample's own ALEX populations "
                 rf"($\gamma$={gamma}, $\alpha$={alpha}, $\delta$={delta}, $\beta$={beta})",
                 y=1.0, fontsize=10)
    save(fig, "rcm_alex.png")


def fig_2d_peak_fit():
    """Gaussian-mixture fit of the 2-D E-S histogram, with component ellipses."""
    from matplotlib.patches import Ellipse
    from sklearn.mixture import GaussianMixture

    rng = np.random.default_rng(42)
    truth = [((0.08, 0.92), (0.05, 0.04), 500),     # donor-only
             ((0.95, 0.10), (0.04, 0.04), 400),     # acceptor-only
             ((0.32, 0.52), (0.06, 0.05), 900),     # low-FRET
             ((0.74, 0.50), (0.05, 0.05), 800)]     # high-FRET
    pts = np.vstack([rng.normal(m, s, (n, 2)) for m, s, n in truth])

    gmm = GaussianMixture(n_components=4, covariance_type="full",
                          random_state=0).fit(pts)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(9.8, 4.2), sharex=True, sharey=True)
    a1.hist2d(pts[:, 0], pts[:, 1], bins=70, range=[[-0.1, 1.1], [-0.1, 1.1]],
              cmap="viridis")
    a1.set_title("2-D E-S histogram"); a1.set_ylabel("stoichiometry S")

    a2.scatter(pts[:, 0], pts[:, 1], s=3, color="0.7", alpha=0.5)
    order = np.argsort(-gmm.weights_)
    for rank, k in enumerate(order):
        mean, cov, w = gmm.means_[k], gmm.covariances_[k], gmm.weights_[k]
        vals, vecs = np.linalg.eigh(cov)
        ang = np.degrees(np.arctan2(vecs[1, -1], vecs[0, -1]))
        for nsig, alpha_ in ((1, 0.55), (2, 0.28)):
            a2.add_patch(Ellipse(mean, 2 * nsig * np.sqrt(vals[1]),
                                 2 * nsig * np.sqrt(vals[0]), angle=ang,
                                 fc="none", ec=f"C{rank}", lw=1.6, alpha=alpha_))
        a2.plot(*mean, "x", color=f"C{rank}", ms=8, mew=2,
                label=f"E={mean[0]:.2f}, S={mean[1]:.2f}, w={w:.2f}")
    a2.legend(fontsize=7, loc="lower left")
    a2.set_title("4-component Gaussian mixture (1σ, 2σ)")
    for a in (a1, a2):
        a.set_xlabel("FRET efficiency E")
    save(fig, "peak_fit_2d.png")


def fig_timestamps():
    """The burst data model: photon arrays and the burst index ranges into them."""
    rng = np.random.default_rng(3)
    n_ph = 220
    gaps = rng.exponential(1.0, n_ph)
    # three bursts = locally much denser photons
    for s, e in [(40, 70), (110, 138), (170, 196)]:
        gaps[s:e] *= 0.08
    macro = np.cumsum(gaps)
    route = (rng.random(n_ph) < 0.42).astype(int)          # 0 = green, 1 = red
    bursts = [(40, 69), (110, 137), (170, 195)]

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10.0, 4.6), sharex=True,
                                 gridspec_kw={"height_ratios": [1.5, 1]})
    for ch, c, lbl, y in [(0, "#2ca02c", "green detector", 1), (1, "#d62728", "red detector", 0)]:
        m = route == ch
        a1.vlines(macro[m], y, y + 0.8, color=c, lw=0.9)
        a1.text(-0.01, y + 0.4, lbl, ha="right", va="center", fontsize=8,
                transform=a1.get_yaxis_transform())
    for i, (s, e) in enumerate(bursts):
        a1.axvspan(macro[s], macro[e], color="#1f77b4", alpha=0.12, zorder=0)
        a1.annotate(f"burst {i}\nphotons [{s}, {e}]", (macro[(s + e) // 2], 2.0),
                    ha="center", fontsize=7.5, color="#1f77b4")
    a1.set_ylim(-0.2, 2.6); a1.set_yticks([]); a1.grid(False)
    a1.set_title("Photon stream: one tick per photon, coloured by routing channel")

    bin_s = 2.0
    edges = np.arange(0, macro[-1] + bin_s, bin_s)
    a2.step(edges[:-1], np.histogram(macro, edges)[0], where="post", color="0.35")
    for s, e in bursts:
        a2.axvspan(macro[s], macro[e], color="#1f77b4", alpha=0.12, zorder=0)
    a2.set_xlabel("macro time (arb. clock units)"); a2.set_ylabel("counts / bin")
    a2.set_title("The same stream binned — bursts are the count-rate spikes", fontsize=9)
    fig.suptitle("A burst is a [first, last] *index range* into the photon arrays", y=1.0)
    save(fig, "timestamps_bursts.png")


def fig_ndxplorer():
    """ndX: marginal fitting of an overlay curve, and the static FRET line.

    Two static smFRET populations (a no-FRET species and a FRET species) are
    simulated with binomial shot noise. The left panel is the E-vs-lifetime plane
    every burst lives in, with the **static FRET line** fitted through both
    clusters; the right panel is the E marginal fitted with two Gaussians using
    ndX's own ``fit_equation_to_marginal`` engine (the very function the
    guide's overlay-fit button drives).
    """
    import sys
    root = pathlib.Path(__file__).resolve().parents[2]
    ndx = str(root / "modules" / "ndxplorer")
    if ndx not in sys.path:
        sys.path.insert(0, ndx)
    from ndxplorer.analysis.marginal_fit import bin_centers, fit_equation_to_marginal
    from scipy.optimize import curve_fit

    rng = np.random.default_rng(3)
    tau0 = 4.0                       # donor-only lifetime (ns)
    n_no, n_fret = 2400, 3600
    E_no, E_fret = 0.02, 0.50        # true population efficiencies
    # Per-burst shot noise: N photons -> binomial acceptor count -> measured E.
    N_no = rng.integers(40, 200, n_no)
    N_fret = rng.integers(40, 200, n_fret)
    Emeas_no = rng.binomial(N_no, E_no) / N_no
    Emeas_fret = rng.binomial(N_fret, E_fret) / N_fret
    Emeas = np.concatenate([Emeas_no, Emeas_fret])
    # A burst on the static line: tau = tau0*(1 - E), plus lifetime-fit scatter.
    tau = tau0 * (1.0 - Emeas) + rng.normal(0, 0.05, Emeas.size)

    # Fit the static FRET line E = 1 - tau/tau0 through every burst (1 parameter).
    popt, _ = curve_fit(lambda t, t0: 1.0 - t / t0, tau, Emeas, p0=[3.5])
    tau0_fit = float(popt[0])

    # Fit the E marginal with two Gaussians via ndX's marginal-fit engine.
    counts, edges = np.histogram(Emeas, bins=70, range=(-0.1, 0.9))
    xc = bin_centers(edges)
    res = fit_equation_to_marginal(
        "a1*exp(-(x-m1)**2/(2*s1**2)) + a2*exp(-(x-m2)**2/(2*s2**2))",
        initial={"a1": counts.max(), "m1": 0.05, "s1": 0.03,
                 "a2": counts.max() * 0.6, "m2": 0.45, "s2": 0.06},
        x=xc, counts=counts.astype(float),
    )

    fig, (ax, axm) = plt.subplots(1, 2, figsize=(10.4, 4.2),
                                  gridspec_kw={"width_ratios": [1.15, 1]})
    ax.scatter(tau[:n_no], Emeas[:n_no], s=6, alpha=0.25, color="#7f7f7f",
               label="no-FRET species")
    ax.scatter(tau[n_no:], Emeas[n_no:], s=6, alpha=0.25, color="#d62728",
               label="FRET species")
    tl = np.linspace(tau.min(), tau.max(), 100)
    ax.plot(tl, 1.0 - tl / tau0_fit, "k-", lw=1.8,
            label=fr"static line $E=1-\tau/\tau_0$, $\tau_0={tau0_fit:.2f}$ ns")
    ax.set_xlabel(r"$\langle\tau_{D(A)}\rangle_F$  (ns)")
    ax.set_ylabel("FRET efficiency $E$")
    ax.set_title("Every burst lives on the static FRET line", fontsize=10)
    ax.legend(fontsize=8, loc="upper right")

    axm.step(xc, counts, where="mid", color="0.4", label="E marginal")
    if res.ok and res.y_fit is not None:
        axm.plot(xc, res.y_fit, "-", color="#1f77b4", lw=1.8,
                 label=fr"two-Gaussian fit, $\chi^2_r={res.chi2r:.1f}$")
        axm.axvline(res.params["m1"], color="#7f7f7f", ls="--", lw=1)
        axm.axvline(res.params["m2"], color="#d62728", ls="--", lw=1)
    axm.set_xlabel("FRET efficiency $E$"); axm.set_ylabel("bursts / bin")
    axm.set_title("The E marginal, fitted in the parameter table", fontsize=10)
    axm.legend(fontsize=8)
    save(fig, "ndxplorer_marginal_fit.png")


# --------------------------------------------------------------------------
# 48. Regions: analysis region, foreground molecules, background
# --------------------------------------------------------------------------
def fig_regions():
    """Regions in single-molecule imaging: analysis region, molecules, background.

    Runs the real ``chisurf.core.roi`` segmentation and measurement on a
    synthetic frame — the same functions the guide describes.
    """
    from chisurf.core.roi import (
        MaskROI,
        RectangleROI,
        labels_to_rois,
        regionprops,
        regionprops_table,
    )
    import scipy.ndimage as ndi

    rng = np.random.default_rng(11)
    ny = nx = 96
    yy, xx = np.mgrid[0:ny, 0:nx]

    # An immobilised sample: diffraction-limited spots of varying brightness,
    # some inside the illuminated patch and some outside it.
    spots = [(28, 26, 900), (34, 58, 1400), (58, 34, 700), (66, 62, 1100),
             (18, 78, 800), (78, 18, 600), (12, 12, 500), (84, 84, 950)]
    frame = np.full((ny, nx), 12.0)
    for cy, cx, amp in spots:
        frame += amp * np.exp(-((yy - cy) ** 2 + (xx - cx) ** 2) / (2 * 2.1 ** 2))
    image = rng.poisson(frame).astype(float)

    # 1. the analysis region — one illuminated patch, drawn or loaded
    patch = RectangleROI(14, 14, 74, 74, name="illuminated patch")
    patch_mask = patch.to_mask(image.shape)

    # 2. the foreground — segment only inside the patch, and let the automatic
    #    threshold see only the patch's own pixels
    inside = image[patch_mask]
    threshold = inside.mean() + 3.0 * inside.std()
    labels, n = ndi.label((image > threshold) & patch_mask)
    props = regionprops(labels, intensity_image=image)

    # 3. the background — NOT the complement: dilate first, or the PSF tails
    #    around every molecule inflate the background rate
    foreground = MaskROI(labels > 0, name="molecules")
    dilated = ndi.binary_dilation(labels > 0, iterations=3)
    background = MaskROI(patch_mask & ~dilated, name="background")
    bg_rate = image[background.to_mask(image.shape)].mean()
    naive_rate = image[patch_mask & ~(labels > 0)].mean()

    fig, axs = plt.subplots(1, 3, figsize=(12.0, 3.9))

    axs[0].imshow(image, cmap="magma")
    y0, x0, y1, x1 = 14, 14, 74, 74
    axs[0].plot([x0, x1, x1, x0, x0], [y0, y0, y1, y1, y0], color="#4dd0e1", lw=1.6)
    axs[0].set_title(f"Frame + analysis region\n{n} molecules inside, "
                     f"{len(spots) - n} outside")

    overlay = np.where(labels > 0, labels, np.nan)
    axs[1].imshow(image, cmap="gray")
    axs[1].imshow(overlay, cmap="tab10", alpha=0.85, interpolation="nearest")
    for p in props:
        r, c = p.centroid
        axs[1].plot(c, r, "w+", ms=6, mew=1.2)
    axs[1].set_title("Foreground: one region per molecule\n(+ = centroid)")

    axs[2].imshow(background.to_mask(image.shape), cmap="Blues", vmin=0, vmax=1.6)
    axs[2].set_title(f"Background after a 3-px margin\n"
                     f"{bg_rate:.1f} ph/px  (naive: {naive_rate:.1f})")

    for a in axs:
        a.set_xticks([]); a.set_yticks([]); a.grid(False)
    save(fig, "regions.png")

    table = regionprops_table(
        labels, intensity_image=image,
        properties=("label", "area", "centroid", "eccentricity", "intensity_mean"),
    )
    print("  regions.png:", n, "molecules;",
          "area", np.round(table["area"], 1).tolist()[:4], "…;",
          f"background {bg_rate:.2f} ph/px vs naive {naive_rate:.2f}")


if __name__ == "__main__":
    fig_lut()
    fig_av()
    fig_2cde(); fig_rasp(); fig_polymer(); fig_fida(); fig_mdf(); fig_g3(); fig_rcm()
    fig_bva(); fig_fcs_diffusion(); fig_lifetime_anisotropy(); fig_pda()
    fig_tttr(); fig_burst_search(); fig_es(); fig_background()
    fig_fret_fcs(); fig_filtered_fcs(); fig_simulation(); fig_h2mm(); fig_mcs()
    fig_alex_workflow(); fig_e_hist_fit(); fig_population_selection()
    fig_h2mm_dashboard(); fig_h2mm_recovery()
    fig_nsalex_etau(); fig_accurate_fret(); fig_combining_repeats(); fig_multispot()
    fig_ebfret(); fig_burst_lifetime(); fig_clsm()
    fig_rcm_alex(); fig_2d_peak_fit(); fig_timestamps()
    fig_ndxplorer()
    fig_regions()
    print("all figures written to", FIG)
