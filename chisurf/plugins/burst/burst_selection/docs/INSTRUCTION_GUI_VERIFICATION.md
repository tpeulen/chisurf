# Instruction: Desktop GUI Verification

## Goal

Verify the current native Burst Analysis hub selection step and, separately,
the retained modern Qt tool (`gui/tool.py`). The public tool/wizard still uses
modern Qt; the older fallback is removed and cannot be launched for comparison.

Use real inputs, owning measured oracles and archived before control inventories.
Headless QApplication tests are available, but construction does not prove
readable plots or reachable controls. The detailed checklist below describes
the retained modern Qt surface; native controls have their own measured receipt.

## Background

Visual verification complements the bounded source/binding tests. Several
classes of issue need actual rendered states:

- Plot rendering (pyqtgraph)
- Layout overflow / clipping
- Missing signal connections
- Button/text visibility
- Drag-and-drop behaviour
- Progress dialog appearance

## Procedure

### 1. Launch the migrated GUI

```bash
pixi run -e test python -m chisurf
```

Open the native **Burst Analysis** hub selection step. For the separately
retained modern Qt wizard, use:

```bash
pixi run -e test python -m chisurf.plugins.burst.burst_selection.wizard
```

### 2. Visual checklist

Compare with archived before inventories, not a new fallback launch. The old
Legacy-column marks below record historical intended controls; they do not
assert current legacy availability or acceptance of the new surface.

| Check | Expected | Legacy | Migrated |
|-------|----------|--------|----------|
| Window title | "Burst Selection" | ✓ | ? |
| Action bar buttons | Add TTTR, Batch, Process, Save .bur, Clear | ✓ | ? |
| Clear button visibility | Hidden (wizard passes `show_clear_button=False`) | ✓ | ? |
| File list area | Drag/drop hint, file paths appear | ✓ | ? |
| Output format checkboxes | CSV, MFD-HDF, Zip, Remove Folder | ✓ | ? |
| Filter group | Channels + microtime fields visible | ✓ | ? |
| dT min/max spinboxes | With enable checkboxes | ✓ | ? |
| Gap fill checkbox + spin | Functional | ✓ | ? |
| Filter mode combo | Burst / Count rate | ✓ | ? |
| Invert checkbox | Toggles enabled state | ✓ | ? |
| Threshold / TW / CR TW #Ph | Present and editable | ✓ | ? |
| Histogram group | Feature combo, bins, range, Auto, GMM controls | ✓ | ? |
| Plot group | Trace range, bin-widths, plot toggles, Refresh | ✓ | ? |
| GMM summary QTextEdit | Read-only, shows GMM results | ✓ | ? |

### 3. Functional test

#### 3a. Load a TTTR file

1. Drag `tests/data/bh_spc132_sm_dna/m000.spc` onto the file list
2. Click **Process**
3. **Expected:** Progress dialog appears, analysis completes, "Analysis complete" shown

#### 3b. Check dock tabs

After analysis:

| Tab | Expected content |
|-----|-----------------|
| Files | File list, output format checkboxes |
| Bursts | Table with burst data (Number of Photons, Duration, Proximity Ratio…) |
| Histogram | Histogram plot of selected feature |
| dT | Macro time difference plot |
| Filter | Photon filter indicator plot |
| MCS | Multichannel scaler trace |
| Decay | Fluorescence decay plot |
| Burst length | Burst duration histogram |

#### 3c. Save .bur

1. Click **Save .bur**
2. Choose a location
3. **Expected:** `.bur` file created, readable with the API:
   ```python
   from chisurf.plugins.burst.burst_selection.api.io import read_bur

   df = read_bur("/path/to/saved.bur")
   print(df.head())
   ```

#### 3d. Histogram + GMM

1. Select "Proximity Ratio" in the feature combo
2. Click **Fit GMM**
3. **Expected:** GMM plot overlay, component parameters in the summary text area
4. Verify: this should NOT auto-run on refresh (no `_fit_gmm_on_update`)

#### 3e. Diagnostic plots

1. Click **Refresh plots**
2. **Expected:** MCS, Decay, Burst length, Filter, dT tabs show plots

### 4. Edge cases

- **Empty state:** Open GUI with no files loaded — no crash
- **Batch dialog:** Click **Batch** — folder selection dialog opens
- **Clear:** Click **Clear** — files and results removed
- **Invalid channels:** Enter "abc" in channels — no crash, clear error message

### 5. Reproduce the `appendPlainText` scenario

1. Load a corrupt or minimal TTTR file that will raise during plot loading
2. **Expected:** Error message in summary QTextEdit (no crash)

## Success criteria

- All items in the visual and functional checklists pass
- No crashes, no unhandled exceptions in the console
- Saved `.bur` output round-trips through the API and matches its owning
  measured oracle; the archived loaded fallback diagnostic is not a legacy
  search rerun or numerical parity proof

## If something fails

Fix the root in the owning surface or UI toolkit and re-test the actual
interface. Do not add a package switch, fallback module or fake legacy class.
Preserve scientific settings and output contracts.

## After verification

Update `STATUS.md`:

- Mark all checklist items as ✅ or ❌
- Note any fixes that were applied
- Treat future engine/framework changes as separate maintained plans, not an
  automatic consequence of GUI verification
