---
type: Concept
title: The workflow agent — driving ChiSurf in plain words
description: How the agent turns a request into tool calls on the live session, when it asks instead of guessing, what each safety tier allows, where provider keys live, the burst-to-distance tool chain, the MCP/ACP surfaces and the user's knowledge bundle.
tags: [concepts, agent, assistant, burst, smfret]
---

# The workflow agent — driving ChiSurf in plain words

The agent is a language model given ChiSurf's analysis functions as **tools**. The
model reads the request, picks a tool, gets the result back as JSON, and repeats
until it can answer. It never computes a number itself: every burst count, fit
parameter and χ²ᵣ in its answer comes from a tool that ran ChiSurf's own code on
the session the user sees. The **Agent** plugin (`chisurf/plugins/core/agent/`,
Tools menu) opens the same assistant panel the code editor hosts
(`chisurf/plugins/core/code_editor/gui/chat_app.py`); the runtime is
`chisurf/core/agent/`. Workflow: {doc}`../guides/40_ai_assistant`.

## The loop

`AgentSession.ask` (`chisurf/core/agent/runtime.py`) sends the conversation and the
tool catalogue to the provider, executes the tool calls of the reply in order,
appends their results, and asks again. It stops when the model answers in text
(`stop_reason = "answer"`) or on a limit: `max_steps` model turns,
`max_tool_calls`, a time budget, or `max_consecutive_failures` failed calls in a
row (`"repeated_failures"`). A failed tool returns its error text to the model,
which can correct the call; it is not an exception for the user.

Tool calls are native function calls when the model supports them; otherwise a
text protocol carries the same calls, less reliably.

## The tool registry

`build_default_registry()` (`chisurf/core/agent/tools/__init__.py`) merges the tool
groups: data, burst, clarify, codebase, documentation, fitting, decay, linking,
scripting, skills and system. Each tool is a `ToolSpec` with a JSON schema and a
**safety tier**:

| Tier | Tools (examples) | Effect |
| --- | --- | --- |
| `read` | `list_files`, `describe_session`, `detect_smfret`, `inspect_bursts`, `fit_report`, `search_api`, `ask_user`, `record_finding`, `save_skill` | Looks; writes only to the user's own knowledge bundle and skills folder. |
| `write` | `load_data`, `create_fit`, `run_fit`, `set_parameter`, `link_parameters`, `run_burst_analysis`, `select_species`, `extract_subensemble_decay`, `fit_distance_distribution`, `export_fit_results`, `save_project` | Changes the session and writes results beside the data. |
| `dangerous` | `run_python`, `run_command`, `write_file` | Runs code or programs as the user. |

`AgentConfig.max_safety` caps the tier; tools above it are not offered to the model
at all. The panel's modes map onto it: *Chat only* → no tools, *ChiSurf tools* →
`write`, *Full control* → `dangerous`. In *Full control* every dangerous call goes
through `AgentContext.confirm`, the panel's Allow/Deny banner; a short list of
indiscriminately destructive commands is refused outright. The command line
defaults to `--safety dangerous` and asks on the terminal unless `-y` is given.

`list_tools` / `python -m chisurf.core.agent --list-tools` prints the catalogue.

## The clarification round

Some requests cannot be run without choices only the user can make — which file
"the data in xy" is, the Förster radius, the donor-only lifetime, how many
components. The model then calls `ask_user` (`chisurf/core/agent/tools/clarify.py`)
with at most five structured questions, each with optional `options` and a
`default`. The run stops with `stop_reason = "needs_input"` and the questions in
`AgentResult.clarifications`; nothing else has run. The rendered questions are
the run's `text` (`render_questions`): the panel shows them as the assistant's
message, the command line prints them. The user's next message answers them and
the plan resumes in the same conversation (the panel keeps its `AgentSession`
between messages).

One request gets **one** round: a second `ask_user` before the request is answered
is refused, and the refusal tells the model to proceed with the best-supported
choice and state it. An agent that keeps asking is as useless as one that guesses.
The rule is in the runtime, so the panel, the command line and the ACP server
behave alike.

## The burst-to-distance chain

`chisurf/core/agent/tools/burst.py` wraps the plugin machinery the GUI buttons call
— no analysis code lives in the tools. State between steps rides the context: each
step caches what the next one picks up and says so in its `next` field.

| Tool | Runs | Reports |
| --- | --- | --- |
| `detect_smfret` | `fret_check` detection on a TTTR file | excitation scheme (cw, PIE, µs-ALEX), donor/acceptor routing channels, micro-time windows, photons per channel, warnings to confirm |
| `run_burst_analysis` | burst search (`min_photons_burst` = 30, `window_ms` = 0.5), apparent E/S, QC; the burst table is written as a run of the measurement's `.pto` | `n_bursts`, E/S distributions, corrected E/S when asked, `factors_used`, `n_flagged_by_qc`, the container path |
| `inspect_bursts` | the cached table | summary statistics, the current selection |
| `select_species` | a range gate on one column (`E`, `S`, `E_corrected`, …) | `n_selected` of `n_total`, the gate |
| `extract_subensemble_decay` | `write_decay_container`: the selected bursts' donor photons pooled into a decay, registered as a dataset | photons, bursts used, bins, container, `dataset_index` |
| `fit_distance_distribution` | the Gaussian distance-distribution TCSPC model (`decay_fit_model.fit_fret_model`); the fit joins the session's fit list | `distances_A`, `sigma_A`, `fractions`, `efficiencies`, `donor_only_fraction`, `chi2_reduced`, `width_mode`, `stated_assumptions` |

