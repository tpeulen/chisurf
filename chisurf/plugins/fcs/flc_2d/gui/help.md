# 2D-FLCS — lifetime–lifetime correlation maps

Ordinary FCS correlates the *total* intensity, so two species that diffuse at the
same rate are one curve. Filtered FCS separates them — but only if you already
know their decay patterns.

**2D-FLCS** (Ishii & Tahara 2013) drops that requirement. At a chosen macro-time
lag it measures the **joint distribution of the micro-time of the first photon
and the micro-time of the second**, then inverts that 2-D decay-correlation
matrix into a map over *pairs* of lifetimes. Nothing has to be known in advance,
and no second detector, colour or polarisation is needed.

Press **Guide** for the walk-through. It runs on a stream this tool simulates
itself, so you can walk it with no data of your own — and check the answer,
because you set it.

## What the map says

- **Diagonal peaks** (τ₁ = τ₂) — a species that still had the same lifetime one
  lag later. Static heterogeneity.
- **Off-diagonal peaks** — a molecule that **changed** lifetime state during the
  lag. Dynamic exchange.

The diagonal is essentially the ordinary lifetime distribution. The information
that is *only* in this map is off the diagonal, and how it grows with the lag is
the kinetics.

## The lag is the question you are asking

`lag` (dT) and `win` (ddT, its half-width) select which photon pairs are
histogrammed. **A lag far below the exchange time shows no cross-peaks**, because
almost nothing has interconverted yet; a lag far above it shows the cross-peaks
saturated, since the pair has forgotten which state it started in. Neither is
wrong — they are different questions — but a single lag is never an answer about
kinetics. **Build the map at several lags and watch the cross-peaks grow.**

A wider window buys photon pairs at the cost of lag resolution. On a real
measurement that trade is usually worth taking; the map is starved of pairs long
before it is starved of resolution.

## The inversion is ill-posed, and that is the whole difficulty

Recovering a lifetime distribution from a decay is an inverse Laplace transform:
many quite different distributions fit the data about equally well, and noise
decides between them. Everything under *Lifetime inversion* is about how that is
constrained.

**Method.** *Tikhonov* is closed-form and fastest. *NNLS* enforces strict
non-negativity and is the default. *MEM* (maximum entropy) is the most faithful
to what the data actually support — it will not sharpen a peak the data do not
justify — and the slowest.

**log λ** is the regularisation weight. Leave it at **0** to have it chosen
automatically from the **L-curve**: plot residual against solution norm on log-log
axes and take the corner, the point past which buying a smaller residual costs a
disproportionate amount of structure. Look at that panel. If there is no clear
corner, the data do not determine the answer and a hand-picked λ is a decision
you are making, not one the data made.

**Peak width is not a measurement.** A regularised inversion controls how sharp a
peak may be, so the *width* of a lifetime peak reports the regularisation at
least as much as the sample. Read positions and areas; do not read widths.

## The IRF decides the short lifetimes

Below roughly a nanosecond, most of what you are fitting **is** the instrument
response. A wrong IRF does not produce a bad fit — it produces a good fit to the
wrong lifetime.

*Synthetic* builds a Gaussian pulse from the centre, FWHM and skew you give it;
*Detect* places one at the decay's own prompt rise; *File* uses a measured IRF
(📈 **IRF**); *None* tail-fits without one, which is honest only if every lifetime
of interest is much longer than the pulse. The **rise** toggle scans the IRF
position during the 1D-MEM and averages around the optimum, which trades a little
resolution for a much smaller timing systematic.

## The demo, and its known answer

The *Simulator* panel generates a two-state exchanging stream: τ₁ and τ₂, the two
rates, a brightness and an acquisition time. With the defaults —
τ = 1 and 3 ns, k₁₂ = 30 s⁻¹, k₂₁ = 10 s⁻¹ — the answers are fixed before you
press anything:

- equilibrium populations **0.25 / 0.75** (p₁ = k₂₁/(k₁₂+k₂₁)),
- relaxation time **1/(k₁₂+k₂₁) = 25 ms**.

So a map built at the default 1 ms lag *should* be almost pure diagonal — 1 ms is
1/25 of the exchange time. Raise the lag toward 25 ms and the cross-peaks appear.
That is the check worth doing once on data whose answer you know, before doing it
on data whose answer you do not.

## Before believing the result

- **The residual map must be structureless noise.** Structure in it means the
  model did not describe the data, and every peak position in the map is then
  suspect.
- **Equal-brightness states are ill-conditioned.** The inversion separates states
  by decay shape; two states of the same brightness and similar lifetime are close
  to degenerate, and the *global multi-lag MEM* is explicitly marked advanced for
  that reason.
- **A single lag says nothing about kinetics.** See above.
- **The species correlation is the cross-check.** Once the lifetimes are
  resolved, the filtered species auto- and cross-correlations must show the
  two-state signature: autocorrelations decaying and the cross-correlation
  *anti*-correlated, both with the same relaxation rate k = k₁₂ + k₂₁. If they do
  not, the map's peaks are not two exchanging states.

## Further reading

- [Filtered FCS and 2D-FLCS](docs/concepts/filtered_fcs.md) — the derivation, in full.
- [Filtered FCS, step by step](docs/guides/17_filtered_fcs.md)
- [FCS correlation](docs/concepts/fcs_correlation.md) — what the lag axis means.
- [TCSPC and fluorescence lifetimes](docs/concepts/tcspc_lifetime.md) — why the IRF matters.
- Ishii & Tahara, *Two-dimensional fluorescence lifetime correlation
  spectroscopy* (parts 1 & 2), *J. Phys. Chem. B* **117**, 11414 & 11423 (2013),
  [10.1021/jp406861u](https://doi.org/10.1021/jp406861u)
- Böhmer, Wahl, Rahn, Erdmann & Enderlein, *Chem. Phys. Lett.* **353**, 439
  (2002), [10.1016/S0009-2614(01)01470-X](https://doi.org/10.1016/S0009-2614(01)01470-X)
