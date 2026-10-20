---
type: Guide
title: 'QuEst Analysis: quench scale and stickiness from measured site lifetimes'
description: Fitting how strongly a dye is quenched on a protein and near which residues it lingers, from lifetimes measured at many labelled sites and free-dye titrations, on the Analysis page of QuEst; the MalE demo, the presets and stages, reading the result tabs, csc quest analyse, the Python API and RPC.
tags: [guides, quenching, inference, fitting, tcspc, headless]
---

# QuEst Analysis: quench scale and stickiness from measured site lifetimes

**Structure → Computation → QuEst** (💧), page **Analysis** in the strip at the top of the
window (`chisurf/plugins/quenching_estimator/gui/analysis_card.py`). The *Forward model* page
({doc}`80_quenching_estimator`) predicts the lifetime of a dye at one site from the structure; this
page runs the other way. From lifetimes measured at many sites and the free dye titrated against
amino acids, it fits the dye's quench scale $\kappa$ (contact quenching relative to the
titrations), its stickiness $s$ per residue group, the contact offset $\delta$ and the shielding
term $\Delta\tau_\text{shield}$. Theory: {ref}`concept-quenching-inference`.

**What you need:** nothing for the demo. For your own data, a folder with three CSV tables (step 1)
and a structure per state.

## 1. Load the data

Press **Load example**. It loads the shipped MalE data set (`examples/male/`): nine sites, the
dyes AF488, Cy3B and Atto655, apo (PDB 1OMP) and holo (PDB 1ANF), 0–100 % D₂O, and sets the
*Quick* preset. **Data folder…** reads your own folder with the same layout:

| file | content |
|---|---|
| `tcspc_fit_results.csv` | lifetime per dye, site, state and D₂O fraction |
| `amino_acid_quenching_flt.csv` | titration points: free dye, amino acid, concentration, $\tau$ |
| `titration_summary.csv` | free-dye lifetimes $\tau_0$ per dye and solvent |

The **Data** tab is filled as the folder is read, before any fit: the Stern–Volmer points with
their posterior slopes, the day-to-day error all titrations share, the $K_{SV}$/$k_q$ table, the
site lifetimes and the water quenching per site. **kQ per dye** shows the contact rate per
quenching residue, scaled from the reference chemistry by the titrations.

```{figure} figures/111_quest_analysis_data.png
:name: fig-quest-analysis-data
:width: 100%

The Analysis page after **Load example** (1280 × 820): *State* reads 64 site lifetimes and
17 titrations. The Data tab shows the AF488 Stern–Volmer lines (Trp steepest, Phe flat), the
hyper-posterior of the relative and absolute day error, and the start of the $K_{SV}$/$k_q$ table.
```

## 2. Choose the settings

| control | meaning |
|---|---|
| **Preset** | *Quick*: 8 searches, short iterations, a first look (about 20 min on a desktop). *Full*: 64 searches, the stored analysis (hours on a desktop; the stored run took 24 min on 44 cores). |
| **Stages** | *all*, or one stage plus what it needs (below). |
| **Workers** | worker processes for the searches; *every CPU* by default. The numbers do not depend on it. |
| **Profile likelihood** | also refit each data set at fixed values of $\kappa$; about one joint fit per point. |

The stages (`settings/analysis/stages.yaml`):

| stage | data | role |
|---|---|---|
| A | AF488, Cy3B in H₂O | $\kappa$ and $s$ where water does not quench |
| B | Atto655 in D₂O alone | the same model without water |
| naive_h2o | B's fit + the free-dye water rate everywhere | predicts H₂O; expected to fail |
| C | Atto655 in D₂O and H₂O | water term $w\,k_{q,w,\text{free}}\,e$, no new parameter |
| summary | A, C | one line per dye |

A and C are views of one graph, so running A solves C as well. Every fit setting is declared in
`settings/analysis/fit_parameters.yaml`; the presets are differences to it.

## 3. Run

Press **Run**. It first builds the site table of every measured site: the dye's accessible volume
at the dye's linker length, the residues and quenchers around each position, and its water
exposure. Tables are cached under the settings folder
(`cache/quenching_estimator/site_tables`), so only the first run pays for them (about 10 s
each, 46 for MalE). Then the stages run in the background. The bar names the table or search in
progress; **Cancel** stops at the next checkpoint. The tabs stay readable meanwhile.

```{figure} figures/111_quest_analysis_running.png
:name: fig-quest-analysis-running
:width: 100%

A first run, building site table 41 of 46 (HOLO 186, Atto655). The kQ per dye tab is open: the
contact rate per quenching residue for each dye, with its error.
```

**Site tables** lists one row per built table (positions, distinct feature rows, mean exposure,
neighbours); select a row for its exposure histogram. **Build site tables** builds them without
fitting.

```{figure} figures/111_quest_analysis_sites.png
:name: fig-quest-analysis-sites
:width: 100%

Site tables after the build: 46 rows, APO 233 (AF488) selected. Most of its positions are almost
fully exposed to water (exposure near 1).
```

## 4. Read the fit

