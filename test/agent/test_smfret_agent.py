"""The owner's acceptance example, end to end, as a recorded test.

The prompt is the owner directive's verbatim example::

    "do a burstwise analysis of the data located in xy. select the fret active
     species and do a fluorescence decay analysis using gaussians to get the
     distance distribution."

The model is scripted (recorded), but everything it drives is real: the
simulated measurement on disk, the burst pipeline, the container IO, the
decay registration and the Gaussian distance-distribution fit. The point the
test pins is the *chain*: an ambiguous request stops the agent for one round
of focused questions; the user's answers resume it; the chain ends in burst
counts, a selected species, a sub-ensemble decay, fitted distance-distribution
parameters and a report that states the assumptions used.

The simulation truth (``fret_check.sim.Scenario``): one FRET population at
E = 0.75 plus a donor-only fraction. With the user's stated R0 = 52 A the
mean distance is 43.3 A; the test asserts the chain reports a fit in that
neighbourhood, with loose bounds — judging a fit is the spectroscopist's
call, the agent's job is to run the software and report honestly.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from chisurf.core.agent import AgentSession, LLMClient, LLMSettings
from chisurf.core.agent.llm import LLMResponse, ToolCall
from chisurf.core.agent.tools.clarify import ASK_USER

OWNER_PROMPT = (
    "do a burstwise analysis of the data located in xy. select the fret "
    "active species and do a fluorescence decay analysis using gaussians to "
    "get the distance distribution."
)

OWNER_ANSWERS = (
    "The file is smfret.ht3. R0 = 52 A, donor-only lifetime 4.0 ns, one "
    "Gaussian component, gate on E in [0.5, 1.0], fit the width."
)

SCENARIO_KWARGS = {
    "populations": ((0.75, 0.8),),
    "donor_only": 0.2,
    "acceptor_only": 0.0,
    "duration_s": 2.0,
    "seed": 3,
}
TRUTH_DISTANCE_A = 43.29  # R0 * (1/E - 1)^(1/6) at E = 0.75, R0 = 52


class RecordedLLM(LLMClient):
    """Replays the model's decisions; the tools it calls run for real."""

    data_dir: Any = None

    def __init__(self, turns):
        super().__init__(LLMSettings(base_url="http://test", model="m"))
        self.turns: list[Any] = list(turns)

    def complete(self, messages, tools=None):
        import numpy as np

        turn: Any = self.turns.pop(0)
        if callable(turn):
            turn = turn(messages)
        calls = []
        for entry in turn.get("calls", []):
            arguments = dict(entry["arguments"])
            # The recorded path argument stands for the per-run data dir.
            if arguments.get("path") == "xy/smfret.ht3":
                arguments["path"] = str(self.data_dir / "smfret.ht3")
            calls.append(
                ToolCall(id=entry["id"], name=entry["name"], arguments=arguments)
            )
        return LLMResponse(
            text=turn.get("text", ""),
            tool_calls=calls,
            raw_message={
                "role": "assistant",
                "content": None if calls else turn.get("text", ""),
                **(
                    {
                        "tool_calls": [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {
                                    "name": call.name,
                                    "arguments": json.dumps(call.arguments),
                                },
                            }
                            for call in calls
                        ]
                    }
                    if calls
                    else {}
                ),
            },
        )


def _turn(name, arguments, call_id):
    return {"calls": [{"id": call_id, "name": name, "arguments": arguments}]}


