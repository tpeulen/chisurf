# Photon Table

Inspect the photons of a TTTR file: one row per photon with its routing channel, micro time and macro time.

## Open a file
Press Open TTTR... and choose a .ptu, .ht3, .phu, .pt3, .ht2 or .t3r file, or drop a file on the window. The status line under the file summary says how many photons were read, or why the file could not be opened. A file that fails to open leaves the table that was shown.

## The summary
The left window shows the file name, the number of photons, the measurement time (the last macro time times the header's resolution), the micro-time channels the header declares and the routing channels in the data.

## Navigate and filter
A file holds millions of photons, so the table shows one page.
- First, Prev, Next and Last move by a page.
- First photon is the index of the first row, counted within the filtered selection.
- Rows is the page size (1 to 20000).
- Channel keeps only the photons of one routing channel. The Photon column then counts the filtered photons and File idx keeps the position in the file.

## The table
Columns: Photon, File idx, Channel, Micro time and Macro time in milliseconds. A header click sorts the page, a right click on a header chooses the columns.

## Copy rows
Copy visible puts the rows of the page on the clipboard as tab-separated text with a header line.

## Panels
Right-click a dock header to close, reopen, undock, or restore the default layout.
