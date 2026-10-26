# Count Rate Analysis

Pick photon streams in the **Input** table -- the TTTR files and container streams of the
Datasets workspace (files enter ChiSurf by dropping them on the ChiSurf window) -- with a
detector setup row if you have one, and press **Use selected**. Select or edit a detector setup;
routing channels, detector micro-time gates and excitation windows define each
reported detector/window channel. Calculate reads each file in a background job.

## Results
The plot reports kHz per input file. The table reports channel mean and standard
deviation, photon totals, and acquisition time. Save writes a tab-separated table.

## File queue and panels
Streams are queued from the Input table above the queue. Select a file and press Remove, or right-click it, to take it off the queue. Close or rearrange docks from their header;
right-click a dock header to reopen hidden panels or restore the default layout.
