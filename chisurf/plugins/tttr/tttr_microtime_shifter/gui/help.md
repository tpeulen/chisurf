# Micro-time shifter

Shifts the micro-times of TTTR photon files, cyclically: a photon in bin b of
routing channel c moves to bin (b + global + shift_c) mod N, with N the number
of micro-time bins. Use it to bring detectors whose cables or electronics
delay them differently onto one time axis before a lifetime or PIE analysis.

## Files

- **➕ Files…**, **📁 Folder…** (recursive), **🗄 Database…** (the MMFDB
  object store), or drop files and folders on the window.
- All queued files must have the same number of micro-time bins. The preview
  sums them by routing channel. Select a file to reload it (shifts reset);
  **➖ Remove** (or right-click) takes the selected file off the queue, it
  stays on disk.

## Align on the rising edges

- **Trigger level** — a count threshold. For each detector, the first bin up
  to its peak at or above the level is its rising edge.
- **Target bin** — where every rising edge should land.
- **⚡ Auto align** sets each routing channel's shift to
  (shift + target − edge) mod N. Editing the level or the target re-aligns,
  and so does releasing a dragged line: green is the target bin, yellow the
  level.
- A level below the background makes the edge the first bin; one above the
  peak falls back to the peak. Pick it where the edge is steep.

## Shifts

**Global shift** moves every channel; each **Routing channel** row adds its
own shift. **↺ Reset** sets a row back to zero.

## Save

- **💾 Save shifted…** — one queued file: name the shifted file; several:
  choose a folder and one shifted file is written per input. Inputs are
  never changed. Inputs with the same file name go to separate subfolders.
- **Batch folder** + **Save batch** — the same, into a folder typed or chosen
  beforehand.

## MMFDB

**🗄 Register shifts in MMFDB** writes the shifted files into the object
store with their inputs, parameters and outputs as provenance, under the
sample chosen above (refresh the list, enter an id, or create one with
**➕ New sample…**). Warnings appear in the Status dock. **⏹ Stop** discards
pending results; a file write or archive already running may finish.

## Further reading

- [Handling TTTR files](docs/guides/12_handling_tttr_files.md)
