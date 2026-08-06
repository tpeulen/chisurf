(fundamentals-quenching-mechanisms)=
# Quenching mechanisms in detail

{ref}`fundamentals-quenching` treats quenching phenomenologically: a rate is
added, or molecules are removed, and the Stern–Volmer plot bends one way or the
other. This page goes underneath that — how fast diffusion can deliver a
quencher, whether the electron transfer is thermodynamically allowed once it
arrives, and why the nucleobases quench in a fixed order that decides where a
dye may be attached to DNA.

It is the page to read when a quenching constant needs to be *explained* rather
than reported.

## How fast can diffusion be?

The Smoluchowski result for the diffusion-controlled encounter rate is

$$
k_0 = \frac{4\pi N_A R D}{1000},
$$

with $R = R_f + R_q$ the sum of the molecular radii, $D = D_f + D_q$ the sum of
the diffusion coefficients, and the factor 1000 converting cm³ to litres so that
$k_0$ comes out in M⁻¹s⁻¹. Combined with the Stokes–Einstein relation
$D = k_BT/6\pi\eta R$, this gives the property worth remembering:

$$
k_0 \propto \frac{T}{\eta},
$$

so the diffusion limit is set by the solvent, not by the pair. In water at 25 °C
it is about $10^{10}\ \mathrm{M^{-1}s^{-1}}$ for small molecules. A measured
$k_q$ is interpreted against that number
({ref}`fundamentals-quenching`), and the two failure modes are informative
rather than fatal: Stokes–Einstein underestimates $D$ for a quencher smaller
than the solvent molecules — oxygen in alcohols is the standard example, giving
apparent efficiencies above unity — and a $k_q$ genuinely above $k_0$ means
binding, not diffusion.

### The rate is not constant in time

The Smoluchowski expression above is the *steady-state* rate, reached once a
concentration gradient has established itself around each excited molecule.
Immediately after excitation there is no gradient: pairs that happen to start
close together react at once, before diffusion has had to bring anything
anywhere. The rate coefficient is therefore time-dependent,

$$
k(t) = k_0\left(1 + \frac{R}{\sqrt{\pi D t}}\right),
$$

large at $t \to 0$ and decaying to $k_0$.

This **transient effect** has two consequences that matter more than the theory
does:

- **The decay is not exponential**, even for a single species with a single
  quencher, and the deviation grows with $[Q]$. A multi-exponential fit will
  describe it with components that are not species.
- **The steady-state Stern–Volmer plot curves upward.** The extra early-time
  quenching adds to $F_0/F$ without adding to the *steady-state* rate, so it
  mimics static quenching almost exactly.

:::{warning}
That gives **three** mechanisms producing upward curvature — a ground-state
complex, a sphere of action, and a purely diffusive transient effect — of which
the third involves no static component at all. Upward curvature on its own
identifies none of them. The transient effect is distinguishable in principle,
because it lives in the *shape of the decay* rather than in its integral: it
shortens the early part of the decay while a complex or a sphere of action
leaves the decay shape untouched and only scales it.
:::

```{figure} /guides/figures/transient_quenching.png
:alt: the time-dependent quenching rate and the non-exponential decay it produces
:width: 100%

Left: $k(t)/k_0$ — pairs that start in contact react before diffusion has moved
anything, so the rate begins orders of magnitude above its steady-state value
and relaxes onto it. Right: what that does to the decay. A straight line on a
semilog plot is an exponential, so the gap between the curve and its **own**
long-time slope is the non-exponentiality — present for a single species with a
single quencher. Constants are the defaults of ChiSurf's shipped
`Transient-Quenching` model, so the figure and the fittable model agree.
```

The Collins–Kimball refinement replaces the assumption that reaction is certain
at contact with a finite intrinsic reactivity there (a radiation boundary
condition), which is what lets a transient-effect fit return a reaction radius
$R$ *and* an intrinsic rate separately instead of one lumped constant.

## Will the electron transfer? Rehm–Weller

Most quenching of the dyes used here is photoinduced electron transfer, and
whether it is thermodynamically allowed follows from the **Rehm–Weller**
equation:

$$
\Delta G = E(\mathrm{D^+\!/D}) - E(\mathrm{A/A^-}) - \Delta G_{00}
           - \frac{e^2}{\varepsilon d},
$$

where the two are *reduction* potentials, $\Delta G_{00}$ is the $S_0 \to S_1$
energy of whichever partner is excited, and the last term is the Coulomb
stabilization of the resulting ion pair at separation $d$ in a solvent of
dielectric constant $\varepsilon$.

The structure is more useful than the algebra. The excitation energy
$\Delta G_{00}$ enters with a **negative** sign: light supplies the driving
force, and a transfer that is hopelessly uphill in the ground state can be
downhill from $S_1$. The Coulomb term is small — about 0.06 eV in acetonitrile,
and smaller still in water where the high dielectric constant screens the ion
pair — so it is routinely dropped, and dropping it is safe in aqueous buffer.

