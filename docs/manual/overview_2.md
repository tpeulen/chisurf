---
type: Manual Page
title: 'Correlator: overview'
description: The Correlator Plugin of ChiSurf provides an interactive user interface to functionality implemented in tttrlib to process single photon counting data and compute correlation curves following a 6 step workflow outlined in Fig.27.
tags: [manual, plugins, photons, correlation]
---

# Correlator: overview

```{image} figures/fcs_hub_files.png
:align: center
```

The correlator of ChiSurf is an interactive user interface to the photon processing of [tttrlib](https://github.com/fluorescence-tools/tttrlib): it turns single photon counting data into correlation curves in a sequence of steps (**Fig.27**). It is the *Correlator* part of the **FCS** tool, opened from **Spectroscopy ▸ Correlation ▸ FCS**.

**Fig.27 The FCS tool.** The rail on the left lists the correlator's steps, followed by optional FCS tools: **1. Channel Definitions** (detectors and the channel pairs to correlate), **2. Files & Steps** (shown: the photon files, here the tool's simulated example, and which optional steps to run -- *Count rate/burst filter* and *FCS merger*), **3. Photon / Burst Filter** (select regions of the photon stream), **4. Correlator** (split the stream into chunks and correlate each, optionally micro-time filtered) and **5. FCS Merger** (inspect the curves, select, and merge them into one curve with uncertainties). **Back**, **>>** and **Next** at the bottom walk the steps.

The workflow can be used to compute simple correlations and allows for more advanced filtering methods to enhance the contrast in fluorescence cross correlation spectroscopy, FCCS, and minimize artifacts. In the first step, the raw photon stream is opened. In the second step, filters are applied to the photon stream to mask photons that do not fulfil certain conditions, e.g., photons in regions of the stream where the count rate exceeds a certain threshold. In the third step, the selected / filtered photon stream in split into subsets. In the next fourth step, the subsets are individually correlated (optionally with a micro time filtered, e.g., for lifetime filtered correlation). Following the correlation, correlation curves are inspected and selected in the fifth step. To be finally merged into a joint correlation curve (**Fig.27**, Step 6, Merging).
