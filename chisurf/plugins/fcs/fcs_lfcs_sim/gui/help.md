# Lifetime-FCS simulator

A sandbox for filtered FCS (FLCS): it simulates two diffusing species with
different fluorescence lifetimes, builds the lifetime filters from their decays,
and correlates the weighted photon streams — so you can see what the species
auto- and cross-correlations look like **when you already know the answer**.

That is the point of it. On real data the filtered curves are the result; here
they are a prediction you can check, which is the only way to learn what a
believable one looks like.

Press **Guide** for the walk-through.

## What is simulated

Molecules diffuse through a 3-D Gaussian focus (w₀ = 0.3 µm) and emit photons
whose micro-times follow their species' exponential decay. Each species has its
own **lifetime** and its own **diffusion coefficient**, and may interconvert with
the other at a symmetric rate.

The diffusion time follows from the waist:

**τ_D = w₀² / (4·D)**

so with the defaults — D₁ = 8 µm²/ms and D₂ = 0.5 µm²/ms — the two species pass
through the focus in **2.8 µs** and **45 µs**. That 16-fold separation is chosen
to make the demo unambiguous; by Stokes–Einstein it is a 16-fold difference in
hydrodynamic radius, which is a much bigger difference than most real pairs.

## What the filters do, and what they cannot do

Every photon carries a micro-time. Given each species' normalised decay, a
photon's micro-time says something — not everything — about which species emitted
it, and the filter is the weight that makes the weighted correlation come out
right *on average*. Correlating the weighted streams then gives the curves you
would have measured if you could have detected each species separately.

**Filtered FCS adds no information. It redistributes it.** The photons are the
same photons; the filters only reallocate them, and the price is noise. Species
curves are always noisier than the raw autocorrelation of the same measurement,
and the more similar the two decays, the more aggressive the filters and the
worse the noise. There is no setting that avoids this.

**The condition number is the number that decides whether any of it is real.**
It is printed after every run, and it measures how nearly degenerate the two
reference decays are. Small — a few — means the decays are genuinely different
and the separation is well posed. Large means the filter matrix is close to
singular: the "separated" curves are then dominated by amplified noise, and they
will still *look* like correlation curves. Watch it move as you bring τ₂ toward
τ₁; that experiment takes ten seconds here and is the intuition to carry to real
data.

## Isolating exchange

With `k = 0` the species are static and each autocorrelation shows only its own
diffusion.

With `k > 0` a molecule can change species while it crosses the focus, and the
signature is in the **cross-correlation**: it becomes *anti*-correlated on the
exchange timescale, because a photon counted towards one species is followed by
photons counted towards the other.

To see that cleanly, **set the two diffusion coefficients equal**. Otherwise the
cross-correlation mixes the exchange with the difference in diffusion time and
the two are hard to tell apart — which is exactly the confusion that makes this
measurement hard on real samples.

## Before believing a filtered curve — here or on real data

- **Check the condition number first.** Everything else is conditional on it.
- **Reference decays must be the right ones.** The filters are only as good as
  the patterns they are built from. Here they are exact by construction; on real
  data they come from separate measurements, and any mismatch — a different
  buffer, a shifted IRF, a slightly different lifetime — biases every species
  curve without making the fit look worse.
- **A cross-correlation is not automatically exchange.** Imperfect filters leak
  one species into the other's channel and produce cross-correlation with no
  kinetics at all. Distinguish them by the shape: leakage looks like the
  autocorrelation, exchange is anti-correlated on its own timescale.
- **Raise the photon budget before believing structure.** A feature that
  disappears when you double the photons was noise.

## Further reading

- [Filtered FCS and 2D-FLCS](docs/concepts/filtered_fcs.md) — the filter
  derivation, F = (DᵀWD)⁻¹DᵀW, and the condition number.
- [Filtered FCS, step by step](docs/guides/17_filtered_fcs.md)
- [FCS correlation](docs/concepts/fcs_correlation.md) — where τ_D comes from.
- [Diffusion by FCS](docs/guides/09_diffusion_fcs.md)
- [Simulating TTTR data](docs/guides/18_tttr_simulation.md) — the engine underneath.
- Böhmer, Wahl, Rahn, Erdmann & Enderlein, *Time-resolved fluorescence
  correlation spectroscopy*, *Chem. Phys. Lett.* **353**, 439 (2002),
  [10.1016/S0009-2614(01)01470-X](https://doi.org/10.1016/S0009-2614(01)01470-X)
- Felekyan, Kalinin, Sanabria, Valeri & Seidel, *Filtered FCS*,
  *ChemPhysChem* **13**, 1036 (2012),
  [10.1002/cphc.201100897](https://doi.org/10.1002/cphc.201100897)
