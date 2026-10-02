# Phasor-FLIM imaging

This tool computes, for every detector window, the **phasor** (g, s) of each pixel: the cosine and sine transform of its micro-time decay at one
frequency. It needs no fit: a single-exponential decay lies on the universal semicircle (short lifetimes at the right, long ones at the left), a mixture
inside it. Press **Guide** at the top of the settings window for a walk-through.

## Workflow

1. Select a **TTTR file** (type a path and press Enter, **Browse**, **Database**, or drop a file; a drop is also run).
2. Set **Min photons** (pixels with fewer are discriminated) and the **Frequency** (-1 reads it from the file header).
3. Optionally give a detector window an **IRF reference** (the instrument response); the Detectors tab edits the windows themselves.
4. Press **Run**; **Cancel** discards the unfinished result. Nothing is recomputed when nothing changed.
5. Read the maps: **Intensity**, **Phasor g**, **Phasor s**, their per-frame movies, the **Frames (movie)** and the **Phasor plot** with its movie.

## Cursors

A cursor is a region on the (g, s) plane. Under **Analysis regions** add a rectangle, an ellipse or a polygon (placed in phasor units), drag its handles in
the plot or type its geometry, tick **Invert** to select everything outside it, and choose how several combine (or / and / xor). The **Selected** tab shows the
intensity of the pixels the cursors select; the line under the list says how many that is. **Save regions** / **Load regions** keep them as JSON.

## Writing and handing on

**Add phasor to HDF5** appends the columns to the imaging HDF5 the pipeline remembers (otherwise a file is asked for); **Save container** writes the
`phasor` artifact beside the photon file; **ndX** explores the table; **Next** hands the file on inside the Imaging Tools pipeline.

## Further reading

[Scan images](docs/guides/24_scan_images.md), [FLIM phasors](docs/concepts/imaging_flim_phasor.md)
