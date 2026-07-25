You are running as an **unattended scheduled job** in the ChiSurf repository.
Your one task is to rebuild the documentation and surface any problems, then
stop. Work autonomously; do not ask questions. Read `CLAUDE.md` first for the
environment and git rules, and honour them strictly.

## Task: rebuild the docs

1. **Regenerate generated inputs**, then build the HTML:
   - `pixi run -e docs docs-plugins` (regenerates `docs/plugins.md` from the
     live plugin manifests), then
   - `pixi run -e docs docs-html` (the full Sphinx build to `docs/_build`).

2. **Read the build output.** Sphinx must finish **warning-free** — a clean
   build is a maintained invariant (see the assessment backlog). If there are
   warnings or errors:
   - Fix the ones that are safe, local, and unambiguous documentation defects —
     e.g. a broken cross-reference, a stale file path in a doc, a mis-nested
     heading, a missing toctree entry, a dead link into `okf/` (the knowledge
     bundle is intentionally excluded from the user-facing build).
   - Do **not** invent content, rewrite prose wholesale, or touch code to silence
     a warning. If a warning needs a judgement call or a non-trivial change,
     leave it and just report it in the log instead of guessing.
   - After any fix, rebuild to confirm the warning is gone and no new one
     appeared.

3. **Commit — carefully.** This is a **shared working tree edited by other
   processes concurrently.** Commit ONLY the documentation files you actually
   changed, by explicit pathspec (e.g.
   `git commit -- docs/<file> …`). The generated `docs/_build/` output is a build
   artifact — do not commit it (it is gitignored; leave it alone). If you changed
   nothing, commit nothing. **Never** push, `git add -A`, `git reset`,
   `git rebase`, `git stash`, `git checkout --`, or `--force`. No commit trailers.

4. If the build was already clean and needed no fixes, exit quietly without a
   commit.

Keep it focused: regenerate → build → fix only clear doc defects → rebuild to
verify → commit just the docs you touched. Then you are done.
