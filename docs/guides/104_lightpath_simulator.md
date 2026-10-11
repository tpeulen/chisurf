---
type: Guide
title: 'Light path simulator: crosstalk and R0 of an optical setup'
description: Build a laser, filter, splitter and detector path from catalogue spectra, read the detected signal, the excitation, emission and detected crosstalk matrices and the Förster radius of every dye pair, in the window, from the command line and from Python.
tags: [guides, spectra, python]
---

# Light path simulator: crosstalk and R0 of an optical setup

**What you get:** before any measurement, the numbers a data file cannot give: how much of each dye's light, under each
laser line, reaches each detector (crosstalk), and the Förster radius $R_0$ of every donor/acceptor pair. The crosstalk
predicts the leakage factor $\alpha$ and the direct-excitation factor $\delta$ of [Accurate FRET](41_accurate_fret.md).
The physics is in [Accurate FRET and its correction factors](../concepts/accurate_fret.md) and the [FRET concept](../concepts/fret.md).

**Tool:** *Tools → Calculators → Light Path Simulator* (`lightpath_simulator`,
`chisurf/plugins/core/lightpath_simulator/`). **Headless:** `csc lightpath-simulator`
and `chisurf.plugins.core.lightpath_simulator.core.workflow`.

```{figure} figures/104_lightpath_simulator.png
:name: fig-lightpath-simulator
:width: 100%

The simulator on the default graph with the dyes Alexa488 and Alexa594 and a 488/640 nm source. Left: **Optical Path**
(light source, sample, splitter, two filter/detector branches and the Förster Radius node); every node draws its spectrum.
Right: **Optical Components** and **Easy Mode**. Bottom: **Emission Probability** with the **Förster radius** tab (rows
donors, columns acceptors, Å). The bundled demo catalogue holds idealised spectra and no filters or detectors, so the
values are illustrative; use a full MMFDB spectra catalogue for real work.
```

## 1. The windows

- **Optical Path:** the graph. Drag nodes, drag from a pin to connect, scroll to zoom, right-click a node (rename,
  duplicate, delete) or the background (add a component, arrange, fit). The toolbar saves and loads graphs.
- **Optical Components:** the list of components to add, **Reset to Default**, the view buttons (**Arrange**, **Fit**,
  **Show minimap**), and the **Backend**, **Connections** and **MMFDB** sections.
- **Easy Mode:** the same path as a form (lasers, excitation dichroic, dyes, splitters, detectors). It edits the graph.
- **Emission Probability:** **Calculate Emission Intensity** and the result tabs.

## 2. Build the path

1. Press **Reset to Default** for a two-detector path, or open Easy Mode and choose a template (the shipped templates
   are 2-color (2 detector), 3-color (3 detector), 3 color polarization (6 detector), anisotropy (2 detector) and
   polarizer-2xcolor beam splitter (4 detector)).
2. In **Light Source** enter lines as `wavelength:relative power`, comma separated (`488:1.0, 640:1.0`), or pick a
   catalogue source.
3. In **Sample / Fluorophore** pick the dyes. Quantum yield and extinction coefficient come from the catalogue.
4. Pick the dichroic, the filters and the detector quantum efficiency in the other nodes.
5. In the **Förster Radius** node check $\kappa^2$ (default 0.6667) and the refractive index $n$ (default 1.33).

A path without a detector spectrum reports no detected signal; its **Signals**, **Emission** and **Detected** tables stay
empty without an error, so check that every detector node has a spectrum.

## 3. Simulate and read

Press **Calculate Emission Intensity**. With **Auto update** on (*Backend*) every edit queues a new simulation; **Stop**
appears while a backend call runs. The tabs:

| tab | content |
|---|---|
| **Signals** | detected intensity per laser, detector and dye |
| **Excitation** | laser × dye: relative excitation of each dye by each line |
| **Emission** | dye × detector: detection per unit excitation |
| **Detected** | (laser, dye) × detector: detected intensity |
| **Förster radius** | donor × acceptor $R_0$ in Å |

## 4. Save, load, export

**Save Graph** and **Load Graph** use JSON files (a dropped `.json` file also loads). **Save Preset** stores the graph
under a name for Easy Mode. **Save to MMFDB** and **Load from MMFDB** keep simulations in the database. **Export
Instrument** writes the instrument setting of the last simulation (lasers, filters, detectors, fluorophores) as JSON.

## 5. Headless

```bash
csc lightpath-simulator simulate graph.json    # signals, crosstalk matrices, instrument setting, node states
csc lightpath-simulator probes                 # catalogue metadata
csc lightpath-simulator save graph.json --name my_setup
csc lightpath-simulator list
csc lightpath-simulator get OPERATION_ID
csc lightpath-simulator contract               # the JSON workflow contract
```

`--db` selects the MMFDB SQLite file. `serve` exposes the same methods over ZMQ (`lightpath.simulate`, `lightpath.save`,
`lightpath.list`, `lightpath.get`, `lightpath.get_probes_info`).

```python
import json
from chisurf.plugins.core.lightpath_simulator.core.workflow import simulate_lightpath

graph = json.load(open("graph.json"))          # a graph saved with Save Graph
result = simulate_lightpath(graph)             # db_path=None: the configured spectra database
r0 = [s["config"]["_last_results"] for s in result["states"].values()
      if s["config"].get("_last_results")]     # [{'donor', 'acceptor', 'r0'}, ...] in Å
ct = result["crosstalk_matrices"]              # 'excitation', 'emission', 'detected'
signals = result["detector_signals"]           # [{'laser', 'detector', 'dye', 'intensity'}, ...]
```

Each matrix is `{"rows", "columns", "values", "records", "value"}`.

## 6. Reading the numbers

- Rows of the $R_0$ matrix are donors. A cell is large only where the donor emission overlaps the acceptor absorption;
  the reverse cell is usually much smaller.
- The excitation matrix is an $\varepsilon$-weighted absorption at the laser line, not a fraction; compare entries
  within one row or column rather than reading them as probabilities.
- Crosstalk is small by nature. Read the matrices in scientific notation: a rounded display erases it.
- The result depends on the catalogue spectra and on $\kappa^2$; a different $\kappa^2$ scales $R_0$ by
  $\kappa^{1/3}$.

## 7. Take it from here

The matrices feed the priors for $\alpha$, $\delta$ and $\gamma$ in [Accurate FRET](41_accurate_fret.md) and in
[FRET calibration](fret_calibration.md). **Guide** in the toolbar walks the controls.
