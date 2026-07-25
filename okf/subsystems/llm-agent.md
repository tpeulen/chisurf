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
* `context.py` — `AgentContext`: working directory, code-execution policy,
  confirmation and event callbacks, and the resolution of loose references
  ("the second fit", a file name, an index) to real session objects.
* `tools/` — the catalogue: `data.py` (find files, load them, describe
  experiments/readers/models), `fitting.py` (create, run, inspect, edit,
  export), `scripting.py` (`run_python` in the live session, read/write
  files), `_dto.py` (compact summaries sized for a context window).
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

# Safety tiers

| Tier | Contains | GUI mode |
| --- | --- | --- |
| `read` | listing files, experiments, datasets, fits, curves | — |
| `write` | loading data, creating and running fits, editing parameters, exporting | *ChiSurf tools* |
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

# Testing

`test/agent/` covers the tools against real sample data, the loop against a
scripted model (`ScriptedLLM`), and the client against fake HTTP responses.
`test/agent/test_live_llm.py` runs the whole harness against a real provider;
it is marked `live_llm` and skips unless an API key is configured. The GUI
panel has widget tests in
`chisurf/plugins/core/code_editor/test/test_agent_panel_widget.py`.

See also: [API facade](/architecture/api-facade.md),
[Actions](/subsystems/core.md), [Fitting engine](/subsystems/fitting.md).
