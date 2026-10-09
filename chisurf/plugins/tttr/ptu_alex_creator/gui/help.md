# ALEX Creator

Load a TTTR file (including .sm: Open…, a typed path with Enter, or a drop), select input and output container formats,
then choose the ALEX period and shift (type a value, or use the arrows or the mouse wheel). The histogram previews the converted
micro-time phase. Period and shift are in macro-time units, not seconds.

Save as writes a new converted file through the same conversion API used by
the Qt tool. The input file is preserved. Photon channels, events and header
metadata follow that API's format conversion rules.

For batch processing, add files or a folder (recursive). Convert each requires
an output folder. Merge into one shifts successive macro-time streams into a
monotonic stream, then applies ALEX folding; its default output directory is
the first input's directory when no folder is given. Select a queued row
and press Remove (or Delete) to drop it; Clear empties the queue. Dropping one file loads the preview; dropping folders or several
files adds them to the batch queue.

Format, timing, file paths and batch options are restored at the
next launch. Loading a remembered file remains an explicit action.

## Excitation regions

Load automatically detects all measured phase candidates at the configured
Period/Shift; Re-detect repeats the inference. Multiple laser phases and all
routing channels are supported. Optional detector groups use comma-separated
channels and semicolons between physical bands. No phase is assigned a wavelength
automatically. Review transition/heterogeneity warnings, edit bounds if needed
and confirm Review. Wrapped bounds are explicit; regions do not filter photons
or alter single/batch/merge conversion. An inconclusive detection leaves the
histogram and export workflow usable.

[Automatic-region workflow](docs/guides/100_alex_creator.md) ·
[µs-ALEX theory](docs/concepts/us_alex.md)
