---
type: File Format
title: Becker & Hickl .set File Reader
description: BeckerHicklSetReader reads the timing parameters of a Becker & Hickl SPC .set file.
tags: [reference, file-formats, becker, hickl]
---

# Becker & Hickl .set File Reader

A Becker & Hickl SPC measurement writes its setup — sync frequency, TAC range,
TAC conversion factor, ADC resolution — to a `.set` file beside the `.spc`
photon stream. `BeckerHicklSetReader` reads it; the channel-definition wizard
uses it to take the micro-time resolution from the measurement rather than from
a typed value.

## Usage

```python
from chisurf.core.fio.fluorescence import BeckerHicklSetReader

reader = BeckerHicklSetReader("test/data/tttr/BH/830/bh.set")

f_sync = reader.get_param("SYN_FQ")          # MHz
dt_macro = reader.macro_time_resolution      # s
dt_micro = reader.micro_time_resolution      # ns
tac_range = reader.tac_range                 # s
reader.summary()
```

For `test/data/tttr/BH/830/bh.set`, `summary()` prints:

```text
File: test/data/tttr/BH/830/bh.set
  SP_SYN_FQ (MHz):          -50.980392
  Macro-time resolution:    19.615 ns
  SP_TAC_TC (s):            1.831e-11 s
  Micro-time resolution:    0.018 ns
  SP_TAC_R (s):             1.500e-07 s
  TAC full-scale range:     150.022 ns
```

## Properties

| Property | Definition | Unit |
| --- | --- | --- |
| `macro_time_resolution` | 1 / \|`SP_SYN_FQ`\| (MHz → Hz) | s |
| `micro_time_resolution` | `SP_TAC_TC` | **ns** |
| `tac_range` | `SP_TAC_R` | s |

Note the mixed units: the micro-time resolution is returned in nanoseconds, the
other two in seconds. A missing parameter makes the property `None`.

## Parameters

Each `SP_<NAME>,<F|I>,<value>]` entry becomes `params[<NAME>]`, a float for `F`
and an int for `I`; `get_param` takes the name without the `SP_` prefix.

| Name | Meaning |
| --- | --- |
| `SYN_FQ` | sync frequency, MHz (the sign only encodes the edge) |
| `TAC_TC` | TAC conversion factor — the micro-time channel width, s |
| `TAC_R` | full TAC span, s |
| `ADC_RE` | ADC resolution — the number of micro-time channels |
