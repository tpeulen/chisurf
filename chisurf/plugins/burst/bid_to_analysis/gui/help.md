# BID → Analysis

A **BID** (or `.bst` / `.txt`) file is a burst selection: two integer columns,
the index of each burst's first and last photon (inclusive) in a TTTR
measurement. This tool turns those selections into burst tables.

## Inputs
The TTTR file is found by stem — `m000.bid` selects from `m000.spc` (or `.ptu`,
`.ht3`, …) in the same folder or up to three parents; a BID name that starts
with the stem also matches. A row whose TTTR is missing says so and is skipped.

## Detector setup
Configure detector channels and PIE windows in **Detector setup** before
**Process**: the per-detector photon counts and windowed columns of every burst
come from it.

## Outputs
- **PTO** — the measurement's `.pto` container gains a `bursts` table derived
  from the original BID bytes, which are stored beside it as provenance.
- **BUR** — legacy `.bur` table (bursts appended to an existing table) and an
  MTI summary with the measurement duration.
- **SL5** — compressed photon-selection mask.
- **HDF5** — columnar burst table with its source file.

Raw TTTR and BID files are never modified. **Cancel** finishes the current file
and stops the rest of the queue.

## Example
**Load example** writes a simulated stream with six bursts on background and
its BID file to the settings demo folder, then queues it. Converted, it gives
six bursts whose photon numbers are exactly `last − first + 1` of each BID row.

## Further reading
- [Intensity traces and file tools](docs/guides/74_intensity_traces_and_file_tools.md)
- [Exporting burst data](docs/guides/34_exporting_burst_data.md)
