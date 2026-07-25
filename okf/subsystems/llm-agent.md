---
type: Subsystem
title: LLM agent
description: The plain-language assistant that operates ChiSurf through a described, safety-tiered tool catalogue.
resource: chisurf/core/agent/
tags: [agent, llm, tools, automation, assistant]
timestamp: '2026-07-25T00:00:00Z'
---

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
* `tools/` — the catalogue: `data.py` (find files, load them, describe
  experiments/readers/models), `fitting.py` (create, run, inspect, edit,
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

A **failing tool does not end the run** — its error goes back to the model,
which corrects itself. Only *repeated identical* failures stop the loop; that
is the difference between an assistant that recovers and one that gives up.

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

The built-in library: `fit-decay`, `fit-correlation`, `batch-fitting`,
`diagnose-fit`, `explore-data`, `report-results`, `write-analysis-script`.
Discovery layers built-in → plugin (`agent_skills/` beside a `manifest.json`)
→ user (`<settings>/agent_skills/`), later overriding earlier, so a lab can
replace `fit-decay` with its own protocol without touching the code.

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

# Safety tiers

| Tier | Contains | GUI mode |
| --- | --- | --- |
| `read` | listing files, experiments, datasets, fits, curves, `fit_report` | — |
| `write` | loading data, creating/running/auto-fitting, IRF and component changes, parameters, plots, exports | *ChiSurf tools* |
| `dangerous` | `run_python`, `write_file` | *Full control* (asks per call) |

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

# Testing

`test/agent/` covers the tools against real sample data, the loop against a
scripted model (`ScriptedLLM`), and the client against fake HTTP responses.
`test/agent/test_live_llm.py` runs the whole harness against a real provider;
it is marked `live_llm` and skips unless an API key is configured. The GUI
panel has widget tests in
`chisurf/plugins/core/code_editor/test/test_agent_panel_widget.py`.

See also: [API facade](/architecture/api-facade.md),
[Actions](/subsystems/core.md), [Fitting engine](/subsystems/fitting.md).
