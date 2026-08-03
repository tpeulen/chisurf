---
type: PRD
prd: "72"
title: "PRD-72: Non-breaking ChiSurf groundwork for 2D MFD fitting"
description: The enabling changes ChiSurf needs before a 2D MFD fit can be written — burst-folder reading with auto-resolved photon sources, a preparation core with plugin and reader surfaces over it, and the mean micro time in the burst tables — each additive, each with its own acceptance, none of them the fit itself.
status: in-progress
phase: "unassigned"
resource: chisurf/core/fluorescence/mfd/
tags: [prd, mfd, burst, groundwork, fio]
timestamp: '2026-07-29T00:00:00Z'
---

# Summary

[PRD-71](prd-71.md) is the design for fitting kinetic models to the 2D MFD burst
histograms. This PRD is the **groundwork underneath it**: the changes ChiSurf
needs so that such a fit *can* be written, each one useful on its own, each one
additive, and none of them the fit. Splitting them out keeps a long modelling
effort from hiding a set of small, testable infrastructure changes that other
work wants anyway — burst folders that know where their photons are, a mean micro
time that exists without a lifetime fit, and one preparation path shared by the
GUI, the CLI, the RPC service and the experiment reader.

The rule for everything here: **additive, or explicitly justified.** A change
that alters what an existing caller sees needs its own reason, its own test, and
a note in this document — nothing lands as a silent behaviour change.

# Status

In progress. Items 1–5 have landed — the burst-table column, the preparation core,
loud source resolution, the `PhotonBursts` loader and the nuisance measure. Items
6–9 (the experiment and its reader, the plugin's four surfaces, model registration,
and whatever chiplot is missing) are specified and next.

Parent: [PRD-71](prd-71.md). Related: [PRD-09](prd-09.md) (the layered-plugin
shape used for item 7), [PRD-38](prd-38.md)/[PRD-40](prd-40.md) (model and view
spec), [PRD-61](prd-61.md) (priors), [PRD-64](prd-64.md) (chiplot).

# Items

## 1. `.bur` carries the mean micro time — ✅ landed

Both writer paths in `chisurf/core/fio/fluorescence/burst.py` emit
`Mean Microtime (<detector>) (ns)`. A burst folder had no mean micro time
anywhere: `.bur` is macro-time only, and the nearest thing — a `bg4` companion —
holds burst-wise *fitted* lifetimes, a biased estimator at the 50–500 photons a
burst has. Anything wanting a per-burst lifetime axis had to reopen the photon
streams or accept the biased one.

Additive by construction: appended after every pre-existing column and before the
trailing blank, so a reader keying on leading positions is unshifted and the
companion reader's trailing-blank strip still finds a blank; nanoseconds rather
than raw channels, because a raw value is meaningless without the header that
produced it; and the shared `-1.0` sentinel when a detector has no photons or the
header offers no positive resolution, rather than a number in unknown units.

*Acceptance*: `test/fio/test_burst_mean_microtime.py` — exact means, both sentinel
paths, agreement between the two writers, positional non-breakage, and both the
ChiSurf and companion readers. Landed with 430 burst-plugin and 335 fio tests
green.

*Also documented, not changed*: `Mean Macro Time (ms)` and
`Mean Macrotime (<detector>) (ms)` are the **first/last midpoint**, not the photon
mean, in both writers. Inherited from the reference format, so the module
docstring says so rather than the value moving under everything that consumed it.

## 2. A preparation core — ✅ landed

New package `chisurf/core/fluorescence/mfd/` with `prepare.py`: burst folder →
fit-ready arrays (`BurstPreparation` — per-detector counts, observation spans in
seconds, mean micro time in nanoseconds, whole-burst duration, photon indices, the
row positions in the burst table). Resolve the photon sources, read the `.bur`
columns, load the photons, compute `⟨t⟩` per channel group where the column is
absent. Qt-free, no plugin imports, headless-testable.

Two things the design did not anticipate, both found by running it against a real
folder and both now enforced rather than assumed:

* **The photon-index convention differs between folder vintages.** `Number of
  Photons` is `Last − First + 1` in folders written by the current writer and
  `Last − First` in older ones. Reading one with the other's convention adds a
  stray photon to every burst — too small to fail an assertion, large enough to
  move a mean micro time and, through it, a fitted lifetime. It is now *detected*
  per folder (`PhotonIndexConvention`, with the agreement reported) and honoured.
* **Detectors are not a partition.** An acceptor-excitation detector is a
  micro-time window *inside* the acceptor detector, so the same photon belongs to
  both, and reproducing the writer's columns needs independent per-detector masks
  rather than the winner-takes-all photon assignment of `stream_index_arrays`
  (which stays correct for the photon-by-photon layout, where a photon counted
  twice would be a duplicated observation).

Because a channel definition that is merely *plausible* would attribute photons to
the wrong colour and make every downstream number wrong-but-believable, the
definition is **verified against the count columns** whenever the photons are open,
and a detector that fails is marked unverified and refused at use
(`BurstPreparation.require_verified`) instead of silently participating.

*Acceptance*: `test/fluorescence/test_mfd_prepare.py` — the shipped
`bh_spc132_sm_dna` folder (a legacy folder with no mean-micro-time column) in,
typed arrays out; the `⟨t⟩` computed from the photons reproduces what the writer's
own helper would have written for the same photon selection, which is the
compatibility path exercised rather than assumed; counts and spans agree with the
table; the conventional two-colour definition verifies at 1.000 and the
acceptor-excitation detector does not, until its window is given.

## 3. Photon-source resolution that fails loudly — ✅ landed

