---
type: Guide
title: One window for the TTTR file tools (TTTR Tools)
description: How the TTTR Tools window hosts the photon-level tools — ALEX Creator, micro-time shifter, photon table, count-rate analysis and audifier — how to find and step through them, and the two clocks (macro time and micro time) that decide which one you need.
tags: [guides, tttr, tools]
---

# One window for the TTTR file tools (TTTR Tools)

**What you get:** one window with the TTTR file tools in a list on the left and the selected tool on the right. A tool is
built the first time you select it and stays alive (with its loaded files) while you visit others.

```{figure} figures/tttr_toolbox.png
:name: fig-tttr-toolbox
:width: 100%

TTTR Tools with **Count Rate Analysis** selected. Left: **Help**, **Guide**, the search field and the tool list. Above the
tool: its name, **Tool help** and its description. Bottom: the status line with **Back** and **Next**.
```

## Two clocks

A TTTR record holds the **macro time** (when the photon arrived on the free-running clock) and the **micro time** (how long
after the laser pulse). Bursts and correlations use the first, lifetimes and decays the second. ALEX alternation lives in the
macro time; PIE gating reads the micro time: the ALEX Creator moves one into the other (see
[ALEX Creator](100_alex_creator.md)).

## Using the window

1. In the native hub, open **0. Setup** first. Select or define detector routing,
   PIE windows, polarization, reading calibration and LUTs once. **Count Rate
   Analysis** and **Audifier** use that shared definition. Their setup panes
   show its name and **Edit setup…**, which returns to step0. Standalone tools
   retain their full editor.
2. Click a tool in the rail. **Photon Table** shows individual photon records;
   **Search** narrows the list by name, description or id. Children are created
   lazily and receive the latest setup when opened.
3. **Back** and **Next** visit neighbouring tools. **Help** explains the hub;
   **Tool help** opens the selected tool's help. **Guide** waits for you to select
   Count Rate Analysis and ALEX Creator yourself.
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

One complete shared detector editor at step0, reading the BH SPC-132 sample's
13.5ns macro-time clock and3.2958984375ps micro-time clock. The green detector
uses routing0/1. PIE, reading, polarization, LUT and optical controls are here.
```

```{figure} figures/tttr_toolbox_shared_audifier.png
:name: fig-tttr-toolbox-shared-audifier
:width: 100%

Audifier inside the hub after loading174438 photons and computing a2-second
waterfall for green routing0/1. Its setup pane is a summary/Edit setup link;
the waterfall, detector colours and analysis controls remain in the tool.
```

Launch the native tool with `pixi run -e test python -m chisurf.emtk --plugin tttr_toolbox`.
For headless interaction, use `QT_QPA_PLATFORM=offscreen`, a scratch
`CHISURF_SETTINGS_DIR`, and `emtk.testing.Driver`:

```python
from emtk.testing import Driver
from chisurf.plugins.tttr.tttr_toolbox.gui.app import make_app

hub = make_app()
driver = Driver(hub, (1280, 900))
setup = hub.ensure_child("setup")
setup.page.load_definition(your_detector_definition)
child = hub.select("count_rate")
child.tool.add_paths(["measurement.spc"])
child.tool.calculate()
driver.frame(3)  # Continue frames until child.tool.job.running is false.
hub.close()
```

## See also

- [Plugin reference: TTTR Tools](../reference/plugins/tttr_toolbox.md)
- [Handling TTTR files](12_handling_tttr_files.md)
