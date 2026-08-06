(fundamentals-quenching)=
# Quenching, blinking, and bleaching

Everything that empties $S_1$ without emitting a photon sits in $k_{nr}$
({ref}`fundamentals-lifetime-quantum-yield`). This page covers the routes that
are not fixed properties of the molecule: collisional and static quenching,
photoinduced electron transfer, the triplet state, and photobleaching. They are
what make a dye's brightness and lifetime depend on where it is attached, and
they are the origin of several features that are easy to misread as structural
dynamics.

## Collisional quenching and Stern–Volmer

A quencher that must diffuse into contact adds a rate proportional to its
concentration, $k_X = k_q[Q]$. Substituting into the efficiency expression from
the previous page gives the Stern–Volmer relation {cite}`sternvolmer1919`,

$$
\frac{F_0}{F} = \frac{\tau_0}{\tau} = 1 + k_q\tau_0[Q] = 1 + K_D[Q],
$$

with $\tau_0$ the unquenched lifetime, $k_q$ the bimolecular quenching constant
and $K_D = k_q\tau_0$ the Stern–Volmer constant. $1/K_D$ is the quencher
concentration at which half the intensity is gone, which is the quickest way to
judge whether a quencher is relevant at the concentrations you actually have.

The defining feature is that intensity and lifetime drop *together*. Collisional
quenching is a rate that competes during the excited-state lifetime, so it
shortens the decay.

The size of $k_q$ says whether the quenching is diffusion-limited. The
Smoluchowski expression for the diffusion-controlled encounter rate,
$k_0 = 4\pi N_A R D$ with $R$ the sum of the molecular radii and $D$ the sum of
the diffusion coefficients, gives about $10^{10}\ \mathrm{M^{-1}s^{-1}}$ in
water for small molecules. Interpret a measured $k_q$ against that number:

- $k_q \approx k_0$ — essentially every encounter quenches. Oxygen, acrylamide
  and iodide against exposed fluorophores behave this way.
- $k_q \ll k_0$ — the fluorophore is shielded, or the quenching itself is
  inefficient. A dye buried in a protein or in a membrane typically shows
  $k_q$ of order half the diffusion limit or below, because the quencher can
  only approach from some directions.
- $k_q > k_0$ — not possible for a diffusive mechanism. This indicates binding,
  a static component, or a wrong $\tau_0$.

```{figure} /guides/figures/stern_volmer.png
:alt: Stern-Volmer plots for dynamic, static and combined quenching
:width: 100%

With $K_D = K_S$ the two mechanisms are indistinguishable in intensity (left);
only the lifetime separates them (right), because static quenching removes
molecules from the observed population rather than shortening their decay. When
both act, the intensity plot curves upward while the lifetime plot stays
straight.
```

## Static quenching, and telling the two apart

If the quencher forms a non-fluorescent ground-state complex, the complexed
molecules never emit and the free ones are unperturbed. The intensity ratio is
governed by the association constant $K_S$,

$$
\frac{F_0}{F} = 1 + K_S[Q], \qquad \frac{\tau_0}{\tau} = 1 .
$$

The intensity relation has the same linear form as the collisional case, so an
intensity measurement alone cannot distinguish the two mechanisms. The lifetime
can: static quenching removes molecules from the observed population rather than
shortening their decay, so $\tau$ is unchanged. This is the practical reason a
lifetime instrument earns its cost in a quenching study.

Two other signatures help. Ground-state complex formation usually perturbs the
absorption spectrum, whereas collisional quenching cannot — it acts only on the
excited state. And the temperature dependence runs opposite: higher temperature
means faster diffusion and *more* collisional quenching, but weaker complexes
and *less* static quenching.

When both mechanisms operate on the same fluorophore the Stern–Volmer plot
curves upward, and

$$
\frac{F_0}{F} = \left(1 + K_D[Q]\right)\left(1 + K_S[Q]\right),
$$

