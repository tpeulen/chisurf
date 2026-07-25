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

## Things to ask it

Every prompt below is shipped with ChiSurf and **run as a test** against a
real model, so none of them is aspirational — see
`python -m chisurf.core.agent --list-examples`, and
`--example <id>` to run one.

| Ask it | What it does |
| --- | --- |
| *“What is in this folder?”* | Lists the files, says what kind of measurement each one is, and points out which are instrument-response references rather than samples — without loading or changing anything. |
| *“What do I have open at the moment?”* | Summarises the datasets and fits in the session, with their indices and reduced chi-squares. |
| *“I measured a fluorescence decay here. Fit it properly and tell me the lifetimes.”* | Loads the decay and its instrument response, attaches the IRF, adds lifetime components until the reduced chi-square stops improving, and reports the lifetimes with uncertainties. Reaches chi2r ~1.03 on the sample data. |
| *“Fit the decay in this folder and make a plot I can look at.”* | As above, and writes a PNG of the data, the fitted curve and the weighted residuals — the picture a reader judges a fit by. |
| *“These are donor-only and donor-acceptor measurements of a labelled sample, each with its own IRF. Work out the FRET efficiency and the distance.”* | Fits the donor-only reference, builds a FRET model on the quenched sample, ties the donor photophysics to the reference, and reports the efficiency, the inter-dye distance and the donor-only fraction with the assumed Foerster radius. Reaches E ~ 0.32 at R ~ 52 A on the sample data. |
| *“Fit every decay in this folder with the same model and give me a csv of the results.”* | Creates one fit per measurement, runs them all, checks each one, and exports a table with every parameter and reduced chi-square. Reference measurements are not fitted as samples. |
| *“Is this fit any good? What would you check?”* | Reports the reduced chi-square, the Durbin-Watson statistic and the parameter uncertainties, and names the most likely cause when something is off — a missing instrument response, too few components, a fit range that includes scattered light. |
| *“Fit this FCS curve and tell me the diffusion time and how many molecules are in the volume.”* | Loads the correlation curve, fits a diffusion model, and reports the particle number and diffusion time — saying which parameters it fixed, because a correlation result is meaningless without that. |
| *“Fit the two decays in this folder and link the long lifetime between them so they share one value. Tell me what that shared value is.”* | Fits each measurement, then links the named lifetime so a single value is determined by both datasets at once, and reruns. Reports what was linked and what the shared value came out as. |
| *“My measurement is in the zip file here. Unpack it somewhere sensible, fit the decay, and leave me a plot.”* | Runs the unpacking outside ChiSurf, then does the analysis inside it — writing into a new directory and leaving the original archive alone. |
| *“Using python, tell me the total number of photons in each loaded measurement.”* | Runs a short script inside the live session — the escape hatch for anything the built-in tools do not do. |
| *“Save all of this so I can carry on tomorrow.”* | Writes the whole session — data, fits and parameters — to a project file that reopens in ChiSurf. |

They are also offered as one-click starters in the assistant panel, so a new
user does not have to guess what the thing can do.

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
python -m chisurf.core.agent --list-examples
python -m chisurf.core.agent --example fit-one-decay -C ./data
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
| `fret-from-decays` | FRET, donor-only/DA pairs, efficiencies, distances |
| `global-fitting` | global or simultaneous analysis, linking parameters |
| `fit-correlation` | FCS, correlation curves, diffusion |
| `batch-fitting` | a whole folder, a series, comparing samples |
| `diagnose-fit` | a bad chi-square, structured residuals, a stuck parameter |
| `explore-data` | what is in a folder, what is loaded |
| `report-results` | exporting, saving, plotting, writing up |
| `write-analysis-script` | custom calculations and scripts |
| `use-the-computer` | unpacking, converting, running other software |
| `estimate-uncertainty` | confidence intervals, error bars, whether a component is justified |
| `program-chisurf` | writing plugins, models or patches to ChiSurf itself |

`python -m chisurf.core.agent --list-skills` prints them with the phrases that
trigger each one.

Behind the skills sits the assistant's own **knowledge base** — a small set of
concepts about fluorescence analysis and about what ChiSurf's objects mean
(`chisurf/core/agent/knowledge_base/`). It is searched alongside the project
documentation, so a skill can stay a short procedure and point at the
background rather than repeat it. It is deliberately separate from the `okf/`
bundle in the repository, which describes how ChiSurf is *built* rather than
what the measurements *mean*.

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

## Asking it to write ChiSurf code

The assistant can also work *on* ChiSurf — a plugin, a fitting model, a
script that uses the API. It does not know the codebase from memory, so it
looks things up instead of guessing: `search_api` gives it the real
signatures and docstrings straight from the source tree, `read_api_source`
the implementation, `search_docs` the architecture concepts and guides, and
`list_plugins` the nearest existing example to follow. `check_python` runs a
syntax and lint check before anything is written to disk.

Asked for *"a standalone script that loads a TCSPC file, fits it with its
IRF, and prints the lifetimes"*, it produces a script that runs and reports
chi2r 1.03 with three lifetimes and their uncertainties.

Code it writes still needs review — it is a competent stranger to your
codebase, not a maintainer of it — but it will be written against the API
that exists.

## What it is good at, and what to check

It is reliable at the mechanical parts: finding files, pairing a decay with
its IRF, applying the same model to twenty measurements, exporting a table,
and following the standard fitting protocol. On a sample donor decay it
reaches a reduced chi-square of 1.03 with three lifetime components,
unassisted.

It also handles the multi-step analyses ChiSurf exists for. Asked only *"these
are donor-only and donor-acceptor measurements, work out the FRET efficiency
and the distance"*, it fits the donor reference, builds a Gaussian-distance
FRET model on the acceptor sample, **links the donor lifetimes across the two
fits**, and reports E = 0.32 ± 0.01 at R = 52 Å with the assumed Förster
radius stated — reduced chi-square 1.09.

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
