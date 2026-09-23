---
type: Guide
title: 'Decay Analysis window, Lazy Lifetime Analysis and synthetic decays'
description: The Spectroscopy:Decay Analysis window and its five panels; the Lazy Lifetime Analysis fit (automatic range, background, IRF shift and component count) and what its component-count scan really tests; and the Synthetic Decay Generator for decays whose answer is known.
tags: [guides, tcspc, lifetime, decay, simulation]
---

# Decay Analysis window, Lazy Lifetime Analysis and synthetic decays

Three tools around a single TCSPC decay. **Decay Analysis** is the window that
collects the decay tools. **Lazy Lifetime Analysis** (LLTF) fits one decay with
a discrete multi-exponential model and makes the choices that are usually made
by hand: fit range, background, IRF shift and, optionally, the number of
components. The **Synthetic Decay Generator** produces decays from parameters
you choose, the only data on which LLTF's choices can be checked.

:::{admonition} Theory
:class: seealso
Reconvolution, the nuisance terms and the two average lifetimes are in
{ref}`concept-tcspc-lifetime`. How to decide the number of components is
{ref}`concept-tcspc-model-selection`; how synthetic decays are sampled and what a
photon budget allows is {ref}`concept-tcspc-synthetic-decays`. Weighting by the
data (Neyman $\chi^2$), which LLTF uses, is discussed in
{ref}`concept-fitting-objectives`.
:::

## Open the tools

| Tool | How to open it |
|---|---|
| Decay Analysis | **Spectroscopy → Decay Analysis** (marked experimental) |
| Lazy Lifetime Analysis | panel **3. Lazy Lifetime Analysis** of Decay Analysis; it has no menu entry of its own. Headless: `csc lltf fit` |
| Synthetic Decay Generator | no menu entry and no hub. From the console, `SyntheticDecayTool().show()` (`chisurf.plugins.fluorescence_decay.synthetic_decay.gui.tool`); headless `csc synth-decay`, or the `synthetic_decay.compute*` RPC methods |

The same generator also drives the synthetic components of the FCS Filter
Calculator ({doc}`17_filtered_fcs`) and the decay dialog of the simulated TCSPC
acquisition device, through a separate editor.

## The Decay Analysis window

```{figure} figures/decay_analysis_hub.png
:name: fig-decay-analysis-hub
:width: 100%

**Spectroscopy → Decay Analysis**, opened on its first panel. The rail lists the
five tools in the order they depend on each other; **Next ▶** and **◀ Back**
walk it, **Guide** and **?** (top right) belong to the window.
```

| Panel | What it does | Guide |
|---|---|---|
| 1. IRF Estimation | estimates an IRF from the decay itself when none was measured | {doc}`irf_estimation` |
| 2. MaxEnt MEM | lifetime or FRET-distance distribution without a component count | {doc}`62_maxent_decay` |
| 3. Lazy Lifetime Analysis | discrete multi-exponential fit of one decay file (below) | this page |
| 4. Histogram-Microtime | builds the decay from a TTTR photon file | {doc}`73_tttr_decay_and_correlation` |
| 5. VV/VH G-Factor | $G$ from a pair of polarized decays | {doc}`10_lifetime_anisotropy_fitting` |

Each panel is the standalone tool embedded unchanged; a panel keeps its state
while you move along the rail. Nothing is passed from one panel to the next: an
IRF estimated in panel 1 has to be saved and loaded into the fit that uses it.

## Lazy Lifetime Analysis

### What it fits

One decay file and one IRF file, both text with a time column (ns) and a count
column. The model is the reconvolved lifetime spectrum of
{ref}`concept-tcspc-lifetime`, with two offsets and a sub-channel shift:

$$
y_k^\text{model} = s\,\big[(\mathrm{IRF}_{\delta} + b_\text{IRF}) \otimes \textstyle\sum_i x_i e^{-t/\tau_i}\big]_k + b,
\qquad \textstyle\sum_i x_i = 1,
$$

