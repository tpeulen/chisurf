---
type: Guide
title: One window for the TTTR file tools (TTTR Tools)
description: How the TTTR Tools window hosts the photon-level tools — ALEX Creator, micro-time shifter, photon table, count-rate analysis and audifier — how to find and step through them, and the two clocks (macro time and micro time) that decide which one you need.
tags: [guides, tttr, photons, file-formats]
---

# One window for the TTTR file tools (TTTR Tools)

**What you get:** one window with the TTTR file tools in a list on the left and the selected tool on the right. A tool is
built the first time you select it and stays alive (with its loaded files) while you visit others.

```{figure} figures/tttr_toolbox.png
:name: fig-tttr-toolbox
:width: 100%

TTTR Tools with **Count Rate Analysis** after **Calculate** on three SPC-132 dsDNA files (detector `green`,
routing channels 0 and 1, from **0. Setup**). Left: **Help**, **Guide**, the search field and the step list. Above the
tool: its name, its **Help** and its description. Bottom: the status line with **Back** and **Next**.
```

## Two clocks

A TTTR record holds the **macro time** (when the photon arrived on the free-running clock) and the **micro time** (how long
after the laser pulse). Bursts and correlations use the first, lifetimes and decays the second. ALEX alternation lives in the
macro time; PIE gating reads the micro time: the ALEX Creator moves one into the other (see
[ALEX Creator](100_alex_creator.md)).

## Using the window

1. Open **0. Setup** first and define detector routing, PIE windows,
   polarization, reading calibration and LUTs once. **Count Rate Analysis** and
   **Audifier** use that shared definition; their setup panes show its name and
   **Edit setup…**, which returns to **0. Setup**. Opened on its own, a tool keeps
   its full editor.
2. Click a tool in the list. The search field narrows the list by name,
   description or id. A tool is built when first selected and receives the
   current setup.
3. **Back** and **Next** visit neighbouring tools. The **Help** at the top left
   explains the hub; the **Help** beside the tool's name opens that tool's help.
   **Guide** waits for you to select Count Rate Analysis and ALEX Creator yourself.
4. Add your TTTR measurement in Count Rate Analysis and press **Calculate**.
   Open Audifier, load the stream, select a detector and a macro-time interval,
   then press **Update** to compute its waterfall. Playing sound is a separate
   action. The detector controls remain reachable through **Edit setup…**.
5. Settings and selected tools persist. Restoring a child reattaches its editor
   to the shared definition. A running job keeps its original input snapshot
   and receives the latest setup after completion. Re-run an analysis to apply
   changed routing or gates to its already computed results.

```{figure} figures/tttr_toolbox_shared_setup.png
:name: fig-tttr-toolbox-shared-setup
:width: 100%

The shared detector editor at **0. Setup**, reading the SPC-132 sample's
13.5 ns macro-time clock and 3.2958984375 ps micro-time clock. Detector `green`
uses routing channels 0 and 1. PIE, reading, polarization, LUT and optical
controls are all here.
```

```{figure} figures/tttr_toolbox_shared_audifier.png
:name: fig-tttr-toolbox-shared-audifier
:width: 100%

Audifier inside the hub after loading `m000.spc` and computing a 2-second
waterfall for detector `green`. Its setup pane is only the setup name and
**Edit setup…**; the waterfall, detector colours and audio controls stay in the
tool.
```

Launch the native tool with `pixi run -e test python -m chisurf.emtk --plugin tttr_toolbox`.
For headless interaction, use a scratch
`CHISURF_SETTINGS_DIR` and `emtk.testing.Driver`:

```python
from emtk.testing import Driver
from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

hub = make_app()
driver = Driver(hub, (1280, 860))
hub.ensure_child("setup").page.load_definition({
    "detectors": {"green": {"chs": [0, 1], "micro_time_ranges": [], "g_factor": 1.0}},
    "windows": {},
    "tttr_reading": {"file_type": "SPC-130"},
})
child = hub.select("count_rate")
child.tool.add_paths(["m000.spc"])
child.tool.calculate()
while child.tool.job.running:
    driver.frame()
hub.close()
```

{src}`docs/guides/screenshots/tttr_toolbox_shot.py` is this script with the
bundled files; it draws {numref}`fig-tttr-toolbox`.

## See also

- [Plugin reference: TTTR Tools](../reference/plugins/tttr_toolbox.md)
- [Handling TTTR files](12_handling_tttr_files.md)

## Theory

- [The photon container](../concepts/photon_container.md): what a TTTR measurement stores, which the photon tools read and rewrite.
- [Micro-time shift](../concepts/microtime_shift.md): why the micro-time shifter exists and what it corrects.
