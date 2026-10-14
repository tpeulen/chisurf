---
type: File Format
title: FCS file formats
description: The correlation-curve file formats the FCS experiment reads, and how each format's columns are interpreted.
tags: [reference, file-formats, fcs, correlation]
---

# FCS file formats

The file formats the **FCS** experiment reads, and how their columns are
interpreted by `chisurf.core.fio.fluorescence.fcs.read_fcs` and the readers
behind it.

The readers offered in the GUI are configured in
`chisurf/core/settings/experiment_configs.yaml`:

| Reader | `experiment_reader` | Files |
| --- | --- | --- |
| Seidel Kristine | `kristine` | `*.cor` |
| FCS-CSV | `csv` | any |
| Zeiss Confocor3 | `confocor3` | `*.fcs` |
| China FCS | `china-mat` | `*.mat` |
| Ries SFCS | `ries-mat` | `*.mat` |
| PyCorrFit | `pycorrfit` | `*.csv` |
| ALV-Correlator | `alv` | `*.asc` |
| Correlator.com SIN | `sin` | `*.sin` |

The PCF experiment reuses the `csv` reader as *PCF-CSV* (`*.csv *.txt *.dat`).

Every reader returns `FCSDataset` dictionaries (`correlation_times`,
`correlation_amplitudes`, `correlation_amplitude_weights`, `acquisition_time`,
`mean_count_rate`, optionally `mask` and an intensity trace). A dataset without
weights gets Suren photon-noise weights from `read_fcs`, so every curve reaches
the fit with a noise model.

---

## Seidel Kristine `.cor` {#fcs-kristine}

Implemented in `chisurf.core.fio.fluorescence.fcs.kristine` as
`read_kristine` / `write_kristine`.

### Column layout (write side)

`write_kristine` writes one row per correlation point with **3**, **4** or
**5** columns:

| Column | Content |
| --- | --- |
| 0 | correlation time $\tau$ |
| 1 | correlation amplitude $G(\tau)$ |
| 2 | metadata: row 0 the acquisition time (s), row 1 the mean count rate (kHz), zeros below |
| 3 | optional: uncertainty $\sigma_G(\tau)$ |
| 4 | optional: mask; requires column 3 (writing a mask without uncertainties raises `ValueError`) |

### Column usage when reading

`read_kristine` loads the table with `np.loadtxt` and:

- keeps only rows with $\tau > 0$; $G(\tau)$ is used as stored, no offset added;
- reads the acquisition time and mean count rate from rows 0 and 1 of column 2,
  falling back to 1.0 for both when the column is missing;
- weights each point by $1/\sigma$ from column 3. A point with $\sigma = 0$ (a
  merged curve has one wherever its repeats agreed), or every point when the
  column is missing, takes its $\sigma$ from the Suren noise model instead
  (`chisurf.core.fluorescence.fcs.complete_noise`);
- reads the mask from column 4, or unmasks every point.

---

## FCS-CSV (generic ASCII) {#fcs-csv}

When `experiment_reader: csv`, `read_fcs` loads the file with the generic
`chisurf.core.fio.ascii.Csv` loader (which handles the header, the delimiter
and decimal commas) and reads its columns as:

| Column | Content |
| --- | --- |
| 0 | correlation time $\tau$ |
| 1 | correlation amplitude $G(\tau)$ |
| 2 | uncertainty $\sigma_G(\tau)$; the weight is $1/\sigma$ |
| 3 | optional: mask (all points used when absent) |

At least three columns are required; further columns are ignored.

---

## Zeiss Confocor3 `.fcs` {#fcs-confocor3}

Implemented in `chisurf.core.fio.fluorescence.fcs.confocor3` as
`read_zeiss_fcs` on top of `openFCS` / `openFCS_Multiple` / `openFCS_Single`.

The `.fcs` files are text-based and contain different labeled sections.
The reader primarily uses two of them:

