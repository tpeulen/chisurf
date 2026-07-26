---
type: Reference
title: Use case — Light Path Simulator (Förster radius and spectral crosstalk of a setup)
description: Build a two-colour detection path from catalogue spectra — lasers, dichroics, bandpasses, detector QE, dye pair — and read the Förster radii and the excitation/emission/detected crosstalk matrices.
tags: [usecase, spectroscopy, crosstalk, forster-radius, lightpath, gui]
timestamp: '2026-07-26T00:00:00Z'
---

# Use case: Light Path Simulator — R₀ and crosstalk of an optical setup

**Goal:** the one core workflow that happens *before* any measurement. The user
has a microscope (two lasers, an excitation dichroic, an emission beam splitter,
one bandpass and one detector per channel) and a dye pair, and wants two numbers
that no data file can give: the **Förster radius R₀** of the pair, and the
**spectral crosstalk** — how much of each dye's light, under each laser, lands in
each detector. Those matrices are the physically motivated priors for the
α/β/γ/δ correction factors in
[accurate FRET](/usecases/burst-selection-fret.md) (see
`docs/guides/fret_calibration.md`).

**Data:** none — everything comes from the MMFDB spectra catalogue
(`~/.chisurf/flr/sample_management.db`, 2165 probes: dyes, filters, dichroics,
polarizers, detectors). The run below used

| slot | catalogue entry | probe id |
|---|---|---|
| lasers | `488:1.0, 640:1.0` (manual lines) | — |
| excitation dichroic | `ZT532/640/NIR rpc` | 988 |
| emission splitter | `ZT640rdc` | 1007 |
| bandpass C1 | `ET585/20m` | 672 |
| bandpass C2 | `ET720/60m` | 722 |
| detector QE (both) | `Becker & Hickl HPM 100 06 Bialkali (hybrid)` | 2182 |
| dyes | `ATTO 550` (QY 0.8, ε 120 000) and `ATTO 647N` (QY 0.62, ε 150 000) | 1722, 1733 |

The tool has two faces in one window: an **Easy Mode** form (a fixed topology
from a template, one table per slot) and the **Optical Path** node graph (the
same graph, editable node by node). Easy Mode is the workflow below; the graph is
where an unusual path is built.

## Steps

1. Start ChiSurf and open **Spectroscopy → Light Path Simulator** (ribbon). The
   window opens on the **Optical Path** node graph; the form is behind the
   **Easy Mode** tab in the right-hand pane.
2. Select the **Easy Mode** tab.
3. From the preset combo at the top pick **`Template: 2-color (2 detector)`**.
   The form rebuilds to that topology: *Lasers*, *Exci. Dichroic*,
   *Splitter 1*, two detector rows (*C1*, *C2*), each with a *Bandpass* and a
   *QE* table, then *Fluorophores* and *Simulation*.
4. Leave *Lasers* at `488:1.0, 640:1.0` (`wavelength:relative power`, comma
   separated).
5. In each component table, type in the **Search…** box and click the row:
   `ZT532` → `ZT532/640/NIR rpc` for the excitation dichroic, `ZT640` →
   `ZT640rdc` for *Splitter 1*, `ET585` → `ET585/20m` for C1's bandpass, `ET720`
   → `ET720/60m` for C2's, and `HPM 100 06` for both *QE* tables.
6. In **Fluorophores**, filter for `ATTO 550` and tick it, then filter for
   `ATTO 647N` and tick it. QY and ε come from the catalogue and are editable in
   the two right-hand columns.
7. Check `kappa²` (0.67) and `n` (1.33) in the *Simulation* row.
8. Click **Recalculate** (or leave **Auto recalculate** on, which recomputes
   after every change).
9. Read the four result tabs: **Förster R₀ [Å]**, **Excitation CT**,
   **Emission CT**, **Detected CT**.
10. Click the ✎ button (*Edit in Full Simulator*) to push the form into the node
    graph, then **Calculate Emission Intensity** in the *Emission Probability*
    pane and read the same four matrices at full precision, plus the per-row
    **Signals** table (`laser × detector × dye → detected intensity`).
