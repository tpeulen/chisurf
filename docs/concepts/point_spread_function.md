---
type: Concept
title: 'The point-spread function: what a focused lens actually makes'
description: The image of a point source through a microscope objective, from the scalar Airy pattern to the vectorial Richards–Wolf focus, and why the textbook widths are wrong by 10–30 % at the numerical apertures people use.
tags: [concepts, imaging, optics, resolution]
anchor: concept-point-spread-function
---

(concept-point-spread-function)=
# The point-spread function: what a focused lens actually makes

The point-spread function (PSF) is the intensity a lens produces from a point
source. Every fluorescence measurement uses one: an image is the object convolved
with it, an FCS focal volume is built from it, and deconvolution, ISM
reassignment and localisation all need a model of it. The usual model is a
formula such as 0.51 λ/NA. At an NA of 1.4 that formula is optimistic by about
10 % even in the best case, and it cannot express the fact that the focus of
linearly polarized light is 40 % longer in one direction than in the other.

For the workflow, see {doc}`the PSF calculator guide </guides/72_psf_calculator>`.

## Definition

For incoherent emitters, such as fluorophores, intensities add. The image
$g$ of an object $f$ is then the object convolved with the intensity PSF $h$,

$$g(\mathbf{r}) = \int f(\mathbf{r}')\, h(\mathbf{r} - \mathbf{r}')\, d^3 r',$$

provided $h$ does not change across the field of view (shift invariance). $h$ is
three-dimensional. Its lateral cross-section sets the lateral resolution and its
extent along the optical axis sets the axial resolution. A confocal microscope
multiplies an excitation PSF by a detection PSF
{cite}`sheppard1977`; the calculator computes a single focus, which is either
of those two factors.

Three quantities fix the focus: the wavelength λ, the immersion index $n$ and the
numerical aperture $\mathrm{NA} = n \sin\alpha$, where α is the half-angle of the
cone of light the lens accepts. NA cannot exceed $n$.

## The scalar focus: the Airy pattern

When the field is treated as a scalar, a uniformly illuminated circular aperture
gives an in-focus intensity {cite}`airy1835,bornwolf1999`

$$h(v) = \left[\frac{2 J_1(v)}{v}\right]^2, \qquad v = \frac{2\pi}{\lambda}\,\mathrm{NA}\, r,$$

with $J_1$ the first-order Bessel function. Three numbers follow directly:

| Feature | Where | Distance |
| --- | --- | --- |
| Half maximum | $v = 1.616$ | FWHM $= 0.514\,\lambda/\mathrm{NA}$ |
| First zero | $v = 3.832$ | $r = 0.610\,\lambda/\mathrm{NA}$ |
| Energy inside the first zero | $1 - J_0^2 - J_1^2$ at $v = 3.832$ | 83.8 % |

Two points are "just resolved" under Rayleigh's criterion when one maximum falls
on the other's first zero, so the Rayleigh distance is $0.61\,\lambda/\mathrm{NA}$
{cite}`rayleigh1879`. Abbe's $\lambda/(2\mathrm{NA})$ {cite}`abbe1873` is a
different quantity: the finest grating period an objective transmits. The FWHM,
the Rayleigh distance and the Abbe period are three different conventions. They
differ by 20 % between them, so a quoted resolution should say which one it is.

Along the optical axis, a uniform spherical wave converging with half-angle α
gives

$$h(0, z) = \mathrm{sinc}^2\!\left[\frac{\pi n z (1 - \cos\alpha)}{\lambda}\right],
\qquad \mathrm{FWHM}_z = \frac{0.886\,\lambda}{n - \sqrt{n^2 - \mathrm{NA}^2}},$$

where $\mathrm{sinc}\,x = \sin x / x$. This is the axial formula quoted in bead-PSF
protocols {cite}`cole2011`. The textbook paraxial form $1.77\, n\lambda/\mathrm{NA}^2$ is its
small-angle limit. At NA 1.4 in oil the paraxial form gives 713 nm, against
495 nm from the formula above. The paraxial form should therefore not be used
for an immersion objective.

## The Gaussian approximation

A Gaussian with $\sigma \approx 0.21\,\lambda/\mathrm{NA}$ matches the core of the
Airy pattern closely {cite}`zhang2007` and is what most simulations use. It has
no rings. Beyond the Airy first zero a Gaussian of the same FWHM holds 1.6 % of
its energy, while the Airy pattern holds 16.2 %. That tenfold difference is
where out-of-focus background and crosstalk between neighbouring detector
elements come from, so a background estimated with a Gaussian PSF inherits the
error.