- A **correlation section** (`"Correlation"` or `"Correlation (Multi, Averaged)"`)
- A **count-rate section** (`"Count Rate"`)

### Correlation section

For multi-curve files (`openFCS_Multiple`), the correlation part is parsed as:

```python
# correlation rows from the FcsDataSet CorrelationArray
corr.append((float(row[3]) * 1000, float(row[4]) - 1))  # tau [ms], corr - 1
...
correlation_time = correlation[:, 0]          # ms
correlation_amplitude = correlation[:, 1] + 1.0
```

Thus each correlation row in the file has at least:

- **Column 3**: lag time `τ` in seconds → converted to **milliseconds**.
- **Column 4**: `G(τ) - 1`
  - The reader adds `+1.0` to get `G(τ)` as stored in
    `correlation_amplitudes`.

For single-curve files (`openFCS_Single`), correlation rows look like:

```python
# tau in ms, corr-function
corr.append((float(row[0]), float(row[1]) - 1))
```

So the **first column** is lag time in **ms** and the **second column** is
`G(τ) - 1`.

### Intensity trace section

In the multiple-curve variant, the **Count Rate** section is read as:

```python
# tau in ms, trace in kHz
trace.append((float(row[3]) * 1000, float(row[4]) / 1000))
```

So each row in the count-rate block contains at least:

- **Column 3**: time in seconds → converted to **ms**.
- **Column 4**: count rate in Hz → converted to **kHz**.

In the single-curve variant:

```python
# tau in ms, trace in kHz
trace.append((float(row[0]) * 1000, float(row[1])))
```

The reader uses the trace to compute acquisition time and mean count rate,
which in turn are used to derive weights for `correlation_amplitude_weights`.

```{note}
The trace column is already a **rate** (kHz), so the mean count rate is the
*mean* of that column. Summing it and dividing by the duration divides by the
number of bins per unit time — a factor set only by how the trace happened to
be binned — and the resulting count rate feeds the noise model, silently
rescaling every weight derived from it. This applies to every FCS reader that
derives a count rate from a trace.
```

### One file, many curves

A ConfoCor `.fcs` is a measurement archive rather than a single curve. A
two-colour (FCCS) session typically yields **four repeats of four different
kinds of curve**, and ChiSurf loads the file as one dataset group holding all
of them:

| curve type | meaning |
| --- | --- |
| `AC1`, `AC2` | autocorrelation of detector 1 / detector 2 |
| `CC12`, `CC21` | cross-correlation between the detectors, computed both ways |

The kind is taken from the `Channel` key of each `FcsDataSet` section and is
preserved in two places: appended to `measurement_id` (so a curve is named
`<file>_<index>_<type>`, e.g. `sample.fcs_2_CC12`) and stored as
`correlation_type` in the curve's `meta_data`.

Curves of different kinds answer different questions — the autocorrelations
give `N` and `D` per channel, the cross-correlations give the co-diffusing
fraction — so they are not repeats of one another and must not be averaged
together. Fitting the group creates one fit with one member per curve.

---

## China FCS MATLAB `.mat` {#fcs-china-mat}

Implemented in `chisurf.core.fio.fluorescence.fcs.china` as `read_china_mat`.

The MATLAB file is expected to contain arrays with specific names, for example:

- `AA`, `BB`, `AAxB`: correlation curves
- `IntA`, `IntB`: intensity traces

Each correlation matrix is paired with its intensity trace(s):

| Correlation | Intensity | Curve |
| --- | --- | --- |
| `AA` | `IntA` | autocorrelation A |
| `BB` | `IntB` | autocorrelation B |
| `AAxB` | `IntA` + `IntB` | cross-correlation |

Curves are named `<correlation>_<measurement>`, e.g. `AA_1`.

### Correlation arrays

For each correlation key, `read_china_mat` interprets the matrix columns as:

```python
correlation_time = m[correlation_key][:, 0]
correlation_amplitude = m[correlation_key][:, measurement_number] + 1.0
```

