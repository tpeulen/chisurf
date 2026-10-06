---
type: Manual Page
title: Overview
description: ChiSurf is modular software for global analysis of fluorescence spectroscopic data.
tags: [manual, fitting, global-analysis]
---

# Overview

ChiSurf is modular software for global analysis of fluorescence spectroscopic data. The main window has three regions: (a) the docks on the left for reading data and setting up and running analyses, (b) the **Console** below, an interactive Python shell inside the running ChiSurf session, and (c) the multiple document interface on the right, where every fit has a window with its plots (**Fig.1**).

```{image} figures/main_overview.png
:align: center
```

**Fig.1 The ChiSurf main window.** Two decays of the IBH sample (`test/data/tcspc/ibh_sample`) fitted with the *Lifetime* model against the measured prompt. (a) The docks on the left share one area, chosen by the tabs at its bottom: **Read data**, **Datasets**, **Analysis** (shown: the active fit's controls and parameters), **Plot settings** and **Logging**. (b) The **Console** below runs Python in the session; here it reads the first fit's name and its reduced χ². (c) The fit windows, tiled; each shows the data, the IRF and the model with the weighted residuals and their autocorrelation above.

Integrated software modules for single-molecule spectroscopy, fluorescence correlation spectroscopy, and image spectroscopy (Fluorescence Lifetime Image Microscopy, FLIM) facilitate the joint analysis of imaging and single-molecule data, while the open Python programming interface allows other software to be integrated for more complex analysis (**Fig.2**).

The accompanying software can be used independently of the main analysis software.

```{image} figures/tools_montage.png
:align: center
```

**Fig.2 Companion tools.** Four of the tools that open from the main window's menus, each in its own window: **ndXplorer** for burst-wise single-molecule data (here a FRET-efficiency histogram with Gaussian populations), the **FCS** hub that turns photon streams into correlation curves (Spectroscopy ▸ Correlation ▸ FCS), the **TTTR Image Browser** for time-resolved images (FLIM), and **Histogram-Microtime** for micro-time histograms of photon streams. Their guides describe each in detail.

```{image} _images/image_rId12.png
:align: center
```

The main purpose of ChiSurf is the global analysis over multiple datasets (**Fig.3**). In ChiSurf this is achied by parameters of models (model parameters) for different data that can be "linked" for a joint/global data analysis. In global analysis multiple datasets are simultaneously described and dependencies of parameters across different datasets are exploited to maximize the accuracy and the precision of the analysis result, which can either be a point estimate determined by maximizing the agreement between the model and the data the variable parameters by fitting or by sampling over the variable parameters.

**Fig.3 Global analysis in ChiSurf. (a)** In ChiSurf data and models are combined to "Fits". (**b**) Each model has a set of parameters, which can be either a fixed parameter or a variable parameter. (**c**) The parameters of different "Fits" can be linked to introduce dependencies. (**d**) In a global analysis multiple fits with corresponding data and parameter dependencies are jointly analyzed, either by optimizing a scoring function or by sampling over the parameters. (**e**) Parameter dependency of a fluorescence decay analysis of the donor fluorescence decay in the presence and the absence of an acceptor, the direct excited acceptor, and the FRET sensitized acceptor. Parameter dependencies are visualized in a network graph.

This introduction gives a general overview and background information without providing specific information on how to use the software in particular use-cases for data analysis. The "Experiments" section provides specific information for experiments. The tutorial section at the end of this manual provides guides on how to use the software in particular use-cases. Code references are printed in a bold monospaced slab serif typeface, e.g., **Example**. This introduction provides background information and is best combined with a tutorial.
