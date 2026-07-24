(concept-anisotropy)=
# Time-resolved fluorescence anisotropy

Fluorescence **anisotropy** measures how the *polarization* of emitted light
decays as a fluorophore rotates. A molecule excited by polarized light emits
partially polarized fluorescence; as it tumbles during its excited-state
lifetime it scrambles that polarization. The rate of this depolarization reports
on **rotational mobility** — the size, shape and local viscosity of the emitter's
environment — a quantity orthogonal to the fluorescence lifetime
({ref}`concept-tcspc-lifetime`). This page explains what the polarized channels
are, how the anisotropy $r(t)$ is built from them, why the **G-factor** matters,
and how the rotational-correlation-time decay maps onto physical volume through
the Perrin equation.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/10_lifetime_anisotropy_fitting`.

## Polarized excitation and detection

A polarized excitation pulse preferentially excites fluorophores whose
absorption dipoles are aligned with the excitation field (*photoselection*).
Immediately after excitation the excited population is therefore anisotropic. Two
detection channels, both after a polarizer, record this:

- **$I_\parallel$ (VV)** — emission polarized *parallel* to the (vertical)
  excitation polarization.
- **$I_\perp$ (VH)** — emission polarized *perpendicular* (horizontal) to it.

The subscripts name the two states of the excitation/emission polarizers, hence
the **VV / VH** convention ChiSurf uses for the two stacked polarized decays. A
third, **magic-angle (VM)** configuration sets the emission polarizer to
$54.7^\circ$, where $I_\parallel$ and $2I_\perp$ contribute equally so the
recorded decay is *free of anisotropy* and gives the pure intensity decay
$I(t)=I_\parallel + 2I_\perp$.

## The anisotropy function and the G-factor

The anisotropy is the normalized difference of the two channels,

$$
r(t) = \frac{I_\parallel(t) - G\,I_\perp(t)}{I_\parallel(t) + 2\,G\,I_\perp(t)}.
$$

The denominator $I_\parallel + 2G I_\perp$ is proportional to the *total*
emitted intensity, so $r$ is dimensionless and independent of concentration and
of the overall decay.

The **G-factor** $G$ corrects for the detection system's intrinsic polarization
bias: gratings, mirrors and detectors do not transmit and detect the two
polarizations equally, so a depolarized (isotropic) source would still give
$I_\parallel \ne I_\perp$. $G = S_\parallel / S_\perp$ is the ratio of the two
channel sensitivities, measured from a reference whose emission is truly
unpolarized (e.g. tail-region emission, horizontally polarized excitation, or a
freely tumbling small dye). Getting $G$ wrong shifts the whole $r(t)$ curve up
or down and biases the recovered $r_0$ and $r_\infty$. ChiSurf additionally
carries two small **channel-mixing** factors $l_1, l_2$ that account for
cross-talk of each polarized channel into the other (imperfect polarizers):

$$
I_{\parallel,\mathrm{m}} = (1-l_1)\,I_\parallel + l_1\,I_\perp, \qquad
I_{\perp,\mathrm{m}}     = l_2\,I_\parallel + (1-l_2)\,I_\perp .
$$

## The fundamental anisotropy $r_0$

At $t=0$, before any rotation, the anisotropy takes its **fundamental** value
$r_0$, set purely by the angle $\theta$ between the absorption and emission
transition dipoles:

$$
r_0 = \frac{2}{5}\left(\frac{3\cos^2\theta - 1}{2}\right).
$$

For collinear dipoles ($\theta = 0$) this gives the theoretical maximum
$r_0 = 0.4$; for perpendicular dipoles ($\theta = 90^\circ$) it reaches its
minimum $-0.2$. Real fluorophores excited near their absorption maximum have
$r_0$ somewhat below $0.4$; ChiSurf's anisotropy group defaults to
$r_0 = 0.38$. $r_0$ sets the amplitude that the rotational decay starts from.

## The rotational-correlation-time decay

As the fluorophore tumbles, $r(t)$ relaxes from $r_0$ toward zero. For a
mixture of rotational modes the decay is a sum of exponentials,

$$
r(t) = \sum_i \beta_i\, e^{-t/\rho_i}, \qquad \sum_i \beta_i = r_0,
$$

where each **rotational correlation time** $\rho_i$ is a depolarization
timescale and $\beta_i$ its amplitude. A single small dye tumbling freely gives
one $\rho$; a dye rigidly attached to a large protein shows a fast $\rho$ (local
wobble of the linker) and a slow $\rho$ (global tumbling of the protein).
ChiSurf stores these as an interleaved rotation spectrum
$[\beta_1, \rho_1, \beta_2, \rho_2, \dots]$, mirroring the lifetime spectrum.

**Hindered rotation.** When the emitter cannot fully randomize — a dye confined
in a membrane or a bound protein sampling only a restricted cone — a fraction of
the initial anisotropy never decays. This residual is modeled by adding a
constant **$r_\infty$** (a $\rho\to\infty$ term):

$$
r(t) = (r_0 - r_\infty)\,e^{-t/\rho} + r_\infty .
$$

The size of $r_\infty/r_0$ measures the cone semi-angle of the restricted
motion (the order parameter), a common readout in membrane and structural work.

## The Perrin equation: $\rho$, volume and viscosity

For a spherical rotor the correlation time is linked to the hydrodynamic volume
$V$ and the solvent viscosity $\eta$ by the **Perrin (Stokes–Einstein–Debye)**
relation,

$$
\rho = \frac{\eta V}{k_\mathrm{B} T} = \frac{1}{6 D_r},
$$

with $D_r$ the rotational diffusion coefficient, $k_\mathrm{B}$ Boltzmann's
constant and $T$ the temperature. Larger, more viscous, or more asymmetric
rotors depolarize more slowly (larger $\rho$). The same physics is often written
for the *steady-state* anisotropy $r$ as the **Perrin equation**,

$$
\frac{r_0}{r} = 1 + \frac{\tau}{\rho} = 1 + \frac{k_\mathrm{B}T\,\tau}{\eta V},
$$

which shows why the interplay of the fluorescence lifetime $\tau$ and the
rotational time $\rho$ governs the measured depolarization: only motions on the
scale of $\tau$ are visible in the anisotropy. ChiSurf reports this
steady-state anisotropy directly from the fitted lifetime and rotation spectra.

## Coupling to the intensity decay (VV/VH combined fit)

The anisotropy cannot be observed on its own — it rides on the intensity decay.
ChiSurf therefore does not fit $r(t)$ in isolation; it reconstructs the two
polarized decays from a *single* magic-angle intensity decay $f_\mathrm{VM}(t)$
(the lifetime spectrum, {ref}`concept-tcspc-lifetime`) and the rotation
spectrum:

$$
f_\parallel(t) = f_\mathrm{VM}(t)\,\big(1 + 2\,r(t)\big), \qquad
f_\perp(t)     = f_\mathrm{VM}(t)\,\big(1 - G\,r(t)\big).
$$

Both channels are then reconvolved with the IRF and compared to the measured
VV and VH histograms in **one combined fit**, with the lifetimes shared (linked)
across the two channels and the calibration parameters $G$, $l_1$, $l_2$ held
in common. Fitting the two polarizations jointly — rather than forming the noisy
ratio $r(t)$ and fitting that — keeps the Poisson statistics correct and lets
short $\rho_i$ shorter than the IRF width be recovered from the *shape*
difference between the channels. ChiSurf supports both a single stacked
`vv/vh` dataset and a linked two-fit group (`vv` + `vh`).

## See also

- Guide: {doc}`/guides/10_lifetime_anisotropy_fitting`; the intensity decay it
  rides on: {ref}`concept-tcspc-lifetime`.
- Implementation: polarized-decay kernels
  `chisurf/core/fluorescence/anisotropy/` (`decay.py` builds VV/VH from the
  magic-angle decay and the rotation spectrum; `integrals.py`, `kappa2.py`);
  anisotropy parameter group and combined-fit model
  `chisurf/core/models/tcspc/anisotropy.py` and
  `chisurf/core/models/tcspc/lifetime.py`.
- Reference: J. R. Lakowicz, *Principles of Fluorescence Spectroscopy*
  (3rd ed., 2006), anisotropy chapters (steady-state and time-resolved
  anisotropy, the Perrin equation, hindered rotors).
