# FitInfo / Data table: plot-settings parity (before: Qt controller, after: emtk)

Before: `../before/FitInfo_{0..3}.png`, `../before/ctrl_*.json` (`FitInfo`, `FitTablePlotEmtk`).
After: `FitInfo_settings_tab{0..3}.png` (plain fit with metadata + one external file),
`FitInfo_settings_case{0,40}.png` (real catalogue science), `FitTablePlotEmtk_page_case0.png`.

| Tab | Before (Qt) | After (emtk) |
|---|---|---|
| Analysis | Analysis id, Analysis type, Sample combo + ↻ UUID, sample details, condition details | same emtk form (unchanged), now hosted in the dock's Analysis tab |
| Metadata | key/value table (key cell = editable catalogue combo), `+`, `−` | key/value `data_table` (cells typed by double click), `Key` choice from the mmCIF catalogue (filterable) for the picked row + its dictionary help line, `+`, `−` |
| External data | `file path / URL` + `format` table, drop hint | same table (typed cells), drop hint; **added** `+` / `−` (rows could only come from drops before) |
| Export | 🔄 (shown as `…`), Copy to clipboard, Save to file…, mmCIF text | 🔄, Copy to clipboard, Save to file… (emtk file chooser in the tab), mmCIF text |

Data table page: the Qt `plot_controller` was empty before and after; the page keeps
Model, Copy table, Columns, Hide empty, Shade, ∥, Export CSV, filter, status line. The
*Model* parameter editor and the CSV chooser were Qt dialogs; they are drawn in the
page's place now (Apply / Cancel).

Deliberate differences: the metadata key moved from a per-cell combo to one `Key`
choice for the picked row (the mmfdb_admin native panel's pattern); drops of non-local
URLs (text drops) are not taken by the emtk host, only file drops.
