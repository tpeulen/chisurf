# Two-colour PDA (PDA2c)

:::{admonition} Theory
:class: seealso
Why the FRET histogram is shot-noise broadened, the binomial forward model of the
photon-count distribution, the corrections, and dynamic PDA are explained in the
concept page {ref}`concept-pda2c`.
:::

## What it does

The FRET-efficiency histogram of freely-diffusing single molecules is broadened
by **shot noise**: even a single, perfectly static distance produces a spread of
apparent efficiencies because each burst contains only a finite number of
photons. **PDA** (Antonik et al. 2006; Kalinin et al. 2007) models this exactly.

Given the experimental burst-size distribution $P(F)$ and a donor–acceptor
distance (or distance distribution), PDA predicts the full two-dimensional
$P(S_1, S_2)$ photon-count distribution — and hence the shot-noise-limited
proximity-ratio histogram — analytically. Fitting a measured histogram to a PDA
model recovers the underlying distance(s) and their populations, distinguishing a
single broadened state from a genuine mixture or from dynamics.

## In ChiSurf

PDA is a first-class **experiment** with AutoForm-rendered models
(`chisurf/core/models/pda2c/`): discrete distances, Gaussian distance
distributions, dynamic two-state and N-state models, an anisotropy model, and the
[SAW-ν polymer](03_polymer_distance_distributions.md) distance model. The
histograms are computed by the `tttrlib.Pda` engine.

```python
import numpy as np
import tttrlib
from scipy.stats import poisson

pda = tttrlib.Pda(hist2d_nmax=60, hist2d_nmin=5)
pda.setPF(poisson.pmf(np.arange(61), 25.0))     # burst-size distribution P(F)

pda.set_probability_spectrum_ch1([1.0, 0.4])    # one species, p(ch0) = 0.4  ->  E ≈ 0.6
s1s2 = np.asarray(pda.get_S1S2_matrix()).reshape(61, 61)
# collapse S1S2 -> proximity-ratio histogram (see make_figures.py)
```

## In ChiSurf

PDA is a fit **experiment**: load a `.pda`-tagged burst dataset and choose a PDA
model (single distance, Gaussian-distributed distance, or dynamic two-/N-state).
The model editor exposes the Förster parameters, the distance distribution, and
the correction/nuisance terms:

```{figure} figures/pda_model_editor.png
:name: fig-pda-model-editor
:width: 90%

The PDA (Gaussian-distance) model editor. **FRET parameters** hold $\tau_0$, the
Förster radius $R_0$, and $\kappa^2$; **Distance distribution** is an add/remove
list of Gaussian components (mean $R_{P}$, width $s_{P}$, fraction $x_{P}$);
**Corrections / nuisance** carries background, leakage, direct excitation and
$\gamma$. These map onto the forward model in {ref}`concept-pda2c`.
```

## Fitting a kinetic scheme

The dynamic N-state model exposes the whole transition-rate matrix. Set the
number of states, then say which rates the scheme has by fixing the rest at zero:

```python
model.n_states = 4
rates = model.states.rates_by_name()          # {"k1_2": parameter, ...}

for name in ("k1_3", "k3_1", "k1_4", "k4_1", "k2_4", "k4_2"):
    rates[name].value = 0.0                   # a linear chain 1-2-3-4
for name in ("k1_2", "k2_1", "k2_3", "k3_2", "k3_4", "k4_3"):
    rates[name].fixed = False                 # fit the rest

rates["k2_1"].link = rates["k1_2"]            # or impose a symmetry
```

`k_ij` is the rate from state *i* to state *j*, in Hz. In the editor the same
matrix is an editable grid with the diagonal disabled, above the parameter table
that controls which entries are free.

## Diagnostics

Every PDA model editor has a collapsed **Diagnostics** panel with two buttons.

**🔗 Apply light path** fills leakage, direct excitation and $\gamma$ from a
simulated optical setup rather than leaving them as guesses. It reads the
light-path graph named in the field below it, or the light-path simulator's last
session when that is empty, simulates it, and maps the excitation and emission
matrices onto the correction terms. Donor, acceptor and the two detectors are
taken from the matrices — a two-dye, two-detector setup needs no further input,
and anything else is *reported* rather than guessed, because picking the wrong
pair silently rescales every corrected quantity.

**🎲 Consistency check** answers a question $\chi^2$ does not. A good $\chi^2$
says the model *can be made* to fit; this says whether the measured bursts could
plausibly have come from the fitted scheme at all. It resamples synthetic
datasets from the fitted spectrum and reports where the measurement falls among
them, as a bootstrap p-value. Run it on a converged fit — the spectrum is read as
it currently stands.

Both are ordinary model methods, so the scripted path is the same code:

```python
model.lightpath_graph = "setup.json"
model.apply_light_path()

model.consistency_resamples = 500
result = model.run_consistency_check()
print(result["p_value"], result["consistent"])
```

## Measuring an exchange rate: several time bins, one rate

A dynamic PDA histogram responds to exchange only through the number of
transitions per observation, $K = (k_1 + k_2)\,T$. That has a consequence worth
being explicit about: **one histogram cannot test a kinetic model.** Some $K$
will fit it whether or not two-state exchange is the right description, so a
good $\chi^2_r$ from a single time window is not evidence.

Requiring one rate to reproduce *several* bin widths is a constraint the data
can fail. In ChiSurf:

1. In the reader, set **Segmentation** to *Fixed time bins*. A burst search
   returns windows whose durations vary with the local flux, so the observation
   time is only a lower bound; fixed bins cut the stream into abutting windows of
   exactly the requested length, which is what makes $T$ a known constant.
2. Give the reader several time-window configurations. Each produces its own
   dataset, named by its bin width.
3. Add a dynamic model to each, then link the exchange rate `k_ex` across them
   (it is a rate in Hz — each model multiplies it by *its own* dataset's
   observation time) and fit the group globally.

```python
from chisurf.core.experiments.pda2c.reader import Pda2cReader

reader = Pda2cReader(
    channels=([0], [1]),
    micro_time_ranges=[(0, 2**15)],
    segmentation="time-bins",
    tw_configs=[(5, 1e-3), (5, 2e-3), (5, 4e-3)],   # (min photons, bin width s)
)
datasets = reader.read(["measurement.ptu"])
```

On synthetic data generated from a single rate at bin widths differing by 4×, the
global fit returns that rate with $\chi^2_r < 1$. On data whose windows imply
*different* rates, each window still fits on its own ($\chi^2_r$ of 0.92 and 1.01)
while the joint fit is rejected at $\chi^2_r \approx 490$ — a factor of 500. That
contrast is the whole reason for reading a measurement at more than one bin
width.

## Result

Two single-species PDA models at different mean efficiencies. Each is a *single*
distance, yet produces a broad, shot-noise-limited proximity-ratio histogram —
the width PDA models exactly and separates from real heterogeneity.

```{figure} figures/pda.png
:name: fig-pda
:width: 90%

PDA shot-noise-limited E histograms.
```

## See also

- Concept: {ref}`concept-pda2c`.
- Models: `chisurf/core/models/pda2c/`; engine `tttrlib.Pda`.
- Distance-distribution models shared with TCSPC: [Polymer distance distributions](03_polymer_distance_distributions.md).
