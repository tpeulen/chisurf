# intensity_trace — emtk port report

**Accepted** 2026-10-05. The ribbon's **Spectroscopy → Single-Molecule → Intensity trace** was a script entry that built
the Qt widget. The manifest now declares `gui` (`qt_tool:IntensityTrace`, the fallback) and `emtk` (`gui.app:make_app`).

## What was built

- `model.py` (Qt-free) holds the binning, histograms, HMM, BIC, dwell times with exponential fits, FRET per state, and
  the structured export (`<stem>_HMM#<n>_<ms>ms/{bst,traces,hist}`).
  - Binning is the trace browser's `bin_trace`; the HMM is the shared HMM core.
  - The Qt widget moved verbatim to `qt_tool.py` and uses the model's functions.
  - `__init__.py` re-exports the Qt names lazily, so the trace browser's imports still work and the native app loads
    without Qt. The pyqtgraph allow-list entry moved with the file.
- `gui/app.py` + `gui/intensity_trace.view.json`:
  - controls as a spec (file row, Processing / HMM tabs), with the detector list as a custom section;
  - an implot grid of each trace with its count histogram, linked time and count axes;
  - the state, occupancy and FRET rows after the HMM;
  - a **Results** dock (BIC elbow, dwell times with fits and their settings and save, transition matrix, FRET per
    state);
  - a **Detector Setup** dock tab: the shared `ChannelDefinitionWidget`, the Qt tool's Setup dialog;
  - binning and fitting on a worker.
- `demo.py` + an **Example** button: a seeded two-state FRET switcher (dwells 20 / 80 ms) with a known answer.
- `help.md`, `guide.json`: awaited steps for Example, the HMM tab, Compute HMM and Dwell Times.

## Fixed relative to Qt (deliberate, tested)

- Without a setup, Qt offered routing channels 0–7 and binned **only the first ticked one** (guide 74 even documented
  this). Natively the selection lists the channels the file uses (0, 1, 8, 9 on BH_SPC132) and bins every ticked one.

## Acceptance gate

1. **Functional**: `intensity_trace/test`, **10 passed**. The model reproduces the Qt baseline exactly on a temp copy
   of BH_SPC132.spc: 6233 bins, counts 56499, 3-state occupancy [5692, 386, 155], the transition matrix, and the same 7
   output files.
2. **Real input**:
   - Example → typed window (re-bins to 4001 bins) → detector untick and re-tick → typed bins → HMM tab → typed
     components → Compute HMM (FRET per state 0.3 / 0.7 recovered) → Dwell Times, Matrix and FRET result tabs, at
     1200x800 and 800x600 (each control scrolled into view in its dock);
   - BIC elbow, then the Save Traces and Save Histograms and Fits dialogs;
   - the Load dialog, a drop, and choosing a setup;
   - Edit setups (the shared editor, whose change re-bins);
   - Help, and the tour waiting for Example;
   - the native app loading without Qt.
3. **Parity**: `compare.json` gives `lost: []`, `untooltipped: []`, Qt-free (Qt 79 → native 171; union over empty,
   loaded, setup editor, HMM and the four results). `deliberate.json`:
   - Qt's Routing Channel 0–7 boxes (see above);
   - the cells of the setup Qt's Setup page had preloaded (the native editor is the accepted shared one, empty in the
     hermetic capture);
   - Edit JSON, removed by the shared editor's own report;
   - axis numbers.
4. **Visual**: `after_<state>_{1200x800,800x600}.png`, read. Bugs found and fixed while reading:
   - the transition-matrix heatmap was flipped (P(0→0) drawn at to-state 2);
   - the four result buttons shared one emtk ID (`…##result`), so only the first answered a press;
   - the Setup field said "Routing channels" while an edited setup was in use;
   - the linked plot columns lost their auto-fit (limits are now set once per binned trace).
5. **Docs**: guide 74 updated for the native window (Setup and Edit setups, Example, the channel rule, the Results
   dock); `figures/intensity_trace.png` regenerated from the native tool in its caption's state
   (`scripts/capture_docs.py`).

## Open

- Single-button rows of the spec stretch to the full width (Load TTTR, Edit setups, BIC Elbow); `weight: 0` does not
  shrink a lone button. That is emtk view_form behaviour, shared by every spec.
- The shared detector editor's "Detectors" header overlaps its "Polarization resolved" box in a narrow dock.
- Duplicate emtk IDs (`label##same`) fail silently; an emtk debug check would catch the whole class.
- `qt_tool.py` still uses pyqtgraph directly (the allow-list line moved, it was not struck).
- The trace browser still hands its HMM button to the Qt `IntensityTrace` (`trace_browser/gui/host.py`, another
  stream's uncommitted files).