which is second order in $[Q]$. The dynamic part can still be separated by
measuring lifetimes, since $\tau_0/\tau = 1 + K_D[Q]$ regardless of the static
term — the lifetime is blind to molecules that never emit.

## Upward curvature: the sphere of action

Upward curvature does not prove a ground-state complex. The same shape arises
when a quencher merely happens to be *adjacent* at the moment of excitation,
close enough that quenching is essentially certain but without any complex
having formed. This is the **sphere of action**, or Perrin, model, and the
probability that the sphere of volume $V$ is empty is Poissonian:

$$
\frac{F_0}{F} = \left(1 + K_D[Q]\right)\exp\!\left(\frac{V N_A [Q]}{1000}\right),
$$

with $V$ in cm³ and $[Q]$ in molar. Fitted volumes correspond to radii of a
few ångström — a contact shell rather than a binding site — which is the check
on whether the number is physical.

```{figure} /guides/figures/static_quenching_mechanisms.png
:alt: intensity and lifetime Stern-Volmer plots for dynamic, sphere-of-action and complex quenching
:width: 100%

Three mechanisms that all bend the plot **upward**, and one lifetime. The
intensity plots differ (left), but
$\tau_0/\tau$ is the same line for all three (right) because the lifetime
reports only the **dynamic** part — so it separates dynamic from static and then
cannot tell a sphere of action from a ground-state complex. The 7 Å contact
shell shown contributes $VN_A/1000 = 0.87\ \mathrm{M^{-1}}$; reproducing the
plotted $K_S = 5\ \mathrm{M^{-1}}$ with a sphere instead would need a radius of
12.6 Å, which is not contact — that arithmetic is the check.
```

:::{warning}
**The lifetime does not distinguish these two.** Both a real complex and a
sphere of action remove molecules *before* they can emit, so both leave
$\tau_0/\tau = 1 + K_D[Q]$ and both look "static" in a lifetime measurement.
The usual advice — "measure the lifetime to tell static from dynamic" —
separates the *dynamic* part correctly and then silently lumps two different
static mechanisms together.

What does distinguish them: a ground-state complex usually perturbs the
**absorption spectrum** and has a temperature dependence that weakens with
heating, whereas a sphere of action is a statistical proximity effect with no
new species and no absorption change. A fitted $V$ implying a radius much larger
than contact is the other tell — it means the exponential is absorbing something
else, usually a real complex.
:::

"Incomplete" is the word to hold onto: the sphere-of-action fraction is not
quenched *by a rate* but *removed with a probability*, so it never appears in
the decay at all. A quenching study that reports only $K_{SV}$ from an intensity
titration cannot tell you which of the three mechanisms produced it, and the
literature contains many such numbers ({cite}`gehlen2020` catalogues what each
deviation from linearity can mean, and how many mechanisms fit each one).

## Downward curvature: incomplete quenching and species mixtures

Everything above adds quenching and bends the plot *up*. The opposite bend has
the opposite cause: something **limits** how much quenching is possible, so
$F_0/F$ saturates instead of growing.

### Incomplete static quenching

If only a fraction $f$ of the fluorophores can be quenched at all — a limited
number of binding sites, a complex that is not fully dark, one conformer that
forms the complex and another that does not — then

$$
\frac{F}{F_0} = (1 - f) + \frac{f}{1 + K_S[Q]} ,
$$

so $F_0/F$ rises towards $1/(1-f)$ and stops there.

The plot bends **down** onto that plateau: adding more quencher cannot
remove emission that was never quenchable. "Incomplete" is doing real work in
that sentence — the mechanism is ordinary static quenching, and what is
incomplete is the *pool it can act on*.

### Species mixtures

The other route to the same shape, and the common one in proteins:
**more than one emitting species, quenched at different rates**. A protein with
several tryptophans, a dye at two labelling positions, or any sample with a
buried and an exposed population gives

