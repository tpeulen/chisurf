---
type: Subsystem
title: LLM agent
description: The plain-language assistant that operates ChiSurf through a described, safety-tiered tool catalogue.
resource: chisurf/core/agent/
tags: [agent, llm, tools, automation, assistant]
timestamp: '2026-07-25T00:00:00Z'
---

# Where to pick this up

1. **The documentation assistant has never run against a real model.** The
   harness, the restricted registry, the citation collection and the retrieval
   are all tested; the *answer* path has only ever seen `ScriptedLLM`, because
   both providers configured on the build machine were unusable on the day
   (expired key, no credit). The measurement, once a key works:
   `csc help ask "what does the gamma factor correct for?"` and check that
   `answer.pages` is non-empty and names `docs/concepts/accurate_fret.md`. An
   empty `pages` means the model answered from memory — the fix is then in
   `skills_builtin/answer-from-docs/SKILL.md`, not in the harness. Recorded in
   [known issues](/references/known-issues.md).
2. **Retrieval is judged by which page comes back, and that is the only way to
   judge it.** `test/agent/test_documentation_tools.py` is the harness: add a
   `(query, expected_document)` row whenever a question routes wrongly, then
   fix the ranking. Two traps already paid for — a *listing* page (the figure,
   table and code registers, the plugin catalogue) names every subject in the
   documentation and wins a term-frequency search while answering nothing, and
   an unfiltered natural-language query ranks by how chatty a page is unless
   the question words are dropped. Both are guarded; a third of the same kind
   is likely.
3. **The synonym map in `doc_index.py` is a stub with 17 entries.** It exists
   because the interface's spelling and the documentation's are not the same
   word (`chi2r` vs *reduced chi-square*), and every entry was added from a
   query that missed. It is worth growing from real questions rather than from
   imagination — the parameter glossary
   (`docs/reference/parameters.md`) is the obvious source, since it already
   pairs a control's label with its meaning.
4. **`browse_documentation` truncates at 60 entries with nowhere to go.** It
   sets `truncated: true`, so the omission is not silent, but there is no
   second page and no way to ask for the rest — a tag like `plugins` (168
   pages) shows the first 60 sorted by kind and title, which is an arbitrary
   third of them. Either page the listing or have the tool refuse and demand a
   narrower filter.

# What it is

`chisurf/core/agent/` is the harness that lets a language model operate
ChiSurf on a scientist's behalf: *"load every decay in this folder, fit them
with a lifetime model and give me the numbers"*. It is Qt-free, so the same
code backs the GUI assistant panel, the `python -m chisurf.core.agent`
command line, and the tests.

The design principle is that **the model is only as good as what it is told**.
Every operation is published with a prose description and a JSON Schema for
its arguments, and every failure is answered with a message that names the
fix. Nothing is left to be guessed.

# Parts

* `spec.py` — `ToolSpec` (name, description, JSON Schema, safety tier),
  `ToolRegistry`, and the argument validation that turns a malformed call into
  a readable error rather than a `TypeError`.
* `skills.py` + `skills_builtin/` — the procedures (see below).
* `context.py` — `AgentContext`: working directory, code-execution policy,
  confirmation and event callbacks, and the resolution of loose references
  ("the second fit", a file name, an index) to real session objects.
* `doc_index.py` — the map of the documentation, built from the
  Open-Knowledge-Format header every page carries (see below).
* `tools/` — the catalogue: `data.py` (find files, load them, describe
  experiments/readers/models), `documentation.py` (browse, search and read the
  documentation by kind and subject), `fitting.py` (create, run, inspect, edit,
  export), `decay.py` (the knobs that decide whether a decay fit means
  anything: IRF, component count, quality report, plot, and the one-call
  expert protocol), `scripting.py` (`run_python` in the live session,
  read/write files), `_dto.py` (compact summaries sized for a context window).
* `llm.py` — an OpenAI-compatible chat client with **native tool calling**,
  retries with backoff, and errors that say what to do (bad key, unknown
  model, rate limit).
* `prompt.py` — the system prompt (ChiSurf's object model, the load → fit →
  run → report workflow, how to judge a reduced chi-square) plus a
  text-protocol fallback for models without tool calling.
