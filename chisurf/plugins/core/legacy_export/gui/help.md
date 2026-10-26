# Legacy export

The way out of the ``.pto`` world: the workflow tools read and write ``.pto`` containers only, and this
window writes the layouts older tools read -- the Seidel/Margarita burst folder (``bi4_bur/<stem>.bur``
plus one ``<ending>4/<stem>.<ending>`` companion per analysis) and the five ALEX-Suite CSV files.

## How it works
1. **Open…** a ``.pto`` container, drop one on the window, or press **Load example** for a demo
   container (12 planted bursts, a burst search and a burst variance analysis). The table lists every
   analysis: its run, the table inside it, the operation that wrote it and the companion ending it
   becomes; a dash means the analysis has no registered companion and is skipped, never guessed.
2. Set the **Output folder** (default: the container's folder) and press **Export burst folder**.
3. Optionally write the ALEX-Suite CSVs: pick the burst-search **Run**, type sample and buffer, tick the
   parts (meta, hist_E, hist_S, hist_2D, original_bursts) and press **Write ALEX-Suite CSVs**.

The same exports run headless: ``csc legacy-export plan|burst-folder|alex-csvs``.

## Before trusting a result
The folder is merged by position and holds bare numbers: a zero in a companion means "skipped" (the
container holds the real NaN); text columns, provenance and older runs of an analysis are left out. The
ALEX-Suite CSVs carry default thresholds, neutral corrections and no fit curves. Keep the ``.pto`` as the
record and export again when a colleague needs the old layout.

## Further reading
- [Legacy export: what the old layouts keep and lose](docs/concepts/legacy_export.md)
- [Exporting burst data](docs/guides/34_exporting_burst_data.md)
