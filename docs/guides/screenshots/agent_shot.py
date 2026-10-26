"""Guide 40: the Agent panel walking the burstwise example (headless emtk, scripted model).

``main`` writes two figures into ``docs/guides/figures``:

* ``40_agent_clarify.png`` -- the shipped burstwise example prompt sent in **ChiSurf tools**
  mode; the assistant stops for its one clarification round (file, R0, τ_D0, component count,
  gate) before it touches anything, and the questions read as its message in the transcript;
* ``40_agent_chain.png`` -- the answers sent; the chain runs as tool calls (``detect_smfret`` →
  ``run_burst_analysis`` → ``inspect_bursts`` → ``select_species`` →
  ``extract_subensemble_decay`` → ``fit_distance_distribution``) and the report closes it.

Only the model is scripted: its turns are replayed, so the figure does not depend on which
provider the machine has configured and no request leaves the machine. Every tool it calls runs
for real -- on a measurement simulated with ``fret_check.sim`` (one FRET population at E = 0.75
plus 20 % donor-only), whose bursts, container run, sub-ensemble decay and fit are genuine.

Read every PNG afterwards. Run from the repository root (arm64 env)::

    IMP_BFF_GPU=off CHISURF_SETTINGS_DIR=$(mktemp -d) MMFDB_SETTINGS_DIR=$(mktemp -d) \\
        python docs/guides/screenshots/agent_shot.py
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from emtk_shot import FIG, REPO  # noqa: E402

os.chdir(REPO)

#: The shipped example ``burstwise-distance-distribution``, verbatim.
PROMPT = (
    "do a burstwise analysis of the data located in xy. select the fret active species "
    "and do a fluorescence decay analysis using gaussians to get the distance distribution."
)
ANSWERS = (
    "The file is smfret.ht3. R0 = 52 A, donor-only lifetime 4.0 ns, one Gaussian "
    "component, gate on E in [0.5, 1.0], fit the width."
)
QUESTIONS = [
    {"id": "file", "question": "Which measurement is 'the data located in xy'?",
     "options": ["smfret.ht3"], "default": "smfret.ht3"},
    {"id": "forster_radius", "question": "Which Förster radius R0 (Å)?",
     "options": ["52", "56", "64"], "default": "52"},
    {"id": "donor_lifetime", "question": "Donor-only lifetime τ_D0 (ns)?",
     "options": ["4.0", "3.2"], "default": "4.0"},
    {"id": "n_gaussians", "question": "How many Gaussian components?",
     "options": ["1", "2"], "default": "1"},
    {"id": "gate", "question": "Which gate selects the FRET-active species?",
     "options": ["E in [0.5, 1.0]", "E in [0.3, 0.7]"], "default": "E in [0.5, 1.0]"},
]


def _scripted_llm(data_file: pathlib.Path):
    """An LLM client that replays the model's turns; the report quotes the real fit."""
    from chisurf.core.agent import LLMClient, LLMSettings
    from chisurf.core.agent.llm import LLMResponse, ToolCall

    path = str(data_file)

    def report(messages) -> dict:
        fit = {}
        for message in reversed(messages):
            if message.get("role") == "tool":
                try:
                    payload = json.loads(message.get("content") or "{}")
                except ValueError:
                    continue
                result = payload.get("result", payload)
                if isinstance(result, dict) and "efficiencies" in result:
                    fit = result
                    break
        def num(value, digits):
            return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "?"

        distance = num((fit.get("distances_A") or [None])[0], 1)
        efficiency = num((fit.get("efficiencies") or [None])[0], 2)
        return {
            "text": (
                f"FRET-active species (E in [0.5, 1.0]) of smfret.ht3, its sub-ensemble donor "
                f"decay fitted with one Gaussian distance distribution: R = {distance} Å, "
                f"E = {efficiency}, chi2r {num(fit.get('chi2_reduced'), 2)}, "
                f"donor-only fraction {num(fit.get('donor_only_fraction'), 3)}. "
                "Assumptions: R0 = 52 Å, τ_D0 = 4.0 ns, one component, width fitted."
            )
        }

    turns = [
        {"calls": [("q1", "ask_user", {"questions": QUESTIONS})]},
        {"calls": [("t1", "detect_smfret", {"path": path})]},
        {"calls": [("t2", "run_burst_analysis", {"path": path, "min_photons_burst": 30})]},
        {"calls": [("t3", "inspect_bursts", {})]},
        {"calls": [("t4", "select_species", {"column": "E", "min": 0.5, "max": 1.0})]},
        {"calls": [("t5", "extract_subensemble_decay", {})]},
        {"calls": [("t6", "fit_distance_distribution",
                    {"n_states": 1, "forster_radius": 52.0, "donor_lifetime": 4.0,
                     "fit_sigma": True})]},
        report,
    ]

    class ScriptedLLM(LLMClient):
        """Replays *turns*; nothing is sent anywhere."""

        def complete(self, messages, tools=None):
            turn = turns.pop(0)
            if callable(turn):
                turn = turn(messages)
            calls = [ToolCall(id=i, name=n, arguments=a) for i, n, a in turn.get("calls", [])]
            raw = {"role": "assistant", "content": None if calls else turn.get("text", "")}
            if calls:
                raw["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": json.dumps(c.arguments)}}
                    for c in calls
                ]
            return LLMResponse(text=turn.get("text", ""), tool_calls=calls, raw_message=raw)

    return ScriptedLLM(LLMSettings(base_url="http://scripted.invalid", model="scripted"))