* `runtime.py` — `AgentSession`: the observe-act loop, budgets, and
  `AgentResult`.
* `cli.py` — the head-less driver.

# How a request is answered

1. The system prompt is refreshed with the live session state, so the model
   starts knowing which datasets and fits exist.
2. The tool schemas are sent with the request; the model answers with
   structured tool calls, possibly several at once.
3. Each call is validated, safety-checked (and confirmed with the user when it
   is `dangerous`), executed, and its result fed back as a tool message.
4. The loop ends when the model answers in prose, or when a budget (steps,
   tool calls, wall clock, consecutive failures) is spent.

A turn the model batched several calls into is answered **whole** even when the
run stops half-way through it: the calls that were never executed get a
`not run — the request stopped` result of their own. The conversation survives
across questions, and a provider rejects an assistant turn whose tool-call ids
are not all answered — so a cancelled or budget-capped run would otherwise
poison every later question in the session rather than just its own.

A **failing tool does not end the run** — its error goes back to the model,
which corrects itself. Only *repeated identical* failures stop the loop; that
is the difference between an assistant that recovers and one that gives up.

# Misformatted actions are recovered, not punished

A model that knows what it wants and expresses it wrongly should not lose a
turn. Three shapes, all seen live, are handled before the loop sees them:

* **A call narrated instead of made** — the name left in the message text with
  the arguments beside it (`…list_plugins{"query": "kappa"}`), or the whole
  payload as `{'run_python': {'code': …}}`. When native tool calling produced
  nothing, the text is scanned for a **known** tool name followed by a JSON
  object (matched by brace depth, so trailing prose is fine, and read as JSON
  or as Python quoting). Only registered names are ever routed, so prose that
  merely contains JSON stays prose.
* **A near-miss name** — `list_plugin`, `functions.run_python`, `Run_Fit`.
  Routed when the name reduces to the same identifier after dropping case,
  separators, a namespace prefix and a trailing plural, and only when that
  reduction is unambiguous. Anything looser could run the wrong operation,
  which is worse than an error.
* **Reasoning in the answer** — `thinking`/`reasoning` content chunks, and
  inline `<think>…</think>` (an unclosed tag takes the rest with it, which is
  what a truncated response looks like). It is scratch work, often longer than
  the answer, and it carries abandoned conclusions that read as findings.

A rejected call is dropped from the **echoed message** as well as from the
parsed calls. The provider's own assistant turn is what goes back on the next
request, so a `tool_calls` entry the parser refused to dispatch would leave an
id that no `tool` message answers — the same poisoned conversation the
"answered whole" rule above exists to prevent, only arriving from the other
side.

The measure of it: the request that first exposed these took **eight** tool
calls with an `unknown tool 'To compute a distance from a FRET efficiency, I
will use…'` among them, and now takes **three** with none.

# Skills: tools say *what*, skills say *how*

`set_irf` is a tool. "Attach the IRF, then add lifetime components until
chi-square stops improving, and never report a chi-square from a fit you have
not judged" is a **procedure** — the knowledge a spectroscopist has and a
general-purpose model does not.

That knowledge cannot live in the system prompt: every experiment type would
add a section that is dead weight for every other request, and the prompt
would grow without bound as ChiSurf covers more methods. Skills are separate
`SKILL.md` documents with their own frontmatter (`name`, `description`,
`triggers`, `experiments`, `tools`); an unloaded skill costs one catalogue
line.

**Loading is automatic and deterministic.** Before the model sees a question
it is scored against every skill's triggers — with multi-word triggers
tolerating real phrasing, so "fit all 20 files" matches `all files` — plus a
weak signal from the experiment types already loaded. The top matches are
injected into the system prompt for that turn and stay active for the rest of
the conversation, so a follow-up does not silently lose the procedure. This
happens *before* the first model call, which makes routing testable without a
model in the loop. `load_skill` remains for what the matcher cannot see.

The built-in library: `fit-decay`, `fret-from-decays`, `global-fitting`,
`fit-correlation`, `fit-series`, `batch-fitting`, `diagnose-fit`,
`estimate-uncertainty`, `explore-data`, `report-results`,
`write-analysis-script`, `use-the-computer`, `program-chisurf`, and the smFRET
family `burst-search`, `burst-selection`, `sub-ensemble-decay`,
`fret-from-bursts`.