$$
\frac{F}{F_0} = \sum_i \frac{f_i}{1 + K_i[Q]},
$$

with $f_i$ the fractional *intensity* of species $i$ in the absence of quencher.
The sum of hyperbolas curves downward, and the initial slope is the
intensity-weighted mean of the $K_i$ — so an apparent $K_{SV}$ read off the
low-$[Q]$ region is an average over species, not a property of any of them, and
it drifts with the concentration range chosen.

:::{important}
Incomplete static quenching and a two-population mixture with an inaccessible
fraction are **the same function**: put $K_b = 0$ in the sum above and it is the
expression in the previous subsection with $f_a$ for $f$. No amount of curve
fitting separates "a fraction the quencher cannot reach" from "a fraction that
cannot form the complex" — they are distinguished by the lifetime (a mixture of
*differently quenched* species has species-specific $\tau_i$; an unquenchable
fraction does not), by the absorption spectrum, and by chemistry, not by the
shape of $F_0/F$.
:::

The limiting case — one quenchable or accessible fraction and one inert — is
resolved by the **modified Stern–Volmer** (Lehrer) plot {cite}`lehrer1971`.
Writing $\Delta F = F_0 - F$,

$$
\frac{F_0}{\Delta F} = \frac{1}{f_a K_a [Q]} + \frac{1}{f_a},
$$

so plotting $F_0/\Delta F$ against $1/[Q]$ gives $1/f_a$ as the intercept and
$1/(f_a K_a)$ as the slope. The intercept has a direct meaning: it is the
extrapolation to infinite quencher, where only the inaccessible fraction still
emits.

```{figure} /guides/figures/quenching_mixtures.png
:alt: downward-curving Stern-Volmer plot for a two-population sample and the modified plot
:width: 100%

Left: with half the emission unquenchable — incomplete static quenching, or an
inaccessible population, the two are the same function — $F_0/F$ bends **down**
onto a plateau at $1/(1-f) = 2$. More quencher cannot remove emission that was
never quenchable. The orange curve is the same sample with that fraction
quenched at one tenth the rate: it has no plateau, but it is still bent away
from the straight line a single species gives. Right: the modified plot
straightens the inert case and its intercept returns $f = 0.50$ exactly, while a
line fitted to the leaky one over an ordinary window returns 0.74 for the same
truth of 0.50.
```

Three cautions, in increasing order of how often they are ignored:

- **The "inaccessible" fraction is rarely inaccessible.** If the buried
  population is quenched with even $K_b \approx 0.1\,K_a$, the modified plot
  still looks straight over a normal concentration range, and the extrapolated
  $f_a$ comes out too large — **0.74 against a true 0.50** in the figure above,
  a 48 % overestimate from a plot that looks perfectly linear. The two-class resolution is *useful but arbitrary*;
  it is a parameterization, not a count of populations.
- **Two classes is a choice.** Nothing in the data says there are two rather
  than three, and a two-term fit will describe a continuum of accessibilities
  perfectly well — the same trap as fitting a continuous lifetime distribution
  with two exponentials ({ref}`concept-maximum-entropy`).
- **Selective quenching shifts the spectrum.** If the exposed and buried
  populations emit at different wavelengths, quenching moves the emission
  maximum, and the difference between the unquenched and quenched spectra *is*
  the spectrum of the quenched population. That is a real measurement and worth
  taking — it tests the two-class model rather than assuming it.

**The lifetime route is the strong one here too.** In a mixture the
intensity-based and lifetime-based Stern–Volmer plots come apart: $F_0/F$ is
weighted by intensity, whereas the recovered $\tau_i$ belong to individual
species, so quenching each component of a resolved multi-exponential decay
separately gives per-species $K_i$ instead of an average. This is the analysis
worth doing when the decay can be resolved at all
({ref}`concept-tcspc-lifetime`).

## Photoinduced electron transfer

