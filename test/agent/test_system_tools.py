"""Tests for the tools that drive the computer rather than ChiSurf."""

from __future__ import annotations

import pytest

from chisurf.core.agent import AgentConfig, AgentContext, ToolError, build_default_registry
from chisurf.core.agent.tools import system as system_tools


@pytest.fixture()
def workspace(tmp_path):
    """Return a context rooted at a scratch directory, execution allowed."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "data.txt").write_text("one\ntwo\n", encoding="utf-8")
    return AgentContext(working_directory=str(tmp_path), allow_code_execution=True)


# ── running programs ──────────────────────────────────────────────────


def test_a_program_runs_and_its_output_comes_back(workspace):
    result = system_tools.run_command(workspace, command="echo hello", purpose="say hello")
    assert result["ok"]
    assert result["exit_code"] == 0
    assert result["stdout"].strip() == "hello"
    assert result["purpose"] == "say hello"


def test_it_runs_in_the_working_directory(workspace):
    result = system_tools.run_command(workspace, command="ls")
    assert "data.txt" in result["stdout"]
    assert result["cwd"] == workspace.working_directory


def test_a_relative_cwd_is_resolved(workspace):
    result = system_tools.run_command(workspace, command="pwd", cwd="sub")
    assert result["stdout"].strip().endswith("sub")


def test_a_failing_command_is_reported_not_raised(workspace):
    result = system_tools.run_command(workspace, command="ls /definitely/not/here")
    assert result["ok"] is False
    assert result["exit_code"] != 0
    assert "status" in result["error"]
    assert result["stderr"]


def test_a_hanging_command_is_killed(workspace):
    with pytest.raises(ToolError, match="timed out"):
        system_tools.run_command(workspace, command="sleep 5", timeout_s=1)


def test_output_is_truncated_to_the_context_budget(workspace):
    workspace.max_result_chars = 200
    result = system_tools.run_command(workspace, command="seq 1 10000")
    assert len(result["stdout"]) <= 200


def test_an_empty_command_is_refused(workspace):
    with pytest.raises(ToolError, match="no command"):
        system_tools.run_command(workspace, command="   ")


def test_a_missing_directory_is_reported(workspace):
    with pytest.raises(ToolError, match="working directory does not exist"):
        system_tools.run_command(workspace, command="ls", cwd="nowhere")


def test_execution_can_be_disabled_entirely(tmp_path):
    context = AgentContext(working_directory=str(tmp_path), allow_code_execution=False)
    with pytest.raises(ToolError, match="disabled"):
        system_tools.run_command(context, command="echo hi")


# ── the refusals ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "sudo rm -rf /  ",
        "RM -RF ~",
        "mkfs.ext4 /dev/sda1",
        "shutdown -h now",
        ":(){ :|:& };:",
    ],
)
def test_indiscriminately_destructive_commands_are_refused(workspace, command):
    """A confirmation dialog is a poor last defence against these."""
    with pytest.raises(ToolError, match="refusing"):
        system_tools.run_command(workspace, command=command)


def test_an_ordinary_removal_is_still_possible(workspace):
    """The refusals must not make the tool useless for real work."""
    target = f"{workspace.working_directory}/data.txt"
    result = system_tools.run_command(workspace, command=f"rm {system_tools.quote(target)}")
    assert result["ok"]


def test_paths_with_spaces_survive_quoting(workspace):
    awkward = "215-268 D0 irf.dat"
    (workspace.resolve_path(awkward)).write_text("x", encoding="utf-8")
    result = system_tools.run_command(workspace, command=f"cat {system_tools.quote(awkward)}")
    assert result["ok"] and result["stdout"] == "x"


# ── inspection ────────────────────────────────────────────────────────


def test_which_program_finds_something_that_exists(workspace):
    result = system_tools.which_program(workspace, program="ls")
    assert result["installed"] is True
    assert result["path"]


def test_which_program_reports_a_missing_tool(workspace):
    result = system_tools.which_program(workspace, program="definitely-not-installed-xyz")
    assert result["installed"] is False
    assert result["path"] is None


def test_list_directory_shows_files_and_directories(workspace):
    result = system_tools.list_directory(workspace)
    names = {entry["name"] for entry in result["entries"]}
    assert "data.txt" in names
    assert "sub/" in names


def test_list_directory_rejects_a_missing_path(workspace):
    with pytest.raises(ToolError, match="does not exist"):
        system_tools.list_directory(workspace, directory="nope")


# ── safety policy ─────────────────────────────────────────────────────


def test_running_programs_needs_the_dangerous_tier():
    registry = build_default_registry()
    permitted = {spec.name for spec in registry.filtered("write")}
    assert "run_command" not in permitted
    assert "which_program" in permitted, "looking is harmless"
    assert "list_directory" in permitted


def test_the_gui_tools_mode_cannot_reach_the_shell():
    """'ChiSurf tools' must stay inside ChiSurf."""
    config = AgentConfig(max_safety="write")
    exposed = {
        tool["function"]["name"]
        for tool in build_default_registry().to_openai_tools(config.max_safety)
    }
    assert "run_command" not in exposed
    assert "run_python" not in exposed


def test_a_declined_confirmation_blocks_a_command(tmp_path):
    from chisurf.core.agent import AgentSession
    from test.agent.test_runtime import ScriptedLLM

    asked = []
    context = AgentContext(
        working_directory=str(tmp_path),
        allow_code_execution=True,
        confirm=lambda name, arguments: asked.append((name, arguments)) or False,
    )
    agent = AgentSession(
        ScriptedLLM([("run_command", {"command": "echo nope"}), "I did not run it."]),
        context=context,
    )
    result = agent.ask("run echo")

    assert [name for name, _ in asked] == ["run_command"]
    assert result.invocations[0].ok is False
    assert "declined" in result.invocations[0].error
