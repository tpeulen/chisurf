You are running as an **unattended, frequently-scheduled job** (every ~30 min) in
the ChiSurf repository. Your task is to make **one small, safe, tested increment**
of self-improvement driven by the roadmap, then stop. Work autonomously; do not
ask questions. Read `CLAUDE.md` first and honour its rules **strictly** — the
shared-working-tree and no-push rules especially. When in doubt, do less.

## Task: advance the roadmap by one well-scoped, verified step

### 1. Choose ONE small item

Read `okf/prds/index.md` (the PRD roadmap + implementation order), the relevant
`okf/prds/prd-*.md`, and `okf/specs/assessment.md` (the cleanup backlog). Pick a
**single** next step that is genuinely small and low-risk:

- the next unchecked task of an **in-progress** PRD, or
- an **open S3 (or clear-cut S2)** backlog finding.

Prefer items that are local, well-understood, and easy to verify. **Do not** start
large architectural work, S1 items, or anything you cannot finish and test in one
run. If nothing safe is available, go to step 4 (documentation-only).

### 2. Implement it cleanly

Make the change the way the surrounding code is written (match idiom, naming,
NumPy-style docstrings; ruff line length 100). Add or extend **tests** that pin
the new behaviour. Keep the diff focused on the one item.

### 3. Verify — this gate is mandatory

Build extensions if needed (`pixi run build-extensions`) and run the **relevant
tests** (`pixi run test`, or a targeted `pytest …` in the project's arm64 env per
`CLAUDE.md`). Also run `pixi run lint` on what you touched.

- **Only commit if the tests you ran are green and lint is clean.**
- If tests fail, or you are unsure the change is correct, **undo your own edits**
  (`git restore -- <only the files you changed>` / delete files you created) and
  fall through to step 4. **Never commit broken, unverified, or speculative code.**

### 4. If no safe code change: improve the knowledge instead

Advance the roadmap without touching code: sharpen a PRD's next-step definition,
record a newly-verified finding in the assessment backlog, fix an inaccurate PRD
status, or note a design decision — all backed by reading the actual source.

### 5. Track and commit — carefully

Update the owning `okf/prds/prd-*.md` (status / Definition-of-Done checkboxes),
`okf/prds/index.md` glyph, and the assessment row when a unit of work lands, and
append a dated bullet to `okf/log.md`. Then commit **only the files you changed,
by explicit pathspec** (`git commit -- <files>`); for a shared file that others
are also editing (e.g. `okf/log.md`), stage just your hunk. **Never** push,
`git add -A`, `git add .`, `git reset`, `git rebase`, `git stash`,
`git checkout -- <not-yours>`, or `--force`. No commit trailers. Commit is
authored by tpeulen only.

### Guardrails (read again)

- **One focused change per run.** A no-op run is a perfectly good outcome.
- **Another instance is probably editing the tree right now.** Touch and commit
  only files that are wholly your own work this run; if a command would sweep in
  or discard someone else's changes, stop and leave it.
- The runner already prevents overlapping runs, so a long verify is fine — do not
  rush the test gate to fit the 30-minute cadence.
