# Photon Table

Inspect every record of a TTTR file: one row per photon or marker record with its kind, routing channel, micro time and macro time.

## Open a file
Press Open TTTR... and choose a .ptu, .ht3, .phu, .pt3, .ht2 or .t3r file, or drop a file on the window. The status line under the file summary says how many records were read, or why the file could not be opened. A file that fails to open leaves the table that was shown.

## The summary
The left window shows the file name, the number of photons and of marker records, the measurement time (the last macro time times the header's resolution), the micro-time channels the header declares, the records of each kind and the routing channels in the data.

## Record kinds
Besides photons, a scanning (imaging) measurement holds the scanner's marker records. tttrlib names them from the file header and the scanner's reading routine (the same conventions it reconstructs the image with):
- **pixel**: a pixel-clock marker (Becker & Hickl pixel-marker scans),
- **line start** and **line stop**: the markers that open and close a scan line,
- **frame**: the marker that opens a frame,
- **other marker**: any marker the header does not name, and every marker of a file that is not an image scan.

Each marker kind has its own colour in the Kind column; photons are not coloured. Macro-time overflow records are not listed: tttrlib folds them into the macro times while it reads the file.

## Navigate and filter
A file holds millions of records, so the table shows one page.
- First, Prev, Next and Last move by a page.
- First record is the index of the first row, counted within the filtered selection.
- Rows is the page size (1 to 20000).
- Channel keeps only the records of one routing channel.
- Kind keeps every record, only the photons, only the markers, or one marker kind. It works together with Channel.

The Record column counts the filtered records and File idx keeps the position in the file.

## The table
Columns: Record, File idx, Kind, Channel, Micro time and Macro time in milliseconds. A header click sorts the page, a right click on a header chooses the columns.

## Copy rows
Copy visible puts the rows of the page on the clipboard as tab-separated text with a header line; the kind column holds the kind key (photon, pixel, line_start, line_stop, frame, other).

## Panels
Right-click a dock header to close, reopen, undock, or restore the default layout.

## Further reading

- [Reading the photons of a TTTR file](docs/guides/108_photon_table.md)
- [The photon container](docs/concepts/photon_container.md)