So in each correlation matrix (e.g. `AA`):

- **Column 0**: lag time `τ` (as stored in the `.mat` file).
- **Columns 1..N-1**: correlation curves for individual measurements, stored
  as `G(τ) - 1`. The reader **adds 1.0** to obtain `G(τ)`.

### Intensity arrays

For each measurement:

```python
# single-channel case
intensity_time = m[intensity_key][:, 0]
intensity       = m[intensity_key][:, measurement_number]

# dual-channel case (Cross_Axb)
intensity = 0
for k in intensity_key:   # 'IntA', 'IntB'
    intensity += m[k][:, measurement_number]
intensity_time = m[k][:, 0]
```

So in each intensity matrix (`IntA`, `IntB`):

- **Column 0**: time points (units as stored in the `.mat` file).
- **Columns 1..N-1**: count-rate traces for individual measurements.

The reader derives:

- `acquisition_time`: last time point of the intensity trace.
- `mean_count_rate`: `sum(intensity) / (acquisition_time * 1000.0)`.

These are used with the correlation data to compute
`correlation_amplitude_weights` via `chisurf.core.fluorescence.fcs.noise`.

---

## PyCorrFit CSV {#fcs-pycorrfit}

Implemented in `chisurf.core.fio.fluorescence.fcs.pycorrfit` as `read_pycorrfit`
(on top of `openCSV`). The format is flexible but the reader assumes a
PyCorrFit-style structure:

- Optional header lines starting with `#`.
- A **correlation section**.
- One or two **trace sections** marked by `# BEGIN TRACE` and
  `# BEGIN SECOND TRACE`.

### Correlation section columns

From the `openCSV` docstring and parsing logic:

- Minimal form (two columns):

  ```text
  tau[s]   G(τ)
  ```

  - Column 0: lag time `τ` in seconds (later converted to ms internally).
  - Column 1: correlation amplitude `G(τ)`.

- Extended form (five columns):

  ```text
  # Channel (tau [s])    Experimental correlation    Fitted correlation    Residuals    Weights [model function]
  2.0e-07    1.56e-01    1.54e-01    2.69e-03    7.31e-03
  ...
  ```

  - Column 0: lag time `τ` in seconds.
  - Column 1: experimental correlation `G(τ)`.
  - Column 2: fitted correlation (ignored).
  - Column 3: residuals (ignored).
  - Column 4: PyCorrFit's weights. They are parsed but **not** used: the
    curve is weighted by the Suren noise model from the duration and count
    rate below.

Internally, the reader stores the correlation as an array of `(τ_ms, G(τ))`
with time converted to milliseconds.

### Trace sections

- After `# BEGIN TRACE`:

  ```text
  time[s]   intensity[kHz]
  ```

  - Column 0: time `t` in seconds.
  - Column 1: intensity (kHz).

- After `# BEGIN SECOND TRACE` (for cross-correlation): same two-column
  layout for the second channel.

The reader collects:

- `Duration`: measurement duration in seconds (from a `#   duration [s]` line).
- `Count rates`: a list of average count rates parsed from lines containing
  `"avg. signal"`.

These are combined to compute noise-based
`correlation_amplitude_weights` via `chisurf.core.fluorescence.fcs.noise`.

---

## ALV-Correlator `.asc` {#fcs-alv}

Implemented in `chisurf.core.fio.fluorescence.fcs.asc_alv` as `read_asc`, built on
`openASC` / `openASC_old` / `openASC_ALV_7004`.

Two related text formats are supported:

- Classic **ALV-6000** `.asc` files (`openASC_old`).
- Newer **ALV-7004/USB** `.asc` files (`openASC_ALV_7004`).

Both provide a **Correlation** section and a **Count Rate** section.

### Classic ALV-6000 `.asc` (openASC_old)

From the docstring and parsing logic:

