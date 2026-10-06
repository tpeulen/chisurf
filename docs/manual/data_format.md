---
type: Manual Page
title: Data format
description: 'For analysis with ChiSurf, your correlation data has to be exported in text format with either three or four columns:'
tags: [manual, file-formats, correlation]
---

# Data format

For analysis with ChiSurf, your correlation data has to be exported in text format with either three or four columns:

1. Column 1: correlation time
2. Column 2: correlation amplitude
3. Column 3: first value reflects the measurement time, second value the average count rate, the rest of this column is filled with zeros
4. Column 4: standard deviation of the correlation amplitude

The measurement time and the average count rate in column 3 are used to estimate the uncertainties in your correlation amplitudes if the standard deviation is not available, i.e. single measurement was performed or the hardware / software used for correlation does not provide these values.
