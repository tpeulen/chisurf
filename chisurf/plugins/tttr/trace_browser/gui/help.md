# Trace Browser

The Trace Browser pages through a folder of single-molecule (point) measurements: it lists the TTTR files, shows the binned intensity trace of the file you select, and lets you rate and annotate every file so that the good measurements can be found again. A burst-search needs a good trace: this is where you look at them first. For what an intensity trace is see [Intensity traces](docs/concepts/intensity_traces.md); for a worked example on real files see [Binned photon traces](docs/guides/22_binned_photon_traces.md).

## How it works
1. Setup page: pick or define the detector setup (which routing channels and micro-time windows make which trace, and the file type, which also decides the listed extensions) and press Continue. When a setup was used before, the window opens straight on the browser page; Select setup goes back.
2. Press Open and choose a folder, or drop a folder on the window. Include subfolders also lists the files in nested folders. The .trash folder is never listed.
3. Click a row in the file table: its trace is drawn on the right, one line per detector plus their sum, with the histogram of the counts beside it. The first file is selected for you after every scan.
4. Rate a file from 0 to 3 (double click the Rating cell, type a whole number, press Enter), write a note in the Notes cell or in the Annotation box under the plot. Ratings and notes are saved beside the data in the folder's .trace_browser_meta.json. Filter shows only the files that pass a rating.
5. Bin window sets the width of a time bin in milliseconds; Y min and Y max set the y range of the plot (equal values fit the data).

## Selecting files
Click a row to select one file. Select all selects every listed file. Export, CSV, DOCX, Delete and the hand-offs act on the selected files.

- Export copies the selected files, unchanged, into a folder you choose.
- CSV writes the binned trace of each selected file (time, then one column per series) at the current bin window into a folder you choose.
- DOCX writes a Word report (name, folder, rating, annotation, trace picture of each file) into the opened folder. It needs the python-docx package; the button is greyed when that is not installed.
- Delete asks first, then moves the selected files and the files that share their name (a measurement's companion files) to the .trash folder of the opened folder. Nothing is deleted for good: move a file back by hand and rescan. The Delete key in the table does the same.
- HMM, TW and NDX open the first selected file in a new Intensity Trace Analysis window, a new TTTR Time Window tool and a new ndX window, with the current bin window. They work inside ChiSurf and are greyed when the Trace Browser runs on its own. NDX first writes the burst table (in a folder next to the data, named after the file and the bin window) and then opens it.

## Speed
Precompute computes and caches the trace of every listed file in the background (Stop ends it); Precompute after scan does that after every scan. Clear caches deletes the cached traces of the folder.

## Before trusting a trace
The trace is counts per bin: a different bin window gives different counts, and a detector whose channels or micro-time window do not match the data draws a flat line. Check the setup first when a trace is empty. The file list shows only point measurements: files that are scan images are skipped.
