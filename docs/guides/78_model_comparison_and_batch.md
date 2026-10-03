---
type: Guide
title: 'Model comparison and batch fits'
description: Comparing two nested fits with the F-Test tool (variance ratio, χ² threshold, χ²-max) against the extra-sum-of-squares F and AIC, and repeating one pre-optimised template fit over many datasets with the Batch-Analysis wizard, its CSV/DOCX/ZIP outputs and its headless runner.
tags: [guides, fitting, statistics, tcspc, batch]
---

# Model comparison and batch fits

Two questions come after every fit. Does the model need the parameter you just
added — is the second lifetime real? And does the answer hold when the same
model is fitted to the next sample, and the one after? The **F-Test** tool
answers the first from two fits' $\chi^2$; **Batch-Analysis** answers the second
by running one template fit over many datasets and collecting the parameters in
one table.

For the statistics (the F distribution, its assumptions, AIC and BIC, the
$\chi^2$ threshold), see {ref}`concept-fitting-objectives-f-test`. For what an
interval on a parameter means, see
[parameter uncertainty](../concepts/parameter_uncertainty.md).

The example throughout is the repository's ibh donor-only decay
(`test/data/tcspc/ibh_sample/Decay_577D.txt`, 4096 channels of 14.1 ps rebinned
to 512, fit window channels 55–480) and its donor–acceptor partner
(`Decay_577D+577A+GTPgS.txt`), with the shared `Prompt.txt` as IRF.

## F-Test

### Open the tool

**Main → Tools → Wizards**, entry **Batch analysis** (the hub embeds this wizard).
The manifest name `Main:Tools:Batch-Analysis` is hidden from the menu. Before
opening it, load a representative dataset, create the fit you intend to use, and
**optimise it by hand**: its parameter values — and which parameters are fixed —
seed every run.

```{figure} figures/wizards_hub.png
:name: fig-wizards-hub
:width: 100%

The Wizards hub: the list on the left, the selected wizard on the right (here the
Anisotropy assistant; click **Batch analysis** for this one).
```

The wizard has five steps in a list on the left; a check mark means the step needs
nothing more from you. Click a step, or use **Back** / **Next**; steps can be
visited in any order, and **Finish** (last step) closes the window. **Help**
explains the steps and **Guide** walks through a batch, waiting for you to
operate each control it points at.

### 1. Welcome

What the tool does and the three preconditions above.

### 2. Loaded data (optional)

```{figure} figures/batch_analysis_loaded.png
:name: fig-batch-analysis-loaded
:width: 100%

The donor-only and donor–acceptor decays, already loaded in ChiSurf, ticked for
the batch.
```

A table of the datasets loaded in ChiSurf (the reserved *Global Dataset* is left
out). Click the check box in the **Use** column to include a dataset; hover a row
for its file name. **Refresh** re-reads the list after loading more and keeps the
ticks of datasets that are still there.

### 3. Files & fit

```{figure} figures/batch_analysis_files.png
:name: fig-batch-analysis-files
:width: 100%

Two files queued and the template fit chosen.
```

* **Files to process** — **Files**, **Folder** (every file below it), **Database**,
  or drop files and folders on the window; select a row and press **Remove** (or
  Delete), **Clear** empties the list. Each file is loaded with the reader guessed
  from its name, else the reader currently selected in ChiSurf, then fitted.
* **Template fit** — the fit whose parameters seed every run, listed by fit
  name. The list is read when the step opens; **Refresh fits** reads it again.

Loaded datasets run first, then files, in list order.

### 4. Run

```{figure} figures/batch_analysis_run.png
:name: fig-batch-analysis-run
:width: 100%

After the run: the written files under the progress bar.
```

* **Results CSV** — the output path; **Browse...** opens a save dialog. Left empty,
  **Run batch** asks for it first.
* **Run batch** — for each item: restore the template's parameter values and
  fixed flags, assign the dataset (or load the file), run the fit, save its
  curves and record every parameter. The bar counts the items (`i/total: name`)
  and a line under it lists the written files, or says why nothing ran (no data,
  no fit) or what failed.

### 5. Results

```{figure} figures/batch_analysis_results.png
:name: fig-batch-analysis-results
:width: 100%

One row per item and parameter, as in the CSV.
```

One row per (item, parameter): **Run**, **Filename**, **Parameter**, **Fixed**,
**Value**, **Chi2r**. Click a header to sort, type in the filter box to narrow the
rows, scroll with the wheel.

### Where results go

