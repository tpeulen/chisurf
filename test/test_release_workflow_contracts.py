"""Release checks gate packaging and keep plugin render evidence inspectable."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
PRIVATE_MODULE_WORKFLOWS = ("test-coverage.yml", "pixi-ci.yml", "pixi-act-test.yml")


def _workflow(name):
    """Read workflow YAML without treating GitHub's ``on`` key as a boolean."""
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _checkout(steps, module):
    """Find the source checkout that supplies one module's sibling symlink."""
    return next(
        step
        for step in steps
        if "git clone" in step.get("run", "") and f'"$GITHUB_WORKSPACE/../{module}"' in step["run"]
    )


def test_release_readiness_checks_run_on_pushes_and_pull_requests():
    """The programme branch and review events must reach the test workflow."""
    events = _workflow("test-coverage.yml")["on"]
    assert {"mcts-native-baseline", "development", "main"} <= set(events["push"]["branches"])
    assert "pull_request" in events
    assert "workflow_dispatch" in events


def test_e2e_renders_are_uploaded_even_when_a_plugin_fails():
    """A failed plugin still leaves screenshots and timing evidence in CI."""
    job = _workflow("test-coverage.yml")["jobs"]["e2e"]
    assert job["runs-on"] == "ubuntu-22.04"
    assert int(job["timeout-minutes"]) == 90
    assert not job.get("needs")
    steps = job["steps"]
    assert any(
        step.get("run") == "xvfb-run -a pixi run --environment test test-e2e" for step in steps
    )
    artifact = next(
        step
        for step in steps
        if step.get("uses", "").startswith("actions/upload-artifact@")
        and step["with"].get("name") == "e2e-renders"
    )
    assert artifact["if"] == "always()"
    assert artifact["with"]["path"] == "renders/e2e"


def test_e2e_uses_the_same_module_sources_as_unit_tests():
    """Plugin tests must exercise the same source builds as ordinary tests."""
    jobs = _workflow("test-coverage.yml")["jobs"]
    regular, e2e = jobs["tests"]["steps"], jobs["e2e"]["steps"]
    for module in ("mmfdb", "tttrlib", "chimol"):  # QuEst is a plugin now, no sibling checkout
        assert _checkout(e2e, module)["run"] == _checkout(regular, module)["run"]
    assert any("xvfb" in step.get("run", "") and "libgl1-mesa-dev" in step["run"] for step in e2e)


@pytest.mark.parametrize("name", PRIVATE_MODULE_WORKFLOWS)
def test_missing_private_module_key_fails_with_an_actionable_error(name, tmp_path):
    """A missing key is a failed prerequisite, never a silently skipped module."""
    jobs = _workflow(name)["jobs"]
    checked = 0
    for job in jobs.values():
        steps = job.get("steps", [])
        agents = [
            step
            for step in steps
            if step.get("uses", "").startswith("webfactory/ssh-agent@")
            and "CHIMOL_DEPLOY_KEY" in step.get("with", {}).get("ssh-private-key", "")
        ]
        if not agents:
            continue
        checked += 1
        assert job["env"]["CHIMOL_KEY"] == "${{ secrets.CHIMOL_DEPLOY_KEY }}"
        assert agents[0]["if"] == "env.CHIMOL_KEY != ''"
        clone = _checkout(steps, "chimol")
        assert clone["if"] == "env.CHIMOL_KEY != ''"
        missing = next(step for step in steps if step.get("if") == "env.CHIMOL_KEY == ''")
        assert steps.index(missing) == steps.index(clone) + 1
        assert missing["shell"] == "bash"
        result = subprocess.run(
            ["bash", "-c", missing["run"]], cwd=tmp_path, capture_output=True, text=True
        )
        assert result.returncode == 1
        assert "::error::CHIMOL_DEPLOY_KEY" in result.stdout
        assert "no published wheel" in result.stdout
        assert "read-only deploy key" in result.stdout
    assert checked, f"{name} did not validate any private module prerequisite"


def test_every_packaging_platform_runs_smoke_checks_first():
    """The source app must start before an installer is built for any OS."""
    job = _workflow("pixi-ci.yml")["jobs"]["build"]
    steps = job["steps"]
    setup = next(
        step for step in steps if step.get("uses", "").startswith("prefix-dev/setup-pixi@")
    )
    assert {"build", "test"} <= set(setup["with"]["environments"].split())
    package = next(
        index
        for index, step in enumerate(steps)
        if "pixi run -e build build-installer" in step.get("run", "")
    )
    smoke = [
        (index, step)
        for index, step in enumerate(steps)
        if "pixi run --environment test test-smoke" in step.get("run", "")
    ]
    assert smoke
    assert all(index < package for index, step in smoke)
    conditions = {step.get("if"): step for index, step in smoke}
    assert {"runner.os == 'Linux'", "runner.os != 'Linux'"} <= set(conditions)
    assert "xvfb-run -a" in conditions["runner.os == 'Linux'"]["run"]
    # No Qt platform plugin to point at "offscreen" any more: the Qt shell left
    # with W9, and the emtk smoke run needs no env override on macOS/Windows.
    assert "QT_QPA_PLATFORM" not in conditions["runner.os != 'Linux'"].get("env", {})
