---
name: answer-from-docs
description: >-
  Answer a question about what ChiSurf does, what a method means, or how to
  carry out a workflow, out of ChiSurf's own documentation — and cite the page.
  Use when the user is asking rather than instructing: "what is", "how do I",
  "why does", "where do I find", "which tool", "what does this setting do".
triggers:
  - what is
  - what does
  - how do i
  - how can i
  - how does
  - why does
  - why is
  - where is
  - where do i
  - explain
  - documentation
  - manual
  - help
  - guide
  - tell me about
  - what setting
  - which page
experiments: []
tools:
  - browse_documentation
  - search_documentation
  - read_documentation
---

# Answering out of the documentation

A question about fluorescence analysis is one you can answer from memory, and
that is exactly the failure this skill exists to prevent. What the user wants
is not *an* answer — it is **what ChiSurf does**: which tool, which control,
which convention, which of two spellings of a symbol this program uses. Your
memory of the literature does not know that, and a plausible answer that does
not match the program is worse than no answer, because the user will go
looking for a button that is not there.

So: **every claim about ChiSurf comes from a page, and you say which page.**

## The procedure

1. **`browse_documentation`** first, filtered by subject.

   The documentation carries a machine-readable header on every page — its
   kind, its title, a one-line description, its subject tags — and browsing
   that header is one call that shows you the whole shelf. It beats searching
   for words, because the page rarely uses the user's words: someone asks
   about "brightness per molecule" and the page says *counts per molecule*.

   Pick by **kind**, because the kind *is* the sort of answer:

   | The user asks | Read a |
   | --- | --- |
   | what does this mean / why does it work | `Concept` — the theory, with the formulas and the citations |
   | how do I do it in ChiSurf | `Guide` — the step-by-step, with the real screenshots |
   | what is the underlying physics | `Fundamentals` |
   | what does this control do | `Plugin Reference` — every parameter of one tool |
   | can ChiSurf read my file | `File Format` |
   | where does this number come from in the code | `scope="code"` — but only if they asked about the code |

2. **`search_documentation`** when browsing did not obviously contain it, or
   when the user used a term you want to look up literally.

3. **`read_documentation`** the page you chose. Pass a `section` when the
   question is about one heading — a reference page runs to hundreds of lines
   and pulling in all of it buys nothing. `outline_only` first if you are not
   sure which heading.

4. **Answer from what you read**, and end with the page:

   > …the γ factor corrects for the different detection efficiencies and
   > quantum yields of donor and acceptor.
   > — *Accurate FRET* (`docs/concepts/accurate_fret.md`)

   The `related` list in the result is how you find the guide that goes with a
   concept. A "what does it mean" question is usually followed by "so how do I
   do it": naming the matching guide saves the round trip.

## Rules

* **Never invent a control, a menu path, a file name or a parameter.** If the
  documentation does not say it, say that it does not, and name the closest
  page you did find. "The guides do not cover this; the nearest is X" is a
  useful answer. A confident wrong menu path is not.
* **Do not answer a usage question from a developer page.** `scope="code"`
  reaches notes about ChiSurf's own source — migrations, architecture, PRDs.
  They describe how the program is built, often describe how it *will* be
  built, and are the wrong source for someone who wants to use it. Use them
  only when the question is explicitly about the code.
* **Prefer the guide to your own instructions.** If a guide gives the
  procedure, point the user at it and summarise it, rather than writing a
  different procedure of your own that has never been checked.
* **Quote the program's spelling.** If the page writes ρ and the user wrote θ,
  answer in the page's notation and note the equivalence once. The user has to
  find the control by its label.
* **You may act as well as answer.** If the user asks how to do something and
  then asks you to do it, the operating tools are still there — but the
  procedure you follow is the one the guide gives.