with $\mathrm{IRF}_\delta$ the IRF shifted by $\delta$ (linear interpolation),
$b_\text{IRF}$ a constant added to the IRF, $b$ the decay background and $s$ a
scale solved in closed form at every step. Amplitudes are renormalized to sum
to one, so the table reports species fractions $x_i$ (take the intensity
fractions as $x_i\tau_i/\sum_j x_j\tau_j$). There is no scatter term. The
residuals are weighted by $1/\sqrt{\max(y_k,1)}$ and minimized with
Levenberg–Marquardt; lifetimes are bounded to 0–10 ns.

"Lazy" means that the choices around the fit are made by rules rather than by
hand, in this order:

1. **Fit range.** The start is the last channel before the peak whose count is
   below `start_fraction` × peak (or the peak itself, `start_at_peak`). The stop
   is where the cumulative counts from the start reach `area` of the total, then
   moved back to the last channel with at least `count_threshold` counts.
2. **Background.** The mean of the last `average_window` channels of the whole
   decay, used as the starting value of $b$.
3. **IRF shift.** $\chi^2$ is evaluated on a grid of
   `irf_time_shift_scan_n_steps` shifts over `irf_time_shift_scan_range` (ns) and
   the best one starts the fit; the fit then refines $\delta$ freely.
4. **Number of components** (only with *Find Optimal*). Models with 1 … *Max*
   lifetimes are fitted and one is chosen by the rule described under
   *The component-count scan*.

### Settings

```{figure} figures/lltf_results.png
:name: fig-lltf-results
:width: 100%

Panel 3 after **Fit** on the plugin's example donor decay (`example/5-44_D0.dat`
with `IRF_D0.dat`), two lifetimes, default settings: 1.350 ns (0.130) and
4.005 ns (0.870), $\chi^2_r = 1.56$ over 4.57–44.1 ns. The dashed lines are the
automatic fit range; the residuals keep a spike on the rising edge.
```

*Input Files*

- **Decay File / IRF File — Load…** — one file each. Only the first two columns
  are read (time, counts), whitespace-delimited, `#` lines skipped. The time
  step is taken from the first two time values and must be in ns.
- **Config File — Edit…** — the YAML file holding every setting not on the
  panel (table below). **Edit…** opens it in the settings editor
  ({numref}`fig-lltf-settings`); **Save** there writes it back.
- **Output Directory — Select…** — where the result files go; defaults to the
  decay file's folder.

*Fitting Options*

- **Number of Lifetimes** — 1–6, used when *Find Optimal* is off.
- **Find Optimal Number of Lifetimes** — run the component-count scan.
- **Max Lifetimes to Try** (2–6) and **Probability Threshold** (0–1) — the
  scan's range and its acceptance level.
- **Verbose Output** — print every step into *Analysis Output*.

**Fit** (and *Analysis → Fit…*) runs `lltf fit` in a child Python process, so
the window stays responsive; **Stop Process** on the *Analysis Output* tab
terminates it.

```{figure} figures/lltf_settings.png
:name: fig-lltf-settings
:width: 70%

**Edit…** — the configuration file in the settings editor. The file is the
plugin's `lifetime_settings.yml`, copied once into the system temp folder.
```

| Key | Default | Meaning |
|---|---|---|
| `analysis_range_parameter.start_fraction` | 0.005 | start where the rise crosses this fraction of the peak |
| `…start_at_peak` | false | start at the peak instead |
| `…area` | 0.9999 | stop at this fraction of the cumulative counts |
| `…count_threshold` | 10 | …then back to the last channel with this many counts |
| `…skip_first_channels`, `…skip_last_channels` | 0 | hard limits on the range |
| `estimate_background_parameter.enabled` | true | estimate $b$ from the tail before fitting |
| `…average_window` | 10 | channels averaged for that estimate |
| `…initial_irf_background`, `…fit_irf_background` | 0, true | start and free/fixed of $b_\text{IRF}$ |
| `estimate_irf_shift_parameters.enabled` | true | run the shift grid |
| `…apply_shift` | true | use a shifted IRF at all |
| `…irf_time_shift_scan_range`, `…_n_steps` | −8…8 ns, 20 | the grid (0.84 ns steps) |
| `lifetime_fit_parameter.randomize_initial_values.min_lifetime`, `max_lifetime` | 0.2, 5.0 ns | starting lifetimes of the scan, spaced evenly between these |
| `…randomize_initial_values.enabled` | false | a fixed-$n$ fit starts from these too; off, it starts from 1, 3, 5, … ns (the scan always uses them) |
| `…amplitude_variation` | 0.5 | random spread of starting amplitudes |
| `…plot_probabilities`, `…plot_weighted_residuals` | true | extra Matplotlib figures during the scan (see *Known defects*) |
| `pile_up_correction.enabled`, `rep_rate` (MHz), `dead_time` (ns), `measurement_time` (s) | off, 80, 85, 60 | Coates-type pile-up applied to the model |

