# Burst Browser

The **Burst Browser** provides an interactive table and distribution inspector for exploring, filtering, and gating single-molecule burst datasets.

---

## Features

- **Multi-File Navigation**: Open and browse burst analysis outputs (`.csv`, `.bur`, `.hdf5`).
- **Interactive Scatter & Histogram**: Visualize multi-parameter burst distributions including FRET efficiency ($E$), stoichiometry ($S$), burst duration, photon counts, and lifetimes.
- **Dynamic Gating**: Define 1D and 2D selection criteria to isolate specific molecular subpopulations.
- **Exporting**: Export filtered burst subsets directly to CSV or send to downstream analysis modules.

---

## Usage

1. Open a burst analysis folder or table using the browse button.
2. Select desired columns for X/Y scatter axes and histogram projection.
3. Apply threshold ranges to filter out donor-only, acceptor-only, or multi-molecule aggregates.
