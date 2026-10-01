# TTTR Time-Window BIDs

The tool cuts TTTR measurements into consecutive windows of equal duration and
writes the photon-index boundaries of every window as a `.bst` (BID) file, one
per input file. The files can later split a photon stream into segments for
time-resolved analysis (TCSPC, FCS, burst-like time slicing).

## Queue files
Press **Files**, **Folder** or **Database**, or drop files or folders on the
window (supported: .ptu, .phu, .ht2, .ht3, .pt3, .t3r, also .gz/.bz2). Click a
queued file to preview its intensity trace; **Remove** takes the previewed file
off the queue, **Clear** empties the queue, the preview and the log.

## Choose duration
Set the duration in milliseconds. Short windows give many windows with few
photons each. The dashed lines of the preview show the window boundaries; when
there would be more than 300 of them they are left out, because they could no
longer be told apart from the trace.

## Choose output
Leave empty and the tool creates a folder next to the first input file; after
processing the field shows the folder that was used.

## Process
Writes one `.bst` file per input with the inclusive start and stop photon of
every window. The processing log lists the windows per file; a failure shows on
the status line and in the log. Press **Stop** in the job window to discard a
running job (a file already being written may finish).

## Panels
Right-click a dock header to close, reopen, undock, or restore the default layout.