The file's `lifetime_fit_parameter` block also holds `find_optimal`,
`maximum_number_of_lifetimes`, `prob_threshold` and `selection_mode`. With
*Find Optimal* ticked, the panel's values override the first three and
`selection_mode` is forced to `lower` (below). Leave `find_optimal` false in the
file: set true, it runs the scan even when the box is unticked.

### Reading the output

*Analysis Output* shows the command and the child process's log; the last block
is a summary with the lifetimes, IRF shift, decay background and $\chi^2_r$.
When the process ends successfully the panel switches to *Results*: a table of
species fractions and lifetimes, the total $\chi^2$ (labelled *Chi-square*), the
fit range and the component count, above the decay (data, model over the fit
range, IRF scaled to the decay maximum) and the weighted residuals.

```{figure} figures/lltf_output.png
:name: fig-lltf-output
:width: 100%

*Analysis Output* of the same fit. The `maxfev` warning means the optimizer
stopped on its evaluation budget rather than on convergence.
```

Two files are written to the output directory:

- `<decay>_fit.json` — `lifetime_spectrum` (interleaved $x_i,\tau_i$),
  `lifetimes`, `irf_shift` (ns), `irf_background`, `decay_background`,
  `chi_square`, `reduced_chi_square`, `dof`, `time_range` (ns and channel
  indices), the model over the fit range (`model.time`, `model.decay`) and, after
  a scan, `optimal_fitting` with the $\chi^2_r$ and probability of every model
  tried.
- `<decay>_fit.png` — the decay and residual plot.

*Save intermediate results* (CLI `-si`) additionally writes one JSON per model
of the scan.

**The fit range decides the answer.** The same example decay fitted with two
lifetimes gives 1.35 ns / 4.00 ns over the default range (4.57–44.1 ns,
`area` 0.9999, `start_fraction` 0.005) and 0.78 ns / 3.90 ns over the example
config's range (4.66–23.3 ns, `area` 0.99, `start_fraction` 0.1). Both
residual traces look acceptable at a glance. When a short component moves by a
factor of two with the fit window, the decay does not determine it. The example
decay is also scaled to a peak of exactly 100 000, so it is not raw counts and
its $\chi^2_r$ does not measure fit quality.

### The component-count scan

The scan fits $n = 1 \dots n_\text{max}$ from fixed starting lifetimes, then
walks up from $n = 1$ and accepts $n$ while its probability exceeds the threshold
and its $\chi^2_r$ is lower than that of $n-1$ (`lower` mode; `upper` returns
the largest accepted $n$ instead). The probability is
$P = F_\text{cdf}(\chi^2_{r,n-1}/\chi^2_{r,n};\,2,\,\nu_n)$, which for any
realistic $\nu$ equals $1 - e^{-R}$ with $R$ the ratio. A model that fits no
better scores $0.632$, the 0.68 default threshold needs a 14 % drop in
$\chi^2_r$, and 0.95 needs a threefold drop, independent of how many photons
were recorded. {ref}`concept-tcspc-model-selection` compares this with the
extra-sum-of-squares test.

Measured on decays from the Synthetic Decay Generator with the example IRF
(6100 channels of 8 ps, $2\times10^6$ photons, three noise seeds each), scan up
to three lifetimes with the default configuration:

