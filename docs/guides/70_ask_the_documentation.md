---
type: Guide
title: Asking the documentation
description: Putting a question to ChiSurf's documentation in plain words and getting an answer with the pages it came from, in the help browser or from the command line.
tags: [guides, documentation]
anchor: guide-ask-the-documentation
---

(guide-ask-the-documentation)=
# Asking the documentation

**What you get:** an answer to *"what does this actually do?"* in plain words,
together with the pages it was taken from — and one click from the answer to
the page, so you can read the rest of it.

**What you need:** a language-model provider configured in **Settings → AI**.
The same one the {ref}`assistant that operates ChiSurf <guide-ai-assistant>`
uses; if you already set that up there is nothing more to do.

## When you need it

The tree and the search box in the help browser both assume you know roughly
where the answer lives. Quite often you do not:

* you know the *symptom* — "my FRET efficiencies are above one" — not the page;
* you know the *word from the paper*, and the documentation uses another one;
* you want to know whether ChiSurf can do a thing at all, which is a question
  about a hundred plugin pages at once.

Search cannot help with any of those, because it matches the words you typed.

## Asking

In the help browser (**Help → Documentation**, or `F1`), press **💬 Ask** on
the toolbar — or `Ctrl+Shift+A`. A third column opens beside the page you are
reading. Type the question and press Enter.

```{figure} figures/ask_the_documentation.png
:name: fig-ask-the-documentation
:width: 100%

The Ask panel beside the page it cited. The links in the answer's own prose go
to the page — and to the heading on it — and the list underneath is what the
assistant actually opened.
```

**The answer itself is linked.** Where it names a page — or a heading on one —
that is a link: click it and the viewer on the left opens there, at the
section, not at the top. The list underneath is **the pages it read**, and it
is not the assistant's own footnote: it is recorded from what it opened, so a
page in that list is a page it saw.

Two warnings can appear under an answer, and both are worth reading:

*No documentation page was opened for this answer.*
: It answered from itself rather than from the documentation. Treat it as a
  suggestion and check it.

*It also named a page that does not exist.*
: It wrote itself a citation. Every path in an answer is resolved before you
  see it, and one that goes nowhere is struck out and reported — but a model
  that invented a citation may have invented the rest, so check the whole
  answer.

The panel keeps the conversation, so a follow-up (*"and where do I set it?"*)
is understood in the context of the previous answer. **🗑** clears it.

## What it can and cannot do

It has three tools and no others: browse the documentation, search it, read a
page. It **cannot** load your data, run a fit, execute Python or write a file,
and that is enforced by what it is given rather than by what it is told. If
you want the program *operated* rather than *explained*, that is the
{ref}`AI assistant <guide-ai-assistant>`, which is the same model with the
analysis tools attached.

It answers from ChiSurf's documentation and, deliberately, not from its own
knowledge of the literature: a plausible answer that does not match this
program is worse than no answer, because you will go looking for a control
that is not there. When the documentation does not cover something it says so
and names the nearest page.

The answer is Markdown, and it is rendered: **bold**, lists, tables, `code`
and — the part that matters here — mathematics. An answer that quotes the
Rehm–Weller equation shows it typeset, in the same face as the pages beside it,
not as `$\Delta G = \ldots$`.

## Which model

The assistant uses whatever is configured in **Settings → AI**; a fresh install
is on **Mistral**, which processes in the EU, with `mistral-large-latest`.

The model size shows on exactly one thing: whether it goes and *reads*. Asked
a two-word question with a misspelled name — *"rhem weller?"* — a smaller model
searched, missed, and told the user their term did not exist, explaining a
different subject instead; the large model finds
{doc}`Quenching mechanisms in detail </fundamentals/quenching_mechanisms>` and
answers from it. Over thirteen deliberately awkward queries (bare nouns,
acronyms, misspellings, and one thing ChiSurf cannot do at all) every one was
answered from a page that had been opened.

Any model with tool calling works, and a local one keeps everything on your
machine. Without tool calling the answer falls back to a text protocol and is
markedly less reliable — the tool calls are what make it read.

## From the command line

The same question, without a window:

```bash
csc help ask "what does the gamma correction factor do?"
```

```text
The gamma factor corrects the raw green/red photon ratio for the detection
efficiencies of the two channels and the fluorescence quantum yields of the
two dyes…

Sources:
  Accurate FRET: correction factors, FRET lines, and where they come from — docs/concepts/accurate_fret.md
  Accurate FRET corrections — docs/guides/41_accurate_fret.md
```

`--json` prints the answer, the pages and the queries as a structure, which is
what to use from a script. `--model` and `--provider` override the configured
ones for one question.

## From Python

```python
from chisurf.plugins.core.help.api import ask

answer = ask.ask("which tool fuses bursts that one molecule produced?")
print(answer.text)
for page in answer.pages:
    print(page["title"], page["document"])
```

Over the plugin's RPC surface the same call is `help.docs.ask`, so a remote
client gets the finished answer without a model of its own.

## Why it finds the right page

Every documentation page carries a short machine-readable header — what kind
of page it is (`Concept`, `Guide`, `Plugin Reference`, `Fundamentals`, `File
Format`), its title, a one-sentence description, and subject tags. The header
never appears in the rendered page; it exists so the assistant can *choose*
before it reads.

That is what lets it route a question by shape rather than by vocabulary: "what
does X mean" goes to a `Concept`, "how do I X" to a `Guide`, "what does this
control do" to the plugin's reference page. The subject tags cross the folders,
so a question about FRET reaches the concept, the guides and the plugin pages
in one step.

If you are writing documentation, the header is generated and checked — see
{doc}`/development/documentation_maintenance`.

## If it will not answer

| It says | What to do |
| --- | --- |
| *no AI provider is configured* | Set one in **Settings → AI**. A local provider (Ollama, LM Studio) needs no key. |
| *no API key for …* | The provider needs one; paste it in **Settings → AI**, or export the usual environment variable (`MISTRAL_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`). |
| *the API key … was rejected* | The key is wrong or expired. |
| *lack of credit* | The account has run out, or `max_tokens` in **Settings → AI** reserves more than it can afford. |
| *the documentation has nothing on …* | It is telling the truth. Try the words the pages use, or browse the tree. |
| *No documentation page was opened* | It answered from itself. Ask again more specifically, or search the tree yourself — the answer is not grounded. |

## See also

* {ref}`The AI assistant <guide-ai-assistant>` — the same model with the tools
  to load data, fit and report.
* {doc}`Driving ChiSurf from its console <59_console>` — when you would rather
  write the Python yourself.