The chain is manifest → legacy `.mti` sidecar → a file of that name beside the
analysis folder, with every open going through `chisurf.core.fio.staging.open_tttr`
(the one seam that resolves container types and applies per-channel corrections),
and **a zero-photon read raising** `UnresolvedPhotonSource`.

*Also fixed in the same change*: `chisurf/core/fluorescence/burst/photons.py`'s
`load_tttrs_for_dataframe` opened `tttrlib.TTTR(path, "SPC-130")` directly —
bypassing the staging/LUT seam and hardcoding a container type, so these files were
read with *un-linearized* micro times while every other reader produced linearized
ones. A lifetime shift, not an error. Routed through `open_tttr`.

*Acceptance*: an unresolvable source raises naming the key and every place that was
searched; a zero-photon read raises rather than returning an empty stream.

## 4. Burst folder → `PhotonBursts` — ✅ landed

`prepare.photon_bursts` builds the packed layout of
`chisurf/core/fluorescence/burst/gopich_szabo.py` from a prepared folder, returning
the per-burst micro times and the surviving row positions alongside it, so the
photon-bearing scoring sources have one loader instead of each writing their own.

*Acceptance*: per-burst offsets reproduce the `.bur` per-detector counts exactly for
the shipped folder (2980 bursts, 225 358 photons), and asking a preparation built
without photons for them raises rather than returning nothing.

## 5. D12 straight from the `.bur` columns — ✅ landed

`P(S, t_G, t_R)` needs no new format: `Duration (d) (ms)` *is*
`macro[last] − macro[first]` for that detector's photons, and
`Number of Photons (d)` gives `S`, both with `-1.0`/`0` sentinels already written
for a detector a burst has nothing in. `prepare.nuisance_measure` is that pure
function; `NuisanceMeasure.binned` compresses it onto a grid so the histogram
source's cost stays independent of the number of bursts.

The `-1.0` span is kept as a **mask** (`span_is_sentinel`) rather than folded into
the value: a burst with fewer than two photons in a channel has no *measurable*
span, which is not the same statement as a zero-length observation, and the forward
model has to be able to tell them apart.

*Acceptance*: sentinel rows are excluded and *counted* in the returned summary, so
a folder where half the bursts have no red photons cannot look like a clean one;
binning conserves the burst total exactly.

## 6. An `mfd` experiment and its reader

`chisurf/core/experiments/mfd/` with `reader.py`, following the per-experiment
package shape already used by `fcs`, `tcspc`, `pda2c`, `deer`, `pch`. The reader
opens a burst folder and calls `prepare.py` directly — **not** through the plugin.
It is data-loading infrastructure on the path for every burst dataset, and routing
it through plugin discovery would let a disabled plugin present as a data-loading
failure.

Registration is additive: a new packaged section in `experiment_configs.yaml`
appears for everyone, because a user's copy simply lacks it. The hazard documented
in `chisurf/core/experiments/__init__.py` is the *opposite* case — a stale user
section shadows the packaged one, since merging replaces lists rather than
extending them — so renaming or removing a section later requires a
`SUPERSEDED_SECTIONS` entry. Nothing here renames anything.

*Acceptance*: a burst folder loads as an MFD dataset with its photons resolved,
and every pre-existing experiment still lists its own readers and models.

## 7. A preparation plugin with four surfaces

GUI, CLI, API and RPC over `prepare.py`, following the layered-plugin shape of
[PRD-09](prd-09.md), so a folder can be prepared and inspected on its own. Purely
additive — a new plugin directory and manifest.

*Acceptance*: headless CLI path first, per the project rule that every feature has
one; the GUI rendered and inspected, not assumed.

## 8. Model registration and data filtering

The MFD models must appear only for MFD datasets, through the existing
`Model.supports_data` mechanism rather than a parallel list. Additive, and it is
the mechanism a previous change already established for exactly this.

*Acceptance*: the model list for a TCSPC or FCS dataset is unchanged; the MFD
models appear only where they apply.

## 9. Whatever chiplot is missing for a 2D histogram

`Canvas.image` exists, so the 2D histogram itself is expressible. What still needs
checking is colour mapping, axis scaling on a binned image, and drawing the
analytic overlay lines on top of it. **Anything missing is added to chiplot**, not
reached around: pyqtgraph is a backend behind the seam, and code that falls
through gets a passthrough warning rather than an error, which is exactly how a
migration never finishes. `chiplot.passthrough_gaps()` names what fell through in
a session — that is the worklist, not an excuse.

*Acceptance*: the 2D plot and its overlay lines draw with no passthrough warning.

## 10. Nothing to build: the statistic and the priors

Recorded so nobody builds them twice. The `2I*` Poisson deviance is already a
`noise_model` option on the shared fit layer (`chisurf/core/fitting/fit.py`), not
something PDA owns privately. The per-parameter priors that the shared σ needs are
[PRD-61](prd-61.md), already landed. The fittable rate matrix is the shared group
in `chisurf/core/fitting/kinetics.py` — `K[target, source]`, not a private copy.

# Deliberately not in scope

The fit itself: the pattern moments, the non-central-chi `p(R)`, the
occupation-time propagator, the three scoring sources, and the milestone gates.
Those are [PRD-71](prd-71.md), and none of them can be validated until it has a
real static burst measurement to run against — which the tree does not contain.

# Order

1 (done) → 2 + 3 together (the core is what needs the resolution chain) → 5 (pure,
testable immediately) → 4 → 6 → 8 → 7 → 9. Items 5 and 9 are independent of the
rest and can move earlier if convenient.