Two conversions are needed constantly and are worth having to hand:

$$
\Delta G\ [\mathrm{kcal\,mol^{-1}}] = 23.06\, n\, \Delta E\ [\mathrm{V}],
\qquad
E\ [\mathrm{kcal\,mol^{-1}}] = \frac{28600}{\lambda\ [\mathrm{nm}]}.
$$

A mole of 400 nm photons is 71.5 kcal; a mole of 600 nm photons is 47.7 kcal.
That is the budget the excitation provides, and it is why a red dye has less
driving force available than a blue one for the same redox pair.

### What the driving force buys, and what it does not

Rehm and Weller's own measurement is the useful empirical result: the
bimolecular quenching rate rises steeply as $\Delta G$ becomes negative and then
**plateaus at the diffusion limit**, and — famously — does not come back down
again at very large driving force. The Marcus inverted region, real in
intramolecular and frozen systems, does not show up in this bimolecular data;
the modern reading is that the encounter is diffusion-limited long before the
inverted region could be reached, so the experiment cannot see it.

For practical purposes: once $\Delta G$ is a few tenths of an eV negative, the
transfer is as fast as encounter allows, and making it more favourable changes
nothing. Quenching efficiency then reports on **access**, not on thermodynamics.

## Nucleobase-specific quenching

The most important instance of all this for the work in this documentation is
that **DNA quenches dyes, and does so base-specifically**.

Seidel, Schulz and Sauer measured static and dynamic quenching constants for a
series of coumarins against the nucleobases and found *one common ordering* that
holds across dyes {cite}`seidel1996`. It follows the nucleobase one-electron
oxidation potentials {cite}`steenken1997`: the easier a base is to oxidize, the
better an electron donor it is, and the more strongly it quenches.

$$
\mathrm{G} \;>\; \mathrm{A} \;>\; \mathrm{C} \approx \mathrm{T}
$$

**Guanine is the strong quencher**, by a margin, because it has the lowest
oxidation potential of the four. Both a dynamic and a static component are
present — the static one from ground-state stacking of dye on base — so a dye
adjacent to a G loses quantum yield in two ways at once.

```{figure} /guides/figures/rehm_weller.png
:alt: quenching rate against driving force, with the four nucleobases marked
:width: 80%
:align: center

The Rehm–Weller shape: the rate climbs steeply with driving force and then stops
at the diffusion limit. Guanine sits where the curve has flattened — more
driving force would buy nothing — while thymine and cytosine are on the steep
part, where a small shift changes the rate by decades. That is why the four
bases differ so much, and why G is the one to keep away from a label.

**The nucleobases are placed by their known *ordering*, not at measured
$\Delta G$ values.** The curve is the Rehm–Weller expression with a typical
$\Delta G^\ddagger(0) = 0.1$ eV; the positions illustrate the ranking
{cite}`seidel1996`, they are not a data set.
```

### Why this matters before it becomes interesting

The consequences run in both directions, and the nuisance one is the one that
bites first:

- **A dye's quantum yield depends on the sequence it is attached to.** Move a
  label two bases along and $Q_D$ changes. Since $R_0 \propto Q_D^{1/6}$, the
  Förster radius changes with it, and a distance computed from a tabulated $R_0$
  is then wrong in a way nothing in the fit reveals
  ({ref}`fundamentals-energy-transfer`).
- **It is position-dependent, not construct-dependent.** Two labelling positions
  on the same molecule can have different $Q_D$, so a comparison between them
  confounds distance with photophysics unless the donor-only lifetimes are
  measured for each ({ref}`concept-accurate-fret`).
- **Intermittent stacking blinks.** A dye that transiently stacks on a nearby
  base is dark while stacked, which broadens burst-efficiency histograms and
  adds a component to correlation curves that is not conformational dynamics
  ({ref}`fundamentals-quenching`).
- **Avoid guanine when placing a label**, and check the donor-only lifetime
  against free dye whenever the sequence near the label changes. This is the
  cheapest control in the whole workflow.

Used deliberately, the same effect is a measurement: PET between a dye and a
guanine (or a tryptophan, which behaves the same way) is a contact probe with
sub-nanometre range, far shorter than FRET, and it is the basis of PET-FCS and
of quencher-based hybridization probes.

## From a bulk constant to a per-structure simulation

Everything above describes quenching between freely diffusing partners, where a
single $k_q$ summarizes the encounter. A dye tethered to a protein is not that
situation: it is confined to its accessible volume, the quenching residues sit
at fixed positions in the structure, and whether the dye reaches one depends on
the linker and the surface — so the decay is determined by geometry, not by a
concentration.

