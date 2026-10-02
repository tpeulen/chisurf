# emtk port report -- `burst_fcs_correlator` (upgrade, audit-all row 61) -- PARTIAL (baseline + hermetic tests only)

Commit: "burst_fcs_correlator: Qt baseline, earlier stream's emtk state, hermetic test settings" (pre-upgrade copies in `pre-upgrade/`).

Done: the folder's tests now run on temporary `CHISURF_SETTINGS_DIR` / `MMFDB_*` / `HOME` (`test/conftest.py`, autouse), with `test/test_hermetic.py` asserting that the wizard's settings path (`wizard.py` `_get_settings_path("settings")` -> `burst_fcs.settings.json`) is the temporary folder and the real `~/.chisurf` is untouched. 24 passed in the folder.

Baseline findings (`before.png` = the Qt tool, which hosts the older `gui/app.py` emtk surface; `before_emtk_*.png` = the stream's new `create_app`): two separate emtk implementations exist (`gui/app.py` `BurstFcsGui` hosted by the Qt tool, and the new controller-based `create_app`); the new one draws one ungrouped column (file buttons, a raw JSON text box for channel pairs, five stacked MaxEnt/fit-window fields, Run/Guide/Help row in the middle, settings at the bottom), fit mode as a plain text field, and no populated state could be captured (no raw TTTR + burst files in the repo: only `.bst` of ndxplorer fixtures).

Not done: checklist, spec forms / data_table for pairs and results, populated parity numbers vs the Qt tool, real-input tests, layout fix, docs, guide with awaits. Needs a synthetic photon stream + burst table fixture first.
