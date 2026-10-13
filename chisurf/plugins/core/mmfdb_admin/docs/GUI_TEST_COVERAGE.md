# MMFDB Admin GUI Test Coverage

Last reviewed: 2026-10-13 (the Qt window retired; every Qt widget test ported to the
native emtk app).

All GUI tests drive the native app (`gui/app.py` over `gui/native/*`) against a seeded
temporary MMFDB (`test/native_support.py`, `test/seeded_admin.py`) with the real
in-process services. Click tests go through `chisurf.plugins.emtk_test_input.Driver`
(pointer and keyboard at the drawn rectangles); model tests call the panel models.

| Surface | Tests | Status |
| --- | --- | --- |
| Shell: rail, groups, pictograms, search, Back/Next, menus, help, guide, 800x600 | `test_admin_navigation.py`, `test_native_clicks.py`, `test_native_app.py` | Interaction tested |
| Login, logout, login dialog (masked password, Advanced fold), Enter logs in, non-admin refusal | `test_connection_dialog.py`, `test_native_model.py`, `test_native_clicks.py`, `test_native_qt_parity.py` | Interaction tested |
| Entity panels: select, typed auto-save, New, tick + Delete (confirmed), FK links, UUID hover, row menu | `test_entity_dock_gui_interactions.py`, `test_native_clicks.py`, `test_entity_extras_clicks.py`, `test_native_qt_parity.py` | Interaction tested |
| Entity actions: Copy ID/UUID, Reveal, Use as seed, Validate, Delete, Details, Change password, Jump to branch, Set head, Open in ndX | `test_entity_dock_gui_interactions.py`, `test_native_model.py`, `test_native_qt_parity.py` | Interaction tested |
| Entity form generation and value coercion (FK labels, JSON fields, empty -> None) | `test_autoform_entity_form.py` | Model tested |
| Experiment data sub-table, Validate setup, archived project versions | `test_entity_extras_clicks.py` | Interaction tested |
| Sample Metadata | `test_entity_dock_gui_interactions.py`, `test_native_model.py` | Interaction tested |
| Measurements, All items, Overview | `test_entity_dock_gui_interactions.py`, `test_native_model.py`, `test_admin_navigation.py` | Model tested |
| Spectra: curation, overlay plot, live search + Auto, row menu, Find Duplicates progress/Cancel, merge | `test_optical_components.py`, `test_native_clicks.py`, `test_native_model.py`, `test_native_qt_parity.py` | Interaction tested |
| Provenance Graph: seeds, loads, node and edge pick | `test_entity_dock_gui_interactions.py`, `test_native_clicks.py`, `test_native_qt_parity.py` | Interaction tested |
| Import / Export, Demo data | `test_entity_dock_gui_interactions.py`, `test/gui/test_mmfdb_demo_captions.py` | Interaction tested |
| eLabFTW (fake remote) | `test_elabftw_view.py`, `test_native_qt_parity.py` | Interaction tested |
| Studies, Protocols, Lifecycle, Calibrations, Reagent Lots, Pipelines | `test_{studies,protocols,lifecycle,calibrations,reagents,pipelines}_view.py` | Interaction tested |
