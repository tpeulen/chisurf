(concept-pda)=
# Photon Distribution Analysis (PDA)

Photon Distribution Analysis (PDA) explains the **shape of a single-molecule
FRET histogram** from first principles. When freely diffusing molecules are
observed one burst at a time, the FRET-efficiency (or proximity-ratio) histogram
is never a set of sharp lines: even a perfectly rigid molecule at a single
donor–acceptor distance produces a *broad* peak. PDA forward-models that width
photon-by-photon, so a fitted histogram tells you whether a broad peak is just
counting noise around one distance, a genuine mixture of states, or the
signature of conformational dynamics.

For the step-by-step workflow in ChiSurf, see the guide {doc}`/guides/11_pda`.

## Why an E-histogram is broad: shot noise

Each burst carries only a finite number of photons $N = F_D + F_A$ split between
the donor ($F_D$) and acceptor ($F_A$) channels. The apparent efficiency of one
burst,

$$
E_\text{app} = \frac{F_A}{F_D + F_A},
$$

is a *ratio of two small integers*. Even if the true probability of an acceptor
photon is a fixed $p_A = E$, the actual split fluctuates from burst to burst
because photon emission is a Bernoulli process. A burst of $N$ photons therefore
draws $F_A$ from a **binomial distribution**,

$$
P(F_A \mid N, E) = \binom{N}{F_A}\, E^{F_A}\,(1-E)^{\,N-F_A}.
$$

This is *shot noise*: for $N = 20$ photons the binomial standard deviation of
$E_\text{app}$ is already $\sqrt{E(1-E)/N}\approx 0.11$ at $E=0.5$. Small bursts
are broad, large bursts are narrow — the observed width is a property of the
photon statistics, not of the molecule. PDA turns this liability into
information: since the broadening is *known exactly*, any excess width beyond
shot noise is real heterogeneity or dynamics.

## Forward-modelling the full count distribution

The measured object PDA fits is not a smooth $E$ curve but the joint
distribution of green/red photon counts, $P(F_D, F_A)$, accumulated over all
bursts. Building it requires two ingredients.

**The burst-size distribution $P(N)$.** Real bursts do not all contain the same
number of photons; the experiment supplies an empirical distribution $P(N)$ of
photons per time window (or per burst). The predicted count distribution is the
average of the per-burst binomials weighted by how often each burst size occurs:

$$
P(F_D, F_A) = \sum_{N} P(N)\; P(F_A \mid N, E)\,\big[\,N = F_D + F_A\,\big].
$$

Fixing the burst-size distribution to the measured one is essential — it is what
makes the shot-noise width quantitative rather than a free parameter.

**Background, crosstalk, direct excitation and $\gamma$.** The clean binomial
above assumes every photon is a signal photon and every acceptor photon comes
from FRET. Real detectors see more:

- **Background** adds uncorrelated counts in each channel at rates $B_D$, $B_R$.
  Per burst these are (near-)Poisson, so the signal binomial is **convolved**
  with a background distribution channel by channel,

  $$
  P(F_D, F_A) = \sum_{s_D + b_D = F_D}\ \sum_{s_A + b_A = F_A}
      P_\text{signal}(s_D, s_A)\; \mathrm{Pois}(b_D \mid B_D)\;
      \mathrm{Pois}(b_A \mid B_R).
  $$

- **Crosstalk / spectral leakage** ($\alpha$): a fraction of donor photons is
  detected in the red channel.
- **Direct acceptor excitation** ($\delta$): the laser excites the acceptor
  directly, adding red photons that are not reporting on distance.
- **Detection-correction $\gamma$**: unequal detection efficiency and quantum
  yield of the two dyes, $\gamma = (g_R\,Q_A)/(g_G\,Q_D)$.

In ChiSurf these enter through a single per-photon *green probability*
$p_G(E)$ that folds excitation ($\mathrm{Ex}_{DG}$, $\mathrm{Ex}_{AG}$),
detection efficiencies ($g_G$, $g_R$), the emission/detection crosstalk matrix
($c_{GD}, c_{GA}, c_{RD}, c_{RA}$) and quantum yields ($Q_D$, $Q_A$) into the
probability that a detected photon lands in the green channel. The distance
enters only through $E$; the corrections turn the ideal binomial with parameter
$E$ into a realistic one with parameter $p_G(E)$.

## From a distance to a histogram

A donor–acceptor distance $R$ maps to efficiency through the Förster relation

$$
E(R) = \frac{1}{1 + (R/R_0)^6},
$$

with Förster radius $R_0$. PDA models therefore come in a hierarchy of
increasing realism:

