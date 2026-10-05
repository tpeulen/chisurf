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

1. Click a tool in the list; each row starts with its tool's icon. **Photon Table** shows the photons of a file one row
   per photon (channel, micro time, macro time). **Search** narrows the list by name, description or id; an empty result says *No matching tools*.
2. **Back** and **Next** (bottom right) step to the neighbouring tool and are grey at the ends.
3. **Help** opens the toolbox help, **Tool help** the help of the selected tool, **Guide** a tour that waits for you to select
   *Count Rate Analysis* and *ALEX Creator* yourself.
4. Dropping a file on the window hands it to the selected tool; the mouse wheel and keys go to the tool while the pointer is
   over it. A tool that cannot open shows the reason and a **Retry** button.
5. The selected tool and each tool's settings are remembered at the next start.

## See also

- [Plugin reference: TTTR Tools](../reference/plugins/tttr_toolbox.md)
- [Handling TTTR files](12_handling_tttr_files.md)
