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
the same loop**. This is the process rule that the root
[`CLAUDE.md`](/references/claude-md.md) "Working practices" section points at.

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

   **USER RULE: keep it short.** Every later session reads this file, so a long
   entry costs everyone context and buries the fact that mattered. Two or three
   tight lines per bullet. Measurement tables, worked numbers and traps belong
   in the **concept** that owns the area — reference material, read on demand —
   and the log points at it. Same for a `CHANGELOG.md` bullet and a commit body:
   say what changed and where the detail lives.
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
7. **Leave a resume point** — see below. A session that ends without one costs
   the next one a rediscovery.

## Leave a resume point, in OKF

Finish by updating the **"Where to pick this up"** section of the concept that
owns the area — [plugins/pymol-parity.md](/plugins/pymol-parity.md) is the worked
example. If the concept has none, create one **at the top**, before the findings:
a reader arriving cold should hit the open front before the history.

`okf/log.md` is not a substitute. The log records *what happened*, in the past
tense, newest-first by date; it answers "what changed" and cannot answer "what
next" without reading every entry and inferring. The two have different jobs.

A resume section is a short ordered list of the open front, ordered by what a
user actually hits. What separates a useful entry from a topic name:

* **the measurement, and how to re-derive it** — including any trap in taking
  it. "790 settings, 55 registered, and the 228 that PyMOL's own Python layer
  references are the worklist" is actionable; "settings coverage is low" is not.
  Record the trap too: the first count here read 770 because the parser silently
  dropped every record with a trailing `/* comment */`.
* **what the gap blocks.** One missing piece often explains several symptoms —
  a hydrogen-bond finder blocks two presets *and* a whole disabled menu — and
  naming that is what turns a list into a priority order.
* **approaches tried and reverted, with why.** Otherwise the next session
  repeats them. If a revert was the right call, say what the suite showed.

Anything left undone belongs here or in
[references/known-issues.md](/references/known-issues.md) — a defect found and
not fixed goes to known-issues with its measurement; work not yet started goes
to the resume section. **Never only in the chat**, and never only in an agent's
private notes, which the next session cannot read.

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
| A new or changed plugin GUI | A **guided tour** — `gui/guide.json` beside the `view.json`. Any tool that calls `add_toolbar_help` grows a **Guide** button as soon as that file exists, so this is one file and no code |
| A *Further reading* list in a `help.md` | Real Markdown links, not backticked paths: a documentation page opens in the ChiSurf documentation browser, a URL or DOI in the system browser. A guardrail test fails on a link to a file that is not there |

### A plugin is not finished until someone can be walked through it

Documentation says what a control *means*. It does not say which control to
touch **first**, and that is the gap a scientific tool actually loses people in:
the panel is full of correct, well-documented settings and nothing says where to
start. So every plugin ships a **guided tour** in `gui/guide.json` — a list of
steps, each pointing at one real widget, read by
[`guided_tour.py`](/architecture/plugin-system.md).

Two rules about what a tour may do, and both are the point rather than detail:

* **It points; the user presses.** A step that needs a button pressed declares
  `"await"` and waits — Next stays disabled until the user uses the *real*
  control. A tour that pressed the button on the user's behalf would be a demo
  reel, and someone who watched a button being pressed has not learned where it
  is.
* **It must be walkable with no data.** Where a tool needs something to
  demonstrate on, the plugin generates a **demo** whose answer is known (the
  flow-map tool simulates a photon stream with a known velocity profile, so the
  tour ends by comparing the result against the truth). A tour that begins
  "open one of your files" teaches nothing to the person who most needs it.

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

## Traceability runs one way — source points at concepts, never at PRDs

Tracking a change in OKF does **not** mean stamping the PRD number into the code
it produced. **Shipped source must never name a PRD.** A PRD is a planning
artifact with a lifecycle — planned → done → superseded — and its number means
nothing to someone reading the file, who cannot follow it from where they are.
Point at the **concept** that owns the area, which is maintained precisely
because it describes what *is*:

```python
# See the columnar-store concept (/subsystems/columnar-store.md).   # yes
# See PRD-82.                                                       # no
```

More often than not the reference should simply go: "this was designed
somewhere" adds nothing the code does not already say. The traceability that
matters lives in `okf/log.md` and the commit message, both of which *may* name
the PRD, and in the concept the PRD updated.

Scope is the shipped package `chisurf/` — Python, `view.json` view specs, YAML
settings, shipped markdown. `okf/` is where PRDs live and `test/` documents
process, so neither is covered. Enforced by `test/test_prd_mentions.py` against
`test/prd_mention_allowlist.txt`, a **shrinking** list of files written before
the rule and never somewhere to add yourself. **A file you touch is a file you
clean**: port its PRD references to the owning concept in the same change and
strike the line.

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