- **Single / few discrete distances.** Each species is one $(E, \text{amplitude})$
  pair; the histogram is a mixture of shot-noise-broadened peaks. This is the
  minimal test of "one state vs. two".
- **Gaussian-distributed distances.** Flexible linkers and conformational
  softness make $R$ itself a distribution. A Gaussian $p(R)$ with mean $\bar R$
  and width $\sigma$ broadens the peak *beyond* shot noise; PDA separates the two
  contributions because it already accounts for the shot-noise part exactly:

  $$
  P(F_D, F_A) = \int p(R)\; P\big(F_D, F_A \mid E(R)\big)\, \mathrm{d}R .
  $$

- **Polymer distance distributions.** For unfolded / intrinsically disordered
  chains the Gaussian is replaced by a self-avoiding-walk (SAW-$\nu$) $p(R)$
  parameterized by a root-mean-square distance and the Flory exponent $\nu$
  (see {doc}`/guides/03_polymer_distance_distributions`).

## Dynamic PDA: dynamics inside the integration time

If a molecule interconverts between states *during* the burst, no single $E$
describes it. What matters is how the total transfer accumulated over the
observation window compares with the exchange time. PDA handles this by
modelling the **fraction of the window** $f$ that the molecule spends in state 1
of a two-state (telegraph) process. For a stationary two-state Markov system
$f$ has a known law $w(f)$ with two boundary masses (the molecule stayed in one
state the whole window) and an interior density expressed through modified
Bessel functions, governed by a single dimensionless exchange parameter
$K = (k_1 + k_2)\,T$ — the mean number of transitions per window. The
time-averaged per-photon green probability is then

$$
p_G(f) = f\,p_{G,1} + (1 - f)\,p_{G,2},
$$

and the count distribution is averaged over $w(f)$. The two limits are the
diagnostic:

- **Slow exchange** ($K\to 0$): only the boundary masses survive — two static
  populations at $E_1$ and $E_2$. This is the static two-state result.
- **Fast exchange** ($K\to\infty$): $w(f)$ collapses onto $f = x_1$ — a single
  averaged population at $E = x_1 E_1 + x_2 E_2$, sitting *between* the states.

The intermediate case — a characteristic "bridge" of counts filling the valley
between the two static peaks — is the fingerprint of dynamics on the burst
timescale, and its shape yields the interconversion rates. ChiSurf provides
two- and three-state dynamic models, and a polarization-resolved variant for
anisotropy PDA.

**One histogram measures $K$, not $k$.** Exchange enters only through
$K = (k_1+k_2)T$, so a single dataset cannot separate a fast rate watched briefly
from a slow one watched for longer — the two give an identical histogram. Given
the observation time the rate follows, but the more important consequence is that
one time window cannot *test* the kinetic model: some $K$ fits it either way.

Cutting the same measurement into several fixed-width time bins and fitting them
with one shared rate turns that into a constraint the data can fail. Windows that
imply different rates each fit alone and are rejected jointly. This requires the
bins to have a known, constant duration, which is why the reader offers
fixed-width segmentation alongside the burst search — under a burst search the
durations vary with the local photon flux and $T$ is only a lower bound.

**Two states have a closed form; more do not.** The two-state occupation-time
distribution above is exact, boundary atoms included. Beyond two states the
three-state model offers a choice. The default keeps the first two moments of
the time average — exact for any rate matrix — and matches a bounded shape to
them (Gopich & Szabo); it is deterministic, which matters because a stochastic
objective makes the optimiser chase sampling scatter. Where that is not enough,
because slow exchange makes the distribution multi-modal and no two-parameter
shape has three peaks, the occupation times can be **sampled** instead.

That sampling runs in the photon simulator's kinetics rather than in ChiSurf.
The simulator records a *state trajectory* — every transition with the time it
occurred — so the fraction of each observation window spent in each state comes
out exactly; a periodic snapshot could not, since it cannot see a state entered
and left between two samples. Each window is one immobile, non-emitting molecule
started from the equilibrium populations, so windows are independent draws, and
the seed is fixed so repeated evaluations of the same parameters agree.

## How much heterogeneity can PDA actually detect?

The shot-noise floor is set entirely by burst size. At $E = 0.5$, where it is
widest, $\sigma_\text{shot} = \sqrt{E(1-E)/N}$ gives

| $N$ (photons/burst) | 20 | 50 | 100 | 200 | 500 |
|---|---|---|---|---|---|
| $\sigma_\text{shot}$ | 0.112 | 0.071 | 0.050 | 0.035 | 0.022 |