Next to the chosen `results.csv`:

* `results.csv` — the table above, all items;
* `results.docx` — a report with the consolidated table and, when the host can
  capture the fit window (the Qt window can), each item's screenshot (needs
  `python-docx`; without it the CSV and ZIP are still written and the window says so);
* `results_fit_results.zip` — each run's `fit.save(..., "csv", save_curves=True)`
  export, named `001_<item>`, `002_<item>`, …

The CSV is long-format; pivot it on **Parameter** to get one row per sample.
On the example, the template (two exponentials, donor-only optimum) gave:

| item | $\tau_1$ (ns) | $\tau_2$ (ns) | $\langle\tau\rangle_x$ (ns) | $\langle\tau\rangle_F$ (ns) | $\chi^2_r$ |
|---|---|---|---|---|---|
| Decay_577D | 0.96 | 4.20 | 3.99 | 4.15 | 6.16 |
| Decay_577D+577A+GTPgS | 0.39 | 3.83 | 1.62 | 3.29 | 34.4 |

The quenched donor shows up as a short component carrying most of the
amplitude, and the jump in $\chi^2_r$ says the two-exponential template does
not describe the donor–acceptor decay as well — the case where a batch
comparison is worth pairing with an F-test on that sample.

### Headless

The numeric work is `chisurf.plugins.core.batch_analysis.core.runner`, Qt-free.
`run_batch` needs a fitting client — an object with `get_fit_objects()`,
`set_parameter_value(parameter_name, value, fit_index)` and
`set_parameter_fixed(parameter_name, fixed, fit_index)`. The GUI installs the
RPC-backed one; a script can pass its own:

```python
import chisurf as cs
import chisurf.core.actions          # run_batch dispatches fit.set_dataset / fit.run
from chisurf.plugins.core.batch_analysis.core import runner

class DirectClient:
    """Write parameters in-process; the shipped client needs the running server."""
    def get_fit_objects(self):
        return list(cs.fits)
    def _p(self, name, i):
        return next(p for p in cs.fits[i].model.parameters_all if p.name == name)
    def set_parameter_value(self, parameter_name, value, fit_index):
        p = self._p(parameter_name, fit_index)
        if not p.fixed:
            p.value = value
    def set_parameter_fixed(self, parameter_name, fixed, fit_index):
        self._p(parameter_name, fit_index).fixed = fixed

cs.fits[:] = [template]                        # an optimised Fit
cs.imported_datasets[:] = [ds_d0, ds_da]       # datasets it can be assigned
items = runner.build_queue([ds_d0, ds_da], [])  # datasets, then file paths
results = runner.run_batch(0, items, fit_client=DirectClient(),
                           fit_export_dir="exports")
results.write_csv("results.csv")               # 32 rows for 2 items x 16 parameters
```

`template`, `ds_d0` and `ds_da` here came from
`chisurf.core.fluorescence.decay_fit_model.build_lifetime_fit` on the two ibh
decays. From a running session the CLI does the same over files:

```bash
csc batch-analysis run --list-fits
csc batch-analysis run --file a.txt --file b.txt --fit-index 0 -o results.csv
csc batch-analysis report results.csv --docx report.docx   # rebuild the report, headless
```

`run` needs the fitting client of a live ChiSurf session and stops with *No
fitting client* otherwise; `report` needs only the CSV.

The F-test numbers above, headlessly:

```python
import numpy as np
from scipy import stats
from chisurf.core.fluorescence.decay_fit_model import build_lifetime_fit
from chisurf.core.math.statistics import chi2_max, f_test_chi2r, f_test_confidence

def ibh(name):
    y = np.loadtxt(f"test/data/tcspc/ibh_sample/{name}", skiprows=9)[:, 1]
    return y.reshape(-1, 8).sum(1)                  # 4096 -> 512 channels
decay = ibh("Decay_577D.txt")
irf = np.loadtxt("test/data/tcspc/ibh_sample/Prompt.txt", skiprows=9)[:, 1]
irf = np.clip(irf - np.median(irf[-800:]), 0, None).reshape(-1, 8).sum(1)

fits = {}
for n in (1, 2, 3):
    fit = build_lifetime_fit(decay, bin_width=0.0141 * 8, irf=irf, n_components=n,
                             initial_lifetimes=[0.5, 2.0, 4.5][-n:],
                             fit_background=True, start_bin=55, stop_bin=480)
    fit.run()
    fits[n] = (fit.chi2r, fit.model.n_points - fit.model.n_free, fit.model.n_free)

(c1, nu1, _), (c2, nu2, k2) = fits[2], fits[3]
print(f_test_confidence(c1, c2, nu1, nu2))          # 0.591  (the tool)
print(f_test_chi2r(c1, 0.95, nu1, nu2))             # 5.244  (chi2r(2) needed)
F = (c1 * nu1 - c2 * nu2) / (nu1 - nu2) / c2        # extra-sum-of-squares F
print(F, stats.f.sf(F, nu1 - nu2, nu2))             # 5.8, 0.0033
c, nu, k = fits[2]
print(chi2_max(c, k, nu, 0.95))                     # 6.324
```

