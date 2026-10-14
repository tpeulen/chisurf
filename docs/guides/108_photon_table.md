---
type: Guide
title: Reading the photons of a TTTR file
description: 'Tool: Tools → TTTR → Photon Table (photon_table). One row per record (photons and the scanner''s pixel, line and frame markers, each marker kind coloured) with routing channel, micro time and macro time, paged and filterable by channel and kind, to check what a file holds before any analysis.'
tags: [guides, photons, tttr, file-formats]
---

# Reading the photons of a TTTR file

**Tool:** *Tools → TTTR → Photon Table* (`photon_table`). **What you get:** the raw records of a TTTR file, one row
per record: its kind (a photon, or a pixel, line-start, line-stop, frame or other marker), the routing channel
(detector or marker channel), the micro time (channel within the excitation period) and the macro time (when the
record arrived, in ms). Use it to check that a file has the channels you expect, that the macro times
run forward, and what the micro-time range is, before building bursts or histograms. How photon records are stored and read:
[photon container](../concepts/photon_container.md).

## 1. Open a file

```{figure} figures/108_photon_table.png
:name: fig-photon-table
:width: 100%

A Becker & Hickl SPC-130 image scan: 1.39 million photons and 7.68 million marker records. Left, the file summary
with the records of each kind; right, a page at a frame boundary, where the pixel clock (teal), a line start (blue)
and a frame marker (orange) interleave with the photons.
```

Press **Open TTTR...** or drop a photon file on the window: a `.pto` container or a vendor file tttrlib reads (`.ptu`, `.ht3`, `.spc`, …). The summary shows
the photon count (and the marker count), the measurement time (last macro time × header resolution), the micro-time
channels the header declares, the records of each kind and the routing channels present. A file that fails to open
leaves the table that was shown, and the status line says why.

## 2. Photons and markers

A scanning measurement interleaves the scanner's marker records with the photons, and the table lists every one.
tttrlib names each record from the file header and the scanner's reading routine — the same conventions it
reconstructs the image with (`tttrlib.CLSMImage.get_record_kinds`):

| Kind | What it is | Colour |
|---|---|---|
| photon | a detected photon | none |
| pixel | pixel clock (Becker & Hickl pixel-marker scans) | teal |
| line start / line stop | the markers that open and close a scan line | blue / purple |
| frame | the marker that opens a frame | orange |
| other marker | a marker the header does not name; every marker of a file that is not an image scan | red |

The colours are the shell's colour vocabulary and the same in the dark and the light theme; the cell text is drawn
in the ink that contrasts with them. The kinds, labels and colours are declared once, in
`chisurf/plugins/tttr/photon_table/core/record_kinds.yaml`. A Leica SP5 PTU whose header names frame marker 4 lists
its second frame channel (6) as *other marker*: the table shows what the file says. Macro-time overflow records are
not listed — tttrlib folds them into the macro times while it reads.

## 3. Navigate and filter

A file holds millions of records, so the table shows one page.

| Control | Effect |
|---|---|
| **First**, **Prev**, **Next**, **Last** | move by one page |
| **First record** | index of the first row, counted inside the filtered selection |
| **Rows** | page size, 1 to 20 000 |
| **Channel** | keep one routing channel |
| **Kind** | keep every record, only photons, only markers, or one marker kind; combines with **Channel** |

**Record** counts the filtered records and **File idx** keeps the position in the file.

A header click sorts the page; a right click on a header chooses the columns. **Copy visible** puts the page on the
clipboard as tab-separated text with a header line; its `kind` column holds the kind key.

## 4. Python

```python
from chisurf.plugins.tttr.photon_table.core.model import PhotonTableModel

table = PhotonTableModel()
table.load_file("measurement.ht3")
table.n_records, table.n_photons, table.n_markers, table.kind_counts()
table.filtered_count(channel=1, kind="markers")
table.page(first=0, rows=25, kind="frame")  # list of {photon, idx, kind, kind_key, channel, micro, macro}
table.page_tsv(first=0, rows=25)            # the text Copy visible produces
```

The kinds themselves come from tttrlib, for any TTTR object:

```python
import tttrlib

tttr = tttrlib.TTTR("scan.spc")
kinds = tttrlib.CLSMImage(tttr, build_pixels=False).get_record_kinds()  # tttrlib.CLSM_RECORD_*
```

For the whole file as arrays use `tttrlib.TTTR` ([handling TTTR files](12_handling_tttr_files.md)). The window has
**Guide** and **Help** buttons; the figure script is `docs/guides/screenshots/photon_table_shot.py`.

## Theory

[Photon container](../concepts/photon_container.md). Tool: Photon Table (`chisurf/plugins/tttr/photon_table/`).
