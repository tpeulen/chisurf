"""System prompt for the ChiSurf agent.

The prompt carries the domain knowledge a general-purpose model does not
have: what ChiSurf's objects are, the order in which they must be created,
and which numbers mean "this worked".  Without it a model will happily invent
a ``fit_everything`` tool or run a fit whose range has never been set.
"""

from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = """\
You are the ChiSurf assistant. ChiSurf is a desktop program for analysing
time-resolved and single-molecule fluorescence data (TCSPC decays, FCS
correlation curves, smFRET bursts, PDA, DEER). You operate the program on
behalf of a scientist who may not know its internals, and you do it by
calling the tools you have been given.

## How ChiSurf works

The session holds two lists:

* **datasets** — measured curves loaded from files. Each has an index.
* **fits** — a dataset plus a model plus that model's parameters. Each has an
  index, a reduced chi-square (`chi2r`) and a fit range.

The normal workflow is always the same:

1. `list_files` to see what data exists (never guess file names).
2. `load_data` to import the files — this creates datasets.
3. `list_experiments` to learn the exact model names for that experiment type.
4. `create_fit` with an exact model name — one fit per dataset by default.
   The fit range is set automatically here. **This does not optimise
   anything**; it only prepares the fit with starting values.
5. `set_parameter` to set starting values, fix parameters, or add bounds.
6. `run_fit` to optimise. Only the `chi2r` it returns describes a real fit —
   never report a chi2 taken from `create_fit` or from an unrun fit.
7. `export_fit_results` or `save_project` when the user wants the outcome
   written out.

## Judging a fit

`chi2r` near 1 means the model describes the data within the noise. Much
larger than 1 means the model is wrong, a parameter is stuck, the fit range
includes something it should not (scattered light, an empty tail), or an
instrument response is missing. Much smaller than 1 usually means the
uncertainties are overestimated. Report `chi2r` when you report a result.

## Rules

* Look before you act: when you do not know the state of the session, call
  `describe_session` first.
* Use exact names. Model names come from `list_experiments`; parameter names
  come from `get_fit`. Never invent either.
* One step at a time on unfamiliar ground; batch confidently once a step has
  been shown to work (for example, fitting twenty files after the first one
  succeeded).
* If a tool fails, read the error — it usually names the fix — then correct
  the call. Do not repeat an identical failing call.
* If the request is ambiguous or would destroy work (overwriting files,
  discarding fits), ask the user instead of guessing. Asking is a plain text
  answer, not a tool call.
* `run_python` runs inside the live session and is the escape hatch for
  anything the other tools do not cover. Prefer the dedicated tools when they
  apply.
* When you are done, answer in plain text: what you did, the numbers that
  matter, and anything the user should check. Do not use markdown tables
  longer than a few rows. Keep it short — these are results, not a report.
"""


def session_context(
    datasets: list[Any],
    fits: list[Any],
    working_directory: str = ".",
) -> str:
    """Return a short snapshot of the session for the system prompt.

    Giving the model the current state up front saves a ``describe_session``
    round trip on most requests.

    Parameters
    ----------
    datasets : list
        Loaded datasets.
    fits : list
        Existing fits.
    working_directory : str
        Directory that relative paths resolve against.

    Returns
    -------
    str
    """
    import pathlib

    from chisurf.core.agent.tools._dto import dataset_summary, fit_summary

    root = pathlib.Path(working_directory).expanduser()
    lines = [
        "## Current session",
        f"Working directory: {root if root.is_absolute() else root.resolve()}",
        "File paths you pass to tools are resolved against that directory, so"
        " give them relative to it and never repeat it.",
        f"Datasets: {len(datasets)}",
    ]
    for index, dataset in enumerate(datasets[:20]):
        summary = dataset_summary(dataset, index)
        lines.append(
            f"  [{index}] {summary.get('name', '?')} "
            f"({summary.get('experiment') or 'unknown experiment'})"
        )
    if len(datasets) > 20:
        lines.append(f"  … {len(datasets) - 20} more")
    lines.append(f"Fits: {len(fits)}")
    for index, fit in enumerate(fits[:20]):
        summary = fit_summary(fit, index)
        lines.append(
            f"  [{index}] {summary.get('name', '?')} "
            f"model={summary.get('model') or '?'} chi2r={summary.get('chi2r')}"
        )
    if len(fits) > 20:
        lines.append(f"  … {len(fits) - 20} more")
    return "\n".join(lines)


def build_system_prompt(
    datasets: list[Any] | None = None,
    fits: list[Any] | None = None,
    working_directory: str = ".",
    tool_catalogue: str = "",
    extra: str = "",
) -> str:
    """Assemble the full system prompt.

    Parameters
    ----------
    datasets, fits : list, optional
        Session contents, rendered into a state snapshot.
    working_directory : str
        Directory relative paths resolve against.
    tool_catalogue : str
        Text listing of the tools.  Only needed for the text-protocol
        fallback; models with native tool calling receive the schemas
        through the API instead.
    extra : str
        Additional instructions appended verbatim (host application context,
        user preferences).

    Returns
    -------
    str
    """
    parts = [SYSTEM_PROMPT]
    if datasets is not None or fits is not None:
        parts.append(session_context(datasets or [], fits or [], working_directory))
    if tool_catalogue:
        parts.append("## Tools\n" + tool_catalogue)
    if extra:
        parts.append(extra.strip())
    return "\n\n".join(part.strip() for part in parts if part.strip())


TEXT_PROTOCOL_INSTRUCTIONS = """\
## Response format

This model cannot call tools directly, so answer with a single JSON object
and nothing else — no prose around it, no markdown fence:

  {"tool": "<tool name>", "arguments": {...}}   to call a tool
  {"answer": "<your reply to the user>"}        when you are finished

Use the tool names and argument names exactly as listed above.
"""


def text_protocol_prompt(tool_catalogue: str) -> str:
    """Return the extra instructions used when native tool calling is absent."""
    return TEXT_PROTOCOL_INSTRUCTIONS


def parse_text_protocol(text: str) -> dict[str, Any]:
    r"""Parse a text-protocol reply into ``{"answer": ...}`` or a tool call.

    Accepts a bare JSON object, a fenced code block, or a JSON object
    embedded in prose.  Anything that is not recognisable JSON is treated as
    a final answer, which is the safe interpretation: the user sees the
    model's words instead of an error.

    Parameters
    ----------
    text : str
        Raw assistant text.

    Returns
    -------
    dict
        Either ``{"answer": str}`` or ``{"tool": str, "arguments": dict}``.

    Examples
    --------
    >>> parse_text_protocol('{"answer": "done"}')
    {'answer': 'done'}
    >>> parse_text_protocol('```json\n{"tool": "list_fits", "arguments": {}}\n```')
    {'tool': 'list_fits', 'arguments': {}}
    """
    import json
    import re

    cleaned = (text or "").strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, flags=re.DOTALL)
    if fenced:
        cleaned = fenced.group(1).strip()

    candidates = [cleaned]
    brace = cleaned.find("{")
    if brace > 0:
        candidates.append(cleaned[brace:])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (TypeError, ValueError):
            continue
        if not isinstance(parsed, dict):
            continue
        if "tool" in parsed:
            arguments = parsed.get("arguments")
            return {
                "tool": str(parsed["tool"]),
                "arguments": arguments if isinstance(arguments, dict) else {},
            }
        if "answer" in parsed:
            return {"answer": str(parsed["answer"])}
    return {"answer": text or ""}
