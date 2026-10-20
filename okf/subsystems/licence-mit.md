---
type: Subsystem
title: 'Licence: GPL → MIT, and the stack table (2026-10-17, audited 2026-10-20)'
description: 'ChiSurf and its family are MIT, tttrlib BSD-3-Clause, IMP.bff LGPL-2.1-or-later; docs/licensing.md holds the table, test/test_stack_licences.py holds every repository to it, the installer ships the LGPL text.'
tags: [subsystems]
timestamp: 2026-10-20T23:00:00+02:00
---

# Licence: GPL → MIT (2026-10-17)

## Where to pick this up

1. Open: **IMP.swarm — split out, 2026-10-20 (owner: "imp-tricks is not imp.bff — separate out").** It is
   now its own package, **imp-swarm** (`~/dev/imp-swarm`, local repo, no remote yet; `CECILL-2.0`, the
   official CeCILL v2.0 en+fr texts; history of its 58 files kept via filter-repo). Commits: imp-swarm
   `5986873`, imp-tricks `9631f9e` (removal + `test_no_cecill_code_ships_here`), chimol `92b106a`
   (demo names the missing package; frozen fallback logs why). The import name `IMP.swarm` survives
   through a `.pth`-installed finder (`src/_imp_swarm_path.py`). ChiSurf imports it nowhere; the
   installer bundles imp-tricks only, held by `test_stack_licences.py::test_the_installer_does_not_bundle_imp_swarm`.
   **Open (owner decision):** should the installer ever ship imp-swarm? CeCILL is a GPL-compatible
   copyleft, so shipping it means its text and source beside the installer, like IMP.bff. Until
   decided, the installed app's biofilm demo shows the frozen run. Also open: a remote for imp-swarm,
   and whether its provenance (translated vs. written from the papers) should be settled anyway.
2. Measure: **the first tagged release with the IMP.bff sdist step** (not yet run on CI). Owner
   decision 2026-10-20: "sdist beside installer" (LGPL 2.1 §6). `build_imp_bff_sdist`
   (build_tools/build_installer.py) resolves the bundled IMP.bff version (`imp-bff` metadata; an IMP
   module build has none and reports its short commit via `get_module_version()`), its revision
   (`direct_url.json` commit, else `+g<hash>`, else tag `v<version>`), clones `IMP_BFF_REPO` with
   history and tags (setuptools-scm needs both to reproduce the version; a shallow clone gives a wrong
   version and the mismatch check fails the build), builds `python -m build --sdist` in a throw-away
   venv; output `dist/source/<name>-<version>.tar.gz`, named in NOTICE.txt. pixi-ci uploads
   `imp-bff-sdist-<os>` from every build job; the release job merges them and attaches
   `artifacts/source/*.tar.gz` with the installers (`fail_on_unmatched_files`). Measured locally
   2026-10-20 against `~/dev/imp.bff` with the arm64 env: 35 MB `bff-0.14.4.dev547+gab5de21d3.tar.gz`
   (pre-rename revisions build as `bff`, hence `IMP_BFF_SDIST_NAMES`). On the first tag, check the
   release page lists the sdist and that a DMG's `Contents/Resources/licenses/NOTICE.txt` names it.
   Guard: `test/test_release_workflow_contracts.py`.
3. Measure: `pytest test/test_stack_licences.py` (skips repos not checked out — on CI only chisurf
   itself is checked, so a sibling repo can drift unseen there; run it on the dev machine) and the
   grep in known issues. `docs/references/review_status.json` shows `licensing.md` stale until the
   docs review pass re-signs it.

Resolved 2026-10-20: tttrlib `c43d77919` gives `PhotonscoreD7.h/.cpp` their upstream notices
(photonscore/d7 Apache-2.0 *and* alex1075/photonsfile MIT — the file ports both), a change statement,
`NOTICE` and `licenses/`, shipped by the wheel and the recipes.

## Owner decision 2026-10-20 — the stack table

chisurf, emtk, chimol, mmfdb, ndxplorer, quest, imp-tricks, labelizer: **MIT**. tttrlib:
**BSD-3-Clause**. IMP.bff: **LGPL-2.1-or-later** (an IMP module; IMP's LGPL modules link the 2.1
text and grant "or any later version"). Documentation: CC BY-SA 4.0. chinet: obsolete, not in the
stack. The table is in [docs/licensing.md](../../docs/licensing.md) between
`<!-- stack-licences:start/end -->`; `test/test_stack_licences.py` parses it and checks each
repository's pyproject (`project.license`, PEP 639 string or legacy table) and recipes, the
tracker's overrides, `__license__`, the About window, the splash art and the installer texts.

What the 2026-10-20 audit found and fixed (commits per repo):

- **chisurf** — the splash art (`splashscreen.svg`, rasterised to `chisurf/emtk/splash.png` and
  `icons/splashscreen.png`) still printed the GPL-2-or-later notice: replaced with an MIT notice
  naming tttrlib/IMP.bff. About window gained a licence line and a companion-licences line (5
  locales). Tracker: imp-bff MPL-2.0 → LGPL-2.1-or-later, binding class 2 → 3, with a note that weak
  copyleft binds only the library. Installer: `install_licence_texts` writes `<runtime>/licenses/`
  (MIT, CC BY-SA, BSD-3, LGPL-2.1, NOTICE with the shipped imp-bff version) because slimming deletes
  `conda-meta`/`share/doc` and conda keeps licence files in `info/`, so nothing carried the LGPL
  before; macOS copies it to `Contents/Resources/licenses`.