| True decay | Chosen $n$ (seeds 1, 2, 3) | What went wrong |
|---|---|---|
| 4.0 ns | 1, 1, 1 | nothing; but $\chi^2_{r,2}$ was 30.2 against 1.13 for seed 3 |
| 1.0 + 4.0 ns, equal amplitudes | 2, 3, 3 | the two-lifetime fit failed ($\chi^2_r$ 2.10 and 4.74 against 1.10); the three-lifetime fit then found the true model with a duplicated 3.94 ns component |
| 3.0 + 4.5 ns, equal amplitudes | 2, 1, 2 | $P$ = 0.689, 0.667, 0.701 around the 0.68 threshold; for seed 2 ($\chi^2_r$ 1.34 → 1.22 over 3704 degrees of freedom) the extra-sum-of-squares test gives $p = 6\times10^{-78}$, and the recovered lifetimes (5.00/3.45, 4.15/2.47 ns) are far from the truth |

A true single-exponential model gave $\chi^2_r$ = 1.09–1.15 rather than 1.0,
the low-count bias of data weighting. With the CLI's built-in defaults instead
of the YAML file (`area` 0.999, `start_fraction` 0.1, starting lifetimes
0.5–5 ns), the same seed-2 bi-exponential decay is resolved correctly: $n = 2$,
3.936 ns (0.511) and 0.949 ns (0.489), in 7 s. The scan's outcome therefore
depends on which of two default sets is in force (see *Known defects*).

Read the scan as a table of fits, not as a verdict: open `optimal_fitting` in
the JSON, check that $\chi^2_r$ falls monotonically with $n$, and judge the
drop yourself.

## Synthetic Decay Generator

```{figure} figures/synthetic_decay_vm.png
:name: fig-synthetic-decay-vm
:width: 70%

Two equal-amplitude lifetimes (1.2 and 4.0 ns) on 1024 channels of 32 ps,
convolved with the LLTF example IRF (binned to 32 ps) and drawn as $10^6$
photons with seed 1. The rotation table is used only in VV/VH mode; in VM mode
its $r(t)$ is plotted for reference.
```

*Lifetime spectrum* — one row per component: **Amp** (pre-exponential
amplitude, not intensity fraction) and **τ** (ns). **➕ Add** / **➖ Remove** edit
rows (at least one stays); **📂 Load** reads a text file holding an interleaved
list `a1 τ1 a2 τ2 …` or a two-column amplitude/lifetime table.

*Histogram* — **Bins** and **Δt** (ns) set the window, Bins × Δt; **Start** is
the channel where the ideal decay begins. With an IRF the decay starts
where the IRF sits, delayed further by **Start**.

*IRF & noise* — **IRF**: a text or `.npy` file with **one** count column,
normalized to unit area and cropped or zero-padded to *Bins*; empty means no
convolution. A two-column time/count file, such as the LLTF IRF, is not
rejected but flattened into one interleaved vector: the LLTF example IRF read
that way put the decay maximum at channel 1238 instead of 624. Strip the time
column first (`awk '{print $2}'`, as in *Headless*). **Noise** on draws Poisson counts with
**Photons** as the expected total and **Seed** for the realization; off returns
the exact decay normalized to unit sum.

*Anisotropy* — **Mode**: *VM (magic angle)* or *VV/VH (polarized)*. In VV/VH
mode the *VV/VH detection corrections* panel (click to open) holds **g**, **l1**,
**l2**, and the *Rotation spectrum* table (**b**, **ρ**) defines
$r(t) = \sum_i b_i e^{-t/\rho_i}$. The two channels follow the forward model of
{ref}`concept-anisotropy` and share one photon budget.

```{figure} figures/synthetic_decay_vvvh.png
:name: fig-synthetic-decay-vvvh
:width: 70%

The same spectrum as a polarized pair, $g = 1.1$, one rotation of 2 ns with
$r_0 = 0.38$. VV starts above VH and the two converge as $r(t)$ decays. The
*Generate / Save / Fit group* row under the rotation table is a duplicate of the
toolbar that appears after switching mode (see *Known defects*).
```

*Actions* (toolbar) — **🧪 Generate** computes and plots; the status line
reports what was made. **💾 Save** writes CSV/text (two columns `time_ns counts`),
`.npy` (counts only) or JSON (`x`, `y`) in VM mode, and a VV/VH `.dat` file whose
footer carries g, l1, l2 and the mode in VV/VH mode, which the VV/VH reader
restores on loading. **🔗 Fit group** adds the generated curve (or the VV/VH pair)
as a dataset and opens a fit with the lifetime model (the polarized one for a
pair), with the bin width and g, l1, l2 carried into the fit.

