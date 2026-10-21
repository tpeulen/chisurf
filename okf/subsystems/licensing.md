---
type: Subsystem
title: Licensing (W15)
description: The owner's 2026-10-17 release licence directive — shipped app emtk-only, chisurf/ndxplorer code MIT — the licence map of every repo in the stack, the gpl-final boundary tags, and what remains open.
resource: LICENSE, pyproject.toml, test/test_license_strings.py
tags: [licence, mit, lgpl, w15, release]
timestamp: '2026-10-21T21:00:00Z'
---

# What it is

The owner's release directive (2026-10-17, W15): **the shipped application is
emtk-only, and the code is MIT** — chisurf and ndxplorer. No GPL visual-analytics
toolkit derivation may remain in the tree; the historic VizRank code was rewritten
clean-room (ndxplorer `a78db6d`; Orange provenance text gone from `analysis/*.py`).

# Licence map (verified 2026-10-21)

| Repo | Licence | Where |
| --- | --- | --- |
| chisurf | MIT | `LICENSE`, `pyproject.toml`, `core/info.py` |
| modules/ndxplorer | MIT | `LICENSE`, `pyproject.toml` (submodule of chisurf; 5 commits ahead of origin — push pending) |
| emtk | MIT | `LICENSE`, `pyproject.toml` |
| chimol | MIT | `LICENSE`, `pyproject.toml` |
| mmfdb | MIT | `LICENSE`, `pyproject.toml` |
| imp.bff | LGPL-2.1-or-later | `pyproject.toml` (made explicit everywhere in `5bb2bf267`, 2026-10-21) |
| tttrlib | BSD-3-Clause | `pyproject.toml` (third-party dependency, not relicensed) |

imp.bff stays LGPL-2.1-or-later deliberately: it is the IMP-bound simulation
kernel, not part of the shipped app's MIT set. Anything that statically links or
vendors imp.bff code into chisurf must respect that; the Python-level import seam
(`pixi` pin `imp-bff 127e1b104`) keeps the boundary.

# Guards

- `test/test_license_strings.py` (W15 step; **not yet written**): bans GPL licence
  strings and the retired toolkit's provenance phrases from source with an empty
  allow-list; covers both chisurf and the ndxplorer submodule.
- `gpl-final` git tags in both repos mark the last commit before the MIT flip —
  required **retroactively** because both flips already landed untagged. Tag the
  commit immediately before each licence change.

# What remains open (2026-10-21)

1. Write `test/test_license_strings.py` (guard above) and get it green.
2. Create the retroactive `gpl-final` tags in chisurf and ndxplorer.
3. Push ndxplorer (5 commits ahead of `origin/development`) and bump the chisurf
   submodule pointer so the recorded `a78db6d` is reachable from the remote.
4. A `docs-release` run afterwards so `docs/licensing.md` (already rewritten to
   MIT) and the generated references stay consistent.

Related: PRD-154 Part D gate 5, W15; [Qt retirement](qt-retirement.md) (the
emtk-only side of the directive).
