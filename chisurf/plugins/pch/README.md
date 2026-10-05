# Photon Counting Histogram (PCH) Analysis Plugin

Analyze the distribution of photon counts in fluorescence time traces to extract molecular brightness and occupancy.

## Architecture

```
pch/
├── manifest.json           # Plugin manifest (entrypoints, RPC methods, metadata)
├── __init__.py             # Bootstrap — loads manifest, exports PCHApp
├── api/
│   ├── models.py           # PchSettings, PchResult, FitResult dataclasses
│   └── algorithms.py       # Pure PCH math (NumPy)
├── backend/
│   └── services.py         # RPC handlers: pch.load_tttr, pch.compute, pch.fit
├── gui/
│   ├── client.py           # PCHClient wrapping InProcessClient
│   ├── model.py            # PchModel: Qt-free state and actions
│   ├── pch.view.json       # the form (drawn by emtk.view_form)
│   ├── app.py              # PchApp, the native emtk window (entrypoints.emtk)
│   ├── guide.json          # guided tour
│   ├── help.md             # help page
│   └── tool.py             # legacy Qt PCHApp (entrypoints.gui), kept until removed
├── cli/
│   └── main.py             # click CLI: pch analyze, pch refit
└── tests/
    ├── test_algorithms.py
    ├── test_manifest.py
    └── test_services.py
```

## Usage

1. From the ChiSurf menu: **Plugins > Spectroscopy > Single-Molecule > PCH**
2. Click **Load TTTR** to select a file (or drop it on the window)
3. Adjust channels, bin time, micro-time range in the Data Settings panel
4. Click **Compute PCH** to build the histogram
5. Set number of species and initial guesses in Model Fit
6. Click **Fit Model** to fit
7. Drag the two vertical lines on the histogram to recompute χ² for a sub-range
8. Click **Save Results** to export NPZ/CSV/TXT

### CLI

```bash
python -m chisurf pch analyze data.ptu --components 2 --bin-time 50
python -m chisurf pch refit results.npz --components 3 --json
```

## Dependencies

- ttrolib (TTTR file I/O)
- numpy, scipy (computation)
- emtk (GUI); qtpy, pyqtgraph only for the legacy Qt tool
- click (CLI)

## Author

Thomas-Otavio Peulen — thomas.peulen@tu-dortmund.de
