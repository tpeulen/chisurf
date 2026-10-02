# Per-pixel intensity

Open or drop a photon imaging file, or resolve an MMFDB dataset. Run computes all detector windows supplied by the shared detector setup. Without a setup, channel 0 is used. Scanner marker geometry is read from the TTTR header.

Each window keeps parallel, perpendicular and total photon counts. Count rate is total photons divided by scanner dwell time in seconds and by 1000, reported in kHz. Per-detector calibrated background in kHz is subtracted from rates and clipped at zero; photon-count columns remain raw counts.

The intensity and count-rate maps use the selected detector window. Raw frames preserve the scanner frame stack. Use Frame to select a scanner frame, or Play movie and Frames per second to animate it. Colormap, gamma and levels affect only the display.

Create imaging HDF5 writes the real per-pixel table, including detector count columns, MFD count-rate names, Number of Photons and the original source back-reference. Save container writes the pixel-map artifact beside the photon stream. An explicitly bound MMFDB session preserves the existing registration and ACL workflows. Closing a computed session flushes its standard HDF5 and container, matching the existing persistence contract.

ndX opens the same live table in the native explorer. Next remembers the source/HDF5 and advances an attached Imaging Tools coordinator; standalone tools identify that missing host integration. Computation and output jobs work on snapshots, then publish results on the UI thread. Setup, pipeline and calibration updates received during a job are applied after delivery.
