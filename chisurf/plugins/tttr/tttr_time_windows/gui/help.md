# TTTR Time-Window BIDs

The tool cuts photon streams into consecutive windows of equal duration and
stores the photon-index boundaries of every window in the measurement's own
`.pto` container, as a burst run named after the window length
(`time_window 10 ms`). The run can later split the stream into segments for
time-resolved analysis (TCSPC, FCS, burst-like time slicing); every burst tool
reads it, and it appears in the Datasets workspace under its photon stream.

## Queue photon streams
The **Input** table lists the photon streams of the Datasets workspace (a TTTR
file, or a stream of a `.pto` container); files enter ChiSurf by dropping them on
the ChiSurf window. Select streams and press **Use selected** to queue them, or
right-click a dataset in the workspace and choose *Open in…*, or drag it onto
this window. Click a queued stream to preview its intensity trace; **Remove**
takes the previewed stream off the queue, **Clear** empties the queue, the
preview and the log.

## Choose duration
Set the duration in milliseconds. Short windows give many windows with few
photons each. The dashed lines of the preview show the window boundaries; when
there would be more than 300 of them they are left out, because they could no
longer be told apart from the trace.

## Choose output
The windows go into the measurement's container beside the input. The output
folder is only used when a vendor file has no container yet: leave it empty and
the container is created next to the input file.

## Process
Writes one `time_window` run per input with the inclusive first and last photon
of every window, and adds it to the workspace as a child of its stream. The processing log lists the windows per file; a failure shows on
the status line and in the log. Press **Stop** in the job window to discard a
running job (a file already being written may finish).

## Panels
Right-click a dock header to close, reopen, undock, or restore the default layout.
