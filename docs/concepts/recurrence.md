(concept-recurrence)=
# Recurrence analysis of single particles (RASP)

In freely-diffusing single-molecule FRET, a molecule crosses the confocal volume
in about a **millisecond** and produces one burst — far too short to observe
slow (ms–s) conformational kinetics. **Recurrence analysis of single particles
(RASP)** recovers those slow timescales without immobilization by exploiting a
simple observation: a molecule that just produced a burst does not vanish. It
lingers near the focus and, by diffusion, is likely to **recur** — re-enter the
detection volume and emit a *second* burst — within a short **recurrence time**.
During that window the recurring burst is, with high probability, the **same**
molecule. Correlating the FRET value of an initial burst with the FRET values of
the bursts that recur shortly after therefore reveals how a molecule evolves
*between* two visits to the focus.

For the step-by-step workflow in ChiSurf, see the guide
{doc}`/guides/02_recurrence_rasp`.

## Recurrence and the same-molecule probability

Consider the stream of burst arrival times. For an uncorrelated (Poisson) burst
stream the number of burst pairs separated by a lag $\tau$ is set purely by the
mean burst rate; recurrence enriches short-lag pairs above that random-coincidence
background. The enrichment is quantified by the normalized autocorrelation
$G(\tau)$ of the burst arrival times, from which RASP defines the
**same-molecule probability**

$$
P_\text{same}(\tau) = 1 - \frac{1}{G(\tau)} .
$$

At short lag, recurrences dominate: $G(\tau)>1$ and $P_\text{same}\to 1$ — a
burst arriving a time $\tau$ after an initial one is almost certainly the same
particle re-entering the focus. As $\tau$ grows the molecule diffuses away and is
replaced by fresh molecules from the bulk: $G(\tau)\to 1$ and
$P_\text{same}\to 0$, i.e. a late "recurring" burst is just a random coincidence.
The lag at which $P_\text{same}$ falls below a chosen threshold defines the
usable **recurrence-time window**, the range of $\tau$ in which conditioning on
the initial burst is meaningful.

## The recurrence FRET histogram

RASP builds a conditional FRET histogram in two steps:

1. **Select an initial sub-population** by FRET efficiency, e.g. all bursts with
   $E$ in an efficiency window $[E_1, E_2]$ (say a low-FRET state).
2. **Histogram the recurrences.** For every initial burst at time $t_i$, collect
   the efficiencies of all bursts arriving in the recurrence window
   $t_i + \Delta t \in [t_1, t_2]$, with $[t_1,t_2]$ chosen inside the region
   where $P_\text{same}$ is high. The distribution of these *recurrence*
   efficiencies is the RASP histogram.

$$
H_\text{rec}(E \mid E_1{\le}E_i{\le}E_2,\; t_1{\le}\Delta t{\le}t_2)
$$

Contrast the recurrence histogram with the overall burst-efficiency histogram. If
the molecule is **static** on the timescale of the window, a molecule selected in
the low-FRET state recurs still in the low-FRET state, and the recurrence
histogram simply reproduces the selected sub-population. If the molecule
**interconverts** between states during $\Delta t$, probability leaks toward the
other state: a recurrence histogram conditioned on low FRET grows a high-FRET
component (and vice versa). Scanning the recurrence window $t_2$ across the
$P_\text{same}$-defined range turns this leakage into a **relaxation curve**, from
which the interconversion rate is read directly — a rate that a single burst,
lasting only a millisecond, can never expose.

## What RASP separates, and how it complements other tools

Burst-integrated FRET histograms collapse everything that happens during a burst
into one number, so **dynamic interconversion** (a molecule switching states)
and **static heterogeneity** (a mixture of molecules frozen in different states)
can produce the *same* broadened or multi-peaked histogram. RASP breaks this tie
along the **time axis**: conditioning on an initial value and watching how the
recurrence histogram relaxes as a function of the recurrence time yields the
interconversion *timescale*. Dynamics show up as a time-dependent leakage between
states; static heterogeneity shows a recurrence histogram that stays put.

This makes RASP complementary to the intra-burst dynamics probes:

