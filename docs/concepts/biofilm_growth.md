(concept-biofilm-growth)=
# Biofilm growth and stratification

A **biofilm** is a community of cells attached to a surface and held in a matrix
they secrete. It does not grow the way a well-mixed culture does. A cell in
suspension meets the same medium as every other; a cell in a film is fed only by
what diffuses in from the outside, and consumed on the way by everything above
it. Two consequences follow, and both are what the simulated demo in
{doc}`/guides/44_molecular_viewer` shows:

* **growth is surface-limited.** A cell walled in by its neighbours has neither
  room to divide into nor substrate to divide on, so the colony extends only
  where it touches open space. That is why a film first covers the substratum and
  only then thickens;
* **the film stratifies.** Solute concentration falls with depth below the
  film–liquid interface, so cells that started at the surface pass through
  successive physiological states *without moving* as the colony grows over
  them.

## Depth is the variable, not height

The quantity that governs a cell is its **depth below the local film surface**,
not its height above the substratum. A cell on top of a low mound is at the
interface even where a taller mound stands nearby, and the two are only the same
number in a film of uniform thickness. Writing $h(x,y)$ for the local surface
height, a cell at $(x,y,z)$ has

$$
d = h(x,y) - z .
$$

For a flat film consuming a solute at a rate proportional to the local biomass,
the steady-state concentration profile follows a reaction–diffusion balance,

$$
D_\text{e}\,\frac{\partial^{2} C}{\partial d^{2}} = \rho\,q(C),
$$

with $D_\text{e}$ the effective diffusivity in the film, $\rho$ the biomass
density and $q$ the specific uptake rate. With zero-order kinetics ($q$ constant,
the usual approximation for oxygen well above the half-saturation constant) this
integrates to a parabola that reaches zero at the **penetration depth**

$$
L = \sqrt{\frac{2 D_\text{e}\, C_0}{\rho\, q}},
$$

below which the solute is exhausted. $L$ is what sets where the aerobic layer
ends: it is a property of the solute, the density and the respiration rate, not a
constant of biofilms. Oxygen penetration depths measured with microelectrodes in
dense films are typically tens to a few hundred micrometres, so a film much
thinner than that is aerobic throughout.

## What the simulation models, and what it does not

The demo grows a colony by division on a lattice-free domain. Each frame, cells
are chosen at random from those still able to divide and a daughter is placed at
about one cell diameter, in a direction biased increasingly upward as the film
thickens. A placement that would put the daughter closer than a contact distance
to an existing cell **fails**, and a cell whose placements all fail leaves the
dividing set. That single rule produces surface-limited growth: it keeps the
density physical and makes *up* the only direction left once the substratum is
covered.

Colour is assigned from $d$ by thresholds set in the configuration. Deliberate
simplifications, stated rather than hidden:

* **the penetration depth is a parameter, not a result.** No solute field is
  solved. The thresholds are chosen so that the strata are visible in a film a
  few micrometres thick, which is far thinner than a real aerobic layer. Read the
  colours as *the model's* state variable;
* **cells do not move once born.** There is no mechanical relaxation, so the
  film does not spread under its own growth pressure as a real one does. The
  compensating effect is that any colour change is unambiguously a burial;
* **no matrix, no detachment, no flow.** Erosion and sloughing set the steady
  thickness of a real film and are absent here, so the simulated film only grows;
* **division is stochastic and unaged.** Cells have no individual growth rate or
  division clock; the population follows an imposed growth curve.

The model is therefore a *depiction* of the mechanism rather than a predictive
simulation. For predictive work the individual-based models in the iDynoMiCS
lineage solve the solute fields and the mechanical relaxation this one leaves
out.

## Why this needs a viewer that plays more than coordinates

A trajectory of a molecule is motion: the atoms are the same atoms throughout. A
colony is not. Cells **appear** as they divide, **grow** back to full size, and
**change state** where they stand. Showing it therefore needs a format that
carries a radius and a colour per frame — which RMF does — and a viewer that
reads them. ChiMOL draws a particle with no radius in the current frame as one
that does not exist yet, which is how a cell that has not divided off is
expressed.

## See also

- Guide: {doc}`/guides/44_molecular_viewer` — the **Biofilm growth** demo, and
  how a per-frame radius and colour are read.
- Simulation configuration: `IMP/swarm/examples/biofilm_growth.yaml` in the
  modelling framework beside ChiSurf; the runner is
  `IMP.swarm.core.visual_runner`.
- Key literature: de Beer, Stoodley, Roe & Lewandowski 1994 (Biotechnol.
  Bioeng. 43:1131, oxygen microelectrode profiles in biofilms); Stewart &
  Franklin 2008 (Nat. Rev. Microbiol. 6:199, physiological heterogeneity in
  biofilms); Lardon et al. 2011 (Environ. Microbiol. 13:2416, iDynoMiCS);
  Picioreanu, van Loosdrecht & Heijnen 1998 (Biotechnol. Bioeng. 58:101,
  mathematical modelling of biofilm structure).
