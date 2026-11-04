---
name: grill-the-user
description: >-
  Interview the user about the choices that change the result before starting
  an analysis: files, gates, models and number of components, correction
  factors, background, and what output they want. Use whenever a request
  starts an analysis, fit or processing run; never for a purely informational
  question. Loaded by the runtime while grilling is on.
triggers:
  - grill me
  - interview me
  - ask me first
  - clarifying questions
tools:
  - ask_user
  - describe_session
  - list_files
---

# Settle the decisions before the analysis

A result is only as good as the choices it was computed with, and those are
the user's. Interview them first — briefly, concretely — then do the work.

## The procedure

1. **Look first.** Find out what the tools can tell you on their own:
   `describe_session`, `list_files`. Never ask what a tool can answer.
2. **List the decisions that change the result** and are not settled by the
   request or by what you remember about this user:
   - which **files** or folder, which **datasets** (and the reference
     measurements: IRF, donor-only, buffer);
   - which **gate** or selection (species, stoichiometry/FRET window, time
     window, channels);
   - which **model** and how many **components** (lifetimes, Gaussians,
     diffusion species);
   - which **correction factors** (gamma, leakage, direct excitation, Förster
     radius R0) and the **background** model;
   - what **output** they want (numbers, plots, a fit saved, a file exported).
3. **Ask with `ask_user`**: one question per open decision, each with concrete
   options (values with units) and your recommended `default`. Ask only what
   is open — a request that already says "two components, R0 = 52 Å" has
   settled those.
4. **Read the answers and go on grilling only what is still open** — a choice
   an answer opened up (a second gate, a model the answer named). At most
   three rounds per request; then act on the best-supported choice.
5. **Then act**, and state the choices you used in the answer.

## When not to grill

A question about the session or the program ("what is loaded?", "explain the
gamma factor", "which models exist?") is answered directly. So is a request
that leaves nothing open, and a follow-up in a thread whose decisions are
already settled ("now export that").
