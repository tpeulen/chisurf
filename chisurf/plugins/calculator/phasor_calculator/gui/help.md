# Phasor calculator — where a lifetime lands on the phasor plot

A data-free phasor plot. It draws the **universal semicircle** and the reference
geometry you expect to see in a measurement, at the frequency and harmonic you
choose. Nothing is loaded and nothing is written.

## Reading the plot

- A **single exponential** of lifetime τ sits on the semicircle at
  g = 1/(1+(ωτ)²), s = ωτ/(1+(ωτ)²), with ω = 2π · frequency · harmonic. Short
  lifetimes are on the right, long ones on the left; the apex is ωτ = 1.
- A **mixture** lies inside, on the chord between its components, at the
  position set by the **photon fractions** (the lever rule).
- Two apparent lifetimes are read from any point: τφ = s/(gω) along the
  **iso-phase** ray, τM = √(1/(g²+s²) − 1)/ω along the **iso-modulation** arc.
  They are equal on the circle; inside it τφ < τM.

## The controls

- **Frequency**, **Harmonic** — use the laser repetition rate; the harmonic
  multiplies it. Aim for nωτ ≈ 1 for the lifetimes you want to separate.
- **Lifetimes (ns)** — reference points; their g, s are listed under **Results**.
- **Iso-lifetime grid**, **Lifetime ticks**, **Polar grid** — reading aids.
- **FRET trajectory**, **Donor τ0** — a mono-exponential donor quenched as
  τDA = τD0(1 − E). Real samples with a donor-only fraction fall off it, towards
  the donor-only point.
- **Two-component line**, **g1 s1 g2 s2**, **Mixing region**, **Fraction c1** —
  two component phasors, their chord and the mixture at a photon fraction.
- **Cursor** — a circular gate outline, as used for selecting pixels in
  Pixel Phasor.

## Further reading

- [The phasor calculator guide](docs/guides/77_phasor_calculator.md) — every
  setting, reading the output, and the headless equivalents.
- [FLIM and the phasor approach](docs/concepts/imaging_flim_phasor.md) — the
  transform, harmonics, apparent lifetimes, unmixing and IRF calibration.
- {cite}`digman2008`