# Reaching the plugins

ChiSurf's ~100 plugins are most of what it can do, and a plugin the assistant
cannot find or call may as well not exist. `list_plugins` therefore reports,
per manifest, the **ways the plugin can be driven without its window**: the RPC
methods it registers (with their summaries), its command line, and its
`api`/`core` packages. The method names are part of the search text, because
they are often the only term a user would think of — "kappa" matches nothing in
the calculator's description and everything in `kappa2_dist.compute`.

Guardrails keep the advertisement honest
(`test/agent/test_plugin_entry_points.py`): every manifest must be valid, carry
an id and a description, name entry-point modules **and callables** that import,
declare RPC method names unique across the tree, and — the strongest of them —
**every declared RPC method must actually be registered** by the plugin's
services entry point, checked by running its registration against a recording
dispatcher. All 102 manifests pass: 41 service registrations, 49 command lines,
100 GUI entry points.

Discovery is only half of it, because a manifest usually leaves
`params_schema` empty: the assistant learns a method's *name* and not its
arguments. The route from there is the API index, and it had two dead ends,
both found by watching a model walk them. Names are `snake_case` and `_` is a
word character, so a query stayed one unsplittable term — searching
`compute_from_efficiency` for
`fret_calculator.fret.compute_from_efficiency` returned **nothing**, because
the real function is `compute_fret_from_efficiency`. The search now also
matches the words of a query, below the weight of a whole-phrase hit. And
`read_api_source` on a *module* — the natural next move after finding a plugin
— failed, because the index holds only the definitions inside one; it now lists
them. The `use-a-plugin` skill ties this together: find it, read the function
that implements it, call it, and check it against a case whose answer is known.

# Skills compose

A skill declares in its `uses:` frontmatter the smaller procedures it is built
out of, and `SkillLibrary.compose` pulls those in **transitively** when it is
loaded (cycle-safe, each skill once). Dependencies are resolved *after* the
match cut, so decomposing a procedure never costs it a slot.

This is what lets a multi-method analysis exist without a monolith.
`fret-from-bursts` is only the part that is genuinely its own — why the
donor-only population is not optional, species- versus intensity-weighted
lifetimes, and the check that the lifetime efficiency must agree with the
proximity ratio it was selected on. The work is in `burst-search` (bursts,
photon-index and detector-role verification), `burst-selection` (proximity
ratio, populations), `sub-ensemble-decay` (pooled micro-time histogram, IRF
from non-burst photons) and `fret-from-decays`.

The parts are independently routable — "show me the PR histogram" loads
`burst-selection` and the burst search it needs, nothing else — and a lab can
write its own protocol skill that `uses:` the shipped ones rather than copying
them. The whole chain runs on `run_python` plus the ordinary fitting tools: no
tool was added for any of it.

**Skills are written against the software, not from memory.** Every claim in
one is checked against a real fit first — the `fit-correlation` skill was
wrong on its first draft (it implied components and an IRF that correlation
models do not have), and `fret-from-decays` quotes the numbers the sample
data actually produces. A skill that misdescribes the program is worse than
no skill: the model follows it confidently into a wall.
Discovery layers built-in → plugin (`agent_skills/` beside a `manifest.json`)
→ user (`<settings>/agent_skills/`), later overriding earlier, so a lab can
replace `fit-decay` with its own protocol without touching the code.

# Capability comes from skills, not from more tools

The tool catalogue is the set of *primitives*; new capability is added as a
**SKILL file**, not as more Python. `estimate-uncertainty` is the worked
example: confidence intervals and model comparison arrived with no new tool
at all, as a procedure that drives `run_python` against
`Fit.adaptive_chi2_scan` and an F-test. Asked for "a proper confidence
interval, not the fit's own error bar", the assistant ran the recipe and
reported the support-plane interval while naming the covariance error as the
optimistic lower bound it is.

