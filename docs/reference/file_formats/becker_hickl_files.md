---
type: File Format
title: Becker & Hickl File Readers
description: Reading Becker & Hickl .sdt decay files and .set setup files from Python.
tags: [reference, file-formats, becker, hickl, files]
---

# Becker & Hickl File Readers

`chisurf.core.fio.fluorescence` exports two readers for files written by
Becker & Hickl SPCM software:

- `SdtFile` — `.sdt` files: TCSPC histograms (decays, or decay images) plus the
  setup and measurement description.
- `BeckerHicklSetReader` — `.set` files: the SPC setup parameters, from which the
  macro- and micro-time resolution of a `.spc` photon stream follow. Its own page
  is {doc}`becker_hickl_set`.

In the GUI, an `.sdt` file is opened through the TCSPC data reader
({doc}`tcspc_files`); the classes below are the Python route.

## Usage

```python
from chisurf.core.fio.fluorescence import BeckerHicklSetReader, SdtFile

sdt = SdtFile("test/data/tcspc/BH_SDT/140507p.sdt")
decay = sdt.data[0]   # counts, shape (1, 1024) for this point measurement
t = sdt.times[0]      # time axis in seconds, same length as the last axis

setup = BeckerHicklSetReader("test/data/tttr/BH/830/bh.set")
dt_macro = setup.macro_time_resolution  # s
dt_micro = setup.micro_time_resolution  # ns
```

## SdtFile

| Attribute | Content |
| --- | --- |
| `data` | list of count arrays, one per data block; the last axis is the micro-time |
| `times` | list of time axes in seconds, one per block |
| `measure_info` | measurement description records |
| `block_headers` | data-block headers; `block_measure_info(i)` returns block *i*'s description |
| `header` | file header |
| `info` | the ASCII info section |
| `setup` | the setup block |

Only "SPC Setup & Data" and "SPC FCS Data" files are read; any other SDT type
raises `NotImplementedError`. A block whose size matches the scan or image
dimensions is reshaped to `(x, y, channels)`; otherwise it is `(n, channels)`.

## BeckerHicklSetReader

| Member | Content |
| --- | --- |
| `macro_time_resolution` | $1/\lvert f_\mathrm{sync}\rvert$, in seconds |
| `micro_time_resolution` | `SP_TAC_TC`, in **nanoseconds** |
| `tac_range` | `SP_TAC_R`, in seconds |
| `get_param(name, default=None)` | a raw parameter, named without the `SP_` prefix |
| `summary()` | prints the timing parameters |