## The vectorial focus: Richards–Wolf

The scalar model assumes the field stays transverse. An aplanatic lens bends each
ray towards the focus, and the field bends with it: a ray arriving at angle θ
carries a field component along the optical axis proportional to $\sin\theta$.
At NA 0.3 this component is negligible. At NA 1.4 in oil (α = 67°) it is not.
Wolf wrote the focal field as an integral over the angular spectrum leaving the
lens {cite}`wolf1959`, and Richards and Wolf evaluated it for an aplanatic
system {cite}`richards1959` (a modern derivation is in
{cite}`novotny2012`). For light polarized along $x$ in the pupil,

$$E_x \propto I_0 + I_2 \cos 2\phi, \qquad E_y \propto I_2 \sin 2\phi, \qquad
E_z \propto -2i\, I_1 \cos\phi,$$

$$I_m = \int_0^\alpha \sqrt{\cos\theta}\, \sin\theta\, g_m(\theta)\,
J_m(k r \sin\theta)\, e^{i k z \cos\theta}\, d\theta,$$

with $g_0 = 1 + \cos\theta$, $g_1 = \sin\theta$, $g_2 = 1 - \cos\theta$,
$k = 2\pi n/\lambda$ and $\alpha = \arcsin(\mathrm{NA}/n)$. The $\sqrt{\cos\theta}$
factor is the aplanatic apodization, which conserves energy through the lens.
The PSF is $|E_x|^2 + |E_y|^2 + |E_z|^2$. As NA/$n$ falls, $I_1$ and $I_2$
vanish, $I_0$ tends to the Airy amplitude and the vectorial PSF converges to
the scalar one.

## Polarization changes the focus

In the scalar model the input polarization plays no role. In the vectorial
model it changes the shape of the focus:

* **Linear.** $E_z$ has two lobes on either side of the axis, *along* the
  polarization direction ($\cos\phi$), and the $I_2$ term adds to the
  asymmetry. The focus is elongated along the polarization axis.
* **Circular**, and **unpolarized** (an incoherent sum of two orthogonal
  linear states), give the same rotationally symmetric intensity. The
  elongations of the two linear states average out, and the width lies
  between their two widths.
* **Radial.** Every ray's field lies in its meridional plane, so the axial
  components of all rays add in phase on the axis and form a strong central
  $E_z$ lobe. The transverse field is a ring. For a uniformly filled pupil
  {cite}`youngworth2000`,

  $$E_r \propto \int_0^\alpha \sqrt{\cos\theta}\,\sin 2\theta\,
  J_1(kr\sin\theta)\,e^{ikz\cos\theta}\,d\theta,\qquad
  E_z \propto 2i \int_0^\alpha \sqrt{\cos\theta}\,\sin^2\theta\,
  J_0(kr\sin\theta)\,e^{ikz\cos\theta}\,d\theta.$$

  The $E_z$ lobe alone is narrower than any linear focus, but the transverse
  ring widens the total intensity. The radial focus beats the linear one
  only when an annular aperture removes the low-angle rays that feed the
  ring: 0.16 λ² against 0.26 λ² at NA 0.9. Over the full aperture, at the same
  NA, the radial spot is *larger* than the linear one {cite}`quabis2000,dorn2003`.
* **Azimuthal.** The field is tangential for every ray. It has no axial
  component at any NA and vanishes on the axis, which gives a doughnut with an
  exact zero in the centre {cite}`youngworth2000,zhan2009`.

## What ChiSurf computes

Measured with `PSFModel` at λ = 520 nm, NA 1.4, $n$ = 1.518, on a 10 nm × 25 nm
grid with the Full quadrature. The widths are FWHM, interpolated at the
half-maximum crossings.

| Model / pupil state | FWHM $x$ | FWHM $y$ | FWHM $z$ |
| --- | --- | --- | --- |
| Airy (scalar), formula $0.514\,\lambda/\mathrm{NA}$ | 191 nm | 191 nm | — (repeated along $z$) |
| Gaussian, FWHM set to $0.5\,\lambda/\mathrm{NA}$ | 186 nm | 186 nm | see below |
| Vectorial, circular / unpolarized / linear at 45° | 210 nm | 210 nm | 510 nm |
| Vectorial, linear $x$ | 250 nm | 179 nm | 510 nm |
| Vectorial, radial | 181 nm (see warning) | 181 nm | 541 nm |
| Vectorial, azimuthal | doughnut: centre 0.6 % of the ring peak | | |

