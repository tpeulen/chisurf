---
type: Guide
title: 'FRET lines: static, dynamic and model lines for the E–lifetime plot'
description: Building FRET lines with the FRET Line Generator — a static line with a linker width, the no-linker diagonal, a dynamic line between two states, worm-like-chain and mixture lines — overlaying several, saving them and sending them to ndX, plus the closed-form and headless routes.
tags: [guides, fret, smfret, lifetime, bursts]
---

# FRET lines: static, dynamic and model lines for the E–lifetime plot

In a multiparameter burst analysis each burst gets an efficiency $E$ and a
donor lifetime $\langle\tau_{D(A)}\rangle_F$. A FRET line is the curve a
population *should* follow in that plane under a stated model. The **static
line** is where a structurally homogeneous species sits, blurred only by its
dye linkers. A **dynamic line** is where a molecule exchanging between two
states during the burst sits. A population on its static line is consistent
with a single structure. A population bowed towards longer lifetimes is
exchanging, or has been corrected with the wrong $\gamma$.

The **FRET Line Generator** computes these lines from the same lifetime models
used for decay fitting, overlays as many as you like, and writes them to a
CSV or onto ndX plots. The theory, including the closed-form lines and the
linker correction, is in {ref}`concept-accurate-fret` (section *The lines in
closed form*). How the E–S and E–τ plots are built from bursts is in
{ref}`concept-smfret-bursts` and {doc}`14_multiparameter_es`. Selecting
populations is covered in {doc}`28_selecting_fret_populations`.

## Open the tool

**Main → Tools → Calculators**, then the **📈 FRET line** entry. It needs no
data. The window can also run on its own:
`python -m chisurf.plugins.fret_line`.

```{figure} figures/fret_line_tool.png
:name: fig-fret-line-tool
:width: 100%

A static line (orange: one Gaussian distance distribution, σ = 6 Å, mean
swept 20–120 Å) and a dynamic line (blue: two Gaussian components at 40 and
70 Å, the fraction of the 40 Å state swept 0 → 1). The Editor shows
component C1 (R_DA = 70 Å, E = 0.164). R0 = 52 Å and τ_D0 = 4 ns throughout.
```

The window is a dock area. Top left are the **Components**, **Sweep** and
**FRET lines** tabs. Top right is the **Editor** of the selected component.
The bottom holds two plots: **FRET line** ($E$ against $\langle\tau\rangle_F$)
and **τ_X(τ_F)** (species- against fluorescence-averaged lifetime, with the
dashed diagonal $\tau_X = \tau_F$). The action bar at the bottom stays visible
whatever the dock layout.

## Set it up

**Components** — the models whose lifetime spectra are mixed.

1. **Model**: *FRET: FD (Gaussian)* (Gaussian distance distributions),
   *FRET: FD (Worm-like chain)*, *FRET: FD (Discrete)* (sharp distances) or
   *Lifetime* (plain exponentials, no FRET). Changing it replaces the selected
   component.
2. **+ Add** / **− Remove**: add a component, or remove the selected one (at
   least one stays).
3. **Weight**: the component's initial mixing weight. Weights are normalised
   over the components.

**Editor** — the model editor from the fitting window, for the selected
component. The groups that matter:

* **Donor**: the donor-only lifetimes. Add several for a multi-exponential
  donor.
* **FRET parameters**: τ0, R0, κ² and the donor-only fraction x_D,0 (keep it 0
  for a line).
* **Gaussian distances** (or **Discrete distances**, or the chain parameters):
  R_DA, the width w (= σ, the linker width), the shape k, and the amplitude x
  of each distance. **add** / **del** change the number of distances within
  one component.

The *Convolution* and *Generic* groups (IRF, background, n0) have no effect. A
line is computed from the model's lifetime spectrum, and no decay is
convolved.

**Sweep** — what varies along the line.

4. **Vary**: a parameter of any component (labelled `C<i> [model] · name`), or
   `fraction · C<i>` for a mixture of two or more components. The box is
   searchable. **all params** also lists the instrument, anisotropy and
   donor-only parameters, which never make a useful line.
5. **Min**, **Max**, **log** (logarithmic spacing, both limits > 0) and
   **Points**.
6. **τ_D0 (ns)**: the reference for $E = 1 - \langle\tau\rangle_x/\tau_{D(0)}$.
   Set it to the species-averaged donor-only lifetime measured on your sample.
   **0** takes it from the donor of the first FRET component. A line built
   only from *Lifetime* components has no donor to take it from, so it needs
   an explicit τ_D0 or it comes out as NaN.