## Native sampler progress callbacks

For a BFF-backed fit, headless sampling can report progress without repeatedly
exporting the growing parameter chain:

```python
from chisurf.core.fitting.sampler_bff import sample_via_graph

# fit is an existing BFF-backed Fit; all proposals/objectives stay native.
def progress(done, total):
    print(f"{done}/{total}")

result = sample_via_graph(
    fit, fit.model, "metropolis", steps=600, seed=31,
    callback=progress,
)
```

An inspectable two-argument callback receives counters only; the final return
still contains the complete result. To update a plot at segment boundaries,
use `def progress(done, total, result=None): ...`. It receives the same partial
result dictionary as before, including `parameter_values`; this costs more than
counter-only progress. Opaque native two-argument callables retain their legacy
fallback. Exceptions raised inside a Python callback are propagated, not
silently treated as an argument mismatch or retried.

Native runs release the GIL so background progress and MCTS cancellation can
run. This does not make shared fit/graph mutation safe: keep one worker as the
owner of a running sampler/search. These changes do not alter the posterior,
recording policy, simulation budget or convergence requirements.

## Using it well

**Compare fits over the same window and weights.** $\nu$ comes from the fit
range; two fits over different channel ranges are not nested, whatever their
models.

**Get $\chi^2_r$ near 1 first.** Every test here treats $\chi^2$ as noise. With
systematic misfit, fix the instrument model before testing the physical one.

**Distrust a component on its bound.** A lifetime at its lower limit or an
amplitude near zero is not a resolved species, whatever the confidence says.

**Batch from a good template, and look at every fit.** Every item starts from
the template's values, so a template far from some samples' optimum leaves
those fits in a local minimum with no warning. The DOCX screenshots exist so
each fit can be eyeballed; a jump in **Chi2r** is the first thing to scan for.

**Keep one experiment type per batch.** One template cannot fit TCSPC decays and
FCS curves; nothing stops you from ticking both (see *Known defects*).

## Known defects

* **F-Test confidence is the variance-ratio form.** For nested fits of the same
  data it is conservative; on the example it gives 0.59 where the
  extra-sum-of-squares test gives $p = 0.003$. There is no readout of the
  extra-sum-of-squares $F$ or its $p$-value.
* **Guide missing on the F-Test window.** `FTestTool` does not call the shared
  help/guide seam, so its tour is not reachable from the window yet (the batch
  wizard's is: **Guide**).
* **Batch: parameter restore can fail silently.** The shipped fitting client
  writes parameters only over RPC and returns `{"ok": False}` when the server is
  not reachable; `restore_parameters` ignores the result, so each item would
  then start from the previous item's optimum rather than the template.
* **Batch: headless `run_batch` crashes** with `module 'chisurf.core' has no
  attribute 'actions'` unless `chisurf.core.actions` was imported first (the
  import in the example above).
* **Batch: mixed experiment types are not rejected.**
  `runner.datasets_have_mixed_types` exists and says mixing is "rejected
  upstream", but nothing calls it.
* **Batch rows include placeholder parameters** — the unused third component
  slot (`a2`, `t2`, fixed) and derived averages appear in the table alongside
  the fitted values; filter on **Fixed = No** for the free ones.

## See also

- Concept: {ref}`concept-fitting-objectives-f-test`;
  [parameter uncertainty](../concepts/parameter_uncertainty.md).
- Guides: {doc}`10_lifetime_anisotropy_fitting` for building a lifetime template
  fit; {doc}`77_phasor_calculator` for a fit-free look at the same decays.
- Tools: `chisurf/plugins/core/f_test/` (Calculators hub),
  `chisurf/plugins/core/batch_analysis/` (Wizards hub);
  `chisurf/core/math/statistics.py` for `f_test_confidence`, `f_test_chi2r` and
  `chi2_max`.
