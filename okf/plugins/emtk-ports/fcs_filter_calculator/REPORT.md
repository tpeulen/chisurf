# emtk port report -- `fcs_filter_calculator` (upgrade, audit-all row 71) -- PARTIAL

Status: baseline committed and one defect fixed; the full parity cycle (checklist of the 3650-line Qt window, real-input tests of every control, spec/data_table rebuild, new one-page detector editor embed, docs) was NOT done in this pass. Commits: `22f0dbc49` Qt baseline + stream state (`pre-upgrade/`), plus the commit "fcs_filter_calculator: reconstruction plot framing, evidence".

## Found
* Reconstruction plot was unusable: log Y axis with limits requested once (ignored later) and an IRF tail of 1e-298 stretching the view over 300 decades, so the decay was a thin line at x=0. Fixed in `gui/app.py` (limits applied when the decay's size changes, counts floored at 0.5, Qt colours white/red/cyan); test `test_emtk_layout.py`. Before/after: `before_emtk_populated_*.png` -> `after_populated_*.png`.
* NUMERIC DISCREPANCY -- ISOLATED, no algorithm bug. Recording the arguments of `compute_filters` in both: total decay, both species patterns and the afterpulse nuisance pattern are identical (max diff 0.0); only the scatter/IRF nuisance pattern differs (sum 0.185 vs 0.038). Cause: the detector table. The Qt example leaves the table empty and uses detector "default" with the defaults width 0.2 ns, skew 0, shift 0; the native example fills "green" with the IRF its patterns were generated with (width 0.16 ns, shift 0.03 ns). With the Qt defaults set on "green" the filters and the reconstruction are bit-identical (diff 0.0). Both call `api.compute_filters` (the reference, PAM Calc_fFCS_Filters). The native example is the self-consistent one (its scatter IRF matches the generating IRF); the Qt example's scatter pattern uses a slightly wrong IRF, a Qt example quirk left untouched (legacy). Guardrail: `test_native_filters_are_bit_identical_to_the_qt_widgets_for_the_same_inputs`.
* Qt vs emtk surface: emtk hand-draws number inputs (`input_float(step=0)`), JSON-text component editor, no data_table for detectors/ranges/instrument, Unmix/Auto-fit tabs without the Qt table of instrument factors, 800x600 not checked.
## Tests
`pytest chisurf/plugins/fcs/fcs_filter_calculator/test/test_emtk.py test_emtk_layout.py`: 13 passed.
## Reuse / Docs
Not done: embed `chisurf/emtk/channel_definition.py` (one-page editor 2773e29d6) for the Detector setup tab; guide/doc update pending.
## Next
Rebuild detectors/instrument/range as spec forms + data_table, embed the shared detector editor, reconcile the detector naming with the Qt numbers, then the real-input tests per control.
