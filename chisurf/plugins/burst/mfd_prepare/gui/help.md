# MFD Prepare

Reads a burst-analysis folder the way the 2D MFD (multiparameter
fluorescence detection) fit reads it, and reports what it found — without
fitting, moving or rewriting anything. When the MFD reader refuses a folder or
a detector, this report says why.

## How to use it

1. **Browse…** to the analysis folder (the one holding `bi4_bur/` and
   `Info/`), its `bi4_bur` directory, or one `.bur` file.
2. Press **Prepare**. Without a connected RPC service it runs in this window,
   so the window waits the few seconds the photons take to read.
3. Read the report.

## What the report says

- **bursts** — bursts read, and the interleaved all-zero sentinel rows of the
  `.bur` format that were removed.
- **photon index** — whether `Number of Photons = Last − First + 1`
  (inclusive, current writer) or `Last − First` (older folders). Detected and
  honoured, so no burst gains a stray photon.
- **mean micro time from** — the `.bur` column when present, otherwise the
  photons.
- **file → path [origin]** — where each measurement's photons were found:
  the analysis manifest, the legacy `.mti` sidecar, or a file beside the
  folder. A photon file that cannot be found or read is an error, never an
  empty stream.
- **bursts with no photons** — per detector.
- **count agreement** — for each detector, the fraction of bursts whose photon
  count, recomputed from the photons with the channel definition in use,
  equals the `.bur` column. **ok** needs 0.98. An **UNVERIFIED** detector
  would put photons under the wrong colour, and the MFD fit refuses it.

The channel definition comes from the analysis manifest, or is inferred from
the photons by reproducing the count columns exactly. An acceptor-excitation
detector is a micro-time window on the acceptor channels; no detector name
can say which window.

Press **Guide** for the walk-through.

## Further reading

- [Checking a burst folder before an MFD fit](docs/guides/85_mfd_prepare.md)
- [Fitting an MFD burst histogram](docs/guides/57_mfd_fitting.md)
- [Fitting the 2D MFD histogram](docs/concepts/mfd_fitting.md)