def _send(driver, model, text: str, timeout: float = 300.0) -> None:
    """Send *text* through the panel's own path and draw until the turn is finished."""
    model.input_text = ""
    model.send_prompt(text)
    end = time.monotonic() + timeout
    while model.is_generating or not model.event_queue.empty():
        if time.monotonic() > end:
            raise TimeoutError("the agent turn did not finish")
        time.sleep(0.05)
        driver.frame(1)
    driver.frame(4)


def main() -> None:
    """Draw the two figures."""
    from emtk.testing_realistic import RealisticDriver

    from chisurf.core.agent import AgentConfig, AgentSession, build_default_registry
    from chisurf.plugins.burst.fret_check.sim import Scenario, simulate
    from chisurf.plugins.core.agent.gui.panel import make_app
    from chisurf.plugins.core.code_editor.agent_modes import AgentMode

    workdir = pathlib.Path(tempfile.mkdtemp(prefix="agent-shot-"))
    (workdir / "xy").mkdir()
    data_file = workdir / "xy" / "smfret.ht3"
    simulate(
        Scenario("guide", populations=((0.75, 0.8),), donor_only=0.2, acceptor_only=0.0,
                 duration_s=2.0, seed=3)
    ).write(str(data_file))

    app = make_app()
    model = app.chat_gui.model
    model.provider = "openrouter"  # any in-process provider; the client below replaces it
    model.mode = "chisurf_tools"
    llm = _scripted_llm(data_file)

    def scripted_session(mode):
        if model._agent_session is None:
            context = model.build_agent_context(mode)
            context.working_directory = str(workdir)
            model._agent_session = AgentSession(
                llm, context=context, registry=build_default_registry(),
                config=AgentConfig(max_safety=AgentMode(mode).safety),
            )
        return model._agent_session

    model.agent_session_for = scripted_session

    driver = RealisticDriver(app, (760, 960), real_painter=True)
    driver.frame(4)
    _send(driver, model, PROMPT)
    # The questions are the assistant's turn in the transcript; the run waits for the reply.
    driver.screenshot(FIG / "40_agent_clarify.png")
    print("wrote 40_agent_clarify.png", flush=True)

    _send(driver, model, ANSWERS)
    driver.screenshot(FIG / "40_agent_chain.png")
    print("wrote 40_agent_chain.png", flush=True)
    app.close()


if __name__ == "__main__":
    main()