This keeps the tool surface small enough to describe honestly, and puts
domain judgement where it can be read and corrected by a scientist rather
than compiled. A skill that carries code is held to it: every ```python block
in every skill is compiled by the test suite, because a recipe a model copies
must not teach a syntax error.

Two things follow from the skills-first rule. New abilities are cheap — a
series/global-fit capability arrived as `fit-series` with no new tool at all,
composing `link_parameters` and a `run_python` comparison recipe. And
verifying a skill against the program is where defects surface: writing that
one showed every FCS fit reporting its *defaults* as results, because
`GeneralFCSModel` exposed all three of its diffusion presets to the optimiser
while computing with one.

# The assistant's own knowledge base

`chisurf/core/agent/knowledge_base/` is an OKF bundle carried **by the
assistant**, and deliberately not the repository's `okf/`:

| bundle | answers | audience |
| --- | --- | --- |
| `okf/` | how ChiSurf is *built* | someone changing the code |
| `knowledge_base/` | what the measurements and the session objects *mean* | the assistant, while operating the program |

Six concepts so far — the session model, TCSPC decays, FRET from lifetimes,
correlation spectroscopy, measurement files, uncertainty and model choice —
each with OKF frontmatter and each checkable against the program. Skills link
into it instead of repeating background, which is what keeps a skill a
procedure. It is searched with the repository documentation through the
`documentation` tool group and ranked slightly above it, since it is written
for this purpose and is deliberately concise.

# Answering *out of* the documentation

Driving the program and explaining it are different jobs, and for a while they
shared one badly-shaped tool. `search_docs` ranked ~570 markdown files by term
frequency, which put the figure register — a page that names every subject in
the documentation and explains none — at the top of most queries, and put a
developer note about a migration next to the guide a user actually wanted.

The fix was to give the corpus a header and rank on it.
`chisurf/core/agent/doc_index.py` reads the Open-Knowledge-Format front matter
every page now carries (`docs/`, `okf/` and the assistant's own bundle) and
builds a cached index over it. Four things it can do that a text search cannot:

* **route by kind before reading.** A `Concept` explains, a `Guide` instructs,
  a `Plugin Reference` enumerates controls, a `Development Note` is about the
  code. "What does X mean" and "how do I X" are different pages and the header
  says which is which.
* **cross the directories by tag.** The FRET concept, the FRET guides and the
  FRET plugin pages share a tag and nothing else.
* **hold a corpus map in one tool result.** ~570 one-line descriptions is a
  listing the model can *choose* from rather than guess at.
* **keep a user's question out of the developer pages.** `user_only` is the
  boundary between using ChiSurf and changing it.

Three ranking rules earn their keep, each from a query that went wrong:
question words (`what`, `does`, `how`, `mean`) are dropped or the two chattiest
guides win every query; **listing pages** — more than half their lines a table
row — are scored down to 0.3, or the registers win everything; and a small
synonym map bridges the interface's spelling and the documentation's
(`chi2r` → *reduced chi-square*, `irf` → *instrument response*).

The `documentation` tool group is `browse_documentation` (the map),
`search_documentation` and `read_documentation` (a page, or one `section` of
it, plus the pages related by tag). `scope` picks the corpus: `user` (default),
`code` (`okf/`), or `all`. `knowledge.search_prose` now delegates here, so
there is **one** implementation of "find the right page" — the codebase group's
own `search_docs`/`read_doc` were deleted rather than left to compete with it.

The `answer-from-docs` skill carries the procedure and, more importantly, the
rule: **a claim about ChiSurf comes from a page, and the answer says which**.
A model's own knowledge of the fluorescence literature is not knowledge of
*this program*, and a plausible wrong menu path sends the user looking for a
control that is not there.

## The documentation assistant

`chisurf/plugins/core/help/api/ask.py` is that agent with everything else taken
away: a registry holding the three documentation tools and nothing more, capped
at the read tier, eight steps. It cannot load data, fit, run Python or write a
file — enforced by the registry, not by the prompt, so a question phrased as an
instruction cannot talk it into doing so.

The pages it cites are **collected from the tool invocations**, not from the
model's own footnotes, which it will happily invent. An answer with no read
behind it is reported as such rather than dressed up as sourced — the help
browser's panel says so in orange.

Three surfaces, one implementation: the **Ask** panel in the help browser
(`gui/ask_panel.py`, a third column beside the page, on a worker thread), the
`help.docs.ask` RPC method, and `csc help ask "…"`. Documented for users in
`docs/guides/70_ask_the_documentation.md`.

# Making the answer *correct*, not just produced

Getting a model to call the right tools is the easy half. On a real TCSPC
decay the reduced chi-square runs 8.5 (no IRF) → 12.8 (IRF, one lifetime) →
1.37 (two) → 1.03 (three): an agent that stops at the first number produces a
confident, wrong answer. Two mechanisms prevent that, and both live in the
**tool results** rather than the system prompt, because that is what the
model is actually reading when it decides to stop:

* `assess_fit` attaches a verdict — `good` / `acceptable` / `poor`, the
  reason, and a concrete `next_step` naming the single most likely fix — to
  every result that carries a chi-square (`run_fit`, `fit_report`,
  `auto_fit_decay`). Before this, a model reported `chi2r = 12.8` as a
  finished result; after it, the same model attaches the IRF, grows the model
  to three components and lands at 1.03 unprompted.
* `load_data` flags datasets whose names look like instrument-response
  measurements (`irf`, `prompt`, `lamp`) so they are used as references
  rather than fitted as samples.
* A dataset that holds several curves reports `n_curves` and, where the
  reader knows it, what kind each curve is; a fit over such a group reports
  `n_members` and the spread of reduced chi-square across members, and is
  judged by its **worst** member. One file is not always one measurement — a
  cross-correlation measurement archive holds four repeats each of two
  autocorrelations and two cross-correlations — and reporting the selected
  member's chi-square as *the* result silently answers for one curve out of
  sixteen.

`auto_fit_decay` packages the same protocol into one call — attach the IRF,
add components until chi-square stops improving materially (2 %), stop early
once the fit matches the noise — and returns the whole trace so the model can
show its work. It turns roughly ten model turns into one.

# Providers and data residency

Every request carries the user's wording, file and dataset names, fitted
parameters and tool results to whichever provider is configured — so the
choice of provider is a data-processing decision, not a performance one.
ChiSurf's users are largely European labs working with unpublished
measurements, so the provider table is ordered by **where the data is
processed**, and a fresh install starts on `mistral` (EU) rather than a
third-country service. A saved choice is never overridden: changing the
shipped default moves new installs only.

Keys are read from the environment under any of the usual spellings
(`MISTRAL_API_KEY`, `MISTRAL_KEY`, `MISTRAL_API_TOKEN`, `MISTRAL_TOKEN`, and
likewise per provider) — a key that exists but is looked for under the wrong
name is indistinguishable, to the user, from a provider that does not work.

The conversation is echoed back to the provider each turn, and providers
validate *input* more strictly than they format *output*: several emit
`content: null` beside `tool_calls` and reject that same null on the way in.
Assistant turns are therefore normalised to the fields every provider accepts
before being re-sent, and `test/agent/test_provider_dialects.py` replays each
provider's reply shape through the loop to keep that true.

# Programming ChiSurf, not just driving it

Operating the program through tools needs no knowledge of the codebase;
writing against it does, and that is exactly what a general-purpose model
lacks. Left to guess it invents an API — plausible names, plausible
arguments, none of them real.

`knowledge.py` answers that from two sources, because they answer different
questions. An **AST index of the source tree** (every public class, function
and method with signature, docstring, file and line, cached under the
settings directory and rebuilt when the tree changes) says *what exists and
what does it take*; it is derived from the code, so it cannot be stale. The
**prose** — OKF concepts and the guides — says *why it is like that and what
the right way is*, which signatures never carry. Changelogs are excluded from
the prose search: they mention everything and answer nothing, and by raw hit
count they win every query.

The `codebase` tool group exposes the index as `search_api`,
`read_api_source`, `list_plugins` and `check_python`; the prose is reached
through the `documentation` group with `scope="code"` (below). All read-tier —
looking something up is free, guessing is expensive. The `program-chisurf`
skill carries the conventions: core stays Qt-free, state goes through the
action layer, every function takes a NumPy-style docstring, a material change
updates its OKF concept.

Having the agent write code is also a good way to find defects in the tools
it writes against: an agent-authored script failed because `auto_fit_decay`
reported `fit` where `create_fit` reports `fit_indices`. Inconsistent result
shapes are invisible in interactive use and fatal in generated code; both now
report both.

# Safety tiers

| Tier | Contains | GUI mode |
| --- | --- | --- |
| `read` | listing files, experiments, datasets, fits, curves, `fit_report` | — |
| `write` | loading data, creating/running/auto-fitting, IRF and component changes, parameters, plots, exports | *ChiSurf tools* |
| `dangerous` | `run_python`, `write_file`, `run_command` | *Full control* (asks per call) |

`run_command` runs any program on the machine, unsandboxed and as the user.
That is deliberate — analysis routinely needs a vendor converter, an archive
tool or somebody else's script, and a sandbox that blocked those would defeat
the purpose. The protection is the confirmation callback: the user sees the
exact command and can refuse it. A short list of indiscriminately destructive
patterns (`rm -rf /`, `mkfs`, `shutdown`, fork bombs) is refused outright,
because a dialog is a poor last line of defence against those and no
legitimate use of them belongs in a fitting assistant.

Destructive operations (clearing the session, removing fits or datasets) are
deliberately **not** in the catalogue.

# Head-less operation

Readers and model classes are registered by the GUI main window, so anything
without it used to see an empty registry.
[`chisurf/core/experiments/bootstrap.py`](/subsystems/data-io.md) performs the
same registration from `experiment_configs.yaml` without building controller
widgets, skipping `QWidget` classes when no `QApplication` exists. The CLI
creates an off-screen `QApplication` by default (`--no-qt` opts out), because
some readers build widgets deep inside `get_data` and Qt aborts the process
rather than raising when none exists.

# Where the sharp edges are

* A newly created fit has the range `(0, 0)` and an empty parameter list;
  `create_fit` therefore applies the reader's `autofitrange` and calls
  `update()` before returning. Without that, the optimiser fails with
  "N must not exceed M" and `get_fit` reports no parameters.
* `create_fit` does **not** optimise. Its result withholds `chi2r` and carries
  a `next_step` telling the model to call `run_fit`, because a model handed a
  starting-value chi-square will report it as a result.
* `Fit.chi2r` is a live property, not a cached number; the agent computes it
  rather than reading the RPC services' cached-only helper.
* Relative paths that repeat the working directory are de-duplicated, and
  "no such directory" errors list what the working directory actually holds.
* `chisurf.macros.model.change_irf` used to attach the IRF and then poke
  `convolve.lineEdit` unconditionally — a *widget* attribute — so it raised
  for every Qt-free model. The presentation write is now guarded.

# Example prompts are the tests

`chisurf/core/agent/examples/prompts.yaml` is one catalogue serving three
consumers: the table in the user guide, the starter menu in the assistant
panel, and the live end-to-end tests. Writing them once is what stops the
three drifting — a documented example that is never exercised rots, and a
test nobody reads teaches nobody.

Each entry carries the sample data it needs, the tools that **must** be used,
the skills its wording must pull in, and the files it should leave behind.
The offline half (catalogue completeness, tools and skills that exist,
routing, buildable scenarios) always runs; the live half is **allowed not to
run** — no key, no network or an exhausted account is a skip, because a
documentation example must never break a build on a machine with no model
configured. What it will not do is pass quietly when the assistant does the
wrong thing.

They pay for themselves: the first live run found three natural phrasings
that reached no skill ("fit **every decay**", "keep it **the same in both**",
"the **zip file**"), and the `save-the-work` example uncovered three separate
defects between the request and a file on disk.

# Testing

`test/agent/` covers the tools against real sample data, the loop against a
scripted model (`ScriptedLLM`), and the client against fake HTTP responses.
`test/agent/test_live_llm.py` runs the whole harness against a real provider;
it is marked `live_llm` and skips unless an API key is configured. The GUI
panel has widget tests in
`chisurf/plugins/core/code_editor/test/test_agent_panel_widget.py`.

The documentation side is tested where retrieval can actually be judged:
`test/agent/test_documentation_tools.py` asserts *which page comes back* for a
question (23 tests, including that the registers never win a search and that a
user's question is never answered from a developer note), and
`chisurf/plugins/core/help/test/test_ask.py` +
`test_ask_panel.py` drive the assistant end to end against a scripted model —
that it holds only the three read-only tools, and that it cites the pages it
read rather than the ones it mentioned.

See also: [API facade](/architecture/api-facade.md),
[Actions](/subsystems/core.md), [Fitting engine](/subsystems/fitting.md).
