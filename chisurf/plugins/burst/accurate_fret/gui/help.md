# Accurate FRET — calibration from your own bursts

A raw single-molecule FRET histogram is not a distance measurement. The photon
counts have to be corrected for four instrument and photophysics factors before
the efficiency means anything outside your own setup:

| factor | symbol | what it removes |
|---|---|---|
| leakage | α | donor emission detected in the acceptor channel |
| direct excitation | δ | acceptor excited by the donor laser |
| detection | γ | different detection efficiency **and** quantum yield of the two dyes |
| excitation flux | β | different green/red excitation power (stoichiometry only) |

With them the accurate efficiency and stoichiometry are

```
F_DD = I_DD − Bg_DD                    F_AA = I_AA − Bg_AA
F_DA = (I_DA − Bg_DA) − α·F_DD − δ·F_AA
E    = F_DA / (F_DA + γ·F_DD)
S    = (γ·F_DD + F_DA) / (γ·F_DD + F_DA + F_AA/β)
```

(Hellenkamp *et al.*, Nat. Methods **15**, 669, 2018 — the multi-laboratory
benchmark that showed these systematics, not counting statistics, are what makes
FRET values differ between laboratories.)

## What this tool does

**It finds the factors for you.** Press *Calibrate* and it

1. fits a Gaussian mixture to the stoichiometry and labels every burst
   donor-only (S ≈ 1), acceptor-only (S ≈ 0) or doubly labelled — no hand-drawn
   gates, so nobody has to defend where the box was put;
2. takes **α** from the donor-only bursts and **δ** from the acceptor-only
   bursts;
3. splits the doubly labelled bursts into efficiency sub-populations and takes
   **γ** and **β** from the `1/S = Ω + Σ·E` fit across them;
4. repeats the whole thing, because the classification depends on the factors it
   is trying to find. It normally converges in two or three passes.

**The optics are the prior.** γ, α and δ are not free — they follow from the
excitation and emission probabilities of your light path. Pick a saved light
path and its computed probabilities become Gaussian priors: the data moves the
factors away from the optical prediction only as far as it is informative, and a
factor the data cannot identify at all (no donor-only bursts in the file, say)
keeps the optical value *and* the optical uncertainty rather than a fitted
illusion.

**The lifetime does what the E–S fit cannot.** The `1/S`-vs-`E` route needs at
least two populations of different efficiency. A single-species sample does not
identify γ that way — but if you map a donor-lifetime column it does: a static
population has to lie on the **static FRET line**, so

```
γ = (F_DA / F_DD) · (1 − E_line) / E_line ,   E_line = line(⟨τ_D(A)⟩_F)
```

This also works without any acceptor-excitation (ALEX) data. When both routes
are available they should agree — running `gamma from = combined` and comparing
the two numbers in the report is the cheapest consistency check there is.

## The FRET lines

The *static* line is where a structurally homogeneous population must lie: every
molecule at the same mean distance, blurred only by the dye linkers. It is not
the straight `E = 1 − τ/τ_D(0)` diagonal — averaging over the linker
distribution makes the efficiency (which follows the species-averaged lifetime)
drop faster than the measured fluorescence-averaged lifetime, and the line bends
upwards. The *dynamic* line connects two limiting distances the molecule
interconverts between during the burst.

Read the E–lifetime plot like this:

* **on the static line** — static population, calibration consistent;
* **bowed towards the dynamic line** — sub-burst dynamics (the classic
  signature; confirm with BVA or 2CDE);
* **systematically below the static line** — γ is too large (the intensity-based
  efficiency falls as γ grows), or τ_D(0) is wrong.

The *Off static line* column in the population table is exactly that vertical
offset.

## Settings that matter

* **τ_D(0)** — measure it on a donor-only sample. It anchors the line at
  `E = 0`; an error here tilts the entire lifetime-based calibration.
* **Linker width** — sets the curvature of the static line. 6 Å is typical.
* **R0** — affects only the distance, never the efficiency.
* **Background** — subtract it. Uncorrected background biases the low-efficiency
  populations most.
* **Bootstrap resamples** — they produce the factor uncertainties, which are
  used twice: to weigh the data against the optics prior, and to propagate into
  the error bar of every reported efficiency and distance.

## Uncertainties

The reported efficiency error combines the burst statistics with the calibration
systematics, propagated as

```
∂E/∂γ = −E(1−E)/γ,  ∂E/∂α = −(1−E)²/γ,  ∂E/∂δ = −(1−E)²·F_AA/(γ·F_DD)
```

and the distance error follows from `R = R0 (1/E − 1)^{1/6}`:

```
σ_R/R = sqrt( (σ_R0/R0)² + (σ_E / (6·E·(1−E)))² )
```

which is why distances are reliable near `R ≈ R0` and get soft at both ends of
the dynamic range.

## Afterwards

*Share in session* publishes the calibration so any fit can link its correction
parameters to it — one calibration, many datasets. *To ndXplorer* writes the
factors into an open ndXplorer window's MFD constants and recomputes its derived
columns. *Export CSV* writes the per-burst accurate values with the calibration
in the file header, so the numbers stay traceable to how they were produced.

Everything here also runs head-less: `csc accurate-fret --help` for the CLI, or
`chisurf.core.fluorescence.fret.accurate.auto_calibrate` from Python.
