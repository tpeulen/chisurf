# Mean micro-time imaging

This tool computes, for every detector window, the **photon-weighted mean arrival time** of each pixel (nanoseconds, from the micro-time resolution of
the file header) and the intensity. It is **not a fitted fluorescence lifetime**: it is the first moment of the micro-time histogram, including the
electronics delay. Press **Guide** at the top of the settings window for a walk-through.

## Workflow

1. Select a **TTTR file** (type a path and press Enter, **Browse**, **Database**, or drop a file; a drop is also run).
2. Set **Min. photons**: pixels with fewer photons are discriminated and set to 0.
3. Check the **Detectors** tab (the Setup tool's editor; without a window the channel-0 window is used).
4. Press **Run** (in the background; **Cancel** discards the unfinished result). Nothing is recomputed when neither the file, the windows nor Min. photons changed.
5. Read the **Intensity**, **Mean micro-time (ns)** and **Mean micro-time movie** tabs; **Detector window** chooses the window drawn.

## Writing and handing on

**Add mean micro-time to HDF5** appends the columns to the imaging HDF5 the pipeline remembers (otherwise a file is asked for); **Save container** writes the
`mean_micro_time` artifact beside the photon file; **ndX** explores the table; **Next** hands the file on inside the Imaging Tools pipeline. Closing a
computed session flushes the HDF5 and the container, as the Qt tool does.

## Further reading

[Scan images](docs/guides/24_scan_images.md)