The IRF's flat floor is convolved along with its peak. The LLTF example IRF has
a floor of 0.48 counts per channel against a peak of $10^5$, and that floor
contributes a slowly rising background to every decay generated with it. Crop or
subtract the floor first if the test is not meant to include it.

## Where results go next

- The LLTF JSON is plain data: read `lifetime_spectrum` into a ChiSurf lifetime
  fit ({doc}`10_lifetime_anisotropy_fitting`) as starting values, and use that
  fit for uncertainties ({doc}`39_parameter_uncertainty`). LLTF itself reports
  none.
- A distribution rather than discrete components: panel 2, {doc}`62_maxent_decay`.
- Synthetic decays go to a fit through **Fit group**, or as files to any tool
  that reads a two-column decay, LLTF included.

## Headless

Both tools are CLI subcommands of `csc`. Generate the bi-exponential test decay
of the table above and fit it with a component-count scan:

```bash
awk '{print $2}' chisurf/plugins/fluorescence_decay/lltf/example/IRF_D0.dat > irf_8ps.txt
csc synth-decay generate --lifetimes 1.0,4.0 --amplitudes 0.5,0.5 \
    --n-bins 6100 --bin-width 0.008 --irf irf_8ps.txt \
    --photons 2e6 --seed 2 --no-normalize -o bi.dat
csc lltf fit bi.dat chisurf/plugins/fluorescence_decay/lltf/example/IRF_D0.dat \
    -f -m 3 -sp out_bi
# Lifetime 1: 3.936 ns, Amplitude: 0.511
# Lifetime 2: 0.949 ns, Amplitude: 0.489
# Reduced chi-square: 1.10
```

`bi.dat` holds 2 000 360 photons. `csc lltf fit` takes `-c` for a YAML
configuration, `-n` for a fixed component count, `-pt`/`-sm` for the scan's
threshold and mode, `--skiprows`, `--delimiter`, `--time-column` and
`--counts-column` for the file layout, and `-si` to keep each scanned model.
`csc synth-decay aniso` generates a VV/VH pair (`--rotation b,ρ,…`,
`--g-factor`, `--l1`, `--l2`, `--vvvh-file`), and `csc synth-decay component`
takes a component definition in JSON.

The same in Python:

```python
import numpy as np
from chisurf.plugins.fluorescence_decay.synthetic_decay.core.algorithms import compute_decay
from chisurf.plugins.fluorescence_decay.lltf.core.fitter import fit_lifetime

irf_file = "chisurf/plugins/fluorescence_decay/lltf/example/IRF_D0.dat"
irf = np.loadtxt(irf_file)[:, 1]                     # 6100 channels of 8 ps

r = compute_decay(n_bins=irf.size, lifetimes=[1.0, 4.0], amplitudes=[0.5, 0.5],
                  bin_width=0.008, irf=irf, normalize=False,
                  photon_count=2e6, seed=2)
np.savetxt("bi.dat", np.column_stack([r["x"], r["y"]]))

res = fit_lifetime(
    "bi.dat", irf_file,
    config={"lifetime_fit_parameter": {"find_optimal": True,
                                       "maximum_number_of_lifetimes": 3,
                                       "plot_probabilities": False,
                                       "plot_weighted_residuals": False},
            "plot_resulting_fit": False},
    save_intermediate_results=False)
print(res["n_lifetimes"], res["lifetime_spectrum"])   # 2 [0.511 3.936 0.489 0.949]
print(res["optimal_fitting"]["scores"])               # [10.403 1.101 1.102]
```

The generator underneath is
{src}`chisurf/core/fluorescence/decay.py#synthetic_decay`, which also takes a
laser `period` (periodic convolution) and an IRF `time_shift` that the GUI does
not expose. Run LLTF with `MPLBACKEND=Agg` when there is no display; the scan
calls `plt.show()`.

## Using it well