- **Correlation** section (quoted header `"Correlation"`):

  ```text
  tau[ms]   G(τ)
  ```

  - Column 0: lag time `τ` in milliseconds.
  - Column 1: `G(τ) - 1`, as ALV stores it.

- **Count Rate** section (quoted header `"Count Rate"`):

  ```text
  time[s]   count_rate[kHz]
  ```

  - Column 0: time in seconds.
  - Column 1: count rate in kHz.

The reader bins and splits traces as needed (for multiple curves or dual
channels) and constructs:

- `correlation_times`: from the first column of the correlation section.
- `correlation_amplitudes`: the second column plus 1.0, i.e. `G(τ)` (for
  both ALV formats).
- `intensity_trace_times`: from the first column of the Count Rate section
  (converted to seconds or ms depending on mode).
- `intensity_trace`: count-rate traces assembled from one or two channels.

### ALV-7004/USB `.asc` (openASC_ALV_7004)

In the newer format, the correlation and count-rate blocks look like:

```text
"Correlation"
  tau   C1   C2   C3   C4
  ...

"Count Rate"
  time[s]   CR1   CR2   CR3   CR4
  ...
```

- **Correlation** rows (parsed into `allcorr`):
  - Column 0: lag time `τ`.
  - Columns 1..4: correlation curves for up to four channels or
    auto/cross-correlations.

- **Count Rate** rows (parsed into `alltrac`):
  - Column 0: time in seconds (later converted to ms internally).
  - Columns 1..4: count rates for up to four channels.

`read_asc` then builds one or more `FCSDataset` entries by:

- Selecting the appropriate correlation column (AC1, AC2, CC12, CC21, etc.).
- Constructing one or two intensity traces from the corresponding count-rate
  columns.
- Converting intensity time to seconds and deriving `acquisition_time` and
  `mean_count_rate`.
- Computing `correlation_amplitude_weights` via
  `chisurf.core.fluorescence.fcs.noise`.

---

## Ries SFCS `.mat` {#fcs-ries-mat}

Implemented in `chisurf.core.fio.fluorescence.fcs.ries_mat` as
`read_ries_mat`. The file must hold the MATLAB `g` structure written by the
Ries scanning-FCS tools; a file without it raises `ValueError`. Every
column of the autocorrelations (`ac`/`act`), dual-colour (`dc`/`dct`),
two-focus (`twof`/`twoft`) and dual-colour two-focus (`dc2f`/`dc2ft`) blocks
becomes one curve, with the amplitudes used as stored. The file keeps only
trace averages (`trace`), so the mean count rate is that average and the
acquisition time is taken as 1 s (both 1.0 without a trace); the Suren noise
weights therefore carry only relative, not absolute, information.

---

## Correlator.com `.sin` {#fcs-sin}

Implemented in `chisurf.core.fio.fluorescence.fcs.sin_correlator` as
`read_sin`, without a PyCorrFit dependency. The `Mode=` line decides the
layout: integer channel indices select the layout with one
`[CorrelationFunction]` block and an `[IntensityHistory]` block, mode names
("Single Auto", "Quad", …) the older layout. Each correlation becomes one curve
with lag times in ms and intensities in kHz; the acquisition time (s) and mean
count rate are estimated from the intensity history and feed the noise model.

---

## Notes on additional FCS backends

`read_fcs` also accepts these `reader_name`s, which the GUI does not offer:

- PicoQuant **`.dat`** (`pq.dat` → `pq_dat.read_dat`): triplets of columns per
  correlation — $\tau$, $G(\tau)$ and $\sigma_G(\tau)$; a zero error is
  replaced by $10^{12}$, which gives the point no weight.
- YAML (`yaml` → `fcs_yaml.read_yaml`): the inverse of `write_yaml`, a list of
  `FCSDataset` mappings; each needs `measurement_id`, `correlation_times` and
  `correlation_amplitudes`.
- PicoQuant **`.pqres`** (`pqres` →
  `chisurf.core.fio.fluorescence.pqres.read_pqres_fcs`).
