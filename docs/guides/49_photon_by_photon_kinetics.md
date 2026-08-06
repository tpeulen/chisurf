# Photon-by-photon kinetics: rates without binning

This tool fits kinetic **rate constants** directly to the arrival time and
colour of every photon. It never bins, so it measures exchange that is faster
than any bin you could choose — and faster than a FRET histogram can even detect.

For the theory, and for the limits of what the method can honestly return, see
{ref}`concept-photon-by-photon-kinetics`.

## When you need it

A burst-wise FRET histogram shows a molecule switching faster than the burst
duration as one broadened peak. It cannot say how fast, and a fast switcher is
not distinguishable from a genuine intermediate state. {doc}`BVA <08_burst_variance_analysis>`
and {doc}`2CDE <01_fret_2cde>` will tell you that dynamics are present; this
tells you the rate.

## Open the tool

**Spectroscopy → Single-Molecule → Photon-by-photon kinetics**.

```{figure} figures/burst_gs_workspace.png
:name: fig-burst-gs-workspace
:width: 100%

Fitted on simulated photons from a molecule with known kinetics — 3000 and
1000 s⁻¹ between states at E = 0.25 and 0.75. The fit returns 2879 and 1027 s⁻¹
at E = 0.244 and 0.750, and a 256 µs relaxation time against a true 250 µs.
Left: where the photons come from and what scheme to fit. Right: the report,
with the fitted parameters, the states and the transition-time scan on tabs
below.
```

## Load the photons

1. Drop the `.bur` burst tables into the file list, or use **+ Files**.
2. Point **TTTR folder** at the raw files the burst table names (left empty, the
   burst table's own folder is used).
3. Check the **donor** and **acceptor** channel lists. These define the two
   colours; photons in neither list are dropped, which is how
   acceptor-excitation photons are correctly excluded from an ALEX measurement.
   The report states how many photons landed in each — check it.
4. Leave **Macro-time tick** at 0 to read it from the file header.

:::{warning}
Every fitted rate is proportional to the macro-time tick. A wrong value rescales
the whole answer with no other symptom — no bad fit, no warning, just rates that
are off by whatever factor the tick is wrong by. If you override it, be sure.
:::

**Min photons/burst** drops bursts too short to show a spread of interphoton
gaps. Ten is a sensible floor; such bursts contribute nothing and cost time.

## Try it without data first

Tick **Simulate** (under *Simulate instead*) and the tool generates photons from
a molecule with rates and efficiencies you set. This is the honest way to find
out what your photon budget can resolve, and the only way to know the right
answer while you are learning to read the output.

Set the simulated rates to what you expect, the photon rate and burst size to
what your instrument delivers, and see whether the fit recovers them. If it
cannot recover known kinetics from simulated data of your size, it will not
recover unknown kinetics from the real thing.

## Fit

Choose the number of **states** and press **▶ Fit**.

* **Initial rate** only needs the right order of magnitude — rates are optimised
  in log space, because plausible exchange spans four decades and a linear
  optimiser either crawls at the bottom of that range or steps over the top.
* **Fix efficiencies** holds the per-state efficiencies at their starting values
  and fits only rates. Do this when the efficiencies are known from a static
  measurement: rates and efficiencies are the most strongly correlated pair in
  the problem, and fixing them sharpens the rates considerably.
* **Optimiser** — Nelder-Mead is derivative-free and robust. L-BFGS-B is faster
  but leans on finite differences of a likelihood that is only piecewise smooth
  in its eigendecomposition.

## Read the result

The **report** gives the rates, the waiting times `1/k`, the per-state
efficiencies, the equilibrium populations and the relaxation time.

**Compare `1/k` with the burst duration.** If the waiting time is much longer
than a burst, most bursts contain no transition at all, and the rate is poorly
determined however confident the fit looks.

**The relaxation time is the observable combination.** For two states it is
$1/(k_{12} + k_{21})$ — the timescale a correlation measurement would report,
and the one to compare against FCS.

**Use the BIC to add states, not the log-likelihood.** An extra state always
fits better because it always has more parameters.

**States** shows where the fitted states sit on the efficiency axis and how much
population each holds. Check this against the burst-wise E histogram before
believing a narrow pair: two states closer together than the shot-noise width of
a burst cannot be separated, and the fit will still return two that look precise.

## Cross-check against H2MM

Tick **Cross-check with H2MM** (under *Extras*). The same photons are fitted by
the discrete-time H2MM engine, which shares no code and fits a per-tick
transition *probability* rather than a rate.

Agreement to a few per cent is real evidence that both are right. Disagreement is
worth chasing before you believe either. On the simulation above the two land
within 3 % on both rates and within 6 × 10⁻⁴ on the efficiencies.

The cross-check needs a tick, since H2MM is discrete-time, and it is derived from
the fitted relaxation time. If the report says the tick was **coarsened**, the
comparison is resolving less than the continuous-time fit does — H2MM caches a
propagator per distinct inter-photon gap, so an arbitrarily fine tick would
commit gigabytes. Treat a coarsened comparison as a sanity check rather than a
precise agreement test.

## The transition-time scan

Tick **Scan transition time** (two states only). After fitting, an explicit
intermediate is inserted that the molecule must cross, and the log-likelihood is
scanned against how long crossing takes — relative to the instantaneous model.

```{figure} figures/burst_gs_transition_time.png
:name: fig-burst-gs-transition
:width: 100%

The expected result: flat at zero while the crossing is too fast to leave a
trace, falling steeply once it is long enough to be visible. The flat region is
the answer — the crossing is faster than the point where the curve breaks. This
is an upper bound, and reporting it as one is the honest reading.
```

**A positive peak is the exception, not the goal.** Only a clear peak is a
measurement of a transition-path time, and it needs a likelihood-ratio test
before it is reported as one. The intermediate's efficiency defaults to the mean
of the two end states, which is an assumption about the transition path, not a
result.

## Decoding states

**Decode state path** computes the most likely state of every photon.

Use it to look at examples of what the fitted model implies. Do not use it to
count transitions: it assigns a definite state to every photon, including in
bursts that contain no evidence for any transition, and it carries no error bar.

## Headless

Everything above runs without a display:

```bash
burst-gs bursts.bur --data-dir ./raw \
         --donor 0,8 --acceptor 1,9 \
         --states 2 --scan-transition-time --cross-check-h2mm \
         --output kinetics.json
```

and, to see what a photon budget can resolve before spending beam time:

```bash
burst-gs --simulate --sim-rates 3000,1000 --sim-efficiencies 0.25,0.75 \
         --sim-bursts 250 --sim-photons 200 --sim-rate-khz 50
```

`--as-json` prints the whole result for a script to consume; the command exits
non-zero if the optimiser did not converge, so it can gate a pipeline. The same
three operations are available as RPC methods (`burst_gs.jobs.fit`,
`burst_gs.jobs.log_likelihood`, `burst_gs.jobs.transition_time_scan`) for a
client that already holds the photons.

## Caveats worth carrying

* The efficiencies are **apparent**, not corrected. Calibrate with
  {doc}`41_accurate_fret` and read the state efficiencies in the same frame.
* **Background photons are not modelled.** They have no state dependence, and
  they bias the fitted efficiencies toward each other.
* Exchange **slower than a burst** is a static mixture, and a static model is the
  right description there — the fit will tell you by driving the rates to zero.

## See also

- Tool: **Photon-by-photon kinetics** (`chisurf/plugins/burst/burst_gs/`).