**Fit** shows one stage and data set (**Stage**, **Data set**): the result in words, measured
against predicted lifetime (outliers ringed, free-dye $\tau_0$ dashed), the estimates with 68 %
intervals, the leave-one-site-out $|z|$ with the outlier line at 3, the $\kappa$ profile, the
estimates and predictions tables, and the titration slopes before and after the fit.

```{figure} figures/111_quest_analysis_fit.png
:name: fig-quest-analysis-fit
:width: 100%

Fit, stage B, Atto655 in D₂O, from the quick run on the shipped demo. The text block states fit
quality, quench strength, stickiness, contact distance, dark fraction, shielding and outliers;
below it the parity plot (four sites ringed) and the forest of estimates.
```

A note in the estimates, *not determined*, *at the edge of its range* or *other regions
possible*, means the data do not fix that parameter: read the interval, not the value. Quick
searches can stop at a bound; a number you report comes from *Full*.

**Water** (stage C) compares the water access per site, model against measured, shows the
time-weighted exposure of the visible dye at two sites, and $\kappa$ from B against C.
**Summary** gives $\kappa$ and $s$ per dye on log axes, and one table row per dye.

```{figure} figures/111_quest_analysis_water.png
:name: fig-quest-analysis-water
:width: 100%

Water, from the same quick run: model against measured water access per site (r with and without
site 322), the table, and the visible dye's exposure histogram at sites 72 and 186.
```

```{figure} figures/111_quest_analysis_summary.png
:name: fig-quest-analysis-summary
:width: 100%

Summary, from the same quick run: $\kappa$ per dye and $s$ per residue group on log axes; the
*scale_note* column flags estimates at the edge of their range.
```

The numbers in these figures are the quick preset's output on the shipped demo when they were
taken. The reference numbers of the full 64-start analysis, and what they do and do not show, are
in the MalE results table of {ref}`concept-quenching-inference`.

**Write results…** writes every declared table as CSV (`<stage>.<table>.csv`, columns declared in
`settings/analysis/result_columns.yaml`), `summary.json` and `report.md`.

## 5. Headless

The CLI is `csc quest analyse`; it writes the same tables, plus `run.json`. Stage B at the quick
preset, with two searches and no profile (a few minutes once the site tables are cached):

```bash
csc quest analyse --quick --stage B --set n_starts=2 --no-profile -o out/
ls out/      # B.estimates.csv ... B.titration_slopes.csv  report.md  run.json  summary.json
```

Without `-o` the run goes into a run directory under the per-user artefact root, which
`csc quest runs` lists. Other forms:

```bash
csc quest analyse --quick --stage B --set n_starts=2 --no-profile \
    --format csv --table B.estimates --no-save          # one declared table on stdout
csc quest analyse --quick --stage A --stage C --format json --no-save   # summary JSON (slow: the joint graph)
csc quest analyse --stage all -o out/                   # the full run (hours)
```

`--set KEY=VALUE` replaces a declared fit setting (dotted keys are nested:
`--set profile_likelihood.points=5`); `--workers 1` runs in process; `--data <folder>` reads your
own three CSVs; `--structure APO=<file>` replaces a state's structure; `--tables tables.json`
(`{"APO:72:20.12": "site.npz"}`) uses stored site tables; `--cache-dir` moves the cache.

From Python (the facade `chisurf.plugins.quenching_estimator.api.local`):

```python
from chisurf.plugins.quenching_estimator.api import local as quest

run = quest.analyse("B", preset="quick", fit_overrides={"n_starts": 2}, profile=False,
                    output="out")
result = run["result"]                        # an AnalysisResult
print(result.stages["B"].text)                # the report text
estimates = result.stages["B"].tables["estimates"]
print(estimates[["parameter", "value", "low_68", "high_68", "note"]])
```

The searches run in worker processes; a plain script needs no `if __name__ == "__main__":` guard.

In the background, with progress and cancel:

```python
job = quest.analyse("all", preset="quick", background=True)["job_id"]
quest.job(job)["progress"]        # percent; "status" ends "completed" or "cancelled"
quest.analysis_result(job)        # once completed: the result, or the stored run's summary.json
quest.cancel_job(job)             # stops at the next checkpoint; the result then raises "cancelled"
```

Over RPC the methods are `quest.analysis.template` (stages, presets, fit settings and result
tables, from the YAML), `quest.analysis.run` (blocking, or `background: true`; `continue_from`
reuses a finished job's solved graphs), `quest.analysis.result` and `quest.analysis.site_table`,
with `quest.jobs.get` / `quest.jobs.cancel`; see {doc}`../reference/plugins/quenching_estimator`.

## Using it well

**Quick is a first look.** Its searches can end before the best fit or at a bound. Use *Full* for
numbers you report.

**The structures decide the answer.** Site tables come from one rigid structure per state at each
dye's linker length; a label that changes the protein locally is outside the model.

**Few sites, many parameters.** Nine sites × two states leave several parameters not determined;
the notes say which. The leave-one-out plot shows which sites the fit hangs on.

**Error bars are Laplace.** They come from the curvature at the best fit; the profile likelihood
shows where that is too narrow.

## See also

- Theory: {ref}`concept-quenching-inference`; the forward model: {ref}`concept-dye-quenching`.
- Tool: the Forward model page, {doc}`80_quenching_estimator`.
- Method: {cite}`peulen2017`.
