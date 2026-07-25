---
type: Plugin Group
title: Core tools plugins
description: Infrastructure plugins — settings, onboarding, plugin/model management, MMFDB admin and user management, project browsing, updates, acquisition and batch analysis.
resource: chisurf/plugins/core/
tags: [plugins, infrastructure]
timestamp: '2026-07-05T00:00:00Z'
---

Core tools are the host-side infrastructure: configuration, onboarding, database and
user administration, project I/O, updates, data acquisition, and batch runs. They live
under `chisurf/plugins/core/` and follow the same manifest contract as feature plugins,
so ChiSurf's own plumbing is packaged as plugins too.

| Plugin dir | Display name | What it does |
| --- | --- | --- |
| `core/setup` | Setup:Settings | Unified Settings dialog that hosts several config panels. |
| `core/boarding` | Help:Boarding Wizard | First-run onboarding wizard (rebuilt as a `boarding.view.json` directed stepper). |
| `core/plugin_manager` | Setup:Plugins | Enable/disable and inspect installed plugins. |
| `core/plugin_check` | Tools:Miscellaneous:Plugin-Check | Startup-error test harness across all plugins; reports pass/fail/skip. |
| `core/model_manager` | Setup:Models | Manage fitting models. |
| `core/mmfdb_admin` | Tools:MMFDB Admin | Manage the Multiparametric Fluorescence Database: samples, experiments, setups, data, provenance, project archives, fluorophore curation. |
| `core/user_editor` | Setup:User Editor | Manage users registered in the MMFDB. |
| `core/switch_user` | Setup:Switch User | Switch the active MMFDB user for the session. |
| `core/database_connector` | Core:Database Connector | Source/user DB resolution, migration, backup/reset, FLR CIF import/export. |
| `core/project_browser` | Tools:Open Project | Browse, save, restore, export/import projects via MMFDB with version control. |
| `core/updater` | Setup:Updates & Packages | Update checker/installer and conda package manager (panels inside Settings). |
| `core/acq` | Main:Tools:Acquisition | Single-molecule acquisition from TCSPC hardware or the built-in tttrlib photon simulator. |
| `core/batch_analysis` | Main:Tools:Batch-Analysis | Apply one template fit to many datasets/files and export consolidated results. |
| `core/globalview` | Main:Tools:Global View | Interactive network graph of parameter relationships across fits. |
| `core/help` | Help:Documentation | Documentation browser and editor (Markdown + the reStructuredText user manual), with human-review sign-off tracking. |
| `core/lightpath_simulator` | Spectroscopy:Light Path Simulator | Compute crosstalk and R₀ overlap integrals for an optical path. |
| `sample_database` | Legacy:Sample Database | Retired prerelease MMFDB surface; active work belongs in `core/mmfdb_admin`. |
| `ai_settings` | Tools:AI Settings | Root-level AI provider/backend configuration tool. |

Every tool is discovered by `manifest.json`, activated with a `PluginContext`, and
renders declaratively ([plugin system](/architecture/plugin-system.md),
[Plugins target](/specs/plugins.md), [GUI & AutoForm](/subsystems/gui-autoform.md)).
The database-facing tools (`mmfdb_admin`, `user_editor`, `switch_user`,
`project_browser`, `database_connector`) are front-ends over the provenance store —
see [MMFDB](/architecture/mmfdb.md) and [PRD-02b](/prds/prd-02b.md). Acquisition tracks
[PRD-32](/prds/prd-32.md)/[PRD-33](/prds/prd-33.md). Because this plumbing is itself
plugins, it exercises the same discovery/lifecycle rules the [Plugins target](/specs/plugins.md)
demands of feature code.

## Documentation review gating

Much of the user manual was machine-drafted, so `core/help` doubles as the review
tool that keeps unchecked prose out of a release. Pages under a tracked directory
(`docs/manual`, listed in `api/review.TRACKED_DIRS`) carry one of three states:
**reviewed**, **stale** or **unreviewed**.

State lives in a per-directory sidecar `review_status.json` rather than in the
pages, so the reStructuredText stays clean and a whole directory's review state
diffs as one file. The registry stores a **content hash** alongside each sign-off,
which is what makes *stale* possible: editing a page after it was approved
invalidates the approval automatically, so a page cannot be signed off once and
then quietly rewritten. The sidecar is safe from regeneration because
`docs-manual` is retired — the manual RST is hand-maintained.

Three surfaces share one Qt-free core (`api/review.py`):

- **GUI** — the browser badges every manual page (✅ / ⚠️ / ⬜), banners the open
  page with its state, offers *Mark reviewed*, and filters the tree by status.
  Saving an edit re-checks the hash, so a page visibly turns stale as you edit it.
- **CLI** — `help review-check` (the gate, exit 1 on any blocking page),
  `help review-list`, `help review-set`.
- **RPC** — `help.review.status` / `.set` / `.check`.

Enforcement is split deliberately. `docs-html` still builds unreviewed pages —
dropping them would hole the toctree and break cross-references — but a Sphinx
extension (`docs/_ext/review_banner.py`) stamps each with a visible warning. The
hard gate is the separate `docs-check-reviewed` task, which `docs-release`
depends on, so a production build refuses to publish human-unchecked prose.

Reading the manual at all is new: discovery previously globbed `*.md` only, so
the 79 `.rst` pages were invisible. `api/rst.py` renders them through bare
docutils (a Sphinx build is far too slow for interactive browsing), registering
no-op fallbacks for Sphinx-only roles such as `:doc:`/`:ref:` so cross-references
degrade to readable labels instead of error markers.
