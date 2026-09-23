---
type: Guide
title: 'Spectra, overlap integrals and R₀'
description: Downloading dye, protein and filter spectra into a staging database with the Spectra Downloader, pushing them into the MMFDB, and computing the spectral overlap J and the Förster radius R₀ of a donor–acceptor pair from them.
tags: [guides, fret, spectra, fluorophores]
---

# Spectra, overlap integrals and R₀

**What you get:** the Förster radius $R_0$ of a donor–acceptor pair, computed
from the donor's emission spectrum and the acceptor's absorption spectrum, and
applied to a FRET model, instead of a value copied from a vendor table whose
$\kappa^2$, $n$ and $Q_D$ you do not know.

Two tools take part. The **Spectra Downloader** fetches spectra from public
sources into a local staging database and pushes them into the MMFDB. It
computes nothing. The **Förster radius calculator**, opened from the κ² row of
the TCSPC FRET models, reads the spectra from the MMFDB and computes $J$ and
$R_0$.

The physics ($J$, the $R_0$ formula, why $R_0$ tolerates errors in its inputs)
is in {ref}`concept-fret`
and {ref}`fundamentals-energy-transfer`. In short, with $f_D$ the
area-normalised donor emission and $\varepsilon_A$ the acceptor's molar
extinction coefficient:

$$
J = \int f_D(\lambda)\,\varepsilon_A(\lambda)\,\lambda^4\,\mathrm{d}\lambda
\;[\mathrm{M^{-1}\,cm^{-1}\,nm^4}],
\qquad
R_0\,[\text{nm}] = 0.02108\,\bigl(\kappa^2\, n^{-4}\, Q_D\, J\bigr)^{1/6}
$$

{cite}`lakowicz2006`. `forster_radius()` returns Å (it multiplies by 10).

## 1. Open the Spectra Downloader

**Spectroscopy → Spectra Downloader**. It is marked experimental: everything
it fetches is stored as `unverified`.

```{note}
Until 2026-09-23 this menu entry opened nothing. The manifest named
`get_db`, which returns the database rather than a window, so the launcher
logged `'FluorophoreDatabase' object has no attribute 'show'`. The entry point
is now `gui.tool:SpectraTool`. An older checkout can open it with
`python -c "from chisurf.plugins.spectra_downloader.gui.tool import main; main()"`.
```

The window has four panels in its left list.

```{figure} figures/spectra_overview.png
:name: fig-spectra-overview
:width: 100%

**Overview** on the staging database of this machine: 2141 components, 1808
of them with at least one spectrum; 977 fluorophores, 898 filters, 190
dichroics, 69 detectors.
```

| panel | what it does |
|---|---|
| **Overview** | counts by category and source. **Refresh** re-reads the database |
| **Browse** | filter by name, **Source** and **Category**; the selected component's fields, its **Properties** and raw **Metadata (JSON)**, and its spectra; **Push selected** / **Push all** send components to the MMFDB |
| **Download** | pick a source under **Available Sources**, **Run Selected Script**, and follow the scraper's log. **Browse this source** jumps to what that source already delivered |
| **Add to MMFDB** | **Endpoint** (local file or ZMQ server), the local MMFDB path or host/ports and user/password, **Replace existing reference set**, **Mark imported as approved**, then push |

```{figure} figures/spectra_browse.png
:name: fig-spectra-browse
:width: 100%

**Browse**, filtered to ATTO 647N. The component merged records from ATTO-TEC
and Chroma (Source `atto,chroma`); it carries QY 0.65 and ε 1.50×10⁵ M⁻¹ cm⁻¹
from ATTO-TEC, and absorption, excitation and emission spectra, all
peak-normalised.
```

## 2. Where the spectra come from, and the terms they come under