The common quenching mechanism for the dyes used in single-molecule work is
photoinduced electron transfer, not energy transfer. It is short-range,
requiring contact or near contact, and it is strongly dependent on the redox
potentials of the two partners.

The consequence that matters for FRET work: **tryptophan and guanine quench many
common dyes on contact**. A dye that transiently stacks on a nearby base or
residue shows reduced quantum yield and lifetime, and if the contact is
intermittent, the dye blinks on the microsecond-to-millisecond timescale. In a
burst experiment this produces broadened efficiency distributions and dynamic
signatures that are photophysics, not conformational exchange. Checking the
donor-only lifetime and anisotropy against the free dye is the standard control
({ref}`concept-mfd-fitting`).

The same mechanism is exploited deliberately in PET-FCS, where the quenching
rate reports on contact formation between two points on a chain.

## Dark states and blinking

A single molecule under continuous illumination does not emit steadily. It
switches between bright and dark on timescales from microseconds to seconds,
and the dark states are of two distinct kinds {cite}`ha2012`.

**Triplet blinking.** Intersystem crossing sends the molecule to $T_1$, which is
dark and slow to empty ({ref}`fundamentals-absorption-emission`). In aerated
solution the triplet lifetime is around a microsecond, because oxygen quenches
it efficiently; remove the oxygen and it stretches to milliseconds. The
occupancy grows with excitation power, since it is populated per absorption
event and emptied on its own clock.

**Redox blinking.** The triplet has a lower oxidation potential than the singlet,
so it readily undergoes electron transfer with whatever redox-active species are
present, producing a **radical anion or cation** that is non-fluorescent and can
persist for milliseconds to seconds — far longer than the triplet itself. This
is the origin of the long dark excursions that dominate single-molecule traces,
and it is why the buffer composition, not just the dye, determines the blinking.

The practical consequence is the **ROXS** idea: adding a reductant *and* an
oxidant together recycles the molecule out of both dark states rather than
deepening one of them. A reductant alone empties the triplet but leaves the
radical anion sitting there — which is exactly why adding a thiol can make
blinking worse. Trolox works as a single additive because it and its quinone
supply both halves.

:::{warning}
Cy5 photoswitching induced by thiols produced a long-lived dark state that in
smFRET reads as a **zero-FRET** population — a real acceptor that is temporarily
dark is indistinguishable, per-burst, from a molecule with no acceptor. Dark
states are not only noise; they can manufacture a state that gets interpreted
structurally {cite}`ha2012`.
:::

### What blinking does to each measurement

- **FCS.** A bright/dark process produces a bunching term at the lag time of the
  dark-state kinetics, well separated from diffusion and fitted as an
  exponential relaxation ({ref}`concept-fcs-correlation`). Two consequences: the
  apparent number of molecules $N = 1/G(0)$ is inflated if the term is omitted,
  because the blinking amplitude adds to the same intercept; and the amplitude
  grows with power, so a "brighter" measurement can have a *worse*
  signal-to-noise ratio in the diffusion part ({ref}`concept-fcs-saturation`).
  Because the dark-state term and afterpulsing occupy the same lag range,
  cross-correlating two detectors is what makes the term trustworthy
  ({ref}`fundamentals-instrumentation`).
- **smFRET.** Blinking broadens efficiency histograms beyond the shot-noise
  width, so a population that is merely blinking can look heterogeneous or
  dynamic ({ref}`concept-bva`, {ref}`concept-pda2c`). Donor blinking depresses
  the apparent efficiency; acceptor blinking raises it and, if long enough,
  splits off a spurious donor-only population.
- **Lifetime.** A dark state removes molecules from the emitting population
  without changing the decay of those that do emit, so it behaves like static
  quenching: intensity falls, $\tau$ does not. That is the diagnostic that
  separates blinking from a new quenching *rate*.

