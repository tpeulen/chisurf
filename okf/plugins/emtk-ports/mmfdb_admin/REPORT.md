# emtk port report — `mmfdb_admin` (IN PROGRESS, stopped at the usage limit)

Status 2026-10-05: **not ported yet.** The Qt baseline is captured and the Qt-free
pieces the native app needs are extracted; the native app (`gui/app.py`, model, view
spec, tests, after-images, docs, guide, help) is not written. `manifest.json` has
**no** `entrypoints.emtk`, so the ribbon still opens the Qt tool (correct: never point
it at an unfinished app). Agent board: T-20261005-MMFDBEMTK.

## Where to pick this up

1. **Build the native app** on the extracted Qt-free pieces (in
   `chisurf/plugins/core/mmfdb_admin/gui/` unless stated): `entity_registry.py`,
   `entity_schema.py`, `legacy_schemas.py` (field specs per entity), `entity_values.py`
   (typed defaults, coerce in/out; shared with the Qt `EntityForm`),
   `password_strength.py`, `optical_components/duplicates.py` (`find_duplicate_groups`),
   `optical_components/*.view.json` (read-only detail forms, drawable by
   `emtk.view_form.draw_form` as is), `chisurf/core/fio/mmcif/metadata_keys.py` (key
   catalogue + descriptions), `chisurf/core/fluorescence/spectrum_traces.py`
   (fluorophores.get spectra to traces), `provenance_graph.py` (Qt-free; its output
   loads with `chisurf.emtk.node_editor.document.GraphDocument.from_dict`; draw with
   `GraphControl(read_only=True)` as `core/pto_inspector/gui/app.py` does),
   `client.py` / `session.py` (Qt-free client and SSO cache).
   Planned shell: one `ImApp` with a menu bar (File: Import / Export selected sample /
   Backup / Reset / Close; Settings: Reset window layout; Help: About), the toolbar
   (host, port, user, masked password, Login, ⋯ connection dialog, Logout, status dot,
   Refresh, Import, Backup, Reset), a left rail (search + grouped panels, drawn like
   `chisurf/emtk/tool_hub.py` — do not edit that file, another lane owns it), the panel
   window, a status bar with Back / Next. Panels: Overview, All items, Measurements,
   21 generic entity panels (table + dictionary form + New/Delete + per-entity extras,
   see `tool.py::_extra_buttons_for_spec`), Sample Metadata, Spectra, Provenance Graph,
   Import / Export, eLabFTW, Studies, Protocols, Lifecycle, Calibrations, Reagent Lots,
   Pipelines; dialogs: connection, password, analysis details, find duplicates,
   validation status, branch head, confirmations.
2. **emtk widgets already added for it** (emtk commit `7751e7d`): `view_form` value
   `kind: "text"` (multi-line, click-away commit — for Details/Address);
   `data_table` column `display: "link"` (FK cells), `activated_cell_call(record, key)`
   (double-click on an FK cell jumps, the Qt `jumpRequested`), column
   `background: {value: colour}` (Spectra status colours). Entity tables: an editable
   bool `checked` column replaces the Qt check column; `filter: true` replaces
   Filter + Auto (deliberate: always live).
3. **Inventory to reach**: `before.json` (457 normalised controls, union of every panel
   and dialog), per panel `before_panels.json`; format in the docstring of
   `capture_qt_populated.py` (visible labels/buttons/actions/short combo option lists/
   placeholders/column headers; table cells are data). Compare with
   `python -m test.gui.emtk_port_parity compare mmfdb_admin --out ...` after writing
   an `after.json` that visits **every** panel (the stock `after` draws only one).
4. **Qt defects to fix as deliberate improvements in the native app** (`deliberate.json`):
   - The visible Provenance Graph panel has no seed controls (they live on a hidden
     legacy tab) and *Use as provenance seed* only switches panel without loading.
     Native: seed type/ID, Load upstream/downstream/full, Export JSON/ZIP in the
     panel; the seed buttons load.
   - Users › *Jump to branch* reads hidden legacy widgets and always warns. Native: a
     dialog (operation ID, branch name, description) → `client.jump_user_to_operation`.
   - Users › *Change password* raised `TypeError` (dialog passed a `client`).
     **Fixed in Qt** here (saves via `client.save_user`).
   - The shell's ">>" fast-forward walks workflow steps; the admin has none.
5. **Test/evidence infrastructure ready**: `test/seeded_admin.py` — `use_folder(tmp)`
   (CHISURF_SETTINGS_DIR / MMFDB_SETTINGS_DIR / MMFDB_DATABASE_PATH / object store in a
   temp folder), `admin_client()` (in-process, bootstrap admin/admin), `seed(folder)`
   (every entity, provenance chain raw_gui→proc_gui→prod_gui, analysis with parameter
   and products, fluorophores with spectra and a near-duplicate pair, calibrations,
   a study with member and field, protocols, reagent lots, sample lifecycle
   registered→measured). Pipelines stay empty (the service lists only injected ones).
   Real-input tests go through `chisurf/plugins/emtk_test_input.py::Driver`.

## Before-images (Qt, seeded temp DB, 1200x800), read

`before_<panel>.png` for all 35 panels, `before_provenance_graph_loaded.png`,
`before_dialog_{connection,password,analysis_details,duplicates}.png`. Re-capture:
`QT_QPA_PLATFORM=offscreen PYTHONPATH="modules/mmfdb/src:modules/chinet:modules/imp-tricks/src:.:$HOME/dev/emtk" python okf/plugins/emtk-ports/mmfdb_admin/capture_qt_populated.py okf/plugins/emtk-ports/mmfdb_admin`.

## Traps met

- `python -m test.gui.emtk_port_parity before mmfdb_admin` builds the widget without a
  client (real endpoint, panel 0 only); use the capture script.
- The Qt widget keeps hidden legacy tabs with `parent=self` detail widgets; inventory
  only `isVisible()` widgets.
- The mmCIF metadata key combos (thousands of items) are recorded as `combo with N options`.
- `chisurf/gui/widgets/spectrum_view.py` keeps its own copy of the trace conversion:
  touching it obliges porting its `.native` calls, which needs chiplot axis-styling and
  legend-colour verbs first (`test/chiplot_native_allowlist.txt`). Left untouched.
- `open(dst, "w").write(f(open(src).read()))` with src == dst truncates first.
- emtk `data_table.py` carried a peer's uncommitted hunk (FLEX_MIN); the emtk commit
  was built as HEAD + my hunks.

## Tests

`pytest chisurf/plugins/core/mmfdb_admin` → 121 passed after the extractions;
`test/gui/test_metadata_editor*.py` → 13 passed; emtk `tests/test_view_form_text.py`
and `tests/test_ui_data_table_links.py` green (each seen failing with the feature off),
existing view_form / data_table suites green.
