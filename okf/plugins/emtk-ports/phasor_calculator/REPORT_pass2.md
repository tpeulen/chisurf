# emtk upgrade report (pass 2) - phasor_calculator
Commits `91e5a065b` (spec forms, layout, tests), `194a0e0db` (evidence, guide 77 figures); baseline `d74a0a821`. Tests: 45 passed. compare exit 0, 54 controls, 0 untooltipped. Compare inventories 0 Qt controls (AutoForm), so `test_every_label_of_the_qt_spec_is_drawn` covers the 19 Qt labels.
Fixed: emoji glyphs against labels, stretched fields without steppers (now spin arrows with Qt steps/limits), toggle row cut at narrow widths, inconsistent toggle indents, g/s pairs split, hand-drawn reference table -> `data_table`, plot click rect was the legend item; `export_settings`/`restore_settings` added.
Tests: `test_emtk_phasor_clicks.py` (frequency, harmonic, lifetimes, four toggles, donor tau0, two-component line, mixing region, cursor, table sort, plot pan/wheel, guide/help, layout). Open: help window shows raw `**bold**`.

## Review (reviewer, 2026-10-02)
Tests re-run by the reviewer with the counts above; populated screenshots read. **Accepted.** Real-input click tests, layout checks at 1200x800 / 800x600 and two deliberate breakages per plugin are the agent's claims, backed by the committed test files named below.
