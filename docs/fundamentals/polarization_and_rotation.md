(fundamentals-polarization)=
# Photoselection, depolarization, and rotation

The transition dipole makes absorption and emission directional. Polarized
excitation therefore selects an oriented sub-population, and anything that
scrambles that orientation before emission shows up as depolarization. This page
covers where the anisotropy limits come from and what can depolarize besides
rotation. The measurement itself — polarized channels, the G-factor, the fitted
decay model — is in {ref}`concept-anisotropy`.

## Photoselection sets the ceiling at 0.4

The probability that a molecule absorbs vertically polarized light goes as
$\cos^2\theta$, with $\theta$ the angle between its absorption dipole and the
excitation polarization. An isotropic ground-state population supplies molecules
at angle $\theta$ in proportion to $\sin\theta\,\mathrm{d}\theta$, so the excited
population is distributed as $\cos^2\theta\sin\theta\,\mathrm{d}\theta$.

Averaging over that distribution gives $\langle\cos^2\theta\rangle = 3/5$, and
with $r = (3\langle\cos^2\theta\rangle - 1)/2$ the anisotropy of a frozen,
colinear emitter is $r = 2/5$. This is the origin of the familiar ceiling: a
single-photon experiment on a randomly oriented sample cannot exceed
$r_0 = 0.4$, however rigid the sample. A single molecule aligned with the
excitation axis would give $r = 1$; the loss to $0.4$ is the price of averaging
over an isotropic ground state.

If the absorption and emission dipoles are displaced by an angle $\beta$, the
same kernel applies a second time:

$$
r_0 = \frac{2}{5}\left(\frac{3\cos^2\beta - 1}{2}\right).
$$

So $r_0 = 0.4$ at $\beta = 0$, passes through zero at the magic angle
$\beta = 54.7^\circ$, and reaches $-0.20$ at $\beta = 90^\circ$. For one-photon
excitation $r_0$ therefore lies in $[-0.20, 0.40]$, and it is a function of
excitation wavelength, because different absorption bands have differently
oriented dipoles. Most practical dyes sit somewhat below 0.4 — partly from a
non-zero $\beta$, partly because more than one electronic transition contributes
at the excitation wavelength.

Two things follow directly. A measured anisotropy above 0.4 is not a very rigid
sample; it is scattered excitation light in the detection channel, which has
$r \approx 1$. And an $r_0$ taken from the literature applies at the excitation
wavelength it was measured at, so it is not transferable between setups without
checking.

## Rotational diffusion

Rotation during the excited-state lifetime randomizes the emission dipole and
reduces the anisotropy. For a sphere the decay is exponential with rotational
correlation time $\rho$ (ChiSurf writes $\rho$; much of the literature writes
$\theta$ — see {ref}`fundamentals-conventions`), and the steady-state anisotropy
is the intensity-weighted average of $r(t)$ over the decay. For a single
exponential intensity decay this gives the Perrin equation {cite}`perrin1926`,

$$
r = \frac{r_0}{1 + \tau/\rho},
$$

usually plotted in the linearized form $r_0/r = 1 + \tau/\rho$.

The competition between $\tau$ and $\rho$ is the whole sensitivity argument. If
$\rho \gg \tau$ the molecule barely moves before emitting and $r \to r_0$; if
$\rho \ll \tau$ it randomizes completely and $r \to 0$. Anisotropy only reports
on motions whose timescale is comparable to the lifetime, which is why the probe
is chosen for its lifetime rather than its brightness when rotation is the
observable.

For a hydrated sphere $\rho = \eta V/(k_B T)$ — larger volume or higher
viscosity means slower depolarization. Measured correlation times of proteins
are routinely about twice the value calculated for an anhydrous sphere, because
proteins are neither anhydrous nor spherical. Treat a volume derived this way as
an order-of-magnitude statement.

```{figure} /guides/figures/perrin.png
:alt: anisotropy decays and the Perrin sensitivity curve
:width: 100%

Left: $r(t)$ for three correlation times and one restricted case that plateaus at
$r_\infty$. Right: the Perrin steady-state anisotropy against $\tau/\rho$.
Anisotropy only reports on motion in the shaded decade either side of the
lifetime — outside it the measurement saturates at $r_0$ or at zero.
```

## What else depolarizes

Rotation is the intended mechanism. Several others contribute, and each has a
different signature:

- **Scattered excitation light.** Nearly fully polarized, $r \approx 1$. It
  raises the apparent anisotropy, particularly at early times and in the blue.
- **Energy transfer between identical fluorophores** (homo-FRET). Each transfer
  step re-randomizes the emission dipole, so anisotropy falls without any
  physical rotation. This is concentration-dependent and is the reason
  fundamental anisotropies must be measured on optically dilute samples.
- **Radiative reabsorption and re-emission.** Same effect, same cause — a small
  Stokes shift and a concentrated sample.
- **Local probe motion.** A dye on a flexible linker wobbles within a cone much
  faster than the biomolecule tumbles. This produces a fast $\rho$ carrying part
  of the amplitude, and it is the dominant term for the linker-attached dyes
  used in FRET work.

The last point is why a two-component anisotropy decay with a fast local term
and a slow global term is the normal result for a labelled protein, and why the
*residual* anisotropy $r_\infty$ — the amplitude that never decays on the
lifetime timescale — is the quantity that reports how restricted the dye is.

## Residual anisotropy, the cone, and $\kappa^2$

A dye that samples only part of the orientational sphere cannot depolarize
completely. The residual $r_\infty$ measures how much of the orientation
survives, and it is conventionally expressed as an order parameter
$S^2 = r_\infty/r_0$: fully free gives $S^2 = 0$, fully rigid gives $S^2 = 1$.
For the common cone model, $S^2$ maps onto a cone half-angle.

This is the direct link between anisotropy and FRET accuracy. The usual
assumption $\kappa^2 = 2/3$ requires that both dyes randomize their orientation
within the excited-state lifetime. The residual anisotropies of the donor and
acceptor are the experimental evidence for or against that assumption, and they
are what bound the possible range of $\kappa^2$ and hence the systematic
distance error ({ref}`fundamentals-energy-transfer`). Measuring anisotropy in a
FRET experiment is not a separate study — it is the control that makes the
distance meaningful. ChiSurf computes the $\kappa^2$ bounds from residual
anisotropies directly ({src}`chisurf/core/fluorescence/anisotropy/kappa2.py#s2delta`).

## See also

- Previous: {ref}`fundamentals-quenching`. Next:
  {ref}`fundamentals-energy-transfer`.
- Concepts: {ref}`concept-anisotropy` (channels, G-factor, fitted model) ·
  {ref}`concept-mfd-fitting` · {ref}`concept-accessible-volume`.
- Implementation: {src}`chisurf/core/fluorescence/anisotropy/__init__.py#r_exp` ·
  {src}`chisurf/core/fluorescence/anisotropy/kappa2.py#s2delta`.
- Literature: {cite}`perrin1926` for the depolarization relation;
  {cite}`dale1979` for bounding $\kappa^2$ from measured depolarization;
  {cite}`lakowicz2006`, anisotropy chapters.