**Test the tool on your conditions before trusting it on your data.** Generate
decays with your IRF, channel width, window and photon count, and the lifetimes
you expect; run LLTF on a handful of seeds. If it does not recover the answer
there, it will not on the measurement.

**Fix the component count yourself for anything you publish.** Use the scan to
see the sequence of $\chi^2_r$, then decide with the extra-sum-of-squares test or
an information criterion ({ref}`concept-tcspc-model-selection`), and confirm
with MaxEnt.

**Vary the fit range.** A lifetime that moves when `start_fraction` or `area`
changes is not determined by the decay.

**Put the IRF into the test.** A deconvolving fit tested on IRF-free synthetic
data has only been shown to work in the easy case; a synthetic decay made with
your measured IRF also carries its floor and shape.

**Keep the window long.** Bins × Δt of at least 3–5 times the longest lifetime;
the generator's default 256 × 0.032 ns (8.2 ns) is too short for its own
default 4 ns component.

## Known defects

:::{admonition} Known defects
:class: warning

- **The component-count test is mis-specified.** The probability refers the
  ratio of reduced $\chi^2$ to $F(2, \nu)$, so it is $\approx 1-e^{-R}$ whatever
  the photon count (table above; `lltf/core/fitter.py`, `find_optimal_lifetime_spectrum`).
  The extra-sum-of-squares F, or the ChiSurf F-Test convention
  (`chisurf.core.math.statistics.f_test_confidence`), would be consistent.
- **Nested fits can end worse than smaller ones**, and the selection then counts
  optimizer failures (the 30.2, 2.10 and 4.74 above). Each $n$ starts from fixed
  lifetimes rather than from the $n-1$ solution.
- **Two default sets.** The GUI copies `lifetime_settings.yml`; the CLI without
  `-c` uses different defaults inside `fit_lifetime`, and the outcomes differ
  (above). With *Find Optimal* the CLI always overrides the file's
  `selection_mode` with its own default `lower`, so `upper` from the file is never
  used from the panel.
- **The config file is created once** in the system temp folder
  (`lltf_config.yml`) and never refreshed, so a changed default in a new ChiSurf
  version does not reach it; delete it to get the current defaults.
- **Matplotlib windows during the scan.** The scan calls `plt.show()` — once
  unconditionally for the selected fit, and again for each `plot_*` option. The
  child process inherits the user's Matplotlib backend; with an interactive one
  these windows open, and the fit waits for them.
- **Reduced $\chi^2$ equals $\chi^2$** when `Decay.fit(find_optimal=True)` is
  called from Python without `fixed`: the degrees of freedom are set to 0
  (measured: `dof` 0, `reduced_chi_square` 31671). The CLI and GUI pass `fixed`
  and are unaffected.
- **Synthetic Decay Generator:** a multi-column IRF file is flattened instead
  of read as time/counts (`synthetic_decay/core/algorithms.py`, `_load_irf`),
  which silently corrupts the IRF.
- **Synthetic Decay Generator:** switching *Mode* rebuilds the form and brings
  back a *Generate / Save / Fit group* row that duplicates the toolbar
  ({numref}`fig-synthetic-decay-vvvh`).
:::

## See also

- Concepts: {ref}`concept-tcspc-lifetime` · {ref}`concept-tcspc-model-selection`
  · {ref}`concept-tcspc-synthetic-decays` · {ref}`concept-fitting-objectives` ·
  {ref}`concept-maximum-entropy` · {ref}`concept-anisotropy`.
- Guides: {doc}`10_lifetime_anisotropy_fitting` · {doc}`62_maxent_decay` ·
  {doc}`73_tttr_decay_and_correlation` · {doc}`irf_estimation` ·
  {doc}`18_tttr_simulation` (photon-level simulation) ·
  {doc}`39_parameter_uncertainty`.
- Tools: **Decay Analysis** (`chisurf/plugins/fluorescence_decay/lifetime_analysis/`),
  **Lazy Lifetime Analysis** (`chisurf/plugins/fluorescence_decay/lltf/`),
  **Synthetic Decay Generator** (`chisurf/plugins/fluorescence_decay/synthetic_decay/`);
  the **F-Test** calculator (`chisurf/plugins/core/f_test/`).
