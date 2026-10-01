# Brief: upgrading an existing emtk plugin app to parity with its Qt tool

Common procedure for an agent assigned ONE plugin whose emtk app already exists but is deficient (the settings plugins). It
is PRD-153 ([prd-153.md](../../prds/prd-153.md)) with the adaptations below. The assignment message names the plugin, the audit
image and its specific gaps. Do only that plugin, then stop.

## Read first (completely)

1. `CLAUDE.md`, then `okf/prds/prd-153.md` (hard rules incl. 8a no invented data, gates, tests, evidence, report, when to stop and ask).
2. `okf/plugins/emtk-ports/settings-audit.md` and your plugin's image `settings-audit/<id>.png` (Qt left, emtk right: READ it).
3. The accepted examples of exactly this kind of upgrade, with their code and tests: `model_manager`, `user_editor`, `plot_settings`,
   `ai_settings` (`okf/plugins/emtk-ports/<id>/REPORT.md`; code in `chisurf/plugins/core/<id>/gui/` or `chisurf/plugins/ai_settings/gui/`:
   `app.py`, `model.py`, `*_emtk.view.json`, `test/test_emtk_*_parity.py`). Also `chisurf/plugins/tttr/trace_browser` for a form + `data_table`.
4. Your plugin: `gui/app.py`, `gui/model.py`/`view_model.py`, `gui/tool.py` (the Qt tool: the feature reference, read it completely), `test/`,
   `manifest.json`, `gui/guide.json`, `gui/help.md`.

## Procedure

* **Starting state is uncommitted by design.** The plugin folder may hold uncommitted files of the earlier emtk-migration stream (`gui/app.py`,
  `gui/strings.py`, `test/test_native.py`, modified `__init__.py`/`manifest.json`). The owner asked for these emtk apps to be fixed, so that state
  is the intended starting point and "git status must be empty" is waived for THIS plugin folder only. Before changing anything copy every
  uncommitted file (and `git diff` of modified tracked ones) into `okf/plugins/emtk-ports/<id>/pre-upgrade/` and commit it with the Qt
  baseline in the first commit. Commit the plugin's files by explicit path, including the earlier stream's `__init__.py`/`manifest.json`
  changes the emtk entrypoint needs.
* **Qt baseline in a populated state first**: `python -m test.gui.emtk_port_parity before <id> --out okf/plugins/emtk-ports/<id>` plus your own
  `before_populated*.png` (selected item, dirty, dialogs, error states) and the CURRENT emtk app as `before_emtk_*.png`. Read every PNG.
  Everything runs on TEMPORARY settings: `CHISURF_SETTINGS_DIR`, `MMFDB_SETTINGS_DIR`, `MMFDB_DATABASE_PATH` pointing into a temp folder; never
  the user's real `~/.chisurf` or keyring; no real network (stub the transport); never a real API key (use obvious fakes).
* **Checklist of EVERY control of the Qt tool** (each toolbar action and when it is enabled, tables and their columns/sort/search, every field and
  its type and range, dialogs and confirmations, status lines, Help/Guide, tooltips, context menus). Implement each in emtk; whatever is impossible
  goes in `deliberate.json` with a reason (`compare` exit 0, `stale_explanations` empty).
* **Build**: a Qt-free model (`gui/model.py`), a `*_emtk.view.json` spec drawn by `emtk.view_form.draw_form` (a `description` on every
  section, column and button; tables are `data_table` sections, never hand-drawn), in-app dialogs for confirmations, `emtk.file_dialog.FileDialog`
  for files, `chisurf.emtk.jobs.SnapshotJob` for slow work, Help window + guided tour wired as in the accepted ports (guide targets are real emtk
  controls, `await` where the user must act), emtk default style, no emoji, every control a tooltip. emtk facts: `choice` is not editable;
  `kind: "password"` is masked; `collapsing_header` int argument = ImGui flags (initial state only); `begin_child` clips hit-testing.
* **Tests** (new `test/test_emtk_<id>_parity.py`; hermetic; `test/__init__.py` present): model values equal the Qt widget's for the same data
  (construct the Qt widget offscreen and compare cells/fields); every action and its error path; confirmations decline = no change; filter/sort;
  draws populated and empty at 1200x800 and 800x600; tooltips (`emtk_inventory` + a spec walk incl. columns); Qt-free proof
  (`qt_free("<id>")`); settings round trip. Existing tests stay green or are updated with an explanation. Break behaviour on purpose once for
  two tests, see them fail, restore.
* **Evidence**: `after` and `compare` into `okf/plugins/emtk-ports/<id>/` (populated screenshots at both sizes, selected, dirty, each dialog,
  narrow; read them all at full size and fix clipping), report `okf/plugins/emtk-ports/<id>/REPORT.md` from `_TEMPLATE.md` (if the environment
  refuses the write, put the full text in the final message under "REPORT.md").
* **Do NOT edit `chisurf/core/plugin/emtk_preview.json`**: the reviewer removes the plugin from the preview list (the swap) after accepting.

## Commits and git

Commits: baseline + pre-upgrade first; `"<id>: emtk app at parity with the Qt tool"` (code + tests); `"<id>: evidence and report"` (+ your own log
hunk). Plain-text messages, NO trailers, no push, explicit paths, `git diff --cached --stat` before every commit. NEVER `git commit -- <path>` for a
shared file such as `okf/log.md`: stage with `git add`, check that nothing foreign is staged (the shared index can hold other agents' files: if it
does, do not commit them, stop and report) and commit with no pathspec. For `okf/log.md` use the blob technique: `git show HEAD:okf/log.md`, insert
your bullet, `git hash-object -w`, `git update-index --cacheinfo`; compute the new text BEFORE opening any file for writing; never write the working
`okf/log.md`. Commit working increments early: a rate limit or network error mid-way loses uncommitted work. Never `git reset --hard`, `checkout --`,
`restore`, `clean`, `stash`, `add -A`, `commit -a`, `--force`. Do not edit emtk (`~/dev/emtk`), other plugins, shared helpers `chisurf/emtk/*`
(another stream's, untracked) or files you did not write apart from this plugin's. Append a claim to `okf/agent-board.md` first (a symlink into
another repo: append only).

Environment: `cd ~/dev/chisurf; export QT_QPA_PLATFORM=offscreen; export PYTHONPATH="$PWD:$HOME/dev/emtk"; PY=~/mambaforge/envs/arm64/bin/python`.
If a "When to stop and ask" condition applies (an emtk gap), stop and report with a 5-line reproduction.

Final reply: commits (hash + subject), test results (pasted counts), what changed, the parity checklist (done / deliberate / blocked), report path.
