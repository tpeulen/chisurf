# QuEst — Quenching Estimator

Structure-based simulation of dynamic PET quenching and FRET for dyes tethered
to proteins by flexible linkers. Peulen, Opanasyuk & Seidel, *J. Phys. Chem. B*
**2017**, 121, 8211 — https://doi.org/10.1021/acs.jpcb.7b03441

QuEst used to be a separate package (`quest`, ~/dev/quest). Since 2026-10-12 it
is this plugin: ChiSurf no longer depends on that package, and a guard test
(`test/test_no_retired_dependency_imports.py`) fails on any `import quest`.

| path | what it is |
|---|---|
| `core/` | The engine: `av.py` (accessible volume via `IMP.bff.get_av`, grid stamps, Brownian walk, FRET rate traces), `dye_diffusion.py` (PET chemistry from IMP.bff, the donor model), `photon.py`, `simulation.py`, `project.py`, `scan.py`, `runs.py`, `tasks.py`, `i18n.py`, `structure/` |
| `settings/` | Parameter catalogue, dye presets, locale files (en/de/fr) |
| `api/local.py` | The facade (`template`, `validate`, `simulate`, `scan`, ...) every surface goes through |
| `rpc/` | Method table (`services.py`), contract, in-process dispatcher |
| `cli/cli.py` | `csc quest` |
| `gui/` | Qt-free form model, generated view spec (`generate_view_spec.py` → `quest.view[.de|.fr].json`), the emtk window (`app.py`) and its Qt host (`tool.py`), `help.md`, `guide.json` |
| `demo.py`, `examples/148l.pdb` | The demo the guided tour starts from |
| `test/` | The engine's suite (moved from QuEst) and the plugin's own tests; `test/baselines/` pins geometry and decay numbers |

## Tests

    QT_QPA_PLATFORM=offscreen python -m pytest chisurf/plugins/quenching_estimator/test -q

Regenerate the baselines only in a change whose log accounts for every moved
number: `python chisurf/plugins/quenching_estimator/test/baselines/generate.py`.
