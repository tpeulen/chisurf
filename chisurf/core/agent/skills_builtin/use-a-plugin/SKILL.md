---
name: use-a-plugin
description: >-
  Find the ChiSurf plugin that already does a job, work out how to call it, and
  drive it head-lessly. Use when a request needs a calculation ChiSurf ships as
  a tool — a calculator, a converter, a simulator, an image or burst analysis —
  rather than something the fitting tools cover.
triggers:
  - plugin
  - calculator
  - is there a tool
  - does chisurf have
  - which tool
  - simulator
  - simulate
  - converter
  - convert
  - estimator
  - what can chisurf do
experiments: []
tools:
  - list_plugins
  - search_api
  - read_api_source
  - read_documentation
  - search_documentation
  - browse_documentation
  - run_python
---

# Using what ChiSurf already ships

ChiSurf carries about a hundred plugins: calculators, simulators, converters,
image and burst analyses. Most jobs that are not "fit this curve" already have
one, and using it beats writing the arithmetic again — it is the version the
user's colleagues use, and it has been checked against real data.

## 1. Find it

```python
list_plugins(query="kappa")      # matches names, descriptions and RPC methods
```

Search the **word the user used**. Method names are searched too, which
matters because a plugin's description often does not contain the term: the
orientation-factor calculator says nothing about "kappa", but registers
`kappa2_dist.compute`.

With no query you get all of them. Each entry says how it can be driven:

* `rpc_methods` — what it registers on the server, with a one-line summary,
* `cli` — a command line,
* `python_packages` — `api` and/or `core`, the importable implementation.

## 2. Work out how to call it

**The manifest usually does not carry the arguments** (`params_schema` is
frequently empty), so do not guess them. The implementation has them, with a
docstring:

```python
search_api(query="compute_kappa2_dist")      # find the function
read_api_source(qualname="...")              # read its parameters
```

A plugin's RPC handler is nearly always a thin wrapper: `<name>.compute` →
`register_services` in `backend/services.py` → a real function in
`core/algorithms.py`. Read that function; its signature and docstring are the
contract.

## 3. Call it

In-process, through `run_python`, is the shortest path and gives you the
result as Python objects:

```python
from chisurf.plugins.calculator.kappa2_dist.core.algorithms import compute_kappa2_dist

result = compute_kappa2_dist(model_type="cone", r_0=0.38, r_Dinf=0.045)
```

The RPC name exists for clients talking to the server; in the session, call the
function. If a plugin only offers a command line, run it with
`run_command` and pass `--help` first — its options are the contract there.

## 4. Check the result before using it

A plugin is not a black box you are entitled to trust. Give it a case whose
answer you already know and see whether it agrees:

* an orientation-factor distribution must average 2/3,
* a FRET efficiency of 0 must give an infinite distance, and R = R0 must give
  E = 0.5,
* a converter run forwards then backwards must return the input.

This costs one extra call and catches both a plugin that is broken and — more
often — arguments you have misunderstood. Two real defects in the κ²
calculator were found exactly this way, by a mean that came out at 0.71 where
2/3 was the only possible answer.

## What to say

Name the plugin you used and the arguments you passed, and quote the check you
made. "I used the κ² distribution calculator (`kappa2_dist`, wobbling-in-a-cone
model) with r_Dinf = 0.045" is reproducible; "I calculated κ²" is not.

If no plugin fits, say so and do the calculation directly rather than bending
one that nearly fits — a tool used outside its assumptions gives a confident
number with nothing behind it.