Triplet population is also the gateway to photobleaching, since a molecule
sitting in $T_1$ for microseconds — or as a radical for milliseconds — has far
more opportunity to react than one in $S_1$ for nanoseconds.

## Photobleaching

Photobleaching is irreversible loss of the fluorophore. Two routes matter and
they respond oppositely to the obvious remedy: a **triplet- and radical-mediated**
route, in which the long-lived dark states react (usually with oxygen), and a
**higher-excited-state** route, in which a molecule already in $T_1$ or a radical
absorbs another photon and reaches a state energetic enough to fragment. Removing
oxygen suppresses the first and *worsens* the second, because the triplet then
lives long enough to absorb again {cite}`ha2012`. A dye emits a finite total number of photons before it dies, and that
budget — not the instantaneous brightness — is what limits a single-molecule
experiment.

Practical consequences that recur throughout the documentation:

- **Acceptor bleaching in a FRET burst** converts a FRET-active molecule into a
  donor-only one mid-burst. These bursts must be excluded, which is what the
  stoichiometry axis in ALEX is for ({ref}`concept-smfret-bursts`).
- **Donor bleaching** truncates a burst and biases the burst-size distribution.
- **In imaging and FCS**, bleaching within the observation volume shortens the
  apparent diffusion time, because a molecule that dies while crossing the spot
  looks like a molecule that left early.
- Removing oxygen suppresses bleaching but *increases* triplet lifetime, because
  oxygen is also the main triplet quencher. Oxygen-scavenging buffers are
  therefore normally combined with a triplet quencher or a full ROXS system;
  scavenging alone trades a bleaching problem for a blinking one.

## Reading the diagnostic

Because all these processes act on the same two observables, the pattern is what
identifies them:

- Intensity and lifetime fall together, linearly in $[Q]$ — a rate has been
  added: collisional quenching, PET, or energy transfer.
- Intensity falls, lifetime does not — molecules have been removed from the
  emitting population *before* they could emit: a ground-state complex, a sphere
  of action, a dark state, or bleaching. The lifetime cannot separate these from
  each other; the absorption spectrum, the temperature dependence and the fitted
  sphere volume can.
- $F_0/F$ curves **upward** — static and dynamic together, a sphere of action,
  or the purely diffusive transient effect, which involves no static component
  at all ({ref}`fundamentals-quenching-mechanisms`).
- $F_0/F$ curves **downward**, onto a plateau — something limits how much
  quenching is possible: an unquenchable fraction (incomplete static quenching)
  or a population the quencher cannot reach. The two are the same function.
  Resolve with a modified Stern–Volmer plot, and do not believe the two-class
  split further than the data support it.
- $F_0/F$ curves **downward** without a plateau — species with *different*
  quenching constants rather than one inert fraction.
- Intensity fluctuates on microseconds with no change in the mean lifetime — the
  molecule is switching between bright and dark states: triplet, or intermittent
  PET.

## See also

- Next, in detail: {ref}`fundamentals-quenching-mechanisms` — the diffusion
  limit and its transient effect, Rehm–Weller, nucleobase-specific quenching,
  and the structure-based simulation ChiSurf and QuEst use instead of a bulk
  constant.
- Previous: {ref}`fundamentals-lifetime-quantum-yield`. Then:
  {ref}`fundamentals-polarization`.
- Concepts: {ref}`concept-fcs-correlation` (the triplet term) ·
  {ref}`concept-fcs-saturation` (power dependence) ·
  {ref}`concept-mfd-fitting` (photophysics versus dynamics in bursts) ·
  {ref}`concept-photophysics-simulation`.
- Literature: {cite}`sternvolmer1919` for the relation itself;
  {cite}`lehrer1971` for the modified plot and fractional accessibility;
  {cite}`gehlen2020` for what every deviation from linearity can mean;
  {cite}`ha2012` for triplet versus redox blinking and ROXS;
  {cite}`lakowicz2006`, quenching chapters.
