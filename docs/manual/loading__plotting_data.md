---
type: Manual Page
title: Loading & plotting data
description: First, the photon stream data needs to be loaded.
tags: [manual, photons, loading, plotting, data]
---

# Loading & plotting data

First, the photon stream data needs to be loaded. In the FCS tool (**Spectroscopy ▸ Correlation ▸ FCS**), the photon files are added in **2. Files & Steps** (Fig.27) -- with **Files…**, **Folder…**, **Database** or by dropping them on the window -- and filtered in **3. Photon / Burst Filter** (**Fig.28**).

```{image} figures/fcs_hub_filter.png
:align: center
```

**Fig.28. The photon filter.** The example photon stream in **3. Photon / Burst Filter**. *Channel selection*: the detector **Channels** and the micro-time range (**µt range**) the filter reads. *Macro time interval*: photons whose time to the next photon (**dMT**) lies outside **min dMT** / **max dMT** are removed, each limit active while its **use** box is ticked. *Filter*: the **Mode** (here *burst*: at least **Min photons** within a **Photon window**), **enable** and **invert**; the line below counts the photons kept. The plots show the time between photons against photon index (*Delta macro-time*, selected and removed photons) and the count rate of all and of the selected photons.

The photon file type is part of the detector setup of **1. Channel Definitions**
(left empty, it is detected from each file). Files are added in **2. Files &
Steps**: **Files…** or **Folder…** opens a file browser,
**Database** picks recorded measurements, and files dropped on the window are added
too. **Example** adds the tool's simulated photon stream. Ticked files are
processed; **Remove** and **Clear** drop the selected or all files. The filter step
is reached only while *Count rate/burst filter* is ticked under **Steps**.
