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
\langle k\rangle = \epsilon\,N\,T,\qquad
\mathrm{Var}(k) - \langle k\rangle = \epsilon^2\,\gamma_2\,N\,T ,
$$

where $T$ is the bin time and $\gamma_2$ is a shape factor of the detection
volume (for a 3-D Gaussian, $\gamma_2 = 1/2^{3/2}$). The first equation is just
the mean; the second — the **excess variance** — is quadratic in $\epsilon$ and
only linear in $N$, so mean and variance together solve for both. This is the
**moment / Number & Brightness (N&B)** route (Qian & Elson 1990): from the raw
apparent brightness $B = \mathrm{Var}(k)/\langle k\rangle$ a photon-counting
detector gives $\epsilon = B - 1$ and $N = \langle k\rangle/\epsilon$. Moments
are fast but throw away the shape of $P(k)$; PCH and FIDA fit the *whole*
histogram and so tolerate multiple species and background far better.

## Single-species PCH

The full histogram follows from two nested randomizations (Chen, Müller,
Berland & Gratton 1999). First, a single molecule sitting at position
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
the reduced coordinate $x$ (`pch_single_species`). Second, the actual number of
molecules in an *open* volume is itself Poisson-distributed with mean $N$, so
the observed histogram is the sum over occupancies of $p^{(1)}$ **self-convolved**
$n$ times — $n$ independent molecules add their counts:

$$
P(k) = \sum_{n=0}^{\infty} \mathrm{Poisson}(n;N)\;
       \big(p^{(1)}\big)^{\ast n}(k) .
$$

That is exactly `pch_open_system`: a Poisson-weighted stack of repeated
convolutions of $p^{(1)}$ with itself.

## Multiple species

Independent species simply **convolve**: the total count in a bin is the sum of
the counts contributed by each species, so their histograms combine by
successive convolution,

$$
P(k) = P_1 \ast P_2 \ast \cdots \ast P_S \,(k),
$$

each $P_s$ being an open-system PCH with its own $(\epsilon_s, N_s)$. ChiSurf's
`pch_mixture` builds this with FFT convolutions, and the fit returns per-species
brightness $\epsilon_s$, occupancy $N_s$, and amplitude fractions.

## FIDA: the generating-function route

Repeated convolutions are exact but stiff; **FIDA** (Kask, Palo, Ullmann & Gall
1999) recasts the same physics through the probability **generating function**
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
(`dvdx_gaussian`), but a real, aberrated PSF deviates from Gaussian in exactly
the way that biases brightness, and FIDA corrects for it by fitting a modified
$w(x)$ (the first- and second-order spatial corrections in Kask 1999). The
histogram is recovered as the Taylor coefficients of $G$ — evaluate $G$ on the
complex unit circle and inverse-FFT (`fida_pch`). FIDA and PCH are two
computational routes to the *same* observables $(\epsilon, N)$; FIDA handles
non-ideal volumes and many species more gracefully, PCH is more transparent.

## Relation to N&B and to FCS

PCH, FIDA, N&B and FCS all read the same underlying molecular brightness and
concentration, at different levels of detail:

- **N&B** uses only the first two moments (mean and variance) of $P(k)$;
  it is the low-order truncation of PCH/FIDA and maps to it via
  $\epsilon = B-1$, $N=\langle k\rangle/\epsilon$.
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

## See also

- Guide: {doc}`/guides/04_fida_pch`; related FCS concept:
  {doc}`/concepts/fcs_correlation`.
- ChiSurf source: single-species and mixture PCH in
  `chisurf/core/models/pch/` and `chisurf/plugins/pch/api/algorithms.py`
  (`pch_single_species`, `pch_open_system`, `pch_mixture`); FIDA
  generating-function model in `chisurf/core/models/pch/fida.py`
  (`fida_pch`, `fit_fida`, `dvdx_gaussian`); the **PCH** plugin
  (`chisurf/plugins/pch/`, RPC `pch.compute` / `pch.fit`).
- Chen, Y., Müller, J. D., Berland, K. M. & Gratton, E. (1999). The photon
  counting histogram in fluorescence fluctuation spectroscopy. *Biophys. J.*
  **77**, 553–567.
- Kask, P., Palo, K., Ullmann, D. & Gall, K. (1999). Fluorescence-intensity
  distribution analysis and its application in biomolecular detection
  technology. *Proc. Natl. Acad. Sci. USA* **96**, 13756–13761.
- Qian, H. & Elson, E. L. (1990). Distribution of molecular aggregation by
  analysis of fluctuation moments. *Proc. Natl. Acad. Sci. USA* **87**,
  5479–5483.