def test_the_owner_example_runs_end_to_end(context, tmp_path):
    """Verbatim prompt -> one grilling round -> answers -> full chain -> report."""
    tttrlib = pytest.importorskip("tttrlib")
    from chisurf.plugins.burst.fret_check.sim import Scenario, simulate

    (tmp_path / "xy").mkdir()
    data = simulate(Scenario("acceptance", **SCENARIO_KWARGS))
    data.write(str(tmp_path / "xy" / "smfret.ht3"))

    model = RecordedLLM(
        [
            # Turn 1: the request is ambiguous in ways that change the
            # analysis — grilling, not guessing.
            {
                "calls": [
                    {
                        "id": "q1",
                        "name": ASK_USER,
                        "arguments": {
                            "questions": [
                                {
                                    "id": "file",
                                    "question": "Which measurement is 'the data located in xy'?",
                                    "options": ["smfret.ht3"],
                                    "default": "smfret.ht3",
                                },
                                {
                                    "id": "forster_radius",
                                    "question": "Which Förster radius R0 (A)?",
                                    "options": ["52", "56", "64"],
                                    "default": "52",
                                },
                                {
                                    "id": "donor_lifetime",
                                    "question": "Donor-only lifetime τ_D0 (ns)?",
                                    "options": ["4.0", "3.2"],
                                    "default": "4.0",
                                },
                                {
                                    "id": "n_gaussians",
                                    "question": "How many Gaussian components?",
                                    "options": ["1", "2"],
                                    "default": "1",
                                },
                                {
                                    "id": "gate",
                                    "question": "Which gate selects the FRET-active species?",
                                    "options": ["E in [0.5, 1.0]", "E in [0.3, 0.7]"],
                                    "default": "E in [0.5, 1.0]",
                                },
                            ]
                        },
                    }
                ]
            },
            # Turn 2: answers arrived — the chain, driven as tool calls.
            _turn("detect_smfret", {"path": "xy/smfret.ht3"}, "t1"),
            _turn(
                "run_burst_analysis",
                {"path": "xy/smfret.ht3", "min_photons_burst": 30},
                "t2",
            ),
            _turn("inspect_bursts", {}, "t3"),
            _turn("select_species", {"column": "E", "min": 0.5, "max": 1.0}, "t4"),
            _turn("extract_subensemble_decay", {}, "t5"),
            _turn(
                "fit_distance_distribution",
                {
                    "n_states": 1,
                    "forster_radius": 52.0,
                    "donor_lifetime": 4.0,
                    "fit_sigma": True,
                },
                "t6",
            ),
            # Turn 3: the report.
            {
                "text": (
                    "Burstwise analysis of smfret.ht3: 100 bursts found; the "
                    "FRET-active species (E in [0.5, 1.0]) keeps a subset; "
                    "their sub-ensemble donor decay was fitted with one "
                    "Gaussian distance distribution. Distance R = 43.0 A, "
                    "E = 0.76, chi2r = 0.23. Assumptions: R0 = 52 A, "
                    "tau_D0 = 4.0 ns, 1 component, width fitted."
                )
            },
        ]
    )
    model.data_dir = tmp_path / "xy"
    agent = AgentSession(model, context=context)

    first = agent.ask(OWNER_PROMPT)
    assert first.stop_reason == "needs_input"
    assert not first.ok
    assert {q["id"] for q in first.clarifications} == {
        "file",
        "forster_radius",
        "donor_lifetime",
        "n_gaussians",
        "gate",
    }
    # Nothing acted before the answers.
    assert first.tool_names() == [ASK_USER]

    second = agent.ask(OWNER_ANSWERS)
    assert second.stop_reason == "answer", second.text
    assert second.ok, second.error
    chain = second.tool_names()
    for step in (
        "detect_smfret",
        "run_burst_analysis",
        "select_species",
        "extract_subensemble_decay",
        "fit_distance_distribution",
    ):
        assert step in chain, f"the chain never ran {step}"
    # Exactly one clarification round for the whole request.
    assert chain.count(ASK_USER) == 0
    assert sum(1 for r in (*first.invocations, *second.invocations) if r.name == ASK_USER) == 1

    by_name = {}
    for invocation in second.invocations:
        if invocation.ok and invocation.result:
            by_name[invocation.name] = invocation.result

    bursts = by_name["run_burst_analysis"]
    assert bursts["n_bursts"] > 0, "no bursts found in the simulated data"
    assert bursts["container"].endswith(".pto"), "the burst run is traceable in the container"

    species = by_name["select_species"]
    assert species["n_selected"] > 0
    assert species["n_selected"] < bursts["n_bursts"], "the gate actually selected"

    decay = by_name["extract_subensemble_decay"]
    assert decay["photons"] > 0
    assert decay["n_bursts_used"] == species["n_selected"]
    assert decay["dataset_index"] is not None

    fit = by_name["fit_distance_distribution"]
    distance = fit["distances_A"][0]
    assert 0.8 * TRUTH_DISTANCE_A < distance < 1.2 * TRUTH_DISTANCE_A, (
        f"fitted mean distance {distance} A vs simulation truth {TRUTH_DISTANCE_A} A"
    )
    assert 0.0 < fit["efficiencies"][0] < 1.0
    assert fit["chi2_reduced"] > 0
    assert fit["width_mode"] == "fitted"

    # The report states the parameters and the assumptions used.
    for fragment in ("43", "R0 = 52", "tau_D0 = 4.0", "width fitted"):
        assert fragment in second.text
    # And the fit is a real session object.
    import chisurf as cs

    assert len(cs.fits) >= 1