- **imp.bff** `5bb2bf267` — pyproject and both recipes said MPL-2.0, doc/about.rst LGPL-3, README
  "version 2 or later": all LGPL-2.1-or-later now, test/test_licence.py. The whole-IMP bundle recipe
  (`conda-recipe/imp`) stays GPL-3.0-or-later because it contains IMP's GPL modules. The BSD-3 headers
  in `include/internal`, `src/fret`, `src/probe` are tttrlib-derived (owner's) and the vendored
  nlohmann/pcg/ptolib/lz4/xsf/webgpu headers are MIT/BSD/Apache: all permissive inside an LGPL library.
  `IMP.bff.labellib` reimplements LabelLib's (MPL-2.0) API; MPL-2.0 is LGPL-compatible.
- **imp-tricks** `358e70a` — recipe said BSD-3-Clause; pyproject had no licence; stale
  `IMP.bff.cgdye` package-data would have shipped FRETpredict (GPL-3.0) files. Fixed + test.
- **quest** `0da1a5b` — README "MIT" followed by LGPL boilerplate; vendored `ngl.js` lacked NGL's MIT
  notice (added `ngl.LICENSE.txt`); PEP 639 string + test.
- **chimol** `ae70b32`, **mmfdb** `1663e31`, **labelizer** `741536c` (had no LICENSE at all) — PEP 639
  strings, README sections, tests. **tttrlib** `d56cc6f89` — a docstring called it GPL-2.0.
- **emtk**, **ndxplorer** — already consistent (ndxplorer's `tests/test_license.py` and the recipe's
  string read were done earlier); vendored colour tables/L2DFileDialog keep their CC0/CC-BY/Apache
  notices in `licenses/`.

Plan: ChiSurf distributed under MIT. Author is the sole copyright holder of
chisurf, chimol, mmfdb, ndxplorer, emtk, tttrlib — every piece is his to relicense.

## Done on s6-merge
- LICENSE → MIT (c) 2026 Thomas-Otavio Peulen; docs/LICENSE split note updated
  (docs stay CC-BY-SA-4.0, by the same author).
- pyproject.toml `license = "MIT"`; rattler recipe `license: MIT`;
  `chisurf/core/info.py` `__license__ = "MIT"` (splash renders it).
- `docs/licensing.md` rewritten: the GPL/CC one-way-compatibility prose replaced
  with the MIT/CC-BY-SA split, modules/ listed as separately-licensed companions.
- `docs/development/licenses.md` regenerated by `build_tools/license_tracker.py`:
  Current license MIT; binding constraint (2026-10-17) was given as MPL for imp-bff
  and labellib — superseded 2026-10-20: imp-bff is LGPL-2.1-or-later and labellib is
  no longer a dependency.
- the reference viewer provenance re-pointed to primary sources: elements.py (IUPAC 2021 weights;
  Bondi 1964 / Mantina 2009 radii — the numbers are facts; the reference viewer parity kept as the
  *check*, not the source), common.py, test_elements.py, guide 44 presets wording.

## Dependency audit result (licence classes)
- All runtime deps permissive except: imp-bff (MPL-2.0), labellib (MPL-2.0),
  psycopg (LGPL, not installed) — weak copyleft dependencies are MIT-compatible;
  nothing is vendored into the MIT distribution (pyproject ships chisurf* only;
  modules/ are separate distributions: chimol MIT, mmfdb MIT, ndxplorer GPL-2
  (separate repo, sole author = owner, needs its own relicensing decision),
  chinet/imp-tricks have no licence files yet (owner's repos).
- the reference viewer: no dependency, no imports. Remaining mentions are interop facts
  (altloc handling, menu labels, camera constants — uncopyrightable facts/measurements)
  and output-format features (write .pml, open_dx, xyz).

## RESOLVED — owner decisions (2026-10-17)

1. **Presets: clean-room (done).** `chimol/plugins/presets/commands.py` rewritten
   from the names' contracts; 43-test behavioural suite green; see
   `okf-mit-cleanroom-audit.md` in the chimol repo (commit `5ad9d9b`) for the
   full clean-room audit it opened — nine chimol modules still carry GPL C++
   expressions (Class A there, plan included) and the fact-tables (Class B)
   need provenance re-pointing.
2. **ndxplorer: MIT (done).** Sole author; committed `2327ef3` in the ndxplorer
   repo (LICENSE, pyproject, README). chisurf's gitlink advance belongs to the
   landing sequence.
3. **chinet: obsolete.** Zero importers in the merged tree (verified by grep
   over chisurf/ + modules/); it survives only as a stale dev checkout on the
   main tree and PYTHONPATH entries in old gate scripts. licensing.md notes it.
   No relicensing needed; the checkout can be dropped from modules/ at leisure.
