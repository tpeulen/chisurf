# emtk port report — `switch_user` (settings plugin upgrade)

Upgrade of the earlier stream's deficient emtk app (a hand-drawn four-field form with a client argument, no Guide, no Help, no
tests) to parity with the Qt `LoginDialog`, by the implementing agent (Sonnet), 2026-10-01. Board entry `T-20261001-SU`.
Commits: `b6edf5f8a` Qt baseline, populated Qt captures and `pre-upgrade/`; `69ba7f91e` emtk app at parity (code, tests, allow-list
strike); the evidence commit follows this file. `emtk_preview.json` untouched.

## What changed

* New Qt-free `model.py` (`SwitchUserModel`) with the dialog's logic: configuration read (`mmfdb` settings through `client_config`),
  server history, offered accounts (configured user plus the desktop accounts in embedded mode), the login and what follows it.
* `switch_user_emtk.view.json` (panels `login`, `notice`), a rewritten `app.py` (logo header, Help / Guide, in-app message box, login
  on a `SnapshotJob`), `guide.json` (5 steps, 3 awaits), `help.md`. `strings.py` kept (translations of the old labels).
* The Qt files (`__init__.py` lazily exports `SwitchUserWidget`, `chisurf/gui/__init__.py` `LoginDialog`) are untouched apart from
  the earlier stream's `__init__.py` / `manifest.json` changes that are committed with the app.
* The earlier root-level `test_native.py` moved to `test/` (the model owns the login now; one smoke test kept).

## Qt control checklist (all from `before_facts.json` / `before.png`)

| # | Qt control | emtk | Status |
|---|---|---|---|
| 1 | Title "ChiSurf Login", modal | tool window; closes on success or Cancel | done (modality is the host's) |
| 2 | Logo, "ChiSurf", "Sign in to the MMFDB workspace" | `cs_logo.png` image, heading, text | done |
| 3 | Server editable combo, history, last server selected | `Server` text field + `Recent servers` choice | deliberate (no editable combo) |
| 4 | Port spin 1..65535, hidden when remote | `Port` int field, `bounds` 1..65535, hidden when remote | done |
| 5 | Remote mode: "MMFDB URL:" label, port hidden | `MMFDB URL` field, no port | done |
| 6 | Select User editable combo: configured user + desktop accounts | `User` text field + `Select user` choice | deliberate (no editable combo) |
| 7 | Empty user uses the account last picked | same (`picked_user`) | done |
| 8 | Password, masked | `Password` (spec `password` kind, masked), never stored | done |
| 9 | Save selected user / Log in automatically when allowed | two toggles, defaults from settings | done |
| 10 | Login: success path (settings, history of 5, last server/port, runtime token, stored token or deleted) | `SwitchUserModel.run_login` | done, compared to the Qt dialog in 8 parametrised tests |
| 11 | Login Failed warning (string / dict error text) | in-app "Login Failed" message, nothing changed | done |
| 12 | Error box "Login failed: ..." on an exception | in-app "Error" message | done |
| 13 | Settings Not Saved / Autologin Not Saved warnings (autologin reset and re-saved) | in-app messages; the window closes after OK | done |
| 14 | Cancel | `cancel`, clears the password, closes, changes nothing | done |
| 15 | Set Password prompt after a login of an account without a password | none | not reachable in Qt either: `self.users` is never filled, so the branch is dead code; not ported (recorded as a finding) |
| 16 | Help / Guide | Help window, 5-step tour | added (Qt tool had none) |

Qt dialog findings: it does not list the MMFDB's users (authentication must not enumerate them); the combo holds the configured
user and, in embedded mode, the desktop accounts. "Current user marked" therefore means the configured user is the selected entry
(alice in the capture, written into the temporary settings).

## Deliberate differences (`deliberate.json`, 6 entries)

Qt combo popup contents and row numbers that the inventory counted as controls: `1`, `2`, `3`, `10.0.0.7`, `127.0.0.1`, `admin`.
The editable combos became text field + choice picker because emtk `choice` is not editable; the choice lists the same entries when
opened. Qt modal boxes became in-app message windows (OK acknowledges; the window closes after the last one, as the dialog closed
after its boxes). `export_settings()` is `{}`: as in Qt, the account and server live in the `mmfdb` settings (YAML); the earlier
app's exported keys are accepted and ignored by `restore_settings`.

## Evidence and tests

```
$ python -m test.gui.emtk_port_parity after switch_user ...   (temp settings holding alice / three servers)
after: 18 controls, 0 without tooltip, qt-free=yes
$ python -m test.gui.emtk_port_parity compare switch_user ...
{ "lost": [], "untooltipped": [] }   qt-free: True   exit=0      (stale_explanations [])
$ python -m pytest chisurf/plugins/core/switch_user -q -p no:cacheprovider
37 passed
$ python -m pytest test/gui/test_emtk_port_parity.py -q -p no:cacheprovider
13 passed
```

Tests (hermetic: `CHISURF_SETTINGS_DIR` / `MMFDB_SETTINGS_DIR` / `MMFDB_DATABASE_PATH` in `tmp_path`, `cs_settings["mmfdb"]` restored,
credential store functions replaced by recorders, no network): initial fields and remote mode equal to the real `LoginDialog`
constructed offscreen; successful login persists identical settings dict, YAML, token calls and runtime token as the Qt dialog (8
combinations of save / autologin / server); rejected logins (three answer shapes), exception, token refused and settings not saved
equal the Qt message boxes and leave settings untouched; history of five and move-to-front; empty user; pickers; cancel; disabled
buttons; invalid settings; round trip through the YAML; a real in-process MMFDB on a temp database (admin/admin signs in, a wrong
password does not); app login on a thread, refusal message and OK, Cancel; draws empty / populated / notice at 1200x800 and 800x600
without the typed password in the drawn strings; remote draw; spec keys, tooltips (inventory + spec walk), guide targets; Qt-free; and
`test_the_real_settings_were_not_touched` (settings path resolves into the temp folder, the real `~/.chisurf/settings_chisurf.yaml`
digest is unchanged). Deliberate breakage (history length +2 and an unstripped user name) failed 9 tests; restored.

## Screenshots read

`before.png` / `before_populated*.png` (Qt: error, edited, remote), `before_emtk_*` (earlier app, rebuilt from `pre-upgrade/`),
`after_*` (empty, populated, edited, Login Failed message, signed in, both sizes). Nothing clipped; the message window fits at 800x600.

## Open points

* Qt `SwitchUserWidget` is still the default launcher; the reviewer removes `switch_user` from `emtk_preview.json`.
* Not run in the real main window; no docs guide page exists for this plugin (docs gap). `test/renders/` of the earlier stream is left
  untracked (stale images of the old app). emtk gap: no editable combo.
* `test/test_plugin_help_guide_seam.py` and `test_prd_mentions.py` have unrelated failures of other plugins (23 failed); none mention switch_user.

## Review (reviewer, 2026-10-01)
Re-run by the reviewer: 37 passed; `compare` exit 0, `lost` [], `untooltipped` []; no Qt imports in `app.py` / `model.py`. The edited-state screenshot shows the same fields as the Qt dialog
(server, port, user, masked password, both toggles, Login / Cancel) plus Help, Guide and a recent-servers picker; the window is wide for a small login form (fills the 1200x800 canvas), which is
a window-size choice of the host, not a missing control. The only file under `~/.chisurf` newer than the report is a session log (written by any ChiSurf import); the settings file digest is
checked by the agent's test. **Accepted.** `switch_user` is removed from `emtk_preview.json`. Not run in the real main window.