- {ref}`concept-bva` (burst variance analysis) tests, within a burst, whether the
  sub-window FRET variance exceeds shot noise — sensitive to dynamics **faster**
  than the burst duration.
- {ref}`concept-burst-2cde` (two-channel kernel density) flags photon-stream
  asymmetry within a burst on the sub-millisecond scale.

RASP reaches the opposite regime: interconversion **slower** than a burst but
faster than the mean time between visits of the same molecule (below the bulk
diffusion time), the ms–s window that intra-burst methods cannot see. Together the
three cover dynamics from sub-burst to seconds, and each conditions on the FRET
value rather than only reporting a marginal histogram.

## The recurrence histogram is a mixture

$P_\text{same}$ is never 1, so the measured recurrence histogram is always a
**mixture** of true recurrences and random coincidences:

$$
H_\text{rec}(E) = P_\text{same}\,H_\text{same}(E)
                + \bigl(1-P_\text{same}\bigr)\,H_\text{all}(E),
$$

where $H_\text{all}$ is the ordinary (unconditioned) burst histogram, since a
random coincidence is just a fresh molecule drawn from the bulk. The quantity of
interest is $H_\text{same}$, recovered by subtracting the known random
contribution:

$$
H_\text{same}(E) = \frac{H_\text{rec}(E) - (1-P_\text{same})\,H_\text{all}(E)}
                        {P_\text{same}} .
$$

This subtraction is not a refinement — it is essential. Skipping it makes every
recurrence histogram look like it is relaxing toward the overall population,
which is precisely the signature of dynamics, so an uncorrected analysis reports
exchange even for a perfectly static sample. The correction also explains why the
usable window is bounded: as $P_\text{same}$ falls, the denominator shrinks and
the noise in $H_\text{same}$ is amplified, so pushing to long recurrence times
buys timescale at a steep cost in precision.

## Assumptions and pitfalls

- **Concentration is a trade-off, and it is the central experimental knob.**
  $P_\text{same}$ is high only when fresh molecules are rare, i.e. at low
  concentration — but low concentration also means few bursts and few
  recurrences, so the statistics degrade. Too high, and random coincidences
  swamp the conditioning.
- **Photobleaching sets the real upper limit on the window.** A molecule that
  bleaches between visits never recurs, which depletes long-lag recurrences and
  biases the apparent kinetics toward faster relaxation. Worse, a molecule whose
  *acceptor* alone bleaches recurs as a spurious low-FRET burst — this mimics
  exchange into a low-FRET state. ALEX stoichiometry filtering of the recurring
  bursts is the standard defence.
- **The molecule must not leave for good.** RASP assumes free diffusion in and
  out of a stationary volume; convection, flow, sticking to the coverslip, or
  focus drift all change the recurrence statistics without any conformational
  change.
- **It measures the FRET value, not the conformation.** Anything that shifts $E$
  between visits — dye photophysics, a change in quantum yield, acceptor
  blinking — is read as a transition.
- **The accessible window is bounded on both sides**: faster than the burst
  duration is invisible (use BVA/2CDE/H2MM), slower than the time for a molecule
  to diffuse away irreversibly is inaccessible at any concentration.

## In ChiSurf

RASP in ChiSurf operates purely on the **per-burst table** (arrival time plus
proximity ratio / efficiency) — no photon-level access is needed. The routines in
`chisurf/core/fluorescence/burst/recurrence.py` compute $P_\text{same}(\tau)$
from the burst arrival times and the recurrence histogram for a chosen efficiency
sub-population and recurrence window. See {doc}`/guides/02_recurrence_rasp` for the
worked example.

## See also

- Guide: {doc}`/guides/02_recurrence_rasp`.
- Related intra-burst dynamics probes: {ref}`concept-bva`, {ref}`concept-burst-2cde`.
- ChiSurf source: `chisurf/core/fluorescence/burst/recurrence.py`.
- Hoffmann, A., Nettels, D., Gopich, I. V., Schuler, B. (2011). Quantifying
  heterogeneity and dynamics in single-molecule FRET via recurrence analysis of
  single particles (RASP). *Physical Chemistry Chemical Physics*, 13, 1857–1871.
