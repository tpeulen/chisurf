# Hidden Markov models

A hidden Markov model explains a binned trace as a molecule hopping between a
small number of **states**. Each state emits counts around its own mean, and
the hopping is memoryless: where the system goes next depends only on where it
is now.

Fitting recovers three things at once:

* **emissions** — the mean and width of each state, per detection channel;
* **transitions** — the probability of each hop per time bin, which becomes a
  rate once the bin width is set;
* **the state path** — which state the molecule was in during each bin, from
  which dwell times follow.

## Choosing the number of states

The likelihood always improves when states are added, so it cannot choose for
you. Use **Scan states** and take the *minimum* of BIC (or AIC), not the elbow
of the likelihood. BIC charges more per parameter and usually returns the model
that a kinetic interpretation can carry. If BIC keeps falling out to the end of
the range, the trace probably has structure the model does not describe —
bleaching, drift, or a continuum of states rather than discrete ones.

## Reading the result

* **Overlapping emission densities** in the intensity histogram mean intensity
  alone does not separate the states; the fit is then leaning on the transition
  structure, and the state assignment is correspondingly less certain.
* **Dwell-time histograms** should be single exponentials — straight on the
  logarithmic axis. Curvature says the state hides substructure, i.e. what is
  drawn as one state is really two with similar brightness.
* **A state with almost no occupancy** or a mean dwell of one bin is usually
  noise being fitted, not a state; refit with fewer states.

## Settings that matter

* **Covariance** — `full` allows the channels of a state to co-vary, `diag`
  does not, `spherical` uses one width per state, `tied` shares one matrix
  across all states. On short traces, fewer parameters fit more stably.
* **Decoder** — `viterbi` returns the most probable *path* and is what dwell
  times require; `map` takes the most probable state in each bin
  independently, which can produce a path the model itself considers
  impossible.
* **Accelerate (SQUAREM)** — extrapolates the EM iteration to the same optimum
  in far fewer steps when the states overlap. Turn it off only to reproduce a
  textbook Baum-Welch run.
* **Seed** — EM finds a *local* optimum. The initialisation is data-driven
  (k-means on the bins), so results are stable, but changing the seed and
  seeing the same answer is a cheap sanity check.

## Where else this lives

The same analysis is reachable without the GUI:

* `csg-hmm fit trace.csv --states 3` on the command line,
* the `hmm.fit` / `hmm.scan` RPC methods,
* `chisurf.plugins.core.hmm.core.fit_traces` in Python,

all of which use `chisurf.core.math.hmm` underneath. For photon-by-photon
kinetics (no binning) use **H2MM**; for an empirical-Bayes treatment of many
short FRET traces use **ebFRET**.