**+ Add FRET line** computes the current mixture and sweep and adds it as a
new line with its own colour. Earlier lines are kept. Editing the mixture
afterwards does not change lines that are already computed, so a family of
lines is built by editing and pressing again.

## The standard lines

| Line | Components | Vary | Range |
|---|---|---|---|
| static, with linker | one *FD (Gaussian)*, w = linker width (6 Å is typical) | `RDA0` | 20–120 Å |
| no-linker diagonal | one *FD (Discrete)* | `RDA0` | 20–120 Å |
| dynamic, two states | two *FD (Gaussian)*, R_DA = state 1 and state 2 | `fraction · C0` | 0–1 |
| chain | one *FD (Worm-like chain)* | `l` (contour length) or `lp` | e.g. 30–150 Å |

The dynamic line can also be made inside a single *FD (Gaussian)* component
with two distances (**add** in the distances table), sweeping the amplitude
`x1` of the second distance from 0 up to a large value.

## Read the result

With τ_D0 = 4 ns, R0 = 52 Å and σ = 6 Å, the static line runs from E = 0.994
(R_DA = 20 Å, τ_F = 0.12 ns) through E = 0.580 (50 Å, 1.93 ns) to E = 0.021
(100 Å, 3.92 ns). It lies above the diagonal $E = 1 - \tau_F/\tau_{D(0)}$ by up
to 0.08 at short distances, where the linker distribution spreads the
lifetimes most. At τ_F = 2.0 ns it passes through E = 0.559 against 0.500 on the
diagonal.

The dynamic line between 40 and 70 Å joins the static line at its two ends
(E = 0.822 at τ_F = 1.04 ns and E = 0.164 at τ_F = 3.37 ns) and bows out to
longer lifetimes in between. At a 50:50 mixture it is at τ_F = 2.96 ns,
E = 0.493, where the static line at the same efficiency sits near 2.2 ns. A
burst population found in that gap exchanges within the burst duration.

The **τ_X(τ_F)** plot shows the same information as a conversion curve. Its
distance from the dashed diagonal is how much the fluorescence-averaged
lifetime from a burst fit overstates the species-averaged lifetime that
determines $E$.

The **FRET lines** tab lists every computed line in its plot colour. Untick a
line to hide it, and use **Show all** / **Hide all**. **− Remove** deletes the
selected line and **Clear all** deletes every line. Hover over a line for the
components it was computed from.

```{figure} figures/fret_line_tool_lines.png
:name: fig-fret-line-tool-lines
:width: 100%

The FRET lines tab with the two lines above, each in its plot colour.
```

## Where the lines go next

* **Save CSV** writes all lines into one file with header
  `line,sweep,log,components,parameter,tau_F_ns,tau_X_ns,E_FRET`, one row per
  point. This is the format to overlay in any plotting program.
* **Push to ndX** adds every line as a curve to each *visible* ndX overlay
  panel, as $E(\tau_F)$. Open the burst data and an overlay panel in ndX
  first ({doc}`46_ndxplorer`).
* To draw a line on the E–τ histogram of **Accurate FRET**, the tool builds
  its own static and dynamic lines from the same formulas
  ({doc}`41_accurate_fret`).

## Headless

The CLI takes the arguments of `compute_fret_line` as JSON. Parameters are
addressed by canonical id (`distance.mean.0`, `distance.sigma.0`,
`chain.contour_length`, `fret.forster_radius`, …). List them with
`get_model_parameters(model_name)`:

```bash
python -m chisurf.plugins.fret_line --list-models
python -m chisurf.plugins.fret_line --params dyn.json      # one line, JSON to stdout
python -m chisurf.plugins.fret_line --batch many.json --output results/
```

with `dyn.json`:

```json
{
  "components": [
    {"model_name": "FRET: FD (Gaussian)", "params": {"distance.mean.0": 40, "distance.sigma.0": 6}},
    {"model_name": "FRET: FD (Gaussian)", "params": {"distance.mean.0": 70, "distance.sigma.0": 6}}
  ],
  "sweep": {"kind": "fraction", "component": 0},
  "param_min": 0.0, "param_max": 1.0, "n_points": 3,
  "tau_d0": 4.0
}
```

which returns `e_fret` = 0.164, 0.493, 0.822 at `tau_f` = 3.369, 2.960,
1.036 ns. From Python:

```python
import numpy as np
from chisurf.plugins.fret_line.core.algorithms import compute_fret_line, fret_line_overlays
from chisurf.core.fluorescence.fret.lines import static_fret_line, dynamic_fret_line

gauss = {"model_name": "FRET: FD (Gaussian)", "params": {"distance.sigma.0": 6.0}}
res = compute_fret_line([gauss], {"kind": "param", "component": 0, "name": "distance.mean.0"},
                        20.0, 120.0, n_points=200, tau_d0=4.0)
line = res["result"]                      # parameter_values, tau_x, tau_f, e_fret
np.interp(2.0, line["tau_f"], line["e_fret"])            # 0.5585

closed = static_fret_line(4.0, r0=52.0, sigma=6.0)       # no model, no Qt
closed.efficiency_at(2.0)                                # 0.5575
dyn = dynamic_fret_line(4.0, r0=52.0, sigma=6.0, distance_1=40.0, distance_2=70.0)

ov = fret_line_overlays([gauss], {"kind": "param", "component": 0, "name": "distance.mean.0"},
                        20.0, 120.0, tau_d0=4.0, name="static σ=6 Å")
```

`compute_fret_line` returns `{"ok": False, "error": …}` instead of raising.
`chisurf.core.fluorescence.fret.lines` holds the closed-form static,
no-linker and dynamic lines. It needs only τ_D0, R0 and σ, and it is what
Accurate FRET uses. The model route and the closed form agree along the curve
to within 0.002 in $E$. The same functions are served over RPC as
`fret_line.compute`, `fret_line.overlays` (the shared overlay-line format ndX
reads), `fret_line.list_models`, `fret_line.get_model_parameters` and
`fret_line.list_sweep_targets`.

## Using it well

**Take τ_D0 and σ from the sample.** τ_D0 anchors the line at $E = 0$, and
σ sets its curvature. Use the donor-only lifetime and the linker width you use
in the Accurate FRET calibration, so the line and the γ it implies are
consistent with each other.

**Check a population against its static line before calling it dynamic.** A
shift towards long lifetimes also results from a γ that is too large, a wrong
τ_D0, or acceptor photophysics. Only a population that stays off a correctly
anchored line points to exchange. Confirm it independently with
{ref}`concept-bva` or {ref}`concept-burst-2cde`.

**A two-state dynamic line needs the right end points.** Choose the two
distances from the static populations you actually see, or from structural
models, and give both the same linker width as the static line.

**Read the line against τ_F, not against the swept value.** The model's
Gaussian labels each point by its mean distance slightly differently from the
closed form (see below). The curve $E(\tau_F)$ is the same either way.

## Known defects

* **The CLI docstring example is wrong.** It addresses parameters as `R(G,1)`
  and `s(G,1)`. That returns `'FRET: Gaussian distances' has no parameter
  'R(G,1)'`. Use the canonical ids shown above
  (`chisurf/plugins/fret_line/__main__.py`, module docstring).
* **The Gaussian model's mean is shifted by about 1 Å.** At `distance.mean.0` =
  40 Å and σ = 6 Å, the lifetime spectrum of *FD (Gaussian)* implies
  ⟨R⟩ = 39.05 Å and gives E = 0.822. A Gaussian with mean 40 Å averaged
  directly, as `lines.static_fret_line` does, gives 0.804 (60 Å: 0.330 against
  0.317). The line as a curve $E(\tau_F)$ agrees to within 0.002. Only the
  distance labels along it differ.
* **σ = 0 in *FD (Gaussian)* returns NaN** at some distances (50, 80 and
  100 Å tested), and 0.2919 instead of 0.2976 at 60 Å. Use *FD (Discrete)* for
  the no-linker line.
* **No ? or Guide button yet.** `help.md` and `guide.json` ship beside
  `gui/tool.py`, but `FRETLineTool` is a plain `QWidget` that does not call
  `attach_help_and_guide`, so neither button is drawn.

## See also

- Concepts: {ref}`concept-accurate-fret` (static, dynamic and linker-corrected
  lines, and the lifetime route to γ) · {ref}`concept-smfret-bursts` ·
  {ref}`concept-bva` · {ref}`concept-burst-2cde`.
- Guides: {doc}`41_accurate_fret` · {doc}`14_multiparameter_es` ·
  {doc}`28_selecting_fret_populations` · {doc}`46_ndxplorer`.
- Tool: **FRET Line Generator** (`chisurf/plugins/fret_line/`), reached through
  the Calculators hub.
