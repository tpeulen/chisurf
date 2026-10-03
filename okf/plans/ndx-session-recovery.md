# ndX session recovery

Scope: finish the executable leftovers from session 62a3ae40-4905-4104-b93f-26b66caa779a. The last push completed; modules/mmfdb is a symlink, not a gitlink.

1. Recover transcript, inspect shared-tree state, and run arm64 baseline. Test with an isolated HOME and NDXPLORER_SETTINGS_DIR **unset**; individual fixtures control settings directories. Never modify original measurements.
2. Reproduce ignored LineSet axes: push FRET lines while viewing another projection. Add tests for exact names, declared scientific aliases, absent/ambiguous axes, and conflicting projections. Resolve the pair before mutating overlays or axes; retain ordinary unhinted line behaviour. Inspect before/after renders of the real host.
3. Reproduce native MMFDB provenance loss: dataset picker returns an artifact identity but gui/app.py consumes only a local path. Preserve the authenticated client/product identity and attach burst_ids_recorder; detach it when a different dataset is opened. Use an in-process MMFDB test database and read saved lineage back.
4. Run the full ndX suite and affected ChiSurf tests. Update user docs, matching OKF concept and own log entry. Commit scoped files only, keeping existing unstaged edits out of each commit. Bump only the ndX gitlink once its own commits are verified.
Excluded: original cal1 calibration objects; other sessions' modified performance_config/accurate_fret/settings/menu files; unrelated plugin ports; global plot/colormap defaults; pushing new work without another explicit request.

## Verification and resume point

Completed: recovered the session, ran red/green regressions for overlay projection
safety and authenticated native-MMFDB selection lineage, and inspected measured-data
before/after host screenshots. No measurements or user plotting defaults changed.

- Full ndX: `1213 passed, 2 skipped, 97 warnings` (381.70 s), with isolated HOME,
  settings override unset, offscreen Qt and scratch basetemp. The warnings are
  numerical runtime warnings in existing non-overlay paths; this is not a
  warning-free suite.
- Overlay/phasor/general-overlay/IO suites: `64 passed` (27.40 s), including four
  follow-up regressions proved RED then GREEN for literal/case-folded axis names
  and a pending save whose source recorder is cleared or replaced.
- ChiSurf ndX host tests + FRET-line parity + ALEX Suite tests: `121 passed` (50.67 s).
  Native provenance cases cover real input/mask lineage, identity detachment,
  expired authentication, and failed input linking.
- New helpers/tests and ChiSurf changed production files pass Ruff. Existing style
  findings in ndX frame/overlays and the shared screenshot script are baseline
  debt, not a reason to sweep unrelated source into this task.
- Independent read-only reviews passed. The follow-up verdict has no security
  concerns, logic errors or suggestions; the reviewer did not run tests or renders.
- ndX guide code checks: `14 passed, 450 deselected` (0.37 s).
- Documentation guards: 9 passed, 2 failed. A scratch replay using the pre-edit
  guide/concept/provenance and register snapshot proves the same 132 unregistered
  images and stale figure/table/code indexes before this recovery. These shared
  documentation-migration failures remain out of scope; the new screenshot and
  Python example have their own scoped inventory entries.
- Published GUI evidence: `docs/guides/figures/ndxplorer_overlay_axes.png`, captured
  by `_grab_ndx_overlay_axes` in the maintained screenshot script.
- ndX implementation committed locally as `04fd5f89fd6e44f8512800cfa82d7ce6c323d203`.
  ChiSurf records that exact gitlink; excluded source/default-setting edits remain
  unstaged. No recovery work was pushed.
- Earlier mixed-Qt exit 139 did not reproduce in baseline/fixed replays or the final
  affected-suite run; the measured limitation is in `okf/references/known-issues.md`.

Resume only the separately owned `plot_backend` / `TOOLBAR_TARGET` changes after
checking their owners' current state. MMFDB is still a symlink, so there is no
MMFDB gitlink to bump. Keep new commits local; do not push this recovery work.
