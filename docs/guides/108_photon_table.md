---
type: Guide
title: Reading the photons of a TTTR file
description: 'Tool: Tools → TTTR → Photon Table (photon_table). One row per photon with routing channel, micro time and macro time, paged and filterable by channel, to check what a file holds before any analysis.'
tags: [guides, photons, tttr]
---

# Reading the photons of a TTTR file

**Tool:** *Tools → TTTR → Photon Table* (`photon_table`). **What you get:** the raw records of a TTTR file, one row
per photon: the routing channel (detector), the micro time (channel within the excitation period) and the macro
time (when the photon arrived, in ms). Use it to check that a file has the channels you expect, that the macro times
run forward, and what the micro-time range is, before building bursts or histograms. How photon records are stored and read:
[photon container](../concepts/photon_container.md).

## 1. Open a file

```{figure} figures/108_photon_table.png
:name: fig-photon-table
:width: 100%

A PicoQuant HT3 file of 1.28 million photons on eight routing channels. Left, the file summary; right, rows
1000 to 1024 of the file.
```

Press **Open TTTR…** or drop a `.ptu`, `.ht3`, `.phu`, `.pt3`, `.ht2` or `.t3r` file on the window. The summary shows
the photon count, the measurement time (last macro time × header resolution), the micro-time channels the header
declares and the routing channels present. A file that fails to open leaves the table that was shown and the status
line says why.

## 2. Navigate and filter

A file holds millions of photons, so the table shows one page.

| Control | Effect |
|---|---|
| **First**, **Prev**, **Next**, **Last** | move by one page |
| **First photon** | index of the first row, counted inside the filtered selection |
| **Rows** | page size, 1 to 20 000 |
| **Channel** | keep one routing channel. **Photon** then counts the filtered photons and **File idx** keeps the position in the file |

A header click sorts the page; a right click on a header chooses the columns. **Copy visible** puts the page on the
clipboard as tab-separated text with a header line.

## 3. Python

```python
from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

table = PhotonTableModel()
table.load_file("measurement.ht3")
table.n_photons, table.used_channels, table.acquisition_time_s
table.filtered_count(channel=1)
table.page(first=0, rows=25, channel=1)    # list of {photon, idx, channel, micro, macro}
table.page_tsv(first=0, rows=25)           # the text Copy visible produces
```

For the whole file as arrays use `tttrlib.TTTR` ([handling TTTR files](12_handling_tttr_files.md)). The window has
**Guide** and **Help** buttons; the figure script is `docs/guides/screenshots/photon_table_shot.py`.

## Theory

[Photon container](../concepts/photon_container.md). Tool: Photon Table (`chisurf/plugins/tttr/photon_table/`).
