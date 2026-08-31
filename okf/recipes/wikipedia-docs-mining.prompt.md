You are running one tranche of a continuous docs-mining loop for ChiSurf.
The working directory is already /Users/tpeulen/dev/chisurf. Confirm
`git rev-parse --abbrev-ref HEAD` prints `development` before touching
anything; if it does not, log that and stop. One tranche per run. When the
tranche is committed (or deliberately skipped), stop.

## Fixed environment facts (verified, do not re-derive)
- Wikipedia dump: /Volumes/SD1TB/wikipedia/ with articles/*.wiki (extracted)
  and tools/ (extraction scripts). If the SD card is not mounted, ground text
  via the live article (https://en.wikipedia.org/wiki/<Title>) or cite from
  Crossref bibliographic queries only.
- Bibliography source of truth: docs/references/bibliography.yaml. NEVER
  hand-edit docs/references/index.md. Regenerate it with:
    pixi run -e docs --frozen python build_tools/docs/make_bibliography.py
  (--frozen is REQUIRED; without it the env fails to solve on wgpu).
- Docs guardrail tests (pytest only exists in the test env):
    pixi run --frozen -e test python -m pytest test/test_docs_links.py \
      test/test_docs_sources.py test/test_docs_okf.py \
      test/test_reference_coverage.py -q
  All must pass before any commit. Tests are FROZEN: if a test blocks a
  change, abort that change and log why; never edit the tests to fit.
- Crossref verification is mandatory before landing ANY DOI:
    curl -s "https://api.crossref.org/works/<DOI>" \
      -H "User-Agent: chisurf-docs-mining/1.0 (mailto:thomas.otavio.peulen@gmail.com)"
  Confirm the returned title/year actually matches what you intend to cite.
  Wikipedia DOIs are sometimes wrong: a mismatch means the DOI is bad, not
  that the paper is. Find the right one or drop the entry.
- Licensing: prose derived from a Wikipedia article (dump or web) requires a
  front-matter sources: block on that page, each entry with text/url/licence;
  accepted licences are CC-BY-SA-4.0, CC-BY-SA-3.0, CC-BY-4.0, CC-BY-3.0,
  CC0-1.0, public-domain (enforced by test/test_docs_sources.py). Prefer
  writing fresh prose grounded in the source over pasting text.
- MyST: every {cite}`key` must resolve in bibliography.yaml; {src}` and
  {doc}` roles for code/doc links; new concept pages get an anchor like
  (concept-<name>)= and a toctree entry in the matching index
  (docs/concepts/index.rst or sibling index).
- Bibliography entry format follows existing entries exactly: key, authors,
  title, journal, year, volume, pages, doi, optional note, topics list; a
  new group gets a comment header like: # ── <Topic> ──

## Safety rules (hard)
- NEVER `git add -A`, `git add .`, or `git commit -a`. Never push. Never
  switch branches. Never `git reset --hard`, `git checkout -- <path>` on a
  file you did not edit this run, `git clean`, or `git stash`.
- This is a SHARED working tree. Other agent sessions have their own
  uncommitted AND STAGED changes in it (okf/prds/*, okf/subsystems/*,
  okf/specs/*, okf/plugins/*, okf/references/known-issues.md, docs/guides/*,
  chisurf/**). Assume every modified/staged/untracked path that you did not
  write this run belongs to someone else.
- Because others have STAGED work, a bare `git commit` would sweep it in.
  Commit through a temporary index instead, which is the only safe form:
    export GIT_INDEX_FILE=$(mktemp -u /tmp/mining-idx.XXXXXX)
    git read-tree HEAD
    git add <exactly the files you edited this run>
    git commit -m "..."
    rm -f "$GIT_INDEX_FILE"
  Run any verification `git status` in a SEPARATE shell invocation, or unset
  GIT_INDEX_FILE first: with the temp index still exported and deleted, git
  reports every tracked file as deleted, which is a display artefact and not
  real damage.
- Allowed files for this loop: docs/**, docs/references/bibliography.yaml,
  docs/references/index.md (generated only), okf/references/wikipedia-mining.md,
  okf/log.md. Nothing in chisurf/ source, pixi.toml, or pyproject.
- If allowed-set files are already dirty when you start, read the diff. If it
  is a predecessor tranche's own unfinished bookkeeping, you may finish and
  commit it. If it is someone else's work, leave it alone.
- If guardrail tests fail after your edits and you cannot fix it quickly,
  revert ONLY the files you changed this run, log the failure, stop.

## Procedure
1. Read the tail of okf/references/wikipedia-mining.md (especially the hunt
   sections and "Where to pick this up") and the last entries of okf/log.md
   to learn the current state and the recorded next lead. Check
   `git status --porcelain` for leftovers.
2. Pick ONE lead. Best pattern so far: "implementations without pages" —
   grep chisurf/ and test/ for a method family with real code and tests,
   then check docs/ for coverage. Other valid leads: a plugin tool with no
   page, an existing page with zero or thin citations, a concept already
   covered by an extracted article in articles/. Record the lead and why.
3. Mine: find the matching Wikipedia article(s), pull candidate DOIs from
   their references, Crossref-verify each, keep only verified. Small tranches
   (2-6 entries) beat big ones.
4. Land: bibliography section, page edits or a new page (with sources: block
   when prose derives from Wikipedia), toctree entry if new page. Then
   REGENERATE docs/references/index.md with the exact command above and
   machine-check it: `grep -c <key> docs/references/index.md` must be >= 1
   for EVERY new key. Landing bibliography entries without a regenerated
   index is a failed run.
5. Verify: run ALL FOUR guardrail test files in a single pytest invocation;
   the summary line must show zero failures and zero errors (currently
   20 passed). Running only some of the files does not count.
5b. Pre-commit checklist, all must be true: index.md contains every new
   cite key; the full four-file test run passed; the temp-index commit
   contains exactly the files you edited this run (verify with
   `git show --stat`); okf bookkeeping updated.
6. Bookkeeping: append a dated entry to okf/log.md and update
   okf/references/wikipedia-mining.md (what landed, next lead). Commit the
   docs/okf files you touched as ONE commit, message style like:
   "docs: <what and why>". No commit trailers of any kind.
7. If the run finds no worthwhile lead (the pool is saturated), append a
   one-line idle note to okf/references/wikipedia-mining.md, commit that
   note alone (through the temp index), and stop. Do not manufacture a
   tranche just to have landed something.

Run one tranche now, following the above exactly: pick the recorded next
lead (or find a better one), mine and Crossref-verify citations, land the
tranche, pass the guardrail tests, commit only your own files through the
temporary index, record the next lead, then stop.
