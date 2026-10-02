# Micro-time histogram

Turns photon files into the decay the TCSPC analysis fits: the micro-times are histogrammed per detector, split into
parallel (VV) and perpendicular (VH) streams, gated by excitation window and optionally by bursts, and written as one
column.

## Inputs and options (tab 1)
- **Run** — **Compute** reads the selected photons in the background; **Save** writes the decay to *Output*; **Save as…**
  asks for another name; **Transfer to ChiSurf** saves and adds the TCSPC dataset. *Autosave after compute* writes
  *Output* once the computation succeeds.
- **Photon files** — **Files…**, **Folder…** (recursive), **Database…** (the MMFDB object store), or drop files on
  the window. Tick a file to include it; **All / None / Remove / Clear** act on the list (right-click a row to remove it).
  Headerless SPC data needs its subtype in *TTTR format*.
- **Burst selections** — queue `.bst`/`.bur` photon-index files; photon bounds are inclusive, overlaps are counted once
  and bounds are clipped to the stream. **Find TTTR** looks four folders up for the matching photon files.
- **Detector and channels** — the detector chooses the interleaved routing channels (parallel, perpendicular, ...) and
  the G-factor; *Parallel* / *Perpendicular* can be edited. Without *Polarization resolved* there is one unpolarized stream.
- **Reading and gates** — *Excitation window* applies an inclusive micro-time gate, *Binning* groups adjacent bins.
- **Time step, G-factor and shifts** — *dt* is read from the file header (typing a value keeps it); the shifts pad or
  clip the VV / VH histogram (the photon Micro-time Shifter instead wraps modulo the TAC period).

## Detector definition (tab 2)
The full shared detector editor: routing, PIE windows, TTTR reading, G-factor, TAC linearization and optical parameters.

## Outputs
The export is the VV bins followed by the VH bins as one integer column. The diagnostic combined trace is VV + 2G VH,
its FWHM is the width between the integer crossings of half the maximum. Transfer hands the time step, G-factor and
polarization to the TCSPC workspace.

Further reading: [Decays and correlation curves straight from a photon file](docs/guides/73_tttr_decay_and_correlation.md),
[TCSPC lifetime fitting](docs/concepts/tcspc_lifetime.md).
