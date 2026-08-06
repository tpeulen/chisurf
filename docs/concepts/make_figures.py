#!/usr/bin/env python
"""Generate the figures of the concept (theory) pages, headlessly.

A theory page describes a *shape* — how efficiency falls with distance, how an
anisotropy decays, what a shot-noise floor looks like — and a page that only
describes it in words asks the reader to draw it in their head. Each figure here
shows the one relationship its page is about.

Every figure is computed with the **shipped functions**, not with a sketch of
them: the FRET curve calls ChiSurf's efficiency, the polarised decays call the
kernel the fit uses, the BVA floor calls the same Monte-Carlo the tool draws.
A figure drawn from a re-implementation would agree with the page and disagree
with the program, which is the one failure a figure must not have.

Run headlessly (no display needed)::

    python docs/concepts/make_figures.py [name ...]
"""

from __future__ import annotations

import pathlib
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

FIG = pathlib.Path(__file__).parent / "figures"
FIG.mkdir(exist_ok=True)

plt.rcParams.update(
    {
        "figure.dpi": 110,
        "font.size": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)


def save(fig, name: str) -> None:
    """Write *fig* to ``docs/concepts/figures/<name>``."""
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# ── FRET: the ruler and its useful window ───────────────────────────


def fig_fret_ruler():
    """E(R) and the error amplification that sets the usable range."""
    from chisurf.core.fluorescence.general import distance_to_fret_efficiency

    r0 = 52.0
    r = np.linspace(0.3 * r0, 2.0 * r0, 600)
    e = np.array([distance_to_fret_efficiency(x, r0) for x in r])

    fig, (left, right) = plt.subplots(1, 2, figsize=(7.6, 3.0))

    left.plot(r / r0, e, color="#2b6cb0", lw=2)
    left.axvspan(0.5, 1.5, color="#2b6cb0", alpha=0.10, lw=0)
    left.axhline(0.5, color="0.6", lw=0.8, ls=":")
    left.axvline(1.0, color="0.6", lw=0.8, ls=":")
    left.annotate(
        "usable window\n$0.5\\,R_0 - 1.5\\,R_0$",
        xy=(1.0, 0.5), xytext=(1.30, 0.72), fontsize=8, color="#2b6cb0",
    )
    left.set_xlabel("$R / R_0$")
    left.set_ylabel("FRET efficiency $E$")
    left.set_title("A steep, calibrated function of distance", fontsize=9)

    # The same curve read as precision: dR/R = dE / [6 E (1-E)].
    grid = np.linspace(0.02, 0.98, 500)
    amplification = 1.0 / (6.0 * grid * (1.0 - grid))
    right.semilogy(grid, amplification, color="#b7791f", lw=2)
    right.axvspan(0.08, 0.98, color="#b7791f", alpha=0.10, lw=0)
    for value in (0.1, 0.5, 0.9):
        y = 1.0 / (6.0 * value * (1.0 - value))
        right.plot([value], [y], "o", color="#b7791f", ms=4)
        right.annotate(f"{y:.2f}", xy=(value, y), xytext=(0, 6),
                       textcoords="offset points", ha="center", fontsize=8)
    right.set_xlabel("FRET efficiency $E$")
    right.set_ylabel(r"$(\Delta R/R)\,/\,\Delta E$")
    right.set_title("The same 2 % in $E$ costs more at the ends", fontsize=9)
    right.set_xlim(0, 1)

    save(fig, "fret_ruler.png")


# ── Anisotropy: what the two polarised channels carry ───────────────


def fig_anisotropy_decays():
    """r(t) for free / hindered rotation, and the VV and VH decays it rides on."""
    from chisurf.core.fluorescence.anisotropy.decay import vm_rt_to_vv_vh

    times = np.linspace(0, 30.0, 1500)          # ns
    vm = np.exp(-times / 4.0)                   # magic-angle intensity decay

    cases = (
        ("free dye, $\\rho = 0.5$ ns", np.array([0.38, 0.5]), "#2b6cb0"),
        ("labelled protein, $\\rho = 12$ ns", np.array([0.38, 12.0]), "#b7791f"),
        ("hindered, $r_\\infty = 0.15$",
         np.array([0.23, 12.0, 0.15, 1.0e6]), "#9b2c2c"),
    )

    fig, (left, right) = plt.subplots(1, 2, figsize=(7.6, 3.0))
    for label, spectrum, colour in cases:
        vv, vh = vm_rt_to_vv_vh(times, vm, spectrum)
        r = (vv - vh) / (vv + 2.0 * vh)
        left.plot(times, r, color=colour, lw=1.8, label=label)
        # The two channels for the extremes: free rotation makes them meet,
        # hindered rotation leaves them apart for ever.
        if "free dye" in label or "hindered" in label:
            style = "VV/VH, " + ("free" if "free" in label else "hindered")
            right.semilogy(times, vv, color=colour, lw=1.6, label=style)
            right.semilogy(times, vh, color=colour, lw=1.6, ls="--")

    left.axhline(0.38, color="0.6", lw=0.8, ls=":")
    left.annotate("$r_0$", xy=(0.6, 0.392), fontsize=8, color="0.45",
                  ha="left", va="bottom")
    left.set_xlabel("time (ns)")
    left.set_ylabel("anisotropy $r(t)$")
    left.set_ylim(-0.02, 0.46)
    left.legend(fontsize=8, loc="upper right")
    left.set_title("Rotation, and rotation that cannot finish", fontsize=9)

    right.set_xlabel("time (ns)")
    right.set_ylabel("counts (a.u.)")
    right.set_xlim(0, 12)
    right.set_ylim(3e-2, 3)
    right.legend(fontsize=8)
    right.set_title("The fit sees these two, not $r(t)$", fontsize=9)

    save(fig, "anisotropy_decays.png")


# ── TCSPC: the two averages are not the same number ─────────────────


def fig_lifetime_averages():
    """A two-component decay, and how far apart its two averages sit."""
    from chisurf.core.fluorescence.tcspc.convolve import convolve_lifetime_spectrum

    n = 4096
    dt = 0.0122                                  # ns per channel (50 ns window)
    times = np.arange(n) * dt
    irf = np.exp(-0.5 * ((times - 1.2) / 0.09) ** 2)
    irf /= irf.sum()

    spectrum = np.array([0.5, 0.5, 0.5, 4.0])    # a1, tau1, a2, tau2
    decay = np.zeros(n)
    convolve_lifetime_spectrum(decay, spectrum, irf, time_axis=times)

    amplitudes = spectrum[::2]
    lifetimes = spectrum[1::2]
    tau_x = float((amplitudes * lifetimes).sum() / amplitudes.sum())
    tau_f = float(
        (amplitudes * lifetimes**2).sum() / (amplitudes * lifetimes).sum()
    )

    fig, (left, right) = plt.subplots(
        1, 2, figsize=(7.6, 3.0), gridspec_kw={"width_ratios": (2.0, 1.0)}
    )
    left.semilogy(times, irf / irf.max(), color="0.65", lw=1.2, label="IRF")
    left.semilogy(times, decay / decay.max(), color="#2b6cb0", lw=1.8,
                  label="reconvolved decay")
    for value, colour, label, height in (
        (tau_x, "#b7791f", r"$\langle\tau\rangle_x$", 0.45),
        (tau_f, "#9b2c2c", r"$\langle\tau\rangle_f$", 0.12),
    ):
        left.axvline(value + 1.2, color=colour, lw=1.2, ls="--")
        left.annotate(f"{label} = {value:.2f} ns", xy=(value + 1.2, height),
                      xytext=(8, 0), textcoords="offset points",
                      color=colour, fontsize=8, va="center")
    left.set_xlim(0, 20)
    left.set_ylim(1e-4, 1.6)
    left.set_xlabel("time (ns)")
    left.set_ylabel("normalised counts")
    left.legend(fontsize=8, loc="upper right")
    left.set_title("Two components, 0.5 and 4.0 ns, equal amplitudes",
                   fontsize=9)

    # The same two species, weighted the two ways.
    species = amplitudes / amplitudes.sum()
    intensity = amplitudes * lifetimes / (amplitudes * lifetimes).sum()
    positions = np.arange(2)
    right.bar(positions - 0.2, species, 0.4, color="#b7791f",
              label="species fraction $x_i$")
    right.bar(positions + 0.2, intensity, 0.4, color="#9b2c2c",
              label="intensity fraction $f_i$")
    for x, value in zip(positions - 0.2, species):
        right.annotate(f"{value:.0%}", xy=(x, value), xytext=(0, 3),
                       textcoords="offset points", ha="center", fontsize=8)
    for x, value in zip(positions + 0.2, intensity):
        right.annotate(f"{value:.0%}", xy=(x, value), xytext=(0, 3),
                       textcoords="offset points", ha="center", fontsize=8)
    right.set_xticks(positions)
    right.set_xticklabels(["0.5 ns", "4.0 ns"])
    right.set_ylim(0, 1.05)
    right.set_ylabel("fraction")
    right.legend(fontsize=8, loc="upper left")
    right.set_title("Half the molecules, a ninth of the photons", fontsize=9)

    save(fig, "lifetime_averages.png")


# ── FCS: the curve is a product of independent factors ──────────────


def fig_fcs_factors():
    """G(tau) built from its triplet and diffusion factors."""
    tau = np.logspace(-7, 0, 700)               # s
    tau_d, gamma, n = 3.8e-5, 5.0, 2.0
    theta, tau_t = 0.18, 3.0e-6

    diffusion = (1 + tau / tau_d) ** -1 * (1 + tau / (gamma**2 * tau_d)) ** -0.5
    triplet = 1 + theta / (1 - theta) * np.exp(-tau / tau_t)

    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.semilogx(tau, diffusion / n, color="#2b6cb0", lw=1.6,
                label="diffusion $D(\\tau)$ only")
    ax.semilogx(tau, triplet / n, color="#b7791f", lw=1.6, ls="--",
                label="photodynamics $P(\\tau)$ only")
    ax.semilogx(tau, diffusion * triplet / n, color="#9b2c2c", lw=2.2,
                label="their product — the measured curve")
    ax.axhline(1 / n, color="0.6", lw=0.8, ls=":")
    ax.annotate("$1/N$", xy=(1.4e-7, 1 / n), xytext=(0, 5),
                textcoords="offset points", fontsize=8, color="0.4")
    ax.axvline(tau_t, color="#b7791f", lw=0.8, ls=":")
    ax.axvline(tau_d, color="#2b6cb0", lw=0.8, ls=":")
    ax.annotate(r"$\tau_\mathrm{trip}$", xy=(tau_t, 0.02), fontsize=8,
                color="#b7791f")
    ax.annotate(r"$\tau_D$", xy=(tau_d, 0.02), fontsize=8, color="#2b6cb0")
    ax.set_xlabel(r"lag $\tau$ (s)")
    ax.set_ylabel(r"$G(\tau)$")
    ax.legend(fontsize=8)
    ax.set_title("Every model is a product of factors on separate timescales",
                 fontsize=9)
    save(fig, "fcs_factors.png")


# ── Accessible volume: three distances from one distribution ────────


def fig_av_distances():
    """The FRET average against the plain one, and where the two swap sign."""
    r0 = 52.0

    def averages(mean, sigma):
        r = np.linspace(max(1.0, mean - 6 * sigma), mean + 6 * sigma, 20001)
        weight = np.exp(-0.5 * ((r - mean) / sigma) ** 2)
        weight /= weight.sum()
        plain = float((weight * r).sum())
        efficiency = 1.0 / (1.0 + (r / r0) ** 6)
        fret = r0 * (1.0 / float((weight * efficiency).sum()) - 1.0) ** (1 / 6)
        return r, weight, plain, fret

    fig, (left, right) = plt.subplots(1, 2, figsize=(7.6, 3.0))

    r, weight, plain, fret = averages(62.0, 12.0)
    left.fill_between(r, weight / weight.max(), color="#2b6cb0", alpha=0.18, lw=0)
    left.plot(r, weight / weight.max(), color="#2b6cb0", lw=1.8)
    for value, colour, label, height in (
        (plain, "#b7791f", r"$\langle R_{DA}\rangle$", 1.06),
        (fret, "#9b2c2c", r"$\langle R_{DA}\rangle_E$", 0.86),
    ):
        left.axvline(value, color=colour, lw=1.4, ls="--")
        left.annotate(f"{label} = {value:.1f} Å", xy=(value, height),
                      xytext=(-6, 0), textcoords="offset points",
                      ha="right", va="center", fontsize=8, color=colour)
    left.set_xlim(25, 100)
    left.set_ylim(0, 1.25)
    left.set_xlabel(r"inter-dye distance $R_{DA}$ (Å)")
    left.set_ylabel("weight (normalised)")
    left.set_title(r"One cloud ($\sigma = 12$ Å), two distances", fontsize=9)

    # The gap, and the inflection where its sign changes.
    means = np.linspace(30, 85, 60)
    for sigma, colour in ((6.0, "#2b6cb0"), (10.0, "#b7791f"), (15.0, "#9b2c2c")):
        gap = [averages(m, sigma)[3] - averages(m, sigma)[2] for m in means]
        right.plot(means, gap, color=colour, lw=1.7, label=f"$\\sigma$ = {sigma:.0f} Å")
    inflection = (5 / 7) ** (1 / 6) * r0
    right.axhline(0, color="0.6", lw=0.8)
    right.axvline(inflection, color="0.4", lw=1.0, ls=":")
    right.annotate(f"$R^*$ = {inflection:.0f} Å", xy=(inflection, 3.0),
                   xytext=(4, 0), textcoords="offset points", fontsize=8,
                   color="0.35")
    right.set_xlabel(r"$\langle R_{DA}\rangle$ (Å)")
    right.set_ylabel(r"$\langle R_{DA}\rangle_E - \langle R_{DA}\rangle$ (Å)")
    right.legend(fontsize=8)
    right.set_title("The gap changes sign — quoting the wrong one is biased",
                    fontsize=9)

    save(fig, "av_distances.png")


# ── BVA: the shot-noise floor a burst cannot go below ───────────────


def fig_bva_static_line():
    """The static line for three slice sizes, with a dynamic population above."""
    from chisurf.core.fluorescence.burst.bva import compute_static_bva_line

    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    bins = np.linspace(0.02, 0.98, 49)
    for photons, colour in ((5, "#2b6cb0"), (10, "#b7791f"), (20, "#9b2c2c")):
        centres, sigma = compute_static_bva_line(
            bins, number_of_photons_per_slice=photons, n_samples=4000
        )
        ax.plot(centres, sigma, color=colour, lw=1.8, label=f"$n$ = {photons}")

    rng = np.random.default_rng(3)
    e = np.clip(rng.normal(0.5, 0.13, 260), 0.05, 0.95)
    floor = np.sqrt(e * (1 - e) / 5.0)
    ax.plot(e, floor * rng.normal(1.35, 0.10, e.size), ".", ms=3,
            color="0.35", alpha=0.7, label="bursts with sub-burst exchange")

    ax.set_xlabel(r"burst mean efficiency $\bar{E}$")
    ax.set_ylabel(r"per-burst scatter $s_E$")
    ax.set_ylim(0, 0.36)
    ax.legend(fontsize=8, loc="lower center", ncol=2)
    ax.set_title("A static molecule cannot sit below its own shot noise",
                 fontsize=9)
    save(fig, "bva_static_line.png")


# ── PCH: identical intensity, different brightness ──────────────────


def fig_pch_brightness():
    """Two samples with the same mean count rate and different histograms."""
    from chisurf.plugins.pch.api.algorithms import pch_open_system

    k = np.arange(0, 12)
    few_bright = pch_open_system(k, 1.0, 2.0)
    many_dim = pch_open_system(k, 0.5, 4.0)

    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    width = 0.4
    ax.bar(k - width / 2, few_bright, width, color="#2b6cb0",
           label=r"$\epsilon T = 1.0$, $N = 2$")
    ax.bar(k + width / 2, many_dim, width, color="#b7791f",
           label=r"$\epsilon T = 0.5$, $N = 4$")
    ax.set_yscale("log")
    ax.set_ylim(1e-5, 1)
    ax.set_xlabel("photons per bin $k$")
    ax.set_ylabel("$P(k)$")
    ax.legend(fontsize=8)
    ax.set_title(
        r"Same $\langle k\rangle = 2$: no intensity measurement tells them apart",
        fontsize=9,
    )
    save(fig, "pch_brightness.png")


# ── Phasor: the universal semicircle ────────────────────────────────


def fig_phasor_circle():
    """The universal circle, a lifetime scale, and a two-component chord."""
    omega = 2 * np.pi * 80e6                     # 80 MHz repetition
    circle = np.linspace(0, np.pi, 400)
    g_circle = 0.5 + 0.5 * np.cos(circle)
    s_circle = 0.5 * np.sin(circle)

    def point(tau_ns):
        wt = omega * tau_ns * 1e-9
        return 1 / (1 + wt**2), wt / (1 + wt**2)

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    ax.plot(g_circle, s_circle, color="0.45", lw=1.6)
    for tau in (0.5, 1, 2, 4, 8):
        g, s = point(tau)
        ax.plot([g], [s], "o", ms=4, color="0.45")
        ax.annotate(f"{tau:g} ns", xy=(g, s), xytext=(2, 5),
                    textcoords="offset points", fontsize=7, color="0.35")

    g1, s1 = point(0.6)
    g2, s2 = point(4.0)
    ax.plot([g1, g2], [s1, s2], color="#2b6cb0", lw=1.6, ls="--")
    for f in (0.25, 0.5, 0.75):
        ax.plot([g1 + f * (g2 - g1)], [s1 + f * (s2 - s1)], "o", ms=4,
                color="#2b6cb0")
    ax.annotate("a mixture lies on the chord,\nat the lever-rule fraction",
                xy=(0.5 * (g1 + g2), 0.5 * (s1 + s2)), xytext=(-6, -34),
                textcoords="offset points", fontsize=8, color="#2b6cb0")

    ax.set_xlabel("$g$")
    ax.set_ylabel("$s$")
    ax.set_xlim(-0.04, 1.10)
    ax.set_ylim(-0.02, 0.60)
    ax.set_aspect("equal")
    ax.set_title("Single exponentials on the arc, mixtures inside", fontsize=9)
    save(fig, "phasor_circle.png")


# ── FRC: the criterion changes the answer ───────────────────────────


def fig_frc_thresholds():
    """One FRC curve, three thresholds, three resolutions."""
    q = np.linspace(0.005, 0.25, 500)            # 1/nm
    frc = np.exp(-((q / 0.085) ** 2))            # a decaying correlation
    rings = np.maximum(4.0, 2 * np.pi * q / q[1])

    half_bit = (0.2071 + 1.9102 / np.sqrt(rings)) / (
        1.2071 + 0.9102 / np.sqrt(rings)
    )
    two_sigma = 2.0 / np.sqrt(rings / 2.0)
    fixed = np.full_like(q, 1.0 / 7.0)

    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    ax.plot(q, frc, color="#2b6cb0", lw=2, label="FRC")
    for curve, colour, label, offset in (
        (fixed, "#9b2c2c", "fixed 1/7", (8, -10)),
        (half_bit, "#b7791f", "½-bit", (-2, 16)),
        (two_sigma, "0.45", r"2$\sigma$", (-70, -6)),
    ):
        ax.plot(q, curve, color=colour, lw=1.3, ls="--", label=label)
        # A crossing counts only where the curve was *above* the threshold and
        # falls through it. Without that rule the count-dependent criteria,
        # which start above 1, "cross" in the first ring and report a
        # resolution the size of the field of view.
        above = np.where(frc > curve)[0]
        crossing = np.where((frc < curve) & (q > q[above[0]]))[0] if above.size else []
        if len(crossing):
            index = crossing[0]
            qc = q[index]
            ax.plot([qc], [frc[index]], "o", ms=5, color=colour)
            ax.annotate(f"{label}: {1 / qc:.0f} nm", xy=(qc, frc[index]),
                        xytext=offset, textcoords="offset points",
                        fontsize=8, color=colour)
    ax.set_xlabel("spatial frequency $q$ (nm$^{-1}$)")
    ax.set_ylabel("FRC")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=8)
    ax.set_title("A resolution without its criterion is not a result",
                 fontsize=9)
    save(fig, "frc_thresholds.png")


FIGURES = {
    "fret_ruler": fig_fret_ruler,
    "anisotropy_decays": fig_anisotropy_decays,
    "lifetime_averages": fig_lifetime_averages,
    "fcs_factors": fig_fcs_factors,
    "av_distances": fig_av_distances,
    "bva_static_line": fig_bva_static_line,
    "pch_brightness": fig_pch_brightness,
    "phasor_circle": fig_phasor_circle,
    "frc_thresholds": fig_frc_thresholds,
}


def main(names=()) -> None:
    """Draw the named figures, or all of them."""
    chosen = names or sorted(FIGURES)
    for name in chosen:
        if name not in FIGURES:
            print(f"unknown figure {name!r}; known: {', '.join(sorted(FIGURES))}")
            continue
        FIGURES[name]()


if __name__ == "__main__":
    main(sys.argv[1:])
