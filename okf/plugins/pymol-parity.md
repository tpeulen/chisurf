---
type: Parity Tracker
title: ChiMOL vs PyMOL parity
description: Measured gap between ChiMOL and PyMOL, with a prioritised route to replacing it.
resource: chisurf/plugins/chimol/
tags: [plugins, structure, viewer, pymol, parity]
timestamp: '2026-07-25T00:00:00Z'
---

# Why this file exists

The goal is for ChiMOL to **replace** PyMOL for this group's work, not merely to
resemble it. That is a programme, not a task, so it needs a tracker that survives
between sessions — otherwise each round rediscovers the same gaps and closes the
easy ones twice.

Source of truth for PyMOL's behaviour is its **source**, checked out at
`junk/pymol-open-source`. Reading it has repeatedly overturned conclusions drawn
from observation alone; see [the log](/log.md) for three cases where a measured
"constant" turned out to be a different algorithm.

# The measured gap

| | PyMOL | ChiMOL |
| --- | --- | --- |
| Code | 515 823 lines C++ + 52 154 Python | 29 442 Python |
| Commands | 303 | 79 |
| Settings | 769 | 44 registered |
| Representations | 16 | 8 |

ChiMOL is roughly **5 % of PyMOL by volume**. Most of that difference is not
missing features but PyMOL's own scale: shaders, pickers, movie machinery, CGO,
volume rendering, four file-format families, and twenty years of edge cases. The
useful question is not "how do we write 500 000 lines" but **which parts are load
bearing for this group's work**, and those are tiered below.

# Tier 1 — daily use, blocks replacing PyMOL

| Item | Status | Notes |
| --- | --- | --- |
| `lines` (per-bond wireframe) | **done** | `RepWireBond`; was wrongly the CA trace |
| `nonbonded` (crosses) | **done** | `RepNonbonded`; waters/ions in a wireframe |
| Cartoon pipeline | **done** | Every step of `RepCartoonGeneratePoints` |
| Camera / `zoom` / view tuple | **done** | Exact against `SceneWindowSphere` |
| Object menus A/S/H/L/C | **done** | 1:1 from `pymol/menu.py` |
| Menu bar | **done** | PyMOL's grouping |
| Selection algebra | partial | No `bymol`, `bychain`, `gap`, `pepseq`, `rep`, `flag` |
| `save` (PDB/mmCIF export) | **missing** | Cannot get structures back out |
| `label` | **missing** | Whole representation; `L` menu is disabled because of it |
| `create` / `extract` | **missing** | No way to split a selection into an object |
| `origin` | **missing** | Rotation about a chosen point |
| Undo / redo | **missing** | No edit history at all |

# Tier 2 — routine, works around-able

`get_area`, `get_extent`, `get_chains`, `get_title`, `get_bond`,
`iterate_state`, `alter_state`, `smooth`, `sort`, `flag`, `protect`, `mask`,
`bond`/`unbond`, `h_add`/`h_fill`, `cealign`, `pair_fit`, `intra_fit`,
`matrix_copy`, `symexp`/`symmetry`, `group`/`ungroup`/`order`, scenes
(`scene`/`view`), `ramp_new`, `spectrum` by property, `cartoon_putty`,
`cartoon_dumbbell`, `cartoon_fancy_helices`, `ellipsoid`, `cell`, `slice`.

# Tier 3 — specialised or superseded here

Volume rendering, `isomesh`/`isosurface`/`map_*` (ChiSurf has its own map
plugins), sculpting, wizards, the movie/`mset` programme language, stereo modes,
CGO scripting, `fab`/`fragment` building, `alias`, `log_open`.

# Where ChiMOL is deliberately ahead

* **Ambient occlusion** in the interactive viewport, normal-aware and baked per
  rebuild. PyMOL has none.
* **Cast shadows** in the interactive viewport. PyMOL casts them only when
  raytracing.
* **Settings honesty**: every registered setting is verified to drive code that
  reads it, so `set` cannot silently do nothing.

These are the answer to "surpass on the view", and they are cheap because they
exploit the one structural advantage of a rebuild-time pipeline: work done once
per geometry change is free while the camera moves.

# Working rules

1. **Read the C++ before implementing.** Every one of `refine_tips`, the
   `weighted` extent, the orientation-blend endpoints and the view-tuple sign was
   wrong when inferred from behaviour and right when read from source.
2. **Transcribe, do not approximate.** A weighted kernel that "looks like" a box
   average converges differently and shows up on screen.
3. **Pin the transcription with a test that names the C++ function**, so a later
   change cannot quietly drift.
4. **A gap that is shown is better than a gap that is hidden** — disabled menu
   entries with reasons, unknown settings reported rather than accepted.
