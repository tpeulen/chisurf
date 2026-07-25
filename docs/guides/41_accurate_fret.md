# Accurate FRET: automatic correction factors

:::{admonition} Theory
:class: seealso
What the four correction factors mean, why the light path predicts them, how the
static and dynamic FRET lines are built, and how the uncertainties propagate into
distances are explained in the concept page {ref}`concept-accurate-fret`.
:::

## What it does

The **Spectroscopy → FRET → Accurate FRET** tool (`accurate_fret`) takes a
per-burst table and determines the Hellenkamp correction factors — leakage
$\alpha$, direct excitation $\delta$, detection $\gamma$ and excitation-flux
ratio $\beta$ — **from the measurement itself**, without hand-drawn population
gates. It then reports the accurate efficiency, stoichiometry and distance of
every population with error bars, and draws the E–S and E–lifetime plots with
the static and dynamic FRET lines.

Three things distinguish it from typing the factors in by hand:

* the **populations are found automatically** (a Gaussian mixture over the
  stoichiometry), and the whole chain iterates to self-consistency;
* the **light path supplies the priors** — $\gamma$, $\alpha$ and $\delta$
  computed from excitation and emission probabilities — so a factor the data
  cannot identify keeps its optical value *and* its optical uncertainty;
* the **donor lifetime plus the static FRET line** determine $\gamma$ even for a
  single-population sample, and without ALEX.

```{figure} figures/accurate_fret_tool.png
:alt: the accurate-FRET tool with a calibrated two-population dataset
:width: 100%

The tool after *Calibrate*: channel mapping and photophysics on the left, the
factors with their uncertainties and how each was determined on the right.
```

## Workflow

### 1. Load the bursts

Use the **Burst table** row (or drop a file on the window): any delimited text
file — `.csv`, `.tsv`, `.txt`, `.bur` — or an `.npz` archive, one row per burst.
Alternatively press **📥 From ndXplorer** to take the columns of an open
ndXplorer window, so the calibration runs on exactly the bursts currently
selected there.

### 2. Check the channel mapping

The four **Channels** combos are filled automatically from the column names
(`Green Count Rate (KHz)`, `Red Count Rate (KHz)`, `S delayed yellow (kHz)`,
`Tau (green)`, the plain `i_dd`/`i_da`/`i_aa` spelling, and the usual `.bur`
headers are all recognised). Fix them if the guess is wrong:

| combo | channel |
|---|---|
| I_DD (donor) | donor emission under donor excitation |
| I_DA (FRET) | acceptor emission under donor excitation |
| I_AA (acceptor) | acceptor emission under acceptor excitation (ALEX/PIE) |
| Donor lifetime | $\langle\tau_{D(A)}\rangle_F$ per burst, in ns |

Only the first two are mandatory. Counts and count rates both work as long as
every channel uses the same unit.

**Without I_AA** there is no stoichiometry: donor-only and acceptor-only bursts
cannot be separated, every burst is treated as doubly labelled, and only the
lifetime route to $\gamma$ remains — so gate the singly labelled bursts out
beforehand.

### 3. Set the photophysics

**τ_D(0)** is the donor-only lifetime, measured on a donor-only sample; it
anchors the FRET lines at $E = 0$. **Linker width** (6 Å is typical) sets the
curvature of the static line. **R0** affects only the distance, never the
efficiency. Backgrounds go in the collapsed **Background** panel — subtract them,
they bias low-efficiency populations most.

### 4. Choose the prior

