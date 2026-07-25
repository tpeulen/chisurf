You are running as an **unattended scheduled job** (every ~30 min) in the ChiSurf
repository. Your task is to **fix one open code-review finding** from the OKF
queue, behind a mandatory test gate, then stop. Work autonomously; do not ask
questions. Read `CLAUDE.md` first and honour its rules strictly. When in doubt,
do less.

## Task: close one finding from the review queue

### 1. Pick one OPEN finding

Read `okf/reviews/findings.md`. Choose a **single** `OPEN` finding that is small,
well-specified, and safe to fix and verify in one run — prefer the highest
severity among those. Re-read the cited source to confirm the finding is still
real and correctly described. If it is stale (already fixed, or wrong), mark it
`WONTFIX` with a one-line reason and stop (that is a complete, valid run).

If there are no actionable OPEN findings, exit quietly without changes.

### 2. Fix it cleanly

Make the change the way the surrounding code is written (idiom, naming,
NumPy-style docstrings, ruff line length 100). Add or extend a **test that pins
the fix** so the finding cannot silently regress. Keep the diff focused on this
one finding.

### 3. Verify — this gate is mandatory

Build extensions if needed (`pixi run build-extensions`), run the **relevant
tests** (`pixi run test` or a targeted `pytest …` in the project's arm64 env per
`CLAUDE.md`), and `pixi run lint` on what you touched.

- **Only commit if the tests you ran are green and lint is clean.**
- If they fail, or you are not confident the fix is correct, **undo your own
  edits** (`git restore -- <only your files>` / delete files you created) and
  leave the finding `OPEN` (optionally add a note on what blocked it). **Never
  commit broken or unverified code.**

### 4. Close the finding + track

Flip the finding's `Status:` to `FIXED` and fill its `Fix note:` (what changed +
the pinning test). If the fix touched a subsystem/PRD, update the matching OKF
concept and append a dated bullet to `okf/log.md` (change-tracking rule).

### 5. Commit — carefully

This is a **shared working tree edited by other processes concurrently.** Commit
ONLY the files you changed for this one finding — the source + test + the
`okf/reviews/findings.md` status flip (+ any OKF concept you updated) — **by
explicit pathspec** (`git commit -- <files>`); for a shared file others are also
editing (e.g. `okf/log.md`), stage just your hunk. **Never** push, `git add -A`,
`git add .`, `git reset`, `git rebase`, `git stash`, `git checkout -- <not-yours>`,
or `--force`. No commit trailers.

### Guardrails

- **One finding per run.** A no-op run is fine.
- **Another instance is probably editing the tree right now.** Touch and commit
  only files that are wholly your own work this run; if a command would sweep in
  or discard someone else's changes, stop and leave it.
- The runner prevents overlapping runs, so do not rush the test gate to fit the
  30-minute cadence.