**Correction factors.** `run_burst_analysis` takes `factors` (γ, β, α leakage, δ
direct excitation). Missing ones default to the neutral values (γ = β = 1,
α = δ = 0), i.e. no correction for that factor, and `factors_used` reports what was
applied. `auto_calibrate` fills them from the measurement (ALEX/PIE: all four; cw:
leakage from the donor-only bursts); explicit values win.

**Width.** `fit_distance_distribution` fits the distribution width σ by default.
Holding σ biases the mean distance: the model sees the FRET rate averaged over the
distribution, which is steeper than the rate at the mean (simulated E = 0.75,
truth 43.3 Å: held σ = 5 Å gives 39.7 Å, fitted σ gives 42.9–44.7 Å). The fit
window starts at the decay maximum, because the amplitude model is not convolved
with the instrument response.

**Validated on.** Simulated cw and PIE measurements (`fret_check.sim`). On PIE the
S gate removes acceptor-only molecules an E-only gate keeps, and the chain recovers
40.8 Å against a 43.3 Å truth: the ~6 % is the donor micro-time window truncating
the decay under the un-convolved model. A window-aware or IRF-convolved fit would
close it; until then, read PIE distances with that bias in mind.

## Providers and keys

The model is reached over an OpenAI-compatible HTTP API
(`chisurf/core/agent/llm.py`). Providers are declared in
`chisurf/core/settings/ai_settings.py`, ordered by where the data is processed:
Mistral (EU, the default), Local (Ollama, LM Studio), OpenAI, OpenRouter, Z.ai
(GLM, `glm-5.3-flash` by default), an ACP agent over stdio, and any custom
OpenAI-compatible endpoint.

A key comes from the AI settings store (`ai_api_settings.json` in the ChiSurf
settings folder, written through **AI Settings**) or, when that is empty, from the
environment: the provider's declared variable (`MISTRAL_API_KEY`, `ZAI_API_KEY`,
…) and its usual spellings (`provider_key_env_names`). Keys are never written into
projects, skills, the knowledge bundle or source. Tests that would reach a paid
endpoint run only with `CHISURF_AGENT_TEST_LIVE=1` set; a key alone does not arm
them.

## Surfaces

| Surface | Start | Serves |
| --- | --- | --- |
| Panel | Tools → **Agent**, or the code editor's 🤖 panel | the live session, mode-capped |
| Command line | `python -m chisurf.core.agent "…"`, `-i` for a conversation | the full registry up to `--safety` |
| ACP server | `python -m chisurf.core.agent --acp` (`acp_server.py`) | Agent Client Protocol over stdio for editors (Zed, JetBrains, VS Code, ChiSurf's code editor); modes `chat_only` / `chisurf_tools` / `full_control` |
| MCP server | `python -m chisurf.core.agent.mcp_server` | every `read`/`write` tool as an MCP tool for an external chat client; the client's own model drives ChiSurf |

The MCP server also turns the RPC methods declared in plugin manifests into tools
(`register_manifest_rpc_tools`). They are born in the `dangerous` tier and only an
allowlist is moved to `write` and served. Its stdout carries the protocol and
nothing else; import-time messages go to stderr.

## Skills and memory

**Skills** are `SKILL.md` procedures (frontmatter `name`, `description`,
`triggers`, optional `uses`) loaded automatically when a request matches
(`chisurf/core/agent/skills.py`). Built-ins ship in
`chisurf/core/agent/skills_builtin/`; the user's own in `agent_skills/` in the
settings folder override built-ins of the same name.

The agent's memory of the user is a standard OKF bundle in `~/.chisurf/okf/`
(`chisurf/core/agent/user_okf.py`): `index.md`, a dated `log.md`, one page per
topic under `concepts/`. Two tools write it — `record_finding` (a durable
conclusion: chosen parameters, a data quirk, a recipe) and `save_skill` (a
procedure or preference, saved as the user's skill so later sessions load it). The
bundle lives beside the user's files, not in the application, and any client that
reads OKF can use it.

## Limits

* The model chooses the tools; the tools compute the numbers. A wrong choice — the
  wrong IRF, too many components, a gate that cuts a species — gives a correct
  computation of the wrong analysis. The transcript shows every call and its
  arguments so it can be checked.
* PIE distances carry the ~6 % window-truncation bias described above.
* The chain covers one measurement at a time; a new path replaces the cached
  analysis.
* Tool results (paths, names, fitted values, down-sampled curves, whatever
  `run_python` prints) go to the configured provider. Measurement files are not
  uploaded. A local provider keeps everything on the machine.
