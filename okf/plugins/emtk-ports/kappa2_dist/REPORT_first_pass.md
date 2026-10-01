# emtk port report — `kappa2_dist` (done by EMTK-1 in error; owner T-20261001-SWAP4B to verify)

**Ownership:** `kappa2_dist` was claimed by T-20261001-SWAP4B at 20:40; EMTK-1 worked on it from 20:45 without re-reading the
board. The commits stand (nothing destructive was done) and are handed to SWAP4B for verification. Commits: `a59fde86d` baseline,
`b34e8cde4` code (also swept in SWAP4B's staged deletion of `fret_calculator/tests/test_emtk_app.py`; repaired by `54a665e47`,
deletion re-staged), evidence commit "kappa2_dist: evidence and report (for SWAP4B)".

## What was found and changed

| Item | Before (stream's emtk app) | After |
|---|---|---|
| Form | hand-drawn; model combo showed raw `cone`/`diffusion`/`isotropic` | `draw_form` on the Qt spec `k2dist.view.json` (labels WIC (Cone) …, descriptions as tooltips); radio → combo because the radio row was cut at 800 px |
| Toolbar | ▶ 💾 📖 ❓ pictograms, green Compute | plain buttons |
| Statistics | hand-drawn table | declared `data_table` (`result_rows`: the five Qt Results values + SD₂, Sₐ₂) |
| true κ² marker | axis tag overprinting the x tick labels | legend line `true κ² = …` |
| Edit during a computation | dropped (`schedule` returned while busy): stale results | recomputed when the run finishes, typed inputs kept |

Model: the committed Qt `_Kappa2DistModel` moved to `gui/model.py` unchanged (`model_diff_vs_head.txt`: `methods: True []`). Results
are Monte-Carlo (numpy-seeded), so Qt/emtk numbers in the screenshots differ by seed; `test_results_equal_the_qt_model_under_one_seed`
compares under seed 7.

## Evidence

```
after: 63 controls, 0 without tooltip, qt-free=yes
compare: exit=0   (deliberate.json: '?', 'results', subscript-label renames, radio entries now in the combo)
$ python -m pytest chisurf/plugins/calculator/kappa2_dist -q -p no:cacheprovider
28 passed
```

`test_emtk_kappa2_parity.py` (8). Breakage: removing the dirty flag → `assert 2 == 3` (computations); removing the marker → legend test
failed. Screenshots read: `before.png` (Qt HEAD), `before_emtk_*`, `after_populated_*` (combo, table, legend; nothing clipped at 800×600).

## Open for SWAP4B

Verify against your own procedure; persistence is geometry-only as in Qt (no `export_settings`); guide targets all resolve (5/5).