Real width adds in quadrature, $\sigma_\text{obs}^2 = \sigma_\text{shot}^2 +
\sigma_\text{het}^2$, so heterogeneity is detectable only once it is comparable
to the floor. With $N = 50$ bursts, a genuine $\sigma_\text{het} = 0.05$ widens
the peak from 0.071 to 0.087 — a 23 % change that is easy to miss if the
background or $\gamma$ is even slightly off. The same heterogeneity at $N = 200$
widens 0.035 to 0.061, a 74 % change that is unmistakable. **Photon budget, not
fit quality, sets what PDA can resolve.**

:::{tip}
This yields a model-free diagnostic that costs nothing. Split the bursts into
size classes and re-measure the width: pure shot noise shrinks as $1/\sqrt{N}$,
while genuine distance heterogeneity does not shrink at all.

| $\sigma_\text{het}$ | $\sigma_\text{obs}$ at $N=50$ | at $N=200$ | ratio |
|---|---|---|---|
| 0 (pure shot noise) | 0.071 | 0.035 | **2.00** |
| 0.05 | 0.087 | 0.061 | 1.41 |
| 0.10 | 0.122 | 0.106 | 1.15 |

A four-fold increase in burst size must narrow a shot-noise-limited peak by
exactly $\sqrt{4} = 2$. Anything less is real width, and you have established
that before fitting a single model.
:::

**Reading the dynamic parameter.** $K = (k_1+k_2)T$ is the mean number of
transitions per observation window, so it is fixed by the experiment as much as
by the molecule. With a $T = 1$ ms window, $K = 1$ corresponds to
$k_1 + k_2 = 10^3\ \mathrm{s^{-1}}$. Sensitivity is limited to roughly
$0.1 \lesssim K \lesssim 10$: below that the boundary masses dominate and the
result is indistinguishable from two static states; above it $w(f)$ has already
collapsed onto the average and only the mixing fraction is recoverable, not the
rates. Because $K$ scales with $T$, changing the burst-size (i.e. time) window
shifts the accessible rate range — analysing two windows is the way to confirm
that a fitted $K$ is real.

## Pitfalls

**The burst-size distribution is data, not a parameter.** $P(N)$ must be taken
from the measurement. Letting it float, or borrowing it from another dataset,
silently converts the shot-noise prediction into a free width and destroys the
entire basis of the method.

**Correction factors propagate straight into the fitted distance.** $\alpha$,
$\delta$ and especially $\gamma$ enter through $p_G(E)$, so an error there
shifts the peak position and is absorbed by the fit as a distance change.
Determine them independently ({ref}`concept-smfret-bursts`) rather than fitting
them alongside the model.

**Background rates must be measured, not assumed.** The background convolution
uses $B_D$, $B_R$ as fixed Poisson rates; underestimating them makes a peak look
narrower than it is, which PDA then reports as spurious homogeneity.

**A wide peak has more than one explanation.** A static Gaussian $p(R)$, a
two-state mixture, and slow exchange can all reproduce a broadened peak. Prefer
the burst-size diagnostic above and, for dynamics, the characteristic valley
*bridge* — a width alone does not identify its cause.

## Reading a PDA fit

- A histogram that is well described by a **single distance** with no extra
  width means the population is static and homogeneous within counting noise.
- A peak **wider than shot noise** implies a distance distribution (linker
  dynamics, disorder) — fit a Gaussian or SAW-$\nu$ $p(R)$.
- **Counts between two peaks** that a static two-state mixture cannot reproduce
  imply exchange during the burst — fit a dynamic model and read off $K$.
- The photon-number window ($N_\text{Ph,min}$, $N_\text{Ph,max}$) selects which
  bursts enter the analysis; narrowing it sharpens all peaks (larger $N$) at the
  cost of statistics.

## See also

- Guide: {doc}`/guides/11_pda`.
- Models: `chisurf/core/models/pda/` — discrete (`simple.py`),
  Gaussian-distance (`pdagauss.py`), dynamic two-/three-state (`dynamic.py`,
  `dynamic_mc.py`), anisotropy (`anisotropy.py`), SAW-$\nu$ polymer
  (`saw_nu.py`); nuisance/background and correction factors in `nusiance.py`;
  the histogram engine is `tttrlib.Pda` (S1S2 matrix).
- Antonik, M.; Felekyan, S.; Gaiduk, A.; Seidel, C. A. M. *Separating
  Structural Heterogeneities from Stochastic Variations in Fluorescence
  Resonance Energy Transfer Distributions via Photon Distribution Analysis.*
  J. Phys. Chem. B **2006**, 110, 6970–6978.
- Kalinin, S.; Felekyan, S.; Valeri, A.; Seidel, C. A. M. *Characterizing
  Multiple Molecular States in Single-Molecule Multiparameter Fluorescence
  Detection by Probability Distribution Analysis.* J. Phys. Chem. B **2008**,
  112, 8361–8374.