| source | carries | terms |
|---|---|---|
| FPbase {cite}`lambert2019` | 432 fluorescent proteins, some dyes, 68 detectors | [data free of copyright](https://www.fpbase.org/terms/); attribute the original authors named on each protein page |
| Chroma | filters, dichroics, dye excitation and emission spectra | no data licence published; the site's terms cover sales only |
| Thorlabs | filters and one APD, via the `thor2` R package's digitised curves | the `thor2` repository declares no licence |
| PhotochemCAD {cite}`taniguchi2018` | 331 compounds with absorption, emission, ε and quantum yield | © Lindsey, Taniguchi, Du; the mirror used declares no licence |
| ATTO-TEC | ATTO dyes with ε, QY and lifetime, recovered from the Internet Archive (the live site moved to Leica and dropped the spectra) | vendor data |
| 3DOptix, Omega | metadata only / dead URLs; off by default | — |

Only FPbase publishes an open data policy. The staging database
(`chisurf/plugins/spectra_downloader/spectra.db`) is git-ignored for that
reason: use it as reference data for your own analysis and do not
redistribute it.

## 3. Push to the MMFDB

The calculator reads the **live MMFDB**, not the staging database, so the
spectra have to be pushed first: **Add to MMFDB** in the window, or

```bash
csc spectra-download push                  # staging → resolved MMFDB
csc spectra-download push --replace        # purge the reference set first (backs up the MMFDB)
```

A fresh MMFDB already holds seed dyes (Alexa488, Alexa594, ATTO647N, …). Where
no measured spectrum was imported, those seeds carry **Gaussian fallback
spectra** built from the absorption and emission maxima and a width, which is
good enough to try the calculator and not good enough to publish an $R_0$ from.

## 4. Compute R₀

In a TCSPC fit with a FRET model (Gaussian, discrete, worm-like chain, …)
press **calc R0** in the κ² row. The **Förster Radius Calculator** opens:

```{figure} figures/forster_calculator.png
:name: fig-forster-calculator
:width: 70%

The calculator on the seed MMFDB: donor Alexa488 (Q_D 0.92 filled from the
database), acceptor Alexa594 (ε_max 87 000 M⁻¹ cm⁻¹ filled from the database),
n = 1.33. R₀ = 58.4 Å, J = 2.30×10¹⁵ M⁻¹ cm⁻¹ nm⁴.
```

1. **Donor emission** and **Acceptor absorption**: searchable lists of the
   MMFDB components that carry an emission and an **absorption** spectrum.
2. **Donor QY**, **Acceptor ε_max**: filled from the component's stored
   `qy`/`q_fluor` and `ext_coeff`/`molar_extinction` when it has them. When it
   has not, the field keeps its previous value, so check it after every change
   of dye.
3. **Refractive index n**: 1.33 for water; 1.4 is often used for a protein
   interior.

The result updates as you type. $\kappa^2$ is fixed at 2/3; orientation is
handled in the FRET model's κ² controls. **Apply R₀ to model** writes the
value into the model's Förster radius.

How the calculator builds $J$: both spectra are interpolated onto 1000 points
spanning the range the two spectra share, the peak-normalised absorption is
scaled so that its maximum equals ε_max, the emission is area-normalised, and
`forster_radius_from_spectra` integrates. If the MMFDB holds a tabulated
$R_0$ for the pair (`flr_fret_forster_radius`), that value is shown
**instead**, marked *(cached)*, whatever QY, ε and n are set to.

## 5. Check it against published values

Measured with the staging spectra and the headless code below ($\kappa^2 = 2/3$,
$n = 1.33$), against the [Molecular Probes Handbook table of R₀ for Alexa Fluor
pairs](https://www.thermofisher.com/us/en/home/references/molecular-probes-the-handbook/tables/r0-values-for-some-alexa-fluor-dyes.html):

| pair | spectra | $Q_D$ | ε_max (M⁻¹ cm⁻¹) | $J$ (M⁻¹ cm⁻¹ nm⁴) | $R_0$ ChiSurf | $R_0$ table |
|---|---|---|---|---|---|---|
| Alexa Fluor 488 → 594 | Chroma em. / exc. | 0.92 | 73 000 | 1.83×10¹⁵ | 56.2 Å | 60 Å |
| Alexa Fluor 488 → 647 | Chroma em. / exc. | 0.92 | 270 000 | 1.57×10¹⁵ | 54.8 Å | 56 Å |
| Alexa Fluor 488 → 647 | Chroma em. / exc. | 0.92 | 239 000 | 1.39×10¹⁵ | 53.7 Å | 56 Å |
| Atto 488 → ATTO 647N | Chroma em. / ATTO-TEC abs. | 0.80 | 150 000 | 1.32×10¹⁵ | 52.0 Å | — |

$Q_D$ = 0.92 is the handbook's quantum yield for Alexa Fluor 488; the ε values
are the manufacturer's (Alexa Fluor 647 is quoted as both 270 000 and 239 000).
The handbook does not state its $\kappa^2$ and $n$.

ChiSurf lands 2–6 % below the table. Two things account for it, and both are
in the inputs, not in the integral:

* **Excitation is not absorption.** Chroma ships excitation spectra for its
  dyes; the red edge of an excitation spectrum is not the absorption band, and
  $J$ weights exactly that edge by $\lambda^4$.
* **ε_max carries the whole scale of $J$.** 270 000 versus 239 000 for
  Alexa Fluor 647 is a 13 % change in $J$ and a 2 % change in $R_0$. The sixth
  root is forgiving, but only of *random* error; a wrong ε_max is a bias in
  every distance.

## 6. Headless

The same computation without a window, reading the staging database read-only:

```python
import sqlite3
import numpy as np
from chisurf.plugins.spectra_downloader import DEFAULT_DATABASE_PATH
from chisurf.core.fluorescence.fret.forster import forster_radius_from_spectra

# immutable=1 reads the staging DB without migrating or locking it
conn = sqlite3.connect(f"file:{DEFAULT_DATABASE_PATH}?immutable=1", uri=True)

def spectrum(name, kind):
    row = conn.execute(
        "SELECT s.wavelengths, s.intensity_values FROM spectra s "
        "JOIN probes p USING (probe_id) WHERE p.chromophore_name = ? "
        "AND s.spectrum_type = ? AND s.deleted_at IS NULL AND p.deleted_at IS NULL",
        (name, kind),
    ).fetchone()
    return np.frombuffer(row[0]), np.frombuffer(row[1])

wl_d, f_d = spectrum("Alexa Fluor 488™", "emission")
wl_a, e_a = spectrum("Alexa Fluor 594™", "excitation")   # Chroma ships excitation only

wl = np.linspace(max(wl_d.min(), wl_a.min()), min(wl_d.max(), wl_a.max()), 1000)
f_d = np.interp(wl, wl_d, f_d, left=0, right=0)
eps_a = np.interp(wl, wl_a, e_a / e_a.max() * 73_000, left=0, right=0)   # ε_max in M⁻¹ cm⁻¹

r0, J = forster_radius_from_spectra(wl, f_d, eps_a, donor_quantum_yield=0.92,
                                    kappa2=2 / 3, refractive_index=1.33)
print(f"J = {J:.3e} M^-1 cm^-1 nm^4, R0 = {r0:.1f} Å")
# J = 1.825e+15 M^-1 cm^-1 nm^4, R0 = 56.2 Å
```

Tabulated pairs in the MMFDB: `chisurf.core.fluorescence.fret.forster.lookup_forster_radius("Alexa488", "Alexa594")`.

The downloader's CLI:

```bash
csc spectra-download list-sources          # the registry: 5 on by default, 2 off
csc spectra-download run fpbase            # one source into the staging DB
csc spectra-download run-all               # all default sources in parallel, then merge + de-duplicate
csc spectra-download consolidate           # merge duplicate components
csc spectra-download push                  # staging → MMFDB
```

## Using it well

* **Use an absorption spectrum for the acceptor.** Where the database has
  only excitation, the calculator does not list the dye; computing it anyway,
  as in the table above, is an approximation to be named, not hidden.
* **Take $Q_D$ from the labelled sample**, not the free dye. Conjugation to a
  protein changes the quantum yield more than anything else in the formula; the
  donor-only lifetime ratio $\tau_{D,\text{conj}}/\tau_{D,\text{free}}$ rescales
  it.
* **Check ε_max and $Q_D$ after every dye change.** A field that could not be
  filled keeps the last dye's value.
* **A *(cached)* result ignores the fields.** Delete the tabulated pair in the
  MMFDB admin (FRET Pairs) to see the computed value.

## Known defects

* **164 of 543 dyes cannot be acceptors in the calculator.** The calculator
  asks for `spectrum_type = 'absorption'`; Chroma dyes (Alexa Fluor, Cy3, Cy5,
  …) carry `excitation` only. Measured on the staging database: 378 dyes have
  an absorption spectrum, 164 have excitation only.
* **ATTO 488 lost its photophysics.** The ATTO-TEC record "ATTO488" (Q_D 0.80,
  ε 90 000) is soft-deleted in the staging database, and the surviving
  "Atto 488" (Chroma) carries neither value.
* **"ATTO-550" holds ATTO 565's properties** (abs 564 nm, em 590 nm, Q_D 0.90,
  synonym ATTO-565). An R₀ from it is ATTO 565's.
* **Opening the tool migrates the staging database** and writes a backup to
  `backups/` first; a copy is safer for experiments.

## See also

- [Förster resonance energy transfer](../concepts/fret.md) — $R_0$, $J$, $\kappa^2$ and the error budget.
- {ref}`fundamentals-absorption-emission` — what an absorption and an emission spectrum are.
- [Accurate FRET](14_multiparameter_es.md) — where the $R_0$ goes next.
