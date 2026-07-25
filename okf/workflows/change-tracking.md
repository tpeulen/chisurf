---
type: Playbook
title: Change Tracking
description: The mandatory loop for every material change — update OKF, keep it traceable, commit.
resource: okf/log.md
tags: [process, okf, provenance, git]
timestamp: '2026-07-07T00:00:00Z'
---

# Change tracking — always update OKF and commit

OKF is the durable, agent-readable knowledge layer that sits beside the code. It
is only useful if it stays in sync with the tree, so **every material change runs
the same loop**. This is the process rule that the per-area
[change policy](/architecture/overview.md) and the root `CLAUDE.md`
"Working practices" section point at.

## The loop (do this for every material change)

1. **Make the change** — prefer a clean implementation over a patch (ChiSurf is
   active-development; large architectural changes are expected).
2. **Update the matching OKF concept** — the `architecture/`, `subsystems/`,
   `workflows/`, `specs/`, `prds/`, or `references/` doc that owns the changed
   behavior. If a burn-down/backlog tracks the work (e.g.
   [specs/assessment.md](/specs/assessment.md), a `specs/*-audit.md` table, a PRD
   Definition-of-Done), update its numbers/checkboxes in the **same** change.
3. **Append a dated bullet to [okf/log.md](../log.md)** under today's `## YYYY-MM-DD`
   heading — one bullet per landed unit of work, saying *what* changed, *why*, the
   verification result, and the affected concept links. OKF wins on conflicts
   (it is newer than the code comments).
4. **Update the user documentation in `docs/`** — OKF is the knowledge layer for
   *agents*; `docs/` is the manual for *people*, and a change that alters what a
   user sees or how they work is not finished until both are updated. See
   [User documentation is part of the change](#user-documentation-is-part-of-the-change)
   below for what that means per change type.
5. **Mark done when done** — flip `status:`/DoD in the relevant PRD, the glyph in
   `prds/index.md`, and the row in the assessment backlog. Never leave finished
   work marked `planned`/`in-progress`/unchecked.
6. **Commit** — a focused commit per file or small coherent batch, with a message
   that states the change, the verification (e.g. "suite: 420 passed"), and any
   audit-number delta. Commit **locally only — never push** (see
   [[feedback-no-push]]). **No commit trailers of any kind** — no
   `Co-Authored-By`, no "Generated with" / tool attribution. Commits are authored
   by tpeulen only; the message body is plain text with no trailer block.

## User documentation is part of the change

`docs/` is not a separate deliverable to be caught up later — a feature that
users cannot find or understand is unfinished. Every change that touches
user-visible behaviour updates it in the **same** change:

| What changed | What to update in `docs/` |
| --- | --- |
| A new analysis method or model | `docs/concepts/<topic>.md` (the theory) **and** `docs/guides/NN_<topic>.md` (the workflow), each registered in `docs/concepts/index.rst` / `docs/guides/index.md` and cross-linked to each other |
| A new or changed plugin | Regenerate the catalogue (`pixi run -e docs docs-plugins`) so `docs/reference/plugins/` matches the manifest and view spec — **plus** the concept + guide pair below |
| A changed parameter / control | Its `description` in the `view.json` (that is the tooltip *and* the generated docs cell) |
| A changed CLI / API surface | The guide's headless section and the API snippet |
| Anything with a UI | A screenshot grabbed from the real widget in `docs/guides/make_screenshots.py`, never a mockup |

### Plugins are documented in theory and in application

A plugin is documented when **both** halves exist, because they answer different
questions and neither substitutes for the other:

* **Theory** — `docs/concepts/`: what the method measures, the formulas, the
  assumptions, what the parameters mean physically, what a defensible result
  looks like, and citations. Written so a reader can judge whether the method
  fits their question at all. Reference-quality prose is the target (see
  [[quickfit3-docs-for-concepts]]).
* **Application** — `docs/guides/`: the numbered step-by-step workflow in
  ChiSurf — which tool, which settings in which order, what the panels show,
  the headless CLI equivalent, the Python API, and a real screenshot. Written so
  a reader can reproduce the result today.

Each half opens with a link to the other: the guide with a `Theory` admonition
pointing at the concept anchor, the concept with a line pointing at the guide.

In-app help follows the same split: short `description` tooltips on every
control, and a `?` **help** section in the `view.json` whose Markdown file ships
beside it — a condensed version of the guide, not a second source of truth.

## Parallel instances — never destroy uncommitted work

Multiple agent instances (and the user) work on this repository **in parallel**,
each with its own uncommitted edits in the shared working tree. Destructive git
that discards working-tree or index state will silently wipe another instance's
in-flight work, so it is **banned**:

- **No `git reset --hard`**, `git checkout -- <path>` / `git restore <path>`,
  `git clean -f`/`-fd`/`-fdx`, `git stash` (it removes changes from the tree),
  `git stash drop`, or any `--force` operation — these throw away edits you did
  not make.
- **Never revert, restage, or unstage files you did not change.** Assume every
  other modified/staged/untracked path belongs to another instance and is mid-flight.
- **Commit only your own changes.** Never `git add -A`/`git add .`/`git commit -a`,
  which sweep up everyone else's changes. Beware the **pathspec footgun**:
  `git commit -- <path>` commits that path's *working-tree* content, not just what
  you staged, so it sweeps a co-editing instance's uncommitted lines from the same
  file. Use `git commit -- <paths>` only for files that are **wholly yours**; when
  a file has another instance's concurrent edits, stage just your hunks
  (`git apply --cached <hunk.patch>` or `git add -p`) and run `git commit` with
  **no pathspec** (index only). Confirm with `git diff --cached` first, and check
  the other instance's hunk is still unstaged afterward. Hot shared files
  (`okf/log.md`, `okf/prds/index.md`, `pixi.toml`) will often be swept into another
  instance's commit — that is fine, the content lands; just do not be the one who
  sweeps theirs.
- **Do not push** (see [[feedback-no-push]]) and do not rebase/amend shared history.
- If a git command *would* discard work that is not yours, stop and report to the
  user instead of running it.

## Make changes traceable

The point of the loop is that anyone (or any future agent) can reconstruct *what
changed and why* from durable artifacts alone:

- **`okf/log.md`** is the running narrative — the first place to look for "what
  happened and when".
- **Burn-down tables** (e.g. `specs/*-audit.md`) carry the running totals so
  progress is measurable, not vibes; keep the `TOTAL` row consistent with the
  per-row sums.
- **Git history** is per-unit: small commits, each self-describing, each
  verified green before it lands. Never bundle unrelated changes.
- **`HANDOVER.md`** (repo root, when a multi-session effort is in flight) holds
  the "start fresh" brief: current state, audit numbers, and an explicit
  *what's next*. Refresh it as the effort advances.

If a change is not worth a log bullet and a commit, it is either trivial (a typo)
or it is not really done — decide which and act accordingly.
