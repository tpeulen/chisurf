# 40 — The AI assistant: operating ChiSurf in plain language

ChiSurf ships an assistant that operates the program for you. You describe
what you want in ordinary words — *"fit the decay in this folder and tell me
the lifetime"* — and it loads the data, sets up the fit, runs it, judges the
result and reports the numbers.

It is not a chatbot bolted onto the side: it drives the same session you are
looking at, so anything it creates appears in your windows and is saved in
your project.

## Setting it up

The assistant talks to a language-model provider over an OpenAI-compatible
API. Configure one in **Settings → AI**: a provider, a model, and an API key.

| Provider | Base URL | Processing location | Key from |
| --- | --- | --- | --- |
| Mistral | `https://api.mistral.ai/v1` | EU (France) | console.mistral.ai |
| Local (Ollama, LM Studio) | `http://localhost:11434/v1` | your machine | no key needed |
| OpenAI | `https://api.openai.com/v1` | US (unless zero-retention/EU terms) | platform.openai.com/api-keys |
| OpenRouter | `https://openrouter.ai/api/v1` | routes to many, varies per model | openrouter.ai/keys |

A key can also come from the environment. ChiSurf accepts the usual spellings,
so `MISTRAL_API_KEY`, `MISTRAL_KEY`, `MISTRAL_API_TOKEN` and `MISTRAL_TOKEN`
all work (and likewise for the other providers).

Any model with tool-calling support works; models without it fall back to a
text protocol and are noticeably less reliable. Good starting points are
`mistral-small-latest`, `gpt-4o-mini`, or a local `llama3.2`.

## Using it in the GUI

The assistant lives in the **AI Assistant** panel of the code editor
(`Tools → Miscellaneous → Code Editor`, then the robot button). The selector
in its header decides how much it may touch:

| Mode | What it can do |
| --- | --- |
| 💬 Chat only | Answers and writes code into the editor. Touches nothing. |
| 🔧 ChiSurf tools | Loads data, creates and runs fits, edits parameters, exports results. Stays inside ChiSurf. |
| 🤖 Full control | Also runs Python inside the session, writes files, and **runs programs on your computer** — asking you before each. |

**Full control means what it says.** In that mode the assistant can run any
program you can: unpack an archive, call a vendor converter, drive another
analysis tool, move results into place. It runs as you, with your
permissions, and is not sandboxed — a sandbox would block the converter you
asked it to run. What protects you is that **you see each command before it
runs and can refuse it**. A handful of indiscriminately destructive commands
(`rm -rf /`, `mkfs`, `shutdown`, fork bombs) are refused outright rather than
offered for confirmation.

Use *ChiSurf tools* for ordinary analysis; switch to *Full control* when the
job genuinely reaches outside the program.

The transcript shows every tool call, the skill it is following, and the
reduced chi-square as fits complete, so you can see what it did rather than
having to trust it.

## Using it from a terminal

```bash
python -m chisurf.core.agent "fit every decay in ./data and export a csv"
python -m chisurf.core.agent --interactive -C ~/measurements
python -m chisurf.core.agent --list-tools
python -m chisurf.core.agent --list-skills
```

Useful flags: `-C/--directory` sets what relative paths mean, `--safety
read|write|dangerous` caps what it may do, `--yes` approves dangerous actions
without prompting, and `--json` prints a machine-readable result.

## Skills: how it knows *how*

The assistant carries **skills** — written procedures for particular kinds of
work. Skills matching your request are loaded automatically before the model
even sees it, so the right method is in play from the first turn.

| Skill | Loaded when you ask about |
| --- | --- |
| `fit-decay` | decays, lifetimes, TCSPC, IRFs |
| `fit-correlation` | FCS, correlation curves, diffusion |
| `batch-fitting` | a whole folder, a series, comparing samples |
| `diagnose-fit` | a bad chi-square, structured residuals, a stuck parameter |
| `explore-data` | what is in a folder, what is loaded |
| `report-results` | exporting, saving, plotting, writing up |
| `write-analysis-script` | custom calculations and scripts |
| `use-the-computer` | unpacking, converting, running other software |

`python -m chisurf.core.agent --list-skills` prints them with the phrases that
trigger each one.

### Writing your own

A skill is a `SKILL.md` file with frontmatter, placed in
`~/.chisurf/agent_skills/<name>/SKILL.md`:

```markdown
---
name: fit-my-assay
description: Fit the standard plate assay. Use when the user mentions the assay.
triggers: [assay, plate, standard measurement]
experiments: [TCSPC]
tools: [load_data, create_fit, set_irf, run_fit]
---

# The lab's standard assay

1. Load the decay and the IRF measured the same day.
2. Fit with two lifetimes; the short one is fixed to 0.35 ns.
3. Report the amplitude ratio, not the lifetimes.
```

Give it the same `name` as a built-in skill and yours replaces it. A plugin
can ship skills the same way, in an `agent_skills/` directory next to its
`manifest.json`.

## What it is good at, and what to check

It is reliable at the mechanical parts: finding files, pairing a decay with
its IRF, applying the same model to twenty measurements, exporting a table,
and following the standard fitting protocol. On a sample donor decay it
reaches a reduced chi-square of 1.03 with three lifetime components,
unassisted.

Check its work as you would a student's:

* **The pairing.** If several IRFs are present it says which one it used —
  make sure that is the one you meant.
* **The number of components.** More components always fit better. Ask whether
  the extra one is physically justified.
* **The fit range.** Narrowing the range hides disagreement.
* **Anything it says it assumed.** It is instructed to state assumptions; read
  them.

It will tell you when a fit is poor rather than dressing it up — but it cannot
know that your IRF was measured with the wrong filter, or that one sample was
mislabelled. Those remain yours.

## What leaves your machine, and where it goes

The assistant sends your request, the system prompt, the loaded skill, and
every tool result to the provider you configured. Tool results are summaries,
not raw data — file names and paths, dataset and model names, fitted
parameters, reduced chi-squares — but `get_curve` sends down-sampled data
points and `run_python` sends whatever your script prints. Measurement files
themselves are never uploaded.

That is still personal or confidential data in many settings, and under the
GDPR the choice of provider is a processing decision you are accountable for:

* **A local model keeps everything on the machine.** Run Ollama or LM Studio
  and select the "Local" provider. Nothing leaves at all, so no transfer,
  no processor agreement, no residency question. This is the right default
  for unpublished or human-subject data.
* **Mistral processes in the EU**, which keeps the data inside the EEA and
  avoids a third-country transfer. It is the straightforward choice for an
  EU-based lab that wants a hosted model.
* **US-hosted providers** mean a third-country transfer. That is workable
  under the EU–US Data Privacy Framework or standard contractual clauses, but
  it is a decision to make deliberately — and check whether your institution
  already has a position on it.
* **OpenRouter routes to whichever provider serves the model**, so the
  processing location depends on the model and can change. Prefer a named
  provider when residency matters.

Whatever you choose, check your provider's retention and training terms: a
default consumer plan may retain prompts and use them for training, while
business terms typically do not. None of this is legal advice — if your data
is sensitive, the local model removes the question entirely.