ChiSurf models this directly rather than through a Stern–Volmer constant, and
the companion tool **QuEst** (`modules/quest`, *QUenching ESTimation*) is built
on exactly the concepts on this page:

1. **Which residues quench, and how fast.** The same PET logic as the
   nucleobases, with the protein's own low-oxidation-potential side chains as
   the donors — **Trp, Tyr, His, Met** (and Pro). Each is assigned a quenching
   rate and a critical distance, shipped as a table in
   `chisurf/core/settings/constants/structure.json`.
2. **Where the dye can be.** The accessible volume of the linker-tethered dye
   ({ref}`concept-accessible-volume`), which is what makes the answer
   structure-specific.
3. **How it moves within it.** A Brownian-dynamics trajectory inside the AV,
   with the dye slowed near the surface to represent the unspecific sticking
   that a real dye shows.
4. **The decay that follows.** Quenching is a step function of distance — active
   whenever the dye is within the critical distance of a quenching atom — so
   each trajectory frame carries the summed rate of whichever quenchers it is in
   contact with ({src}`chisurf/core/structure/av/dynamic.py#_quenching_rate_per_frame`),
   and integrating that along the trajectory gives the donor decay.

The output is a **non-exponential donor decay computed from a structure**, and
that is the point: the multi-exponential decay of a labelled protein need not
mean conformational states at all — it can be one dye sampling a distribution of
distances to a fixed set of quenchers
({ref}`fundamentals-lifetime-quantum-yield`).

Two things this buys that a fitted $k_q$ cannot:

- **A predicted donor quantum yield per labelling position**, before the
  experiment. Since $R_0 \propto Q_D^{1/6}$, that is a prediction about the
  Förster radius of a construct, and it is how a labelling site can be chosen to
  avoid quenching rather than discovered to suffer from it.
- **A physical reading of a short donor-only lifetime.** If a measured
  $\tau_{D(0)}$ is below the free-dye value, the simulation says whether the
  structure explains it — and if it does not, the discrepancy is evidence about
  the structure or the linker rather than a number to absorb into a fit.

In ChiSurf the fittable form is `AVDecayModel`
(`chisurf/core/models/tcspc/av_decay.py`), which puts the simulated
quenching decay into the ordinary TCSPC fitting path
({ref}`concept-tcspc-lifetime`).

The experimental groundwork this rests on is worth reading before trusting a
simulated quantum yield. {cite}`doose2005` measured how a range of organic dyes
are quenched by tryptophan and established that the interaction needs van der
Waals **contact** — which is what justifies a step function of distance rather
than a smooth $1/r^n$ falloff. {cite}`doose2009` develops the same contact
quenching into a reporter for conformational dynamics, and is the reference for
what the technique measures once the quenching is deliberate rather than a
nuisance. For ATTO 655, the dye most used for PET work,
{cite}`vandeLinde2018` separates the static and dynamic contributions at the
single-molecule level and finds both a ground-state complex and a sphere of
action alongside the dynamic term — the three mechanisms of
{ref}`fundamentals-quenching` in one system. For Alexa 488, the donor in much of
the FRET work here, {cite}`chen2012` tracks how tryptophan quenching changes
between folded, molten-globule and unfolded states, which is the clearest
demonstration that $Q_D$ is a property of the *conformation* and not of the dye.

## See also

- Previous: {ref}`fundamentals-quenching` — the phenomenology, the Stern–Volmer
  forms and how to read the curvature.
- Concepts: {ref}`concept-accurate-fret` (why a position-dependent $Q_D$ biases
  a distance) · {ref}`concept-accessible-volume` (the volume the dye samples) ·
  {ref}`concept-fcs-correlation` (where blinking appears) ·
  {ref}`concept-tcspc-lifetime`.
- Implementation: the quencher table
  `chisurf/core/settings/constants/structure.json`, the trajectory-based rate
  {src}`chisurf/core/structure/av/dynamic.py#_quenching_rate_per_frame`, the
  fittable `AVDecayModel` in `chisurf/core/models/tcspc/av_decay.py`, and the
  QuEst simulator in `modules/quest`.
- Fundamentals: {ref}`fundamentals-energy-transfer` ·
  {ref}`fundamentals-fluorophores` · {ref}`fundamentals-solvent`.
- Literature: {cite}`seidel1996` for the nucleobase ordering and the quenching
  constants behind it; {cite}`steenken1997` for the redox potentials it tracks;
  {cite}`doose2005` and {cite}`doose2009` for contact quenching by tryptophan and
  what it can be used to measure; {cite}`vandeLinde2018` for ATTO 655 and
  {cite}`chen2012` for Alexa 488; {cite}`rehm1970` for the driving-force
  dependence;
  {cite}`gehlen2020` for the Stern–Volmer deviations these mechanisms produce;
  {cite}`lakowicz2006`, the chapter on quenching mechanisms and dynamics, for the
  Rehm–Weller treatment.
