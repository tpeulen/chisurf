---
type: Guide
title: Polymer inter-dye distance distributions
description: FRET between two dyes on a flexible chain reports on the distribution of inter-dye distances $P(R)$, not a single distance — and for unfolded / intrinsically disordered proteins the shape of $P(R)$ is set by polymer statistics.
tags: [guides, polymer, fret]
---

# Polymer inter-dye distance distributions

:::{admonition} Theory
:class: seealso
See {ref}`concept-accessible-volume` for the inter-dye distance distributions these polymer models describe (and how AV distances relate).
:::

## What it does

FRET between two dyes on a flexible chain reports on the **distribution** of
inter-dye distances $P(R)$, not a single distance — and for unfolded /
intrinsically disordered proteins the *shape* of $P(R)$ is set by polymer
statistics. ChiSurf provides the common analytic models in one place
(`chisurf.core.math.functions.rdf`):

- `gaussian_chain` — the ideal (theta) chain.
- `worm_like_chain` — semi-flexible chain (persistence length).
- **`saw_nu`** — the self-avoiding walk with Flory exponent $\nu$ (des Cloizeaux
  form; {cite}`zheng2018`):
  $P(R)\propto R^{2+\theta}\,e^{-(R/r_0)^{\delta}}$, $\theta=(\gamma-1)/\nu$,
  $\delta=1/(1-\nu)$, scaled to a target RMS. $\nu\approx0.588$ is an expanded
  chain, $0.5$ theta, $<0.4$ collapsed.
- **`ising_chain`** — a two-state (folded/unfolded) chain: each residue is
  structured or unstructured under a nearest-neighbour Ising Hamiltonian
  (cooperativity $J$, field $h$), with a Gaussian bond per residue. Because the
  characteristic function factorises, $\varphi(k)$ is an exact 2×2
  transfer-matrix product and $P(R)$ follows from the isotropic inverse
  transform. It reduces to `gaussian_chain` when the two bond lengths are equal.

## In ChiSurf

```python
import numpy as np
from chisurf.core.math.functions import rdf

r = np.linspace(1e-3, 160.0, 4000)

# SAW-ν at fixed RMS, varying the Flory exponent
p_expanded = rdf.saw_nu(r, r_rms=55.0, nu=0.588)
p_theta    = rdf.saw_nu(r, r_rms=55.0, nu=0.50)

# Ising two-state chain: field drives folded (compact) <-> unfolded (expanded)
p_folded   = rdf.ising_chain(r, number_of_residues=40, b_structured=4.0,
                             b_unstructured=9.0, coupling=1.5, field=+3.0)
p_unfolded = rdf.ising_chain(r, 40, 4.0, 9.0, coupling=1.5, field=-3.0)
```

Both are wired into ChiSurf's fit stages as distance-distribution FRET models:

- **TCSPC** (time-resolved FRET decay): the models *“FRET: self-avoiding chain
  (SAW-ν)”* and *“FRET: Ising two-state chain”* in the TCSPC experiment.
- **PDA** (burst FRET-E histograms): the *“PDA2c-SAW-ν-distance”* model.

In the TCSPC editor the chain replaces the Gaussian distance block: the
**SAW chain** panel holds `Rrms` (default 55 Å, bounds 1–1000) and `nu`
(0.588, bounds 0.3–0.95); the **Ising chain** panel holds `N` (residues,
fixed at 40), the bond lengths `bS`/`bU` (4 and 8 Å), the cooperativity `J`
(1.5) and the field `h` (0). The donor lifetimes, `R0`, `κ²` and the donor-only
fraction `xD,0` sit in the usual **Donor** and **FRET parameters** panels, and
`EFRET` is computed (0.679 for the SAW defaults, 0.892 for the Ising defaults at
`τ0` = 4 ns, `R0` = 52 Å).

```{figure} figures/03_saw_nu_editor.png
:name: fig-saw-nu-editor
:width: 60%

The TCSPC model editor with *FRET: self-avoiding chain (SAW-ν)* selected.
```

```{figure} figures/03_ising_chain_editor.png
:name: fig-ising-chain-editor
:width: 60%

The same editor with *FRET: Ising two-state chain*.
```

## Result

**Left:** SAW-ν distributions at a fixed RMS distance — increasing $\nu$
(expansion) shifts the peak outward and thins the short-distance side.
**Right:** the Ising two-state chain — the field $h$ tunes the population from a
compact folded state (green), through a broad mixed distribution at the midpoint
(blue), to an expanded unfolded state (red).

```{figure} figures/polymer.png
:name: fig-polymer
:width: 90%

Polymer distance distributions.
```

## See also

- Concept: {ref}`concept-distance-distributions` — why the donor decay carries
  the *width* and a steady-state efficiency does not, and how to choose $p(R)$.
- {src}`chisurf/core/math/functions/rdf.py` (`saw_nu`, `ising_chain`, `worm_like_chain`, `gaussian_chain`)
- Models: the IMP.bff descriptions `tcspc_fret_saw_nu` and `tcspc_fret_ising_chain` (shown in ChiSurf through `chisurf.core.models.description`), and `core/models/pda2c/saw_nu.py`.
