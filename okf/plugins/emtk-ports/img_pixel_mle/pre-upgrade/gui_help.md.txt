# Pixel-wise lifetime MLE

Add confocal TTTR image files and an IRF measurement. Choose parallel and perpendicular routing channels, the binned micro-time fit window and photon threshold. Detector setup supplies the G factor and polarization mixing corrections; IRF calibration supplies its files, background and fit range.

fit23 fits one lifetime and anisotropy, fit24 a bi-exponential decay, and fit25 selects among four fixed candidate lifetimes. Initial values and fixed flags are retained independently for each model. A saved ROI can restrict fitting to selected pixels.

Run fits a detached snapshot on a background thread. Cancel stops after the current C++ file fit and discards its unpublished result; completed files remain available. It cannot interrupt an ongoing C++ fit. Per-file failures remain in the status area.

The lifetime map shows τ in ns. The rotation map shows ρ only for fit23. Use the image frame slider for multi-frame measurements. The table preview shows the first 100 rows; CSV, HDF5 and ndX receive the complete table, including skipped pixels and the same numerical values as the Qt tool. Automatic CSV output is written beside every successful input. Save container records the current table as a pixel-map artifact beside the source photons.
