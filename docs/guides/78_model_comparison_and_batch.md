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

**Main → Tools → Calculators**, entry **📉 F-test / χ²-max**. The manifest name
`Main:Tools:F-Test` is hidden from the menu. The window title is
*F-Calculator*. **?** (top right of the form) opens the formulas.

```{figure} figures/f_test_tool.png
:name: fig-f-test-tool
:width: 90%

The F-test loaded from two real fits of the donor-only decay with
**📊 From fit**: one exponential ($\chi^2_r = 11.12$, $\nu = 422$) against two
($\chi^2_r = 6.16$, $\nu = 420$), confidence 1.00000. The $\chi^2$-max panel
holds the two-exponential fit: at 95 % for 5 parameters, $\chi^2_\text{max} =
6.324$.
```

### Load the numbers

**📊 From fit ▾** lists every open fit, each with three targets:

* **→ F-test model 1 (χ²₁, n₁)** — the simpler fit: its $\chi^2_r$ and
  $\nu = $ points − free parameters.
* **→ F-test model 2 (χ²₂, n₂)** — the more complex fit.
* **→ χ²-max (χ²min, params, ν)** — one fit, for the upper-limit panel.

Loading model 1 recomputes the $\chi^2_2$ threshold; loading model 2 recomputes
the confidence. Typed values work the same way.

### F-test — compare two nested models

* **χ²(1)**, **n₁** — reduced $\chi^2$ and degrees of freedom of the simpler
  model.
* **χ²(2)**, **n₂** — the same for the more complex model.
* **confidence** — $F_\text{cdf}(\chi^2_{r,1}/\chi^2_{r,2};\ n_1, n_2)$.
  Editing **χ²(2)**, **n₁** or **n₂** recomputes it. Editing **confidence** (or
  **χ²(1)**) does the inverse: it solves for the **χ²(2)** the complex model must
  reach, $\chi^2_{r,1}/F_\text{ppf}(\text{conf};\ n_1, n_2)$, and writes it into
  **χ²(2)**, overwriting what you loaded.

Equal reduced $\chi^2$ gives 0.5 — no preference. The ratio is simpler over
complex, so it exceeds one exactly when the extra parameters help.

### χ²-max — upper limit from one fit

* **χ² min**, **params**, **ν (dof)**, **confidence** — a fit's minimum, its
  free-parameter count $p$, $\nu$, and a level.
* **χ² max** — $\chi^2_\text{min}(1 + p/\nu\,F(p, \nu; \text{conf}))$: every
  parameter set with $\chi^2_r$ below this is inside the joint confidence region.
  For the interval of *one* parameter set **params** to 1; the loaded value is
  the fit's full free-parameter count, which describes the joint region of all
  of them.

### Reading it: the case where the tests disagree

| comparison | $\chi^2_r$ | tool confidence | $\chi^2_{r,2}$ needed at 95 % | extra-SS $F$ ($p$) | $\Delta$AIC |
|---|---|---|---|---|---|
| 1 → 2 exp. | 11.12 → 6.16 | 1.0000 | 9.471 | 171 ($5\times10^{-55}$) | −2101 |
| 2 → 3 exp. | 6.16 → 6.02 | 0.5911 | 5.244 | 5.8 (0.003) | −66 |

The second lifetime is justified by every measure. The third is not justified by
the tool (0.59) but is by the extra-sum-of-squares test and by AIC. The tool's
variance-ratio form treats the two $\chi^2$ as independent; two fits of the same
data are not, so it is conservative and needs the ratio to exceed one by about
$3.3/\sqrt{\nu}$ (17 % here) regardless of how many parameters were added.
But neither verdict should be trusted on this decay: $\chi^2_r = 6$ means the
residuals are systematic misfit rather than noise, and the three-exponential fit
put $\tau_1$ on its lower bound (0.1 ns, amplitude 0.05) — a boundary
parameter the F reference distribution does not describe. Read the table as
"the third component is not resolved", and fix the model (IRF, scatter,
background) before asking again.

## Batch-Analysis

### Open the tool

**Main → Tools → Wizards**, entry **📋 Batch analysis**. The manifest name
`Main:Tools:Batch-Analysis` is hidden from the menu. Before opening it, load a
representative dataset, create the fit you intend to use, and **optimise it by
hand**: its parameter values — and which parameters are fixed — seed every run.

The wizard has five steps in a left rail; **Next ›** / **‹ Back** move along it
and steps can be visited in any order.

### 1. Welcome

What the tool does and the three preconditions above.

### 2. Loaded data (optional)

```{figure} figures/batch_analysis_loaded.png
:name: fig-batch-analysis-loaded
:width: 100%

The donor-only and donor–acceptor decays, already loaded in ChiSurf, ticked for
the batch.
```

A check-list of the datasets loaded in ChiSurf (the reserved *Global Dataset* is
left out). Hover a row for the file name and a preview of the curve;
**🔄 Refresh** re-reads the list after loading more.

### 3. Files & fit

* **Files to process** — **➕ Files**, **📁 Folder**, **🗄 Database**, drag and
  drop; **➖ Remove**, **🗑 Clear**. Each file is loaded with the reader guessed
  from its name, else the reader currently selected in ChiSurf, then fitted.
* **Template fit** — the fit whose parameters seed every run, listed by fit
  name (e.g. *Lifetime (magic angle only) - Decay_577D*).

Loaded datasets run first, then files, in list order.

### 4. Run

```{figure} figures/batch_analysis_run.png
:name: fig-batch-analysis-run
:width: 100%

Ready to run: two loaded datasets, no files, the two-exponential template fit
on the donor-only decay, and the results path.
```

* **Results CSV** — the output path; **…** browses. Left empty, **Run batch**
  asks for it.
* **▶️ Run batch** — for each item: restore the template's parameter values and
  fixed flags, assign the dataset (or load the file), run the fit, save its
  curves, grab a screenshot of the fit window, and record every parameter. A
  progress dialog counts the items; a message box lists the written files.

### 5. Results

One row per (item, parameter): **Run**, **Filename**, **Parameter**, **Fixed**,
**Value**, **Chi2r**.

### Where results go

Next to the chosen `results.csv`:

* `results.csv` — the table above, all items;
* `results.docx` — a report with each item's screenshot and the consolidated
  table (needs `python-docx`; without it the CSV and ZIP are still written);
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
* **Guide missing on both windows.** Neither `FTestTool` nor the batch wizard
  calls the shared help/guide seam, so their shipped `guide.json` tours are not
  reachable from the window yet.
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
* **Batch Results step is hard to read.** Values are printed at full float
  precision, so cells wrap, and the table sits in a short scroll box above empty
  space. Read the CSV instead.
* **Batch rows include placeholder parameters** — the unused third component
  slot (`a2`, `t2`, fixed) and derived averages appear in the table alongside
  the fitted values; filter on **Fixed = No** for the free ones.
* **The wizard rail hides the selected step's label** — the selected row is
  painted in the highlighted-text colour on an almost-white highlight, so only
  its icon is visible.

## See also

- Concept: {ref}`concept-fitting-objectives-f-test`;
  [parameter uncertainty](../concepts/parameter_uncertainty.md).
- Guides: {doc}`10_lifetime_anisotropy_fitting` for building a lifetime template
  fit; {doc}`77_phasor_calculator` for a fit-free look at the same decays.
- Tools: `chisurf/plugins/core/f_test/` (Calculators hub),
  `chisurf/plugins/core/batch_analysis/` (Wizards hub);
  `chisurf/core/math/statistics.py` for `f_test_confidence`, `f_test_chi2r` and
  `chi2_max`.
