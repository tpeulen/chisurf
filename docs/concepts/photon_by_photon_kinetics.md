---
type: Concept
title: Photon-by-photon kinetics (Gopich–Szabo)
description: A molecule that switches conformation while it is being observed leaves the evidence in the order of its photons, not in their sum.
tags: [concepts, photons, kinetics]
anchor: concept-photon-by-photon-kinetics
---

(concept-photon-by-photon-kinetics)=

# Photon-by-photon kinetics (Gopich–Szabo)

A molecule that switches conformation while it is being observed leaves the
evidence in the **order of its photons**, not in their sum. Bin those photons
and the evidence is averaged away; the Gopich–Szabo likelihood never bins, and
so resolves exchange faster than any bin you could have chosen.

The matching guide is {doc}`/guides/49_photon_by_photon_kinetics`.

## The problem with histograms

Take a molecule interconverting between a low-FRET and a high-FRET state. What a
burst-wise efficiency histogram shows depends entirely on how the exchange rate
compares with the burst duration:

| exchange | histogram | what you can measure |
| --- | --- | --- |
| much slower than a burst | two clean peaks | the two states; **not** the rate |
| comparable to a burst | two peaks with a bridge | the rate, roughly, from the bridge |
| much faster than a burst | one peak at the mean | nothing — it looks static |

The last row is the dangerous one: fast exchange is *indistinguishable* from a
single intermediate state in a histogram. Broadening beyond shot noise hints at
it, and that is the basis of {doc}`BVA <bva>` and {doc}`2CDE <burst_2cde>`, but
neither returns a rate constant.

## The likelihood

Write the state kinetics as a rate matrix $K$, with $K_{ji}$ the $i \to j$ rate
in s⁻¹ and the diagonal fixed by conservation, $K_{ii} = -\sum_{j} K_{ji}$. Let
$\Phi_c = \mathrm{diag}(p_{c,1}, \dots, p_{c,n})$ collect the probability that a
photon emitted from each state carries colour $c$. For two colours that is
$p_a = E$ and $p_d = 1 - E$.

The probability of observing a specific burst — colours $c_1 \dots c_N$ at times
$t_1 \dots t_N$ — is a product alternating **emission** and **propagation**, one
factor per photon:

$$
L = \mathbf{1}^{T}\,
    \Phi_{c_N}\, e^{K \Delta t_{N-1}} \cdots
    \Phi_{c_2}\, e^{K \Delta t_1}\,
    \Phi_{c_1}\, \mathbf{p}_{\mathrm{eq}},
$$

with $\Delta t_i = t_{i+1} - t_i$ and $\mathbf{p}_{\mathrm{eq}}$ the equilibrium
populations. Read right to left: start at equilibrium, emit the first photon,
propagate for the real gap to the next photon, emit that one, and so on;
finally sum over whichever state the molecule ended in.

Everything the method knows is in $e^{K \Delta t}$. Because $\Delta t$ is the
*actual* gap between two photons — a real number, not a bin index — there is no
time resolution to choose and nothing is averaged before the model sees it.

### Why it is computable

Two practicalities turn that expression into something that runs.

**Diagonalise once.** With $K = U \Lambda U^{-1}$, conjugating the whole product
by $U$ replaces every matrix exponential with an elementwise
$e^{\lambda \Delta t}$. The per-photon cost becomes a few multiplications
instead of a matrix exponential.

**Rescale every photon.** The product underflows to zero within a few hundred
photons. Normalising the running vector at each photon and accumulating the
discarded magnitude in a log is the standard HMM scaling trick, and makes bursts
of any length safe.

### Complex spectra are not a corner case

A rate matrix obeying detailed balance has a real spectrum. A **non-reversible
cycle** — three or more states with a net circulation, say $1 \to 2 \to 3 \to 1$
driven by an energy source — has a genuinely complex conjugate eigenvalue pair.

This matters in practice. A widely used reference implementation takes the real
part of the transformed emission matrices while keeping the eigenvalues complex,
which is self-consistent only when the spectrum is real. On a pure three-state
cycle that lands roughly 24 log units away from the correct answer — a factor of
$10^{10}$ in likelihood. ChiSurf keeps the arithmetic complex throughout and
takes the real part only of the final scalar, and this is pinned by a test
against an independent matrix-exponential propagation.

So a circulating scheme — exactly the interesting case for a molecular motor or
an ATP-driven machine — is where the shortcut fails.

## What sets the accessible range

Two hard limits, neither negotiable by better fitting:

* **Fast end — the interphoton time.** Exchange faster than the mean gap between
  detected photons leaves no signature. At 50 kHz detected that is about 20 µs.
  Brightness, not cleverness, moves this limit.
* **Slow end — the burst duration.** If the molecule rarely switches *within* a
  burst, almost every burst is a single state and the data are a static mixture.
  The likelihood will say so: the fitted rates go to zero and a static model fits
  as well.

Between them the method works, and near the fast end it is the only thing that
does.

## Relation to H2MM

{doc}`H2MM <h2mm>` addresses the same problem and is a close relative, but the
two parameterise time differently and the difference is not cosmetic:

| | H2MM | Gopich–Szabo |
| --- | --- | --- |
| time | discrete — macro-time ticks | continuous |
| free parameter | transition **probability** per tick, $A$ | rate matrix $K$, s⁻¹ |
| propagator | $A^{\Delta t}$ | $e^{K \Delta t}$ |
| fitting | expectation-maximisation (Baum–Welch) | direct likelihood maximisation |
| tick convention | must be chosen; the answer depends on it | none |

H2MM's EM is efficient and scales well; the continuous-time form returns rates
without a tick convention to defend and extends naturally to schemes such as the
transition-state model below.

Because the two share no code and reach the answer by different routes,
**fitting the same photons both ways is the sharpest available check on either**.
ChiSurf's tool does this on request. Agreement to a few per cent is evidence;
disagreement is worth chasing before believing either number.

:::{note}
H2MM's third photon stream is usually an ALEX/PIE *excitation window* used for
stoichiometry, not a third chromophore. Genuine three-colour FRET — two
acceptors reporting two distances — is a different thing, and is what the
multi-colour emission matrix below describes.
:::

## More than two colours

Nothing in the derivation assumes two colours. Replace $\Phi_c$ with the general
row-stochastic emission matrix $p_{sc}$ — the probability that a photon from
state $s$ has colour $c$, with $\sum_c p_{sc} = 1$ — and three-colour FRET is
the same code path.

Three-colour earns its keep because it is sensitive to *which* of two distances
changed. A two-colour experiment sees one coordinate and cannot separate a
change in the donor–acceptor distance from a change in orientation; with two
acceptors the two distances constrain each other.

In practice a three-colour measurement produces **two photon sets** with
different emission models — the photons following blue excitation see three
colours, those following green excitation two — that describe the *same*
molecule. They share one rate matrix, so their log-likelihoods simply add.

## Transition paths

A two-state model asserts that switching is instantaneous. It is not: crossing a
barrier takes a finite time, and for protein folding that **transition-path
time** is a quantity of real interest — it is the part of the trajectory where
the molecule is actually doing the thing being studied.

The test is to make the crossing explicit. Insert an intermediate state that the
molecule must pass through, entered from either side and leaving to either side
with equal probability:

$$
1 \;\rightleftharpoons\; \mathrm{TS} \;\rightleftharpoons\; 2
$$

Because escape from TS goes either way with probability $\tfrac12$, the entry
rates are **doubled** to keep the effective exchange rates at $k_{12}$ and
$k_{21}$, and the mean crossing time is $t_p = 1/(2 k_T)$. Scanning $t_p$ and
plotting the log-likelihood against it asks the data directly how long the
crossing takes.

**Expect an upper bound, not a measurement.** A crossing much faster than the
interphoton time leaves no trace, so the curve is flat at zero for short
durations and falls once the crossing becomes long enough to be visible. That
flat region *is* the answer: the crossing is faster than where the curve breaks.
Only a clear positive peak is a measurement, and it needs a likelihood-ratio
test before it is reported as one.

The intermediate's efficiency is conventionally set to the mean of the two end
states. That is an assumption, not a derivation — a real transition path need
not sit halfway between the two structures — and it should be set explicitly
when the geometry says otherwise.

## Choosing the number of states

Every extra state adds $2n$ rates and one efficiency, and always fits a little
better. Use an information criterion, and prefer the BIC, whose $\ln N$ penalty
is severe at the photon counts involved here.

Two failure modes deserve naming:

* **States closer together than the shot-noise width cannot be separated.** A
  burst of $N$ photons determines its efficiency to about
  $\sqrt{E(1-E)/N}$; two states within that are not resolvable, and the fit will
  still return two of them looking precise.
* **Background is not a state, but the fit may make it one.** Unmodelled
  background photons have no state dependence and pull the efficiencies toward
  each other; a spurious third state can appear to absorb them.

## Caveats

* Efficiencies fitted here are **apparent** — uncorrected for leakage, direct
  excitation and detection efficiency. Calibrate ({doc}`accurate_fret`) and
  interpret them in the same frame.
* The **macro-time resolution** is not optional information. Every fitted rate is
  proportional to it, so a wrong tick period rescales the entire answer with no
  other symptom.
* A **Viterbi state path** is a point estimate with no error bar. It assigns a
  definite state to every photon, including in bursts containing no evidence for
  any transition. It illustrates a fitted model; it does not measure one.

## See also

- Tools in ChiSurf: **Photon-by-photon kinetics** (`chisurf/plugins/burst/burst_gs/`) maximises the Gopich-Szabo likelihood for continuous-time rates and per-state efficiencies.

## References

- {cite}`gopich2006` — the theory of photon-by-photon likelihood for a kinetic scheme.
- {cite}`gopich2009` — the colour-pattern likelihood that photon-by-photon FRET analysis maximises.
- {cite}`chung2012` — the same likelihood used to measure a transition path time.
- {cite}`pirchi2016` — H2MM - the algorithm that makes that likelihood tractable on real burst data.
