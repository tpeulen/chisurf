---
type: Concept
title: 'File tools: operations on the container, not the measurement'
description: What the File › Data tools are for, why moving a recording between containers, cutting it into windows or correcting a header does not change the photons, and which tool does which.
tags: [concepts, file-formats, file, tools]
anchor: concept-file-tools
---

(concept-file-tools)=
# File tools: operations on the container, not the measurement

A recording exists twice: as photons (detector, macro time, micro time) and as a *file* that carries them with a header
and a vendor layout. Some operations act on the second only. They split, convert, pack, inspect, window or relabel,
and none of them estimates a physical quantity. The File tools are ordinary tools in **File › Data**, each in its own window
(`tttr_splitter`, `tttr_to_pto`, `pto_inspector`, `tttr_header_edit`, `tttr_time_windows`, `bid_to_analysis`,
`mfd_prepare`).

| tool | does |
|---|---|
| TTTR Split / Convert | splits a recording into files of $N$ photons; converts between container formats |
| ⇄ .pto | packs vendor files into a `.pto` container and unpacks one back |
| PTO Inspector | lists what a `.pto` contains before it is used |
| TTTR header | shows and corrects the tags a vendor wrote into the header; the edited header is saved as a **new** PTU |
| TTTR → Time Windows | cuts each recording into fixed-duration windows, written as a burst-ID (`.bst`) file with one row per window |
| BID → Analysis | turns a BID/`.bst` file into a burst table in the measurement's `.pto` |

## What stays the same

Splitting, packing and windowing move or select photons; they never change a macro or micro time. A header correction
changes what the stored values *mean*, so it is saved as a new PTU. Keep the original.

The one-measurement-one-file arrangement behind the `.pto` is explained in
[The photon container](photon_container.md). Fixed-duration windows are the simplest burst-ID file: every window is a
"burst", so the downstream burst tools can treat time-binned photon data like a burst selection.

## Workflows

- [Intensity traces and file tools](../guides/74_intensity_traces_and_file_tools.md)
- [Handling TTTR files](../guides/12_handling_tttr_files.md)
- [Inspecting a container](../guides/63_pto_inspector.md)