The circular focus is 10 % wider than 0.514 λ/NA. The linear focus is 40 %
longer along the polarization than across it. These are the two numbers the
scalar formula cannot give. At lower NA the vectorial result converges on
the scalar formulae:

| NA, medium | lateral: vectorial vs $0.514\,\lambda/\mathrm{NA}$ | axial: vectorial vs $0.886\,\lambda/(n-\sqrt{n^2-\mathrm{NA}^2})$ |
| --- | --- | --- |
| 0.3, air | 899 vs 892 nm | 10 004 vs 10 003 nm |
| 0.9, air | 324 vs 297 nm | 837 vs 817 nm |
| 1.2, water | 244 vs 223 nm | 625 vs 609 nm |
| 1.4, oil | 210 vs 191 nm | 510 vs 495 nm |

These widths are for one focus. A confocal PSF is narrower, because it is the
product of the excitation and detection foci. Bead measurements through a 1.4 NA
objective scatter around 230–245 nm laterally {cite}`cole2011`, which is what a
~210 nm excitation focus becomes once the bead size, the pinhole and aberrations
are added.

:::{warning}
Two of the calculator's models are wrong in one respect each, and both errors
come from the TTTR library's `psf_volume`:

* **Radial.** The longitudinal term is weighted twice as strongly as in the
  integrals above, which makes the radial focus look *tighter* than the
  circular one (181 against 210 nm). A direct numerical Debye integral over the
  pupil gives 241 nm for radial and 209 nm for circular. This agrees with the
  full-aperture result of {cite}`dorn2003`. The linear and circular results
  match the same check to within 1 nm.
* **Gaussian, axial.** The envelope $1/(1 + (z/z_R)^2)$ uses
  $z_R = \pi\sigma^2 n/\lambda$. That is a quarter of the Rayleigh range of a
  Gaussian beam with waist $w_0 = 2\sigma$, so the Gaussian's axial FWHM
  (117 nm at NA 1.4) is about four times too short. Use the Gaussian for its
  lateral profile only.
:::

## Sampling

An incoherent imaging system transmits no spatial frequency above
$2\mathrm{NA}/\lambda$ laterally or above $(n - \sqrt{n^2-\mathrm{NA}^2})/\lambda$
axially. By the sampling theorem {cite}`nyquist1928,shannon1949`, pixels no
larger than

$$\Delta x = \frac{\lambda}{4\,\mathrm{NA}}, \qquad
\Delta z = \frac{\lambda}{2\,(n - \sqrt{n^2 - \mathrm{NA}^2})}$$

capture everything the lens passes: 93 nm and 279 nm at NA 1.4 and 520 nm
{cite}`pawley2006`. Reading a *width* off a sampled profile needs finer
sampling than that. Bead protocols use about a third of the FWHM
{cite}`cole2011`, and the calculator's defaults (30 nm, 100 nm) are finer
still. The summary interpolates the half-maximum crossings, so the width it
reports does not snap to the pixel grid.

## See also

- Guide: {doc}`/guides/72_psf_calculator`. What the PSF means for a measured
  image: {ref}`concept-frc-resolution`.
- Implementation: the model and the reported widths,
  {src}`chisurf/plugins/calculator/psf_calculator/core.py#PSFModel`; the optics
  are the TTTR library's `CLSMSuperRes.psf_volume`.
- Tools in ChiSurf: **PSF calculator** (Calculators hub,
  `chisurf/plugins/calculator/psf_calculator/`).

## References

- {cite}`airy1835`, {cite}`bornwolf1999`: the scalar focus, in focus and
  along the axis.
- {cite}`rayleigh1879`, {cite}`abbe1873`: the two classical resolution
  conventions.
- {cite}`zhang2007`: Gaussian approximations to the PSF and how far they hold.
- {cite}`wolf1959`, {cite}`richards1959`, {cite}`novotny2012`: the vectorial
  focus of an aplanatic lens.
- {cite}`youngworth2000`, {cite}`quabis2000`, {cite}`dorn2003`,
  {cite}`zhan2009`: radially and azimuthally polarized foci.
- {cite}`cole2011`, {cite}`pawley2006`, {cite}`shaw1991`: measuring a PSF on
  a real microscope, and sampling it.
- {cite}`nyquist1928`, {cite}`shannon1949`: the sampling theorem.
