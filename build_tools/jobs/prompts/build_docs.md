You are running as an **unattended scheduled job** in the ChiSurf repository.
Your task is to keep the documentation **truthful to the source code** and
building cleanly, then stop. Work autonomously; do not ask questions. Read
`CLAUDE.md` first for the environment and git rules, and honour them strictly.

## Task: reconcile docs with the source, then rebuild

### 1. Find drift between the docs and the code

Both documentation surfaces must describe what the code **actually does today**:

- **`docs/`** — the user-facing Sphinx manual, guides, and API/plugin reference.
- **`okf/`** — the Open Knowledge Format bundle (architecture, subsystems,
  workflows, specs, prds, references). Per `CLAUDE.md`, OKF is the durable
  knowledge layer and **wins on conflicts** — but "wins" means it must be kept
  *correct*, not left stale.

Focus your search using what changed recently: skim `git log --since=... --stat`
and `okf/log.md` for subsystems touched since the docs last moved. Look for:

- documented module paths, class/function names, CLI flags, pixi tasks, settings
  keys, RPC methods, or manifest fields that were **renamed, removed, or changed**
  in the code;
- new subsystems / plugins / view.json sections / PRD outcomes the docs don't
  mention yet;
- OKF concepts describing behaviour the code no longer has (or vice-versa), and
  dead cross-links or file references.

Verify each suspected mismatch against the **actual source** before changing
anything — do not trust one doc against another.

### 2. Update the stale docs and OKF concepts to match the code

Correct what you verified as wrong; add what is genuinely missing. Keep edits
**accurate and minimal — never invent behaviour or pad prose.** For any material
OKF change, update the matching concept **and** append a dated bullet to
`okf/log.md` (the change-tracking rule). If a mismatch needs a judgement call or a
large rewrite, leave it and note it in the log instead of guessing.

### 3. Rebuild and keep the build clean

- `pixi run -e docs docs-plugins` (regenerate `docs/plugins.md` from live
  manifests), then `pixi run -e docs docs-html` (full Sphinx build).
- Sphinx must finish **warning-free** (a maintained invariant). Fix only clear,
  local defects (broken xref, stale path, mis-nested heading, missing toctree
  entry, a dead link into `okf/` which is excluded from the user build). Rebuild
  to confirm each fix and that no new warning appeared. Do not touch code to
  silence a warning.

### 4. Commit — carefully

This is a **shared working tree edited by other processes concurrently.** Commit
ONLY the documentation / OKF files you actually changed, by explicit pathspec
(`git commit -- docs/<f> okf/<f> …`). Stage your own hunks only if a shared file
(e.g. `okf/log.md`) also has others' uncommitted edits. The generated
`docs/_build/` is a build artifact — never commit it. If you changed nothing,
commit nothing. **Never** push, `git add -A`, `git reset`, `git rebase`,
`git stash`, `git checkout --`, or `--force`. No commit trailers.

If the docs were already truthful and the build already clean, exit quietly
without a commit.
