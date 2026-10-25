# Metadata editor

Edit the metadata of a measurement: sample, dyes, buffer, instrument, and the identifiers that later tools
(BURST, QuEst, MMFDB deposit) read. The editor writes structured fields — not free text — so a value entered
here is the value every downstream tool sees.

## How it works
1. Open the tool on a loaded measurement (or from the burst workflow's metadata step).
2. Fill the fields: sample name, dyes (donor/acceptor), concentrations, buffer, temperature, instrument and
   detector details, and the measurement identifier.
3. Press Save. The metadata is written to the measurement's record and travels with the ``.pto`` project and
   any MMFDB deposit.

## Before trusting a result
Dye names must match the dye repository's spelling — a typo silently disables the per-dye corrections that
QuEst and the FRET corrections apply.
