# Mean micro-time imaging

Open or drop a TTTR scanner image, or select a registered MMFDB dataset. Configure detector windows from Imaging Setup or add named routing-channel and micro-time gates here. Run calculates every window in the background.

Mean micro-time is photon-weighted arrival time in nanoseconds, derived from the source header resolution; it is not a fitted fluorescence lifetime. Pixels below Minimum photons are zero. Inspect intensity, mean time and the per-frame mean-time movie.

Create imaging HDF5 appends the maps and source back-reference. Save container records the mean_micro_time artifact in the source PTO container. ndX explores all per-pixel columns. Next advances an attached imaging pipeline. State preserves detector windows, threshold and display preferences.

Cancel discards the pending result when the worker finishes; native calculations already running may continue until completion.
