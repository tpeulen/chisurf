---
type: Manual Page
title: VV/VH format
description: 'If both parallel and perpendicular data is saved within the same file and no time axis is defined, the following settings need to be made:'
tags: [manual, file-formats, settings]
---

# VV/VH format

If both parallel and perpendicular data are saved within the same file (the VV channel followed by
the VH channel, one column of counts, no time axis), tick *Two stacked VV/VH files* in the
anisotropy wizard's *Data* step:

```{image} figures/anisotropy_wizard_stacked.png
:align: center
```

**The Data step for stacked VV/VH files.** One field for the IRF (*IRF VV/VH*) and one for the
decays (*Data VV/VH*); each file is split into its VV and VH halves. Without a time column the
*Bin width (ns)* sets the time axis -- here 0.008 ns for the bundled recording in
`test/data/tcspc/Jordi` (2048 channels per polarisation).

Set *Repetition rate (MHz)* to the excitation rate each fluorophore sees; with pulsed interleaved
excitation (PIE) that is half the laser's total rate (e.g. 20 MHz of a 40 MHz PIE scheme).
