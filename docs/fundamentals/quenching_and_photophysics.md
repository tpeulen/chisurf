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

which is second order in $[Q]$. The dynamic part can be separated by measuring
lifetimes, since $\tau_0/\tau = 1 + K_D[Q]$ regardless of the static term. An
apparent static component at high quencher concentration may instead be a
*sphere of action* — a quencher that happens to be adjacent at the moment of
excitation, without a real complex — which produces the same upward curvature.

Downward curvature means the opposite situation: two populations, one of which
the quencher cannot reach. That is informative in its own right, and it is the
basis of accessibility measurements on proteins.

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

## The triplet state

Intersystem crossing sends a fraction of excitations to $T_1$, which is dark and
long-lived ({ref}`fundamentals-absorption-emission`). The molecule is then
unavailable for microseconds — orders of magnitude longer than a fluorescence
lifetime — so a single molecule under continuous illumination switches between a
bright and a dark state.

In FCS this appears as a bunching term at short lag times, well separated from
diffusion, and it is fitted as an exponential relaxation with a triplet fraction
and a triplet time ({ref}`concept-fcs-correlation`). Two things follow. The
apparent number of molecules $N = 1/G(0)$ is inflated if the triplet term is not
included, because the triplet amplitude adds to the same intercept. And the
triplet fraction grows with excitation power, so a "brighter" measurement can
have a *worse* signal-to-noise ratio in the diffusion part of the curve
({ref}`concept-fcs-saturation`).

Triplet population is also the gateway to photobleaching, since a molecule
sitting in $T_1$ for microseconds has far more opportunity to react with
dissolved oxygen than one in $S_1$ for nanoseconds. This is why triplet-state
quenchers and reducing–oxidizing systems both stabilize dyes and reduce blinking.

## Photobleaching

Photobleaching is irreversible loss of the fluorophore, generally through a
reaction from the triplet or a higher excited state, most often involving
oxygen. A dye emits a finite total number of photons before it dies, and that
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
  therefore normally combined with a triplet quencher.

## Reading the diagnostic

Because all these processes act on the same two observables, the pattern is what
identifies them:

- Intensity and lifetime fall together — a rate has been added: collisional
  quenching, PET, or energy transfer.
- Intensity falls, lifetime does not — molecules have been removed from the
  emitting population: static quenching, a permanently dark fraction, or
  bleaching.
- Intensity fluctuates on microseconds with no change in the mean lifetime — the
  molecule is switching between bright and dark states: triplet, or intermittent
  PET.

## See also

- Previous: {ref}`fundamentals-lifetime-quantum-yield`. Next:
  {ref}`fundamentals-polarization`.
- Concepts: {ref}`concept-fcs-correlation` (the triplet term) ·
  {ref}`concept-fcs-saturation` (power dependence) ·
  {ref}`concept-mfd-fitting` (photophysics versus dynamics in bursts) ·
  {ref}`concept-photophysics-simulation`.
- Literature: {cite}`sternvolmer1919` for the relation itself;
  {cite}`lakowicz2006`, quenching chapters.
