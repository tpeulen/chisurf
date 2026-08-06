# Photon-by-photon hidden Markov models (H2MM)

:::{admonition} Theory
:class: seealso
The hidden-Markov model for photon streams — emission/transition matrices, the
$A^{\Delta t}$ propagator, Baum-Welch optimization, and state-number selection by
BIC/ICL — is explained in the concept page {ref}`concept-h2mm`.
:::

## What it does

**H2MM** ({cite}`pirchi2016,harris2022`) fits a hidden Markov model
directly to the **photon stream** — not to binned intensities — so it resolves
sub-burst FRET-state dynamics down to the microsecond scale, well below the bin
sizes an intensity-trace HMM needs. It maximises the photon-by-photon likelihood
over the state emission rates and the transition-rate matrix, selecting the
number of states by BIC/ICL, and recovers the most-likely state path (Viterbi),
per-state dwell times and the transition-density map.

## In ChiSurf

The `burst_h2mm` plugin is a Qt-free numba engine (with an equivalent C++
`tttrlib.H2MM`) under an RPC service and GUI, embedded in the burst workflow:

```python
from chisurf.plugins.burst.burst_h2mm.core.analysis import analyze

result = analyze(bundle, states=(1, 2, 3), criterion="bic")
result.dwells        # per-dwell measured E (and S with an acceptor-excitation stream)
result.transitions   # Viterbi transition-count matrix
```

From the guided workflow: `bursts.h2mm(states=(1, 2, 3))`. Optional ALEX/PIE
stoichiometry, nanotime divisors (lifetime-resolved states) and bootstrap
uncertainties are supported.

In the burst workflow, **step 6 starts fitting as soon as you open it**. A state
scan with restarts runs for minutes, so it runs off the GUI thread and **Stop**
in the toolbar ends it — a stopped scan is discarded rather than reported as the
answer, and coming back to the step does not restart it. Opening the step again
does not refit either; see [53 — Reusing results](53_reusing_results.md).

## Reproducing a scan

The restarts are **seeded**, so the same bursts and the same options give the
same answer every time. The seed is an ordinary fit option (*Seed*, default 0),
it is recorded in the result alongside the settings it was fitted with, and the
status line reports it: `Selected 3 states (BIC) from 2495 bursts / 275973
photons (seed 0)`.

This matters more than it looks. Model selection over state counts is not always
decisive — with few bursts, or states that overlap in E, two independent sets of
restarts can prefer different state counts. Reporting a state count without the
seed that produced it is therefore not reproducible. To find out whether your
result is robust rather than lucky, change the seed and refit: an answer that
survives several seeds is one you can report. Pressing **🔁 Restart** does *not*
do this — it reproduces the same fit, by design.

## Choosing a decoder

Fitting decides *what the states are*; decoding decides *which state each photon
belongs to*. They are separate options, and the second one changes what a
per-state decay, a per-state FCS curve or a reported occupancy is made of.

The default, **Viterbi**, returns the single most likely state sequence. That is
not the same as the distribution of photons over states, and the difference is
one-directional: photons whose posterior is (0.7, 0.3) all land in state 0, so
well-separated states are inflated and ambiguous or short-lived ones are erased.
On simulated two-state data with 75 / 25 occupancy and overlapping E, Viterbi
counts 0.789 / 0.211 where the truth is 0.713 / 0.287.

| *Decoder* | what it does | use it for |
|---|---|---|
| Viterbi (most likely path) | the maximum-likelihood sequence | one trajectory to look at; dwell and transition statistics |
| Jitter (draw per photon) | draws each photon from its own posterior | occupancies, per-state decays and spectra, a state-labelled photon stream |
| FFBS (draw whole paths) | draws a whole trajectory from the joint posterior | the same, **plus** dwell times and transition counts; error bars over several draws |

Two things are handled for you:

- **The unbiased occupancy is always reported**, whichever decoder ran, as
  `posterior_populations` in the result and in the status line
  (`… — occupancy 0.713, 0.287`). Compare it against the counted `populations`
  to see how much the argmax is costing you.
- **Jitter never drives dwell statistics.** Its draws are independent per
  photon, so they shatter a solid dwell into single photons. Selecting it still
  gives you dwells and transitions — derived from a Viterbi path, with
  `dwell_decoder` recording that. If you want sampled *dwells*, use FFBS.

*Seed* beside the decoder makes a draw reproducible; the same seed gives the
same assignment, independent of how many threads ran it. Change it to draw an
independent assignment and see how much of your result is decoding noise.

```python
result = analyze(data, state_counts=(1, 2, 3), decoder="jitter", decoder_seed=0)
result.populations            # counted from the draw
result.posterior_populations  # the unbiased occupancy
result.dwell_decoder          # "viterbi" — see above
```

