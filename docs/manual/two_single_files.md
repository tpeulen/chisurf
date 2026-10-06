---
type: Manual Page
title: Two single files
description: 'If the parallel and perpendicular data is saved in two separate files, including a time axis, the following reading parameter should be set:'
tags: [manual, single, files]
---

# Two single files

If the parallel and perpendicular data are saved in separate files, each with a time axis, the
anisotropy wizard reads them with four paths and its own reader settings (*Data* step):

```{image} figures/anisotropy_wizard_two_files.png
:align: center
```

**The Data step for four two-column files.** *Two stacked VV/VH files* is off, so there is one
field each for *IRF VV*, *IRF VH*, *Data VV* and *Data VH* (type a path, press **Browse**, or drop
the files on the window); *First column is time (ns)* is ticked, which greys *Bin width* because the
time axis comes from the files. "found" beside each field confirms the file exists. The files here
are the bundled stacked recording of `test/data/tcspc/Jordi` written as time/count columns.

If the files carry a header, tick *Use file header* or give the number of *Header rows* to skip.

The *Repetition rate (MHz)* is needed when the excitation period is shorter than the full decay
(e.g. pulsed interleaved excitation or single-molecule set-ups), so that the repeated excitation is
part of the lifetime model. The g-factor is set two steps later, under *Corrections*.
