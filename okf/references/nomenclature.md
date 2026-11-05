---
type: Reference
title: Nomenclature
description: The names ChiSurf, ndX and tttrlib show and store (detectors G|G, Bg_<detector>, VV/VH, Tau (G|G), ranges a:b, no HDF5), where old data is renamed on read, and the guard that keeps retired names out.
---

## Where to pick this up

1. **Shrink `test/nomenclature_allowlist.txt`.** Measure with
   `python -m build_tools.dev_utils.nomenclature_audit` (counts per area) or
   `--hits --area chisurf --rule polarisation_ident` (every line). After the
   2026-11-04 sweep 1120 hits remain (from 1541 on the starting commits, same rules):
   the bulk is `polarisation_ident` (206: `i_par`, `n_perp`, `par_raw` in the anisotropy,
   FCS-filter, microtime-histogram and VV/VH G-factor code) and `hdf5` (620, half in OKF
   and docs). Each line says why it is still there.
2. **HDF5 writers in ChiSurf** (`plugins/microscopy/imaging_common/base.py`,
   `imaging_tools`, `imaging_emtk/pixel_model.py`, `core/fluorescence/imaging/pixel_maps.py`,
   `core/fitting/fit.py`, `core/datastore.py`): imaging maps and fit/project files are still
   written as `.h5`. The rule is CSV at most for exports, the measurement container for the
   rest; this is a format migration (readers of old files, docs, tests), not a rename. ndX's
   HDF5 selection export is gone (ndX 318d5cb); HDF5 *input* (MFD HDF5 folders,
   Photon-HDF5 TTTR) is still read and is allow-listed as such.
3. **Stored parameter names:** the PDA models' `BG`/`BR` (stored in fits, registry keys),
   the legacy `fg_fr(Sg, Sr, Bg, Br)` API in `core/fluorescence/fret/__init__.py`, the
   `n_bg` key of the IRF/background results table, `"BG"` of the simulator's species table
   (asserted by `test_setup_widgets`). Each needs its readers moved with it.
4. **tttrlib build.** tttrlib f2f21e89e writes window columns `| lo:hi` and reads both;
   until the arm64 tttrlib is rebuilt from it, ChiSurf (`detector_names.guess_burst_columns`)
   and ndX (`fret_backend.guess_burst_columns`) hand the installed tttrlib the `lo-hi`
   spelling and map back. Drop both shims after the rebuild; tttrlib's own
   `test_a_range_written_lo_colon_hi_is_a_gated_stream` is red until then.
5. **Figures to re-shoot** (captions already in the new names): `52_send_selection_menu`,
   `21_burst_mle*`, `99_img_calibration`, and the ndX/accurate-FRET shots whose scripts now
   write the new column names (`make_screenshots.py`, `screenshots/emtk_shot.py`).

## The names

1. **Detectors** `<emission>|<excitation>` from the setup: `G|G`, `R|G`, `R|R`, `B|B`
   (or the setup's own, `A|A`). Never `green`/`red`/`yellow` detector names, never
   "donor/acceptor channel" for a detector; a role picker reads "Donor (G|G)".
2. **Background** `Bg_<detector>` in kHz, taken off as rate x the burst's `Duration (ms)`.
   No `Bg`/`Br`/`By`, `B_<det>`, `n_bg`, `g_bg`/`s_bg`; a column header is `Bg (kHz)`.
3. **Polarisation** `VV` / `VH`, `G = S_VV / S_VH`; never par/perp or the parallel /
   perpendicular signs.
4. **Lifetimes, anisotropies** after their detector: `Tau (G|G)`, `r (R|R)`, as Burst MLE
   writes them; ndX's gating dimensions read `τ (G|G)`, `r (R|R)` from the columns present.
   `τ_D(0)` of the FRET line and the FCS diffusion time `τ_D` are physics, not detector names.
5. **Ranges** `a:b` (`S prompt G|G (kHz) | 616:3784`, micro-time windows `start:end`).
6. **G factor** per detection colour: `G (G|G)`.
7. **No HDF5**: CSV at most for exports.
8. **Short cells**, explanations in tooltips.

## Where old data is renamed (read side only, no aliases)

- ndX `io/loading.py::current_names` renames a table's columns once when it is read
  (`Tau (green)` -> `Tau (G|G)`, `| 0-2048` -> `| 0:2048`); `app/features/session.py`
  reads a session saved under the old names onto the renamed table; a calibration option
  saved as `measurement` reads as `run` (`fret_backend.background_source`); retired
  constants are dropped on load (`settings/defaults.py` `RETIRED`).
- ChiSurf: setups are converted once (`core/fluorescence/detector_names.LEGACY`); a
  window range is matched by `detector_names.RANGE` (`lo:hi`, and `lo-hi` of older
  tables); PDA micro-time ranges and the G-factor gate parse both separators and write `a:b`.
- tttrlib: `guess_burst_columns` reads `| lo:hi` and `| lo-hi`.

## The guard

`test/test_nomenclature.py` runs the audit against the shrinking
`test/nomenclature_allowlist.txt` (`rule path count  # reason`): a new hit fails, and a
count that went down without its line being lowered fails too. A line that has to name a
retired spelling (a list of names dropped on load) carries `nomenclature: ok`.
