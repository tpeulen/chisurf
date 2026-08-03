---
type: Subsystem
title: Data IO
description: File loading and the format registry — TTTR photon data via tttrlib, ASCII/FCS curves, structures, and slow-storage staging.
resource: chisurf/core/fio/
tags: [io, core]
timestamp: '2026-07-05T00:00:00Z'
---

# Scope

`chisurf/core/fio/` is the Qt-free IO layer: it turns files on disk (or a slow
network share) into the domain objects consumed by [Core](/subsystems/core.md)
and the fitting models.

| Module | Handles |
| --- | --- |
| `fluorescence/photons.py`, `burst.py` | single-photon (TTTR) streams |
| `fluorescence/fcs/*` | correlation curves (Kristine, ALV, ConfoCor3, PyCorrFit, ISS, …) |
| `fluorescence/tcspc.py`, `sdtfile.py`, `bhfiles.py`, `thdfile.py` | TCSPC decays / B&H |
| `ascii.py`, `vv_vh.py`, `zipped.py` | generic text / stacked VV/VH decays (historically "jordi", see [reference](/references/vv-vh-decay-format.md)) / gz-bz2 wrappers |
| `structure/coordinates.py`, `density.py` | PDB / density structures |
| `mmcif/` | mmCIF importer + database resolver (feeds [MMFDB](/architecture/mmfdb.md)) |
| `staging.py` | slow/network-file staging (below) |

# Format registry (`chisurf/core/file_formats.py` + `file_formats.json`)

`FILE_FORMATS` maps an extension to `{name, description, tttrlib_container,
reading_routine, experiments}`. Extension → experiment routing:

| Ext | Format | tttrlib container | Experiments |
| --- | --- | --- | --- |
| `.ptu` / `.ht3` | PicoQuant PTU/HT3 | PTU / HT3 | pda, tcspc, fcs, pch, rics |
| `.spc` | Becker & Hickl SPC | SPC-130 | pda, tcspc, fcs |
| `.h5` / `.hdf5` | Photon-HDF5 | PHOTON-HDF5 | pda, tcspc, fcs, pch, rics |
| `.pt3`, `.t3r`, `.sm`, `.raw` | PicoQuant / SM / CZ-RAW | (varies) | tcspc (+fcs/pda) |
| `.csv` / `.txt` / `.fcs` | text / ISS FCS | — | fcs, pda |

# Correlation curves carry their own weights

An FCS reader does not only parse a curve: it derives
`correlation_amplitude_weights` from the acquisition time and the **mean count
rate**, so the count rate is part of the fit, not metadata. The intensity trace
is stored as a *rate* per bin, so that mean is the mean of the trace; summing
it and dividing by the duration divides by the bins per unit time — a factor
set only by the binning — and rescales every weight. Two readers did that (the
ConfoCor cross-correlation branch and the ALV fallback), which made affected
curves fit far "better" than curves built from the same photons. A file that
records the instrument's own count rate is the ground truth for checking this,
and at short lag the derived error must match the empirical scatter between
repeats.

A measured uncertainty of **zero** is not a small uncertainty, it is a missing
one — and a reader inverts that column into a weight, so a zero becomes an
infinite weight and a handful of such points decide the χ² alone. Merged curves
produce them by construction: the standard error over the repeats is exactly
zero at every lag where the repeats agreed, which at long lags is common. The
seam that handles this is `fluorescence/fcs.complete_noise`, which fills the
unusable points from the noise model and guarantees a strictly positive result;
readers route the measured column through it, and the merger completes the
column before writing so the file itself never carries a zero.

A reader may also return **many curves per file**: a cross-correlation
measurement archive holds repeats of two autocorrelations and two
cross-correlations, which are different quantities rather than repeats of one.
Whatever distinguishes them must survive into the dataset — see
[the assistant's use of it](/subsystems/llm-agent.md).

# Photon / TTTR data (tttrlib)

Time-tagged single-photon records are parsed by the compiled `tttrlib`
container (see [compiled modules](/subsystems/compiled-modules.md)); ~30 modules
across `core/fio`, `core/experiments`, and models depend on it. Per-domain
readers wrap it: `experiments/tcspc/tttr_reader.py`, `experiments/rics/tttr_loader.py`,
`experiments/{pch,pda,fcs}/reader.py`, `experiments/deer/reader.py`.

`fluorescence/photons.py` holds `Photons`, a sliceable wrapper around one
`tttrlib.TTTR`: the per-photon arrays (`macro_times`, `micro_times`,
`routing_channels`, `event_types`), the calibration (`mt_clk` and `dt`, **both
in seconds**), `by_channel(...)`, and `where("(ROUT == 0) & (TAC > 100)")` for
expression selection. `photons.tttr` exposes the underlying object, so anything
that wants `tttrlib` directly can have it.

It used to convert every format into a **bespoke Photon-HDF5 file** — a
PyTables table written to a scratch file per measurement, read back through
per-format record parsers of its own (`fluorescence/tttr.py`). That whole layer
is gone: it doubled every measurement on disk, kept an HDF5 file open for the
life of the process, and duplicated format support `tttrlib` already has. The
chisurf-side multi-tau correlator (`core/fluorescence/fcs/correlate.py`) went
with it, for the same reason — `tttrlib.Correlator` is the one implementation.

# Slow-storage staging (`chisurf/core/fio/staging.py`)

Because `tttrlib.TTTR(path)` is a single blocking C++ call with **no progress
hook**, multi-GB reads from a slow share would freeze the caller. `staging`:

1. Probes source throughput via a small head read.
2. If *slow* + large, stream-copies to a local temp with a chunked loop that
   emits `progress_cb` (bytes/%/MB·s/ETA), then parses the local copy.
3. If *fast*, returns the original path unchanged (no copy).

`staged_source(path)` is a context manager (temp is ephemeral, auto-deleted);
`open_tttr(path)` stages+parses+cleans in one call. It is **Qt-free** — reusable
from the [server](/architecture/server.md)/CLI; the GUI
(`chisurf/gui/widgets/staged_loading`) only adds a progress dialog. Tunables live
in the `data_loading` settings section; `StagingCancelled` reports user cancel.

See also: [overview](/overview.md), [macros & CLI](/subsystems/macros-cli.md),
[history](/subsystems/history.md).
