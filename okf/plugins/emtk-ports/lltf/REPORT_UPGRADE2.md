# lltf: layout, real-input and docs upgrade (T-20261002-EMTKUP5)

Builds on REPORT.md (parity, EMTK-1C). Qt baseline: `before_populated.png` (unchanged wizard). Emtk before this pass: `before_layout_{1200x800,800x600}.png`; after: `layout_*.png` (populated, config editor, guide, help; script `scripts/capture_populated.py ... emtk layout` / `emtk-states layout`). All read at full size.

## Defects found and fixed
- The four file rows put the caption left of the path field; in the 320 px dock at 800x600 each path was cut to a stub ("...-44_D0.dat") -> caption above, path (elided at the start) under it at the dock's width less the button; `config_file` stays editable, the others read-only (as Qt).
- The Results tab put **Export result JSON** under the table and the summary lines: below the fold at 800x600 -> the button first, table height 96, the details dock 46 % of the height; all four summary lines visible at both sizes.
- Number of Lifetimes / Max Lifetimes / Probability Threshold had no spin arrows (the Qt spin boxes do) -> `style: spin`; typed values are clamped to the Qt ranges, the wheel steps them.
- Pictograms touched their captions (Guide, Help, Fit, Stop, Export) -> two spaces.

## Control -> test (test_emtk_lltf_clicks.py, 22; test_emtk_lltf_layout.py, 11 cases; parity 18 unchanged apart from captions)
Guide/Help/Next/Prev/Close and "no tour card button is dead on any step" (real, no gap here); Load... and Load IRF... dialogs (filtered list, empty Open, Cancel, x, select+Open); Select... folder dialog; drops by kind (data, IRF, YAML, folder); path fields read-only; Edit... editor (typed text stored, dirty flag, Save configuration dialog, Close editor); non-mapping YAML refused; Find Optimal toggle greys/ungreys (typing into a greyed field refused), Max/Threshold typed; Number of Lifetimes typed/clamped/arrows/wheel; Verbose; Fit through the button (real LLTF subprocess on the shipped example: 2 lifetimes, fractions sum to 1, chi2r 1.0-2.0, json + png written), Stop ends a running fit; Results tab (table, summary), tabs, Clear output, Export result JSON (dialog ways out, typed name, content), plot tabs and wheel; real ~/.chisurf untouched; Qt-free.
Layout at both sizes: paths >= 150 px and inside the dock, buttons inside dock and window, option fields inside the dock, Results complete without scrolling, no overlapping texts, pictograms clear, plots with axes and legend.

## Gaps
None new. (Known issue stays: unseeded random starting values, so two fits agree to ~3 digits.)

## Deliberate breakage (13 mutations, two rounds)
Round 1: 13/13 caught. Round 2: 13/13 caught. Folder tests: 82 passed (compare exit 0, 0 lost). Mutations (path field squeezed, greying inverted, Stop no-op, Clear output no-op, dropped YAML as data, config edits not stored, spin arrows removed, verbose ignored, results dock too short, icon touching, Fit enabled without files, export key lost, output dir drop ignored).

## Reuse
Shared: spec forms (`draw_form`, `table`), `FileDialog`/`DialogWindow`, `emtk_layout.layout_spec`, help window and tour; the LLTF CLI itself. No local duplicates found.

## Docs
`docs/guides/76_decay_analysis_tools.md`: figures `lltf_results.png` and `lltf_settings.png` regenerated from this app, captions and the Stop / Edit... text updated. Reference page already links the guide.
