# Time-resolved anisotropy

Sets up a **linked VV/VH global fit**: two polarisation-resolved decays, fitted
together with one shared lifetime spectrum and one shared rotational spectrum.

The wizard exists because the corrections between "two measured decays" and "an
anisotropy" are where the answer is usually lost — and none of them announces
itself in the fit statistic.

Press **Guide** for the walk-through.

## What is measured, and what is fitted

Excite with vertically polarised light and detect through a polariser: **VV**
(parallel) and **VH** (perpendicular). Immediately after the pulse the excited
molecules are photoselected along the excitation axis, so VV exceeds VH; as they
rotate, the two converge. The anisotropy

**r(t) = (I_VV − G·I_VH) / (I_VV + 2·G·I_VH)**

decays from the fundamental anisotropy r₀ with the rotational correlation
time(s).

**ChiSurf does not fit r(t).** It fits VV and VH *themselves*, linked — because
forming the ratio first propagates noise in a way that is difficult to weight
correctly, and destroys the Poisson statistics the fit relies on. The shared
parameters are the lifetime spectrum and the rotational spectrum; the two decays
differ only through the polarisation algebra.

## The corrections, in the order they bite

**g = S_VV/S_VH** is the instrument's *detection* bias between the two
polarisations — gratings and detectors are not polarisation-neutral. It
multiplies I_VH throughout, so **g scales r(t) as a whole**: a 10 % error in g is
roughly a 10 % error in every anisotropy you report, including r₀. Measure it
(tail-matching on a fast-rotating dye, or horizontal excitation), do not assume
1.0.

**l1 and l2** are the channel-mixing (depolarisation) factors of a
high-aperture objective. A large collection angle mixes the two polarisations
geometrically, which **compresses** the measured anisotropy toward zero. Leaving
them at 0 on a high-NA setup reports a smaller r₀ and a smaller amplitude than
the sample has. The mixing model is that of Koshioka, Sasaki and Masuhara
(1995); Schaffer et al. (1999) use it with the g convention above for
single-molecule MFD, and Erdelyi et al. (2014) for TIRF anisotropy imaging.

**Background matters more here than in a plain lifetime fit.** Background is
unpolarised, so it enters VV and VH equally and pulls their *ratio* toward 1 —
i.e. toward zero anisotropy — and it does so most severely in the tail, exactly
where the slow rotation lives. The *Normalize IRF* step subtracts a background
region you pick and intensity-matches the two IRFs, which is why it is a step of
its own rather than a checkbox. With two separate detectors (as on a
microscope) the IRFs must be normalized to the same total photon number after
background removal. The model is convolved with the IRF, so changing the IRF
also changes the number of photons in the model.

## Reading the result

**r₀** should come out near the theoretical 0.4 for a collinear absorption and
emission dipole, and below it for a real dye. A fitted r₀ **well above 0.4** is
not a discovery; it is a g-factor or a background error.

**Rotational correlation times** relate to volume through the Stokes–Einstein–
Debye relation ρ = ηV/kT. A protein of 30 kDa in water at 20 °C rotates in
roughly 10 ns, so a rotation much slower than the fluorescence lifetime is
**invisible** — the molecules have not turned appreciably before they stop
emitting, and the fit reports it as a constant offset rather than a decay.

That is the honest limit of the method: the accessible rotation window is set by
the lifetime. A long-lived probe buys slower rotations; nothing else does.

## Before believing the numbers

- **Was g measured, or left at 1?** It scales everything.
- **Are l1/l2 appropriate to the objective?** Zero is right only for a low-NA
  setup.
- **Was the background region picked in a genuinely dark part of the record?**
  A region containing signal subtracts signal.
- **Is r₀ physically possible?** Above 0.4 means a correction is wrong.
- **Is the slow component slower than the lifetime?** If so it is not measured,
  it is extrapolated.
- **Do VV and VH share the same IRF timing?** A shift between the two channels
  mimics a fast rotational component.

## Further reading

Original papers:

- [10.1366/0003702953963652](https://doi.org/10.1366/0003702953963652) —
  M. Koshioka, K. Sasaki, H. Masuhara, *Time-dependent fluorescence
  depolarization analysis in three-dimensional microspectroscopy*, Appl.
  Spectrosc. **49**, 224 (1995): the l1/l2 channel mixing of a high-NA objective.
- [10.1371/journal.pone.0100526](https://doi.org/10.1371/journal.pone.0100526) —
  M. Erdelyi, J. Simon, E. A. Barnard, C. F. Kaminski, *Analyzing receptor
  assemblies in the cell membrane using fluorescence anisotropy imaging with
  TIRF microscopy*, PLoS ONE **9**, e100526 (2014).
- [10.1021/jp9833597](https://doi.org/10.1021/jp9833597) — J. Schaffer et al.,
  *Identification of single molecules in aqueous solution by time-resolved
  fluorescence anisotropy*, J. Phys. Chem. A **103**, 331 (1999): the g = S_VV/S_VH
  convention with the l1/l2 correction.

In the ChiSurf documentation:

- [Fluorescence anisotropy](docs/concepts/anisotropy.md) — theory, r₀, rotors.

- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md)
- [Lifetime and anisotropy fitting](docs/guides/10_lifetime_anisotropy_fitting.md)
  — the step-by-step workflow.
- [The VV/VH stacked decay format](okf/references/vv-vh-decay-format.md)
- [Background rates](docs/guides/15_background_rates.md) — measuring the
  background this step subtracts.
