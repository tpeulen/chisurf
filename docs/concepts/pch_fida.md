(concept-pch-fida)=
# Photon-counting histogram (PCH) and FIDA

Where FCS reads the *time structure* of intensity fluctuations, the
**photon-counting histogram (PCH)** and **fluorescence-intensity distribution
analysis (FIDA)** read their *amplitude* structure: how often a fixed sampling
interval collects exactly $k$ photons. That single histogram $P(k)$ separates
two quantities that a mean intensity trace, and even the FCS amplitude, cannot
disentangle on their own — the **molecular brightness** $\epsilon$ (counts per
molecule per second, "cpm") and the **number of molecules** $N$ in the
detection volume. Brightness is the fingerprint of stoichiometry: a dimer is
twice as bright as its monomer at the *same* concentration and the *same*
diffusion time, so PCH/FIDA resolve oligomerization that FCS alone leaves
ambiguous.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/04_fida_pch`.

## Why the histogram carries brightness

If molecules were perfectly stationary point sources of equal brightness, the
photon count per bin would be pure Poisson, whose variance equals its mean.
Real fluctuations make the histogram **super-Poissonian** — broader than a
Poisson of the same mean — because at any instant a random *number* of
molecules sit at random *positions* in a non-uniform detection volume. The
excess width over Poisson is precisely the brightness information:

$$
\langle k\rangle = N\,\epsilon\,T,\qquad
\mathrm{Var}(k) - \langle k\rangle = \gamma_2\,N\,(\epsilon\,T)^2 ,
$$

where $T$ is the bin time, $\epsilon$ the molecular brightness in counts per
second per molecule (so $\epsilon T$ is counts per molecule per bin), and
$\gamma_2$ a shape factor of the detection volume (for a 3-D Gaussian,
$\gamma_2 = 1/2^{3/2} \approx 0.354$). The first equation is just the mean; the
second — the **excess variance** — is quadratic in $\epsilon T$ and only linear
in $N$, so mean and variance together solve for both. This is the **moment /
Number & Brightness (N&B)** route ({cite}`qian1990`): from the apparent
brightness $B = \mathrm{Var}(k)/\langle k\rangle$ a photon-counting detector
gives $\epsilon T = B - 1$ and $N = \langle k\rangle/(\epsilon T)$, the classic
N&B convention that folds $\gamma_2$ into the reported brightness (so N&B
brightnesses are *apparent* and compare only within one instrument). Moments
are fast but throw away the shape of $P(k)$; PCH and FIDA fit the *whole*
histogram and so tolerate multiple species and background far better.

**Worked numbers — why intensity alone is not enough.** Two samples, both giving
the *same* mean count rate at $T = 50\ \mu\mathrm{s}$:

| sample | $\epsilon$ | $N$ | $\epsilon T$ | $\langle k\rangle$ | $\mathrm{Var}-\langle k\rangle$ | $B$ |
|---|---|---|---|---|---|---|
| few, bright | 20 kHz | 2 | 1.0 | 2.0 | 0.71 | 1.35 |
| many, dim | 10 kHz | 4 | 0.5 | 2.0 | 0.35 | 1.18 |

Halving the brightness and doubling the concentration leaves the intensity
trace *identical* — no intensity measurement can tell these apart. The excess
variance differs by exactly the factor 2 in $\epsilon T$, and the full histogram
differs even more distinctly in shape. That separation of $\epsilon$ from $N$ is
the entire reason to build the histogram.

## Single-species PCH

The full histogram follows from two nested randomizations
({cite}`chen1999`). First, a single molecule sitting at position
$\mathbf{r}$ emits with a local brightness $\epsilon\,\bar{PSF}(\mathbf{r})$ set
by the point-spread function, and its photon count is Poissonian at that rate.
Integrating over all positions weighted by the PSF-shaped detection profile
gives the **single-molecule histogram**

$$
p^{(1)}(k) = \frac{1}{V}\int_V
  \frac{\big[\epsilon\,\bar{PSF}(\mathbf{r})\big]^{k}}{k!}\,
  e^{-\epsilon\,\bar{PSF}(\mathbf{r})}\; \mathrm{d}\mathbf{r}.
$$

In ChiSurf the confocal volume is the 3-D Gaussian (3DG), so the radial
brightness profile is $\bar{PSF}\propto e^{-2x^2}$ and the integral is taken over
the reduced coordinate $x = r/w$ with the spherical volume element
$\mathrm{d}\mathbf{r} = 4\pi w^3 x^2\,\mathrm{d}x$ ({src}`chisurf/plugins/pch/api/algorithms.py#pch_single_species`) — that
$x^2$ shell weight is what makes the volume three-dimensional; without it the
same integral describes a *1-D* Gaussian and returns $\gamma_2 = 2^{-1/2}$
instead of $2^{-3/2}$. Second, the actual number of
molecules in an *open* volume is itself Poisson-distributed with mean $N$, so
the observed histogram is the sum over occupancies of $p^{(1)}$ **self-convolved**
$n$ times — $n$ independent molecules add their counts:

$$
P(k) = \sum_{n=0}^{\infty} \mathrm{Poisson}(n;N)\;
       \big(p^{(1)}\big)^{\ast n}(k) .
$$

That is exactly
{src}`chisurf/plugins/pch/api/algorithms.py#pch_open_system`: a Poisson-weighted stack of repeated
convolutions of $p^{(1)}$ with itself.

## Multiple species

Independent species simply **convolve**: the total count in a bin is the sum of
the counts contributed by each species, so their histograms combine by
successive convolution,

$$
P(k) = P_1 \ast P_2 \ast \cdots \ast P_S \,(k),
$$

each $P_s$ being an open-system PCH with its own $(\epsilon_s, N_s)$. ChiSurf's
{src}`chisurf/plugins/pch/api/algorithms.py#pch_mixture` builds this with FFT convolutions, and the fit returns per-species
brightness $\epsilon_s$, occupancy $N_s$, and amplitude fractions.

## FIDA: the generating-function route

Repeated convolutions are exact but stiff; **FIDA** ({cite}`kask1999`) recasts the same physics through the probability **generating function**
$G(\xi)=\sum_k P(k)\,\xi^k$, which turns convolutions into products and integrals
into an exponent:

$$
G(\xi) = \exp\!\Big\{\sum_i N_i\!\int_0^1\! w(x)\,
         \big[e^{(\xi-1)\,q_i x}-1\big]\,\mathrm{d}x
         \;+\;(\xi-1)\,\lambda_\text{bg}\Big\}.
$$

Here $w(x)$ is the **spatial brightness profile** $\mathrm{d}V/\mathrm{d}x$ — the
volume element that emits at relative brightness $x\in(0,1]$, normalized to
$\int w\,\mathrm{d}x = 1$ — and $\lambda_\text{bg}$ is the mean background per
bin. Crucially, $w(x)$ is an *explicit, adjustable* description of the optics:
an ideal 3-D Gaussian gives $w(x)\propto(-\ln x)^{1/2}/x$
({src}`chisurf/core/models/pch/fida.py#dvdx_gaussian`), but a real, aberrated PSF deviates from Gaussian in exactly
the way that biases brightness, and FIDA corrects for it by fitting a modified
$w(x)$ (the first- and second-order spatial corrections of {cite}`kask1999`). The
histogram is recovered as the Taylor coefficients of $G$ — evaluate $G$ on the
complex unit circle and inverse-FFT ({src}`chisurf/core/models/pch/fida.py#fida_pch`). FIDA and PCH are two
computational routes to the *same* observables $(\epsilon, N)$; FIDA handles
non-ideal volumes and many species more gracefully, PCH is more transparent.

## Relation to N&B and to FCS

PCH, FIDA, N&B and FCS all read the same underlying molecular brightness and
concentration, at different levels of detail:

- **N&B** uses only the first two moments (mean and variance) of $P(k)$;
  it is the low-order truncation of PCH/FIDA and maps to it via
  $\epsilon T = B-1$, $N=\langle k\rangle/(\epsilon T)$.
- **FCS** reads brightness through the **zero-lag amplitude**: the ACF
  extrapolates to $G(0)\propto 1/N$, so FCS gives $N$ (hence concentration) and,
  combined with the mean intensity, the counts-per-molecule
  $\epsilon=(I-B)/N$ — the same brightness observable
  (see {doc}`/concepts/fcs_correlation`). But FCS obtains $\epsilon$ only as an
  average and is entangled with the diffusion model; PCH/FIDA obtain a
  *distribution* of brightnesses at a single time scale, **independent of
  diffusion**, and so resolve a bright minority against a dim majority.

The practical payoff is stoichiometry. Two samples with identical FCS curves —
same $N$, same $\tau_D$ — can differ in PCH if one has half as many particles
each twice as bright: monomer-versus-dimer, ligand binding, aggregation. That
brightness axis is what PCH and FIDA add on top of FCS.

## Choosing the bin time, and where PCH breaks

**The bin time is the one setting that can invalidate the result.** PCH assumes
each molecule holds a *fixed* brightness for the whole bin, which is only true
if the molecule barely moves in time $T$. The requirement is therefore
$T \ll \tau_D$. As $T$ approaches the diffusion time, each molecule samples both
bright and dim regions of the PSF within one bin, its effective brightness
averages toward the mean, the histogram narrows toward Poisson, and the fitted
$\epsilon$ is **biased low** while $N$ is biased high — smoothly, with no
warning sign in the fit quality.

Pushing $T$ down has its own limit: once $\langle k\rangle \ll 1$ the histogram
is almost all zeros and ones and carries little shape, so precision comes only
from very many bins. With a typical confocal $\tau_D \approx 200\ \mu\mathrm{s}$
for a small dye, $T \approx \tau_D/10 = 20\ \mu\mathrm{s}$ with
$\langle k\rangle$ of order 0.1–5 is a reasonable working point. Fitting the same
data at two or three bin times is the cheapest sanity check available: a
brightness that drifts systematically with $T$ means the assumption is being
violated.

**Brightness resolution is coarse.** Separating two species by brightness alone
is far harder than separating them by lifetime. Below a brightness ratio of
roughly 1.5–2 the mixture fit becomes badly conditioned and the amplitudes trade
against each other; fix what you can independently ($N$ from FCS, or one species'
$\epsilon$ from a pure sample) rather than floating everything.

**Other systematics.** Uncorrelated **background** must be modelled explicitly —
absorbed into the signal it dilutes the apparent brightness. Detector **dead
time** truncates the high-$k$ tail (pushing the histogram sub-Poissonian) and
**afterpulsing** adds spurious low-$k$ pairs; both matter at high count rates.
**Triplet blinking** in the microsecond range sits squarely in the PCH bin window
and lowers apparent brightness. Finally, the **3-D Gaussian PSF is an
idealization** — real volumes have wings, which is why FIDA carries an explicit
volume-shape correction ({src}`chisurf/core/models/pch/fida.py#dvdx_gaussian`)
rather than assuming the ideal profile.

## See also

- Guide: {doc}`/guides/04_fida_pch`; related FCS concept:
  {doc}`/concepts/fcs_correlation`.
- ChiSurf source: single-species and mixture PCH in
  {src}`chisurf/plugins/pch/api/algorithms.py`; the FIDA generating-function
  model in {src}`chisurf/core/models/pch/fida.py`; the **PCH** plugin
  (`chisurf/plugins/pch/`, RPC `pch.compute` / `pch.fit`).

## References

- {cite}`chen1999` — PCH itself: the histogram derived from the detection
  profile, and the open-system convolution above.
- {cite}`kask1999` — FIDA: the same physics through the generating function,
  with an adjustable description of the optics.
- {cite}`qian1990` — the moment analysis that Number & Brightness is, and the
  low-order truncation of both.
