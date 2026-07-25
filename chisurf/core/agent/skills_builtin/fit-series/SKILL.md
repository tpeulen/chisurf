---
name: fit-series
description: >-
  Fit a series of related measurements together — a power series, a titration,
  a time course, repeats — sharing what the measurements have in common and
  comparing what changes across them. Use when the user has several
  measurements that belong to one experiment.
triggers:
  - series
  - power series
  - titration
  - dilution
  - time course
  - time series
  - concentration series
  - repeats
  - replicates
  - globally
  - global fit
  - across the
  - vary
  - varying
  - trend
  - link *
  - share *
  - keep the same
  - same across
  - across the series
  - across all
experiments: [FCS, TCSPC, PCF]
tools:
  - list_files
  - load_data
  - create_fit
  - link_parameters
  - list_links
  - set_parameter
  - run_fit
  - fit_report
  - export_fit_results
  - run_python
---

# Fitting a series together

A series is several measurements of one experiment in which **something was
deliberately varied** — excitation power, concentration, time, or nothing at
all in the case of repeats. Two things follow from that, and they are the
whole job:

* what the measurements **share** should have one value, determined by all of
  them at once — so link it;
* what the experiment **varied** must stay free in each fit — that is the
  result the user came for.

Linking the shared quantity is not a nicety. It is usually the only way to
pin a parameter that no single measurement constrains, and it stops each fit
inventing its own value for something that is physically identical.

## The procedure

1. **Read the file names.** A series announces itself: `..._010uW`,
   `..._100uW`; `_1nM`, `_10nM`; `_t0`, `_t30`; `_rep1`, `_rep2`. Tell the
   user the order you inferred, because everything downstream depends on it.
2. **Fit one measurement properly first**, on its own. A series fitted with a
   model that does not describe a single member is just a wrong answer
   repeated. For decays that means the IRF and the component count; for
   correlation curves it means knowing which parameters you intend to fix.
3. **Create one fit per measurement** with the same model — `create_fit` does
   that by default.
4. **Link what is shared** (below), then `list_links` to confirm the
   free-parameter count actually dropped.
5. **Run every fit** and check each one, not just the first.
6. **Compare the parameters across the series** — the recipe below. This is
   the point of the exercise; a table of numbers per fit is the result.

## What to link

**If the user says what to share, do that** — they know their experiment.
Otherwise the default is the quantity that belongs to the *instrument or the
molecule* rather than to the individual measurement:

| series | link | keep free |
| --- | --- | --- |
| FCS power series | the shape of the observation volume, `w_r` and `w_z` | `N`, `D`, the bunching terms |
| FCS titration / dilution | `w_r`, `w_z` (and `D` if the species is unchanged) | `N` |
| decay series, one dye | the donor lifetimes, the IRF shift | amplitudes, background |
| repeats of one sample | everything physical; only the amplitudes should differ | scaling, background |

```python
# link the observation-volume shape across an FCS series
link_parameters(parameters=["w_r", "w_z"], source_fit=0)
```

Never link what the experiment varied. In a power series the brightness and
the triplet fraction change *with power* — that is the measurement. Linking
them would manufacture the answer.

Note that a correlation model's parameter names depend on its diffusion mode
(`w_r`/`w_z` in the default Gaussian mode, `w0`/`wem` in the MDF mode). Read
them from `get_fit` rather than assuming.

## Comparing across the series

Fit the series, then look at the parameters *together*. Run this with
`run_python`:

```python
import numpy as np

names = ["N", "D", "w_r"]          # the parameters you care about
header = ["fit", "dataset", "chi2r", *names]
print(" | ".join(f"{h:>10}" for h in header))
for index, fit in enumerate(fits):
    p = fit.model.parameters_all_dict
    row = [index, str(fit.data.name)[:10], round(float(fit.chi2r), 3)]
    row += [round(float(p[n].value), 4) if n in p else None for n in names]
    print(" | ".join(f"{str(v):>10}" for v in row))

for n in names:
    values = [float(f.model.parameters_all_dict[n].value)
              for f in fits if n in f.model.parameters_all_dict]
    if values:
        spread = (max(values) - min(values)) / abs(np.mean(values))
        print(f"{n}: mean {np.mean(values):.4g}, spread {spread:.1%}")
```

Then read it as a scientist would:

* **A parameter that should be constant but drifts** across the series is the
  most informative thing in the table. In a power series a diffusion time
  that grows with power is optical saturation, not slower diffusion.
* **A parameter that should trend but does not** means the experiment did not
  do what was intended, or the model is absorbing the change elsewhere.
* **One member out of line** with the rest is an outlier worth naming — a bad
  measurement, a bubble, a mis-set power — not something to average away.
* **The spread** of a quantity across repeats is the honest estimate of its
  reproducibility, and usually larger than any individual fit's error bar.

Report the trend, not just the mean. `export_fit_results` writes the whole
table to CSV when the user wants it.

## What to say

State which parameters were linked and which were free, in the same breath as
the numbers — a value from a global fit means something different from the
same value fitted alone. If the reduced chi-square rose slightly for the
individual measurements when you linked, that is expected and is the price of
the constraint; if it rose a lot, the quantity is not actually shared and
that is a finding.