Leave **Use the optics prior** on and pick a **Light path** saved by the
light-path simulator. Its excitation matrix (which laser excites which dye) and
emission matrix (which fraction of each dye's emission reaches each detector)
become Gaussian priors for $\gamma$, $\alpha$ and $\delta$; fill in the quantum
yields and detection efficiencies next to it. With no light path selected the
calibration is a pure data estimate.

### 5. Calibrate

**🎯 Calibrate** runs the iteration in a worker thread. The report at the bottom
left names every route that contributed:

```text
Automatic FRET calibration
==========================
  alpha  = 0.0801 ± 0.0008
  delta  = 0.0597 ± 0.0005
  gamma  = 0.6579 ± 0.0035
  beta   = 1.3900 ± 0.0046
  bursts: 500 donor-only, 500 acceptor-only, 3000 FRET in 2 population(s)
  stoichiometry cuts (mixture): 0.252 / 0.747
  gamma [E-S population fit] = 0.6579
  gamma [static FRET line]   = 0.6552
  population 0: n = 1500, E = 0.277 ± 0.002, R = 61.0 Å, tau_f = 2.954 ns, off-line by -0.003
  population 1: n = 1500, E = 0.718 ± 0.001, R = 44.5 Å, tau_f = 1.430 ns, off-line by -0.000
  converged after 2 iteration(s)
```

The two independent $\gamma$ estimates agreeing to 0.4 % is the consistency check
worth doing on every new sample; set **gamma from** to `combined` in the
**Procedure** panel to average them, or to `lifetime`/`es` to force one route.

### 6. Read the plots

```{figure} figures/accurate_fret_es.png
:alt: E-S plot with the automatically classified burst populations
:width: 90%

**E–S.** Donor-only near $S = 1$, acceptor-only near $S = 0$ (their "efficiency"
is meaningless — no donor signal), and the doubly labelled populations at
$S = 0.5$ once $\beta$ is right. The colours are the classes the mixture found,
not gates that were drawn.
```

```{figure} figures/accurate_fret_etau.png
:alt: E versus donor lifetime with the static and dynamic FRET lines
:width: 90%

**E–lifetime.** Both populations sit on the static line (white), as a static
sample must; the dynamic line (red dashed) connects them. A population bowing
towards the dynamic line exchanges within the burst; a population sitting
systematically *below* the static line points at a too-large $\gamma$ or a wrong
$\tau_{D(0)}$.
```

The **Populations** tab puts numbers on it: accurate $E$ with its combined
statistical and systematic error, the distance, and the *Off static line*
offset.

### 7. Use the calibration

* **🔗 Share in session** publishes it as a linkable pseudo-fit, so any fit can
  link its correction parameters to this one calibration (global analysis).
* **📤 To ndXplorer** writes the factors into an open ndXplorer window's MFD
  constants and recomputes its derived columns.
* **💾 Export CSV** writes the per-burst $E$, $S$, lifetime and distance with the
  calibration report in the file header, so the numbers stay traceable.

## Doing it entirely inside ndXplorer

If the bursts are already open in ndXplorer, the round trip through this tool is
unnecessary. ndXplorer's own toolbar carries **🎯 Optimize FRET calibration**,
which does the whole thing in one click on the loaded measurement:

1. it reads the burst columns out of the window;
2. it **starts from the constants that window already has** — backgrounds,
   quantum yields, Förster radius and `tauD0` stay yours; only what the data can
   improve is changed;
3. it runs the same automatic calibration and writes the posterior back into
   ndXplorer's MFD constants (`gG/gR`, `alpha`, `beta`, `r`, …), recomputing its
   derived columns;
4. it adds the accurate per-burst columns — `FRET efficiency (accurate)`,
   `Stoichiometry (accurate)`, `R_DA (accurate)`, `Off static FRET line` and
   `Population` — so they can be plotted and gated like any other column.

Step 4 is not redundant. ndXplorer's own efficiency equation corrects donor
leakage but has **no direct-excitation term**, so pushing constants alone cannot
make its native `FRET efficiency` column accurate; the injected column is the
fully corrected one. ndXplorer's own columns and equations are left untouched, so
nothing is corrected twice.

A dialog reports what changed — every constant with its old and new value, the
factors with their uncertainties, and the populations that were found.

Head-less, the same call is:

```python
from chisurf.plugins.ndxplorer.calibration_bridge import optimize_calibration_from_ndx

result = optimize_calibration_from_ndx(ndx)     # ndx = the open window
print(result["report"])
print(result["constants"])                      # what was written
```

### Naming differences to watch

ndXplorer's constants do not use Hellenkamp's letters:

| ndXplorer | meaning | Hellenkamp |
|---|---|---|
| `alpha` | donor leakage | $\alpha$ |
| `beta` | direct excitation | $\delta$ |
| `r` | scales $F_{AA}$ in the stoichiometry | $1/\beta$ |
| `gG/gR`, `PhiA`, `PhiD` | detection · quantum yield | $\gamma = (\Phi_A/\Phi_D)/(g_G/g_R)$ |

The bridge translates in both directions, so the numbers in the tool and in
ndXplorer always mean the same thing.

## Trying it without data (and checking it works)

ChiSurf can simulate the whole experiment with tttrlib — diffusing molecules,
two alternating lasers, per-photon micro-times — from *declared* parameters, so
the tool can be tried, and its recovery checked, without a measurement:

```bash
csc accurate-fret --simulate demo_bursts.csv --simulate-photons 350000
```

That writes a burst table (with the declared factors in its header) and
calibrates it immediately. From Python the same simulation is:

```python
from chisurf.core.fluorescence.burst.simulate import SmfretParameters, simulate_smfret

parameters = SmfretParameters(
    efficiencies=(0.30, 0.75),          # the populations to recover
    gamma=0.65, alpha=0.08, beta=1.40, delta=0.06,
    tau_d0=4.0, linker_sigma=6.0, r0=52.0,
    donor_only=0.05, acceptor_only=0.05,   # the reference populations
)
simulation = simulate_smfret(parameters)
bursts = simulation.burst_table(min_photons=50)
```

The photons are a real `tttrlib.TTTR` object whose routing channel is the ALEX
stream (`0` = I_DD, `1` = I_DA, `2` = donor detector under acceptor excitation,
`3` = I_AA), and every burst carries the ground-truth species it came from. The
donor decay of a FRET population is the multi-exponential decay of the same
Gaussian-broadened distance the static line integrates, so the simulated
populations lie *on* the line and the lifetime route can be judged.

On such a simulation (≈1500 bursts of ~70 photons, three seeds) the automatic
calibration returns

| factor | declared | recovered |
|---|---|---|
| α | 0.080 | 0.074 – 0.084 |
| δ | 0.060 | 0.056 – 0.063 |
| γ (E–S fit) | 0.650 | 0.636 – 0.672 |
| γ (FRET line) | 0.650 | 0.644 – 0.663 |
| β | 1.400 | 1.389 – 1.404 |
| E | 0.30 / 0.75 | 0.289–0.309 / 0.738–0.758 |

which is the accuracy to expect at that photon count: a few per cent on the
factors, ≈0.01 on the efficiency. Brighter bursts tighten all of it.

## Head-less

```bash
# what can be mapped, and which light paths can serve as the prior
csc accurate-fret bursts.csv --list-columns
csc accurate-fret bursts.csv --list-lightpaths

# calibrate, with the lifetime route available and a light-path prior
csc accurate-fret bursts.csv \
    --tau-d0 4.0 --r0 52 --linker-sigma 6 \
    --lightpath lightpath_20260725_ab12cd34 \
    --bootstrap 100 -o bursts.accurate.csv
```

Add `--as-json` for a machine-readable reply (the same payload the
`accurate_fret.calibrate` RPC method returns).

## From Python

```python
import numpy as np
from chisurf.core.fluorescence.fret.accurate import auto_calibrate, accurate_fret
from chisurf.core.fluorescence.fret.lines import static_fret_line

line = static_fret_line(4.0, r0=52.0, sigma=6.0)      # tau_D(0), R0, linker width

result = auto_calibrate(
    i_dd, i_da, i_aa,                                  # per-burst channels
    tau_f=tau,                                         # per-burst donor lifetime (ns)
    line=line,
    lightpath={"matrices": crosstalk, "donor": "AF488", "acceptor": "AF647",
               "green_detector": "green", "red_detector": "red",
               "qy_d": 0.92, "qy_a": 0.33},            # the optics prior
    n_bootstrap=100,
)
print(result.report())
print(result.factors["gamma"], "±", result.uncertainties["gamma"])

acc = accurate_fret(i_dd, i_da, i_aa, calibration=result.calibration,
                    tau_f=tau, line=line, uncertainties=result.uncertainties)
```

`gamma_from_lifetime` is available on its own when only the FRET-line route is
wanted, and `dynamic_fret_line` builds the two-state line for the overlay. The
older reference-sample API (`calibrate_from_samples`, explicit donor-only and
acceptor-only measurements) is described in
[FRET calibration](fret_calibration.md) and remains the right choice when the
reference samples were measured separately.

## In the Global View

Both sides of the calibration are published as ordinary **fitting parameters**,
so they appear in the Global View next to every fit parameter — with their
bounds, their link column and an editable value:

* **ndXplorer constants** — every scalar the open window holds (`gG/gR`,
  `alpha`, `beta`, `r`, the backgrounds, `PhiA`/`PhiD`, `forster_radius`,
  `tauD0`, …), read from the window rather than hard-coded, so a setup with extra
  constants exposes those too.
* **Optical path** — the light-path simulator's excitation and emission
  probabilities, the per-dye quantum yields and the per-detector efficiencies,
  plus the `gamma`/`alpha`/`delta` they imply. Re-running the simulation
  refreshes the same group, so links into it survive.

That makes the two things you would otherwise keep in your head explicit:

```python
# a fit's Förster radius follows the one ndXplorer is using
from chisurf.plugins.ndxplorer.parameters import bound_ndx_parameters

constants = bound_ndx_parameters()
fit.model.parameters_all_dict["R0"].link = constants.parameter("forster_radius")
```

and the optical model can hand itself over as the calibration prior directly:

```python
from chisurf.plugins.core.lightpath_simulator.core.parameters import (
    registered_lightpath_parameters,
)

optics = registered_lightpath_parameters()
result = auto_calibrate(i_dd, i_da, i_aa, lightpath=optics.as_prior_arguments())
```

Editing an ndXplorer constant in the Global View reaches the window: the group
pushes the changed value and ndXplorer recomputes. The `⟲ Sync constants`
toolbar action in ndXplorer does the same on demand, in both directions.

Note that the optics `gamma`/`alpha`/`delta` are **derived** — recomputed from
the probabilities whenever the optical model changes — so read them, do not fit
them; fit the quantum yields and efficiencies they are made of.

## Pitfalls

* **A single FRET population without lifetimes cannot give $\gamma$.** The tool
  says so instead of inventing one — supply lifetimes, a second population, or a
  light-path prior.
* **$\beta$ from $S = 0.5$ is a definition**, used only when the E–S fit is
  unavailable. It assumes 1:1 labelling and never touches $E$.
* **Dynamics and mis-calibration look alike** in the E–lifetime plot. Calibrate
  on a sample known to be static, then use the off-line offset as a dynamics
  test — confirmed with [BVA](../concepts/bva.md) or
  [2CDE](01_fret_2cde.md).
* **Distances are only quotable near $R \approx R_0$**; the sixth root inflates
  the error bar at both ends of the efficiency range.