11. **File → Export Instrument Setting (JSON)** writes the mmCIF-ready instrument
    setting (lasers, filters, detectors, fluorophores with QY/ε).

Headless equivalent (no GUI, full precision):

```bash
lightpath-simulator simulate graph.json     # -> crosstalk_matrices, detector_signals,
                                            #    instrument_setting, per-node states
lightpath-simulator probes                  # catalogue metadata
```

## Expected

- Step 9's **R₀** matrix is dye × dye in Å; the off-diagonal cell for the donor →
  acceptor pair should match the literature R₀ of that pair, and the reverse cell
  should be much smaller.
- **Excitation CT** is one row per laser line, one column per dye.
- **Emission CT** and **Detected CT** are one row per dye (resp. per
  laser × dye) and one column per detector — these are the crosstalk numbers the
  whole tool exists for.
- Step 10 reproduces the same numbers from the node graph.

## Observed (last run: 2026-07-26)

Driven headlessly (`QT_QPA_PLATFORM=offscreen`, arm64 env, embedded RPC server on
a private port) through the real widgets — `LightPathSimulatorWidget`, the preset
combo, each `_SingleProbeTable`'s search box and row selection, the dye table's
check boxes, `Recalculate`, the full simulator's `Calculate Emission Intensity` —
with screenshots at every step.

**The physics is right.** With ATTO 550 as donor and ATTO 647N as acceptor the
tool returns **R₀ = 65.1 Å** (literature ≈ 65 Å for that pair), 14.2 Å for the
reversed pair, and homo-transfer radii of 57.6 Å and 65.0 Å on the diagonal. The
propagation chain through splitter → bandpass → detector conserves and attenuates
sensibly, and one recalculation takes **6–18 ms** (measured on
`_simulate_with_db`), so *Auto recalculate* is a reasonable default. The CLI
`simulate` returns exactly the same numbers as the GUI.

**Two defects make the tool unusable as it stands out of the box.**

- **The detector's quantum efficiency is looked up as `quantum_efficiency` only,
  and the catalogue's `APD120A2` stores its curve as `responsivity`.** That
  probe is the *first row* of both QE tables (and the one saved in the last-used
  config on this machine), so the default choice multiplies the whole detected
  signal by an all-zero spectrum. Every detected intensity is exactly 0, they are
  then dropped by a `val <= 1e-12` filter, and *Signals*, *Emission CT* and
  *Detected CT* come back **empty with no error at all**. Swapping in a detector
  whose curve is stored as `quantum_efficiency` (`Becker & Hickl HPM 100 06`,
  probe 2182) fills all three tables from the same graph. See RF-269.
- **Every Alexa Fluor dye is invisible in the fluorophore table.** The table
  keeps probes with `has_abs and has_em`, but 165 of the catalogue's
  fluorophores — including all 16 Alexa Fluor entries — store their absorption
  spectrum under the type `excitation`. Searching "Alexa" in the dye filter
  returns **0 rows** out of 696. The simulator's sample node asks for
  `"absorption"` too and has no fallback, so even a graph that names them by
  probe id would compute a zero absorption. `docs/guides/fret_calibration.md`
  tells the user to feed exactly this tool's matrices with
  `donor="Alexa488", acceptor="Alexa647"`. See RF-270.

**And when it does work, the Easy Mode tables hide the answer.**

- **The crosstalk matrices are printed with one decimal.** With the working
  detector, *Detected CT* showed `0.0` in seven of eight cells and `0.8` in the
  eighth; *Emission CT* was `0.0` everywhere. The full simulator's own tables,
  fed by the same result, show `2.3642e-04 … 8.4617e-01` and
  `3.9137e-11 … 8.1051e-05`. Crosstalk is by nature ≪ 1, so `%.1f` erases it.
  See RF-271.
- **Configuring the path pops a modal warning after every single click.** With
  *Auto recalculate* on (the default) and the *Fluorophores* section at the
  bottom of the form, each component pick recalculates, finds no dye, and raises
  a modal **"No Dyes — Select at least one dye"**. One ordinary top-down
  configuration pass produced **seven** of them. See RF-272.

**Startup and connection are fragile.**

