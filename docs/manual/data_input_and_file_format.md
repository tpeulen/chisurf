---
type: Manual Page
title: Data input and file format
description: ChiSurf can read a variety of text files and formats.
tags: [manual, file-formats, data, input, file, format]
---

# Data input and file format

ChiSurf can read a variety of text files and formats. For time-resolved fluorescence intensities in polarization-resolved experiments, we usually use two different file formats: (i) two files of two columns each, or (ii) a single file of one column (the "VV/VH format").

In the first case, two files are required, one containing the parallel channel and one the perpendicular channel data. Both files contain two columns; the first column is the time in nanoseconds, while the second column contains the actual data (photon counts in this respective time bin).

In the second case, only a single file is required, in which the data from perpendicular and parallel channel are stacked on top of each other.

A header is allowed in both formats: the number of rows to skip is set in the
**Read data** dock (*Skiprows*).

A two-column file, here the start of a decay of the bundled IBH sample
(`test/data/tcspc/ibh_sample/Decay_577D.txt`): ten header rows, then channel and
counts, tab separated (read with *Skiprows* 10):

```text
Item name: Decay

Real time: 362.06
Live time: 155.88

Comment: 


Chan	Data
1	0
2	0
3	0
```

A single-column VV/VH file (`test/data/tcspc/Jordi/02_18-577+7.5uM(577)UP_8ps.dat`,
4096 rows): rows 1–2048 are the parallel (VV) decay, rows 2049–4096 the
perpendicular (VH) one, stacked without a separator. The time per channel is not
in the file (here 8 ps); it is entered in the dock.

```text
row  300:  698
row  301:  774
...
row 2348:  119
row 2349:  122
```

I personally prefer the single-column VV/VH-format as it reduces the amount of files in my data export folders by 50%, however, I need of course to remember with which time resolution (here 20 ps) the TCSPC histograms were exported.

ChiSurf is started from the project environment:

```shell
pixi run chisurf          # or, inside the activated environment: python -m chisurf
```

```{image} figures/main_read_data_vvvh.png
:align: center
```

**Fig. Reading a VV/VH file.** The **Read data** dock with **Experiment** TCSPC and
**File type** TXT/CSV. Under *Anisotropy (VV/VH)*, **stacked** is ticked and
**pol.** set to **VV,VH**: the file's two halves are read as the parallel and the
perpendicular decay (ticking *stacked* also drops the header row and scales dt by
the rebin factor). *g-factor* is the detection-efficiency ratio of the two
channels, *l1*/*l2* the mixing factors and *VH shift* a channel shift of VH
relative to VV; the **g-factor** button opens the tool that adjusts shift and
g-factor with a reference dye.