The sampling decoders need the `tttrlib` C++ backend; with
`CHISURF_H2MM_BACKEND=numba` they raise rather than silently falling back to the
biased answer they exist to avoid.

## Writing the states back into the photons

Tick **State photons → write** and the run writes its assignment beside each
source measurement, so every other tool can select a state without knowing
anything about H2MM:

- `<file>_h2mm_states.ptu` — the complete measurement with each photon's routing
  channel replaced by the id of its `(stream, state)` pair. A per-state decay or
  per-state FCS is then an ordinary channel selection.
- `<file>_h2mm_states.msgpack` — the per-photon state array plus the model, the
  decoder, its seed and the channel map. The source file is untouched, and there
  is no channel-id budget.

Both come from the same assignment and select exactly the same photons.

```bash
csc h2mm compute ./analysis --decoder jitter --state-tttr
```

Three things worth knowing before you use the PTU:

- **Channel ids are compacted, and none of the originals survive.** The source
  channels are renumbered to `0…k-1` and the `(stream, state)` pairs allocated
  densely after them, so the whole file fits the smallest possible id range —
  detectors at 1, 12 and 30 with two states end up in `0…6` rather than needing
  ids up to 30. Read the channel map (printed in the result, stored in the
  sidecar) rather than assuming a number.
- **Photons no decoder saw keep their own ids.** Anything outside a burst, or
  matching no stream, lands on the compressed form of its original channel. So
  after a split those ids hold *only* background — summing what used to be the
  donor channel gives you background, not the donor total.
- **PTU is the target.** Its records carry six channel bits (0–63); narrower
  containers silently truncate an out-of-range id, which would merge two states
  without a word of warning.

This pairs naturally with the jitter decoder: a per-state decay built from a
Viterbi split is made of the photons that state won outright, which is a biased
sample of it. Drawing from the posterior gives each state a photon set whose
size *and* composition match what the model actually says.

## Per-state decays

Once every photon carries a state, each state has a fluorescence decay — but
**only within one detection colour**. Donor and acceptor photons have different
instrument responses and different meaning, and the ratio in which they arrive
*is* the FRET efficiency. Histogramming all of a state's photons together
therefore produces a curve whose shape is set by the efficiency rather than by
any lifetime: two states with identical lifetimes but different E would show
different "decays". It is not a decay of anything.

The *Per-state decay* panel splits photons by stream and merges only within a
colour: one curve per (colour, state), drawn in the colour of the light that
produced it, with the line style giving the state (solid S0, dashed S1, …).

Colours × states is more curves than a small plot can carry, so the panel has a
**filter bar**: a checkbox per detection colour and one per state. It opens
showing the **donor alone, all states** — the per-state donor lifetime is the
FRET readout, and everything at once is unreadable — with the other colours one
tick away. The legend appears only when more than one colour is shown; with a
single colour it would just sit on top of the curve it names.

Splitting by *stream* rather than by detector matters under PIE/ALEX, where the
acceptor-excitation stream shares its detectors with the acceptor stream and is
separated only by a micro-time window. In the panel below you can see it
directly: the red curve stops at ~6.8 ns and the yellow one begins there.

```{figure} figures/h2mm_state_decays.png
:name: fig-h2mm-state-decays
:width: 90%

Per-state decays of a two-state fit with **every colour ticked**. Green is
the donor, red the sensitised acceptor, yellow the directly excited acceptor —
red and yellow share the same detectors and are separated by the PIE window at
~6.8 ns. Solid is S0 (low FRET: little red), dashed is S1 (high FRET).
```

The underlying histograms are written to **`h2mm_state_decays.csv`**, at the
finest key that is physically meaningful:

| Column | Meaning |
|---|---|
| `State` | Viterbi state |
| `Stream` | stream index (what separates red from yellow on one detector) |
| `Channel` | TCSPC routing channel — the physical detector |
| `Micro Time`, `Micro Time (ns)` | bin centre |
| `Counts` | photons in that bin |

Per detector, not per colour, so the merge stays yours to make and to check.
Summing several detectors of one colour assumes their responses are aligned; two
detectors of the same colour can still differ by an IRF shift, and this table is
what you look at to find out. (ChiSurf can correct such a shift when the data is
read — see the per-channel micro-time shifts in the channel-definition editor.)

## Result

A two-state Viterbi state path and the resulting per-dwell FRET-efficiency
histogram — two states cleanly separated (dashed lines mark the true state
efficiencies).

```{figure} figures/h2mm.png
:name: fig-h2mm
:width: 90%

H2MM state path and dwell E histogram.
```

## See also

- `chisurf/plugins/burst/burst_h2mm/`; the binned-trace complement below.
- HMM of binned traces: [ebFRET](20_ebfret_binned_hmm.md).