- The spectra catalogue is fetched over RPC with a hard **1500 ms** timeout; the
  cold call takes ~0.73 s on this machine and it did time out on one of the
  runs. The failure path logs an ERROR and opens the plugin with **zero probes**
  — every component table blank, no message, and every subsequent action silently
  producing nothing. See RF-273.
- The plugin builds its client from the legacy flat `mmfdb.last_server` /
  `last_port` keys instead of the `client_config()` contract, so a profile that
  configures `mmfdb.client.cmd_port` connects the rest of ChiSurf to that port
  and the Light Path Simulator to `8765`. See RF-274.
- Five ChiSurf starts within fifteen minutes **locked out the embedded MMFDB
  admin**: each start makes one passwordless autologin attempt that is recorded
  as a failed login, and MMFDB throttles at 5 failures / 15 min. The sixth start
  hung on the login step. See RF-275.

The node graph is informative once you can see it — every node draws its own
spectrum, the detector nodes overlay the QE curve with the transmitted signal,
and the Förster node embeds the R₀ matrix — but the nodes are laid out **50 px
apart while they are 150–350 px wide**, so *Excitation Dichroic* is almost
entirely hidden behind *Dichroic Splitter 1* and each bandpass is covered by its
detector. See RF-276.

## Bugs filed

RF-269 (detector `responsivity` → silent zero signal), RF-270 (Alexa/`excitation`
dyes invisible), RF-271 (`%.1f` erases the crosstalk numbers), RF-272 (modal
"No Dyes" per click), RF-273 (silent 1500 ms catalogue timeout), RF-274 (plugin
ignores the `mmfdb.client` endpoint contract), RF-275 (startup autologin
self-throttles the MMFDB admin), RF-276 (node positions overlap), RF-277 (presets
bypass the ChiSurf settings directory).

## UX / UI suggestions

- **Open on Easy Mode, not on the node graph.** A first-time user gets a dark
  canvas with overlapping nodes; the guided form is the third tab of the
  right-hand pane and has to be discovered.
- **Show which dyes are selected.** After the dye filter is cleared the table
  scrolls back to the top of 696 rows and nothing anywhere says that ATTO 550 and
  ATTO 647N are ticked. A "Selected: …" chip row (with an ✕ per dye) above the
  table would make the state readable and undoable.
- **Label the R₀ matrix axes.** The corner cell is empty; nothing says rows are
  donors and columns acceptors. Same for *Detected CT*, whose row labels
  (`488 nm | ATTO 550`) are self-describing but whose values carry no unit or
  normalisation hint.
- **Say what the crosstalk numbers are.** *Excitation CT* shows `10440.0`,
  `145200.0` — an ε-weighted overlap, not a fraction. Either normalise per row
  (so it reads as a fraction of the strongest channel) or put the unit in the
  header.
- **Picking a template silently discards the current component choices.** The
  2-colour template carries topology only (all probe ids `null`), so choosing it
  clears the dichroic/filter/QE selections the user already made. Either keep
  compatible slots or confirm first; better, ship the templates with a sensible
  default component set.
- **Component tables show bare part numbers** (`21004v2`, `27001`, `ZT640rdc`)
  with no manufacturer, passband or description column. The spectra thumbnail
  tooltip helps once you hover the right row, but the list cannot be scanned.
  Add a second column with the centre/edge wavelength parsed from the spectrum.
- **`kappa²` and `n` have 2 decimals**, so the standard 0.6667 becomes `0.67` and
  is persisted that way into the user's `settings_chisurf.yaml`. Use 4 decimals.
- **Detector names from the template are dropped in the form.** The template
  names the channels *Transmission* and *Reflection*; the form labels them `C1`
  and `C2`, and the name only reappears in the results. Show the real name.
- **The results tables do not stretch to the panel width** — the columns sit in
  the left third with a wide empty area to the right.
- **No theory or workflow documentation.** The plugin has only the generated
  reference page (`docs/reference/plugins/lightpath_simulator.md`); there is no
  `docs/concepts/` page for the overlap integral / crosstalk model and no
  numbered `docs/guides/` walkthrough, although `docs/guides/fret_calibration.md`
  depends on this tool's output.
