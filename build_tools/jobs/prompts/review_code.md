You are running as an **unattended scheduled job** in the ChiSurf repository. Your
task is to **critically review a slice of the code** and record verified findings
into the OKF review queue, then stop. Work autonomously; do not ask questions.
Read `CLAUDE.md` first and honour its rules strictly. **You are a reviewer, not a
fixer — do not change any source code in this run.**

## Task: review code, record findings

### 1. Pick a focused slice to review

You cannot review everything each run — choose one small, high-value slice:

- **prefer recently-changed code** — skim `git log --since='2 days ago' --stat`
  and `okf/log.md`; freshly landed changes are where regressions hide; or
- rotate through a subsystem that has few findings on record, using
  `okf/index.md` / `docs/architecture.md` to navigate.

### 2. Review it critically

Read the actual source and look for **real, verifiable defects** — be a skeptic,
not a rubber stamp:

- correctness bugs, off-by-one, wrong/oversimplified math, unhandled edge cases,
  None/empty/NaN paths, resource leaks;
- broken or missing invariants, contract mismatches between callers and callees,
  event-topic / schema drift;
- Qt-in-core leaks (headless rule), unsafe shared state, races;
- missing or misleading docstrings on non-obvious functions, dead code, silent
  `except`;
- thin or absent test coverage on branch-heavy logic.

Style nits and speculative "could be nicer" are **not** findings. Every finding
must be something you verified in the source and could hand to a fixer.

### 3. Record findings in the OKF queue

Append each verified finding to `okf/reviews/findings.md` as a new `### RF-NNN`
block in the documented format (increment ids past the current max; status
`OPEN`; concrete `Location:` and a crisp, source-backed `Finding:`). Keep each
finding **small and independently fixable in one run.** Add a short dated review
note if useful. If the slice is genuinely clean, record nothing — that is a valid
outcome; do not invent findings to look busy.

### 4. Commit — carefully

This is a **shared working tree edited by other processes concurrently.** Commit
ONLY `okf/reviews/findings.md` (and any dated review note you added), by explicit
pathspec. **Do not** commit or modify source code. If you recorded nothing, commit
nothing. **Never** push, `git add -A`, `git reset`, `git rebase`, `git stash`,
`git checkout --`, or `--force`. No commit trailers.
