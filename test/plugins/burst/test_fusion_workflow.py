"""Which burst folder the pipeline analyses after the optional fusion step.

Two rules, and the whole point of calling the step *optional* is the first:

* walking past it — pressing **Next** without running it — must leave every
  later step on the burst folder it already had, un-fused;
* running it must hand the **fused** folder to every later step.

Both are asserted through the real shell (its Next button, its context
propagation), not through the plugin in isolation, because the failure mode
being guarded against is a workflow-level one: bursts changing under the
analysis without anyone asking.
"""

from __future__ import annotations

import os
import pathlib

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qapp():
    try:
        from qtpy import QtWidgets
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"qtpy unavailable: {exc}")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def demo(tmp_path):
    """Return a real burst folder with a known answer, and its detectors."""
    from chisurf.plugins.burst.burst_fusion.demo import create_demo, demo_detectors

    result = create_demo(directory=tmp_path / "demo")
    return result, demo_detectors()


@pytest.fixture
def shell(qapp, demo):
    """Return the burst workflow, on the fusion step with the demo loaded."""
    from chisurf.plugins.burst.burst_analysis.gui.tool import BurstAnalysisTool

    result, detectors = demo
    tool = BurstAnalysisTool()
    tool.resize(1100, 700)
    tool.workflow_context.burst_folder = pathlib.Path(result["folder"])
    tool.workflow_context.channel_settings = {"detectors": detectors, "windows": {}}
    names = [panel["name"] for panel in tool.panels]
    tool.nav_list.setCurrentRow(names.index("3. Burst Fusion (optional)"))
    qapp.processEvents()
    return tool


def _fusion_panel(shell):
    panel = shell._workflow_panels.get("fusion")
    assert panel is not None, "the fusion step must have loaded"
    return panel


def test_the_step_is_declared_optional(shell):
    """The flag is what makes the walk pass over it; without it, Next would run."""
    fusion = next(p for p in shell.panels if p.get("role") == "fusion")
    assert fusion.get("optional") is True


def test_next_without_running_leaves_the_bursts_un_fused(shell, qapp, demo):
    """Pressing Next on the fusion step must change nothing at all."""
    result, _ = demo
    original = pathlib.Path(result["folder"])
    assert shell.workflow_context.burst_folder == original

    fusion = _fusion_panel(shell)
    assert shell.process_current_step() is False, "an optional step is not run by the walk"
    shell._on_next_clicked()
    qapp.processEvents()

    # The later steps still analyse the folder burst selection produced …
    assert shell.workflow_context.burst_folder == original
    # … and nothing was written or even estimated on the way past.
    assert fusion.output_folder() == ""
    assert not fusion.model.has_analysis()
    assert not list(original.parent.glob("*_fused_*")), "no fused folder may exist"


def test_the_fast_forward_also_passes_over_it(shell, qapp, demo):
    """⏩ walks the numbered steps; the optional one must not act."""
    result, _ = demo
    original = pathlib.Path(result["folder"])
    fusion = _fusion_panel(shell)

    assert shell.process_current_step() is False
    qapp.processEvents()
    assert shell.workflow_context.burst_folder == original
    assert fusion.output_folder() == ""


def test_running_the_step_hands_the_fused_folder_to_the_later_steps(shell, qapp, demo):
    """Running it must redirect the pipeline — that is what running it is for."""
    result, _ = demo
    original = pathlib.Path(result["folder"])
    fusion = _fusion_panel(shell)

    fusion.model.threshold = 0.7
    written = fusion.process_bursts()
    qapp.processEvents()

    assert written and pathlib.Path(written).is_dir()
    assert shell.workflow_context.burst_folder == pathlib.Path(written)
    assert shell.workflow_context.burst_folder != original
    assert shell.workflow_context.bur_files, "the fused .bur files must be published"
    assert all(pathlib.Path(written) in path.parents for path in shell.workflow_context.bur_files)

    # And it survives the context refresh a step change performs — burst
    # selection re-publishes its own output folder on every refresh.
    shell._refresh_workflow_context()
    assert shell.workflow_context.burst_folder == pathlib.Path(written)


def test_the_run_button_is_the_one_that_fuses(shell, qapp):
    """The canonical Run action must produce the folder, not only a preview."""
    from qtpy import QtWidgets

    fusion = _fusion_panel(shell)
    button = fusion.findChild(QtWidgets.QToolButton, "toolAction_run")
    assert button is not None

    fusion.model.threshold = 0.7
    button.click()
    qapp.processEvents()

    assert fusion.output_folder(), "pressing Run must write the fused folder"
    assert shell.workflow_context.burst_folder == pathlib.Path(fusion.output_folder())


def test_re_running_the_burst_search_supersedes_a_fusion(shell, qapp, demo):
    """A fresh search must take the pipeline back to its own bursts."""
    result, _ = demo
    original = pathlib.Path(result["folder"])
    fusion = _fusion_panel(shell)

    fusion.model.threshold = 0.7
    fusion.process_bursts()
    qapp.processEvents()
    assert shell.workflow_context.burst_folder != original

    # What the wrapped ``analyze_files`` does when burst selection runs again.
    shell._fusion_source = None
    shell._fused_folder = None
    shell.workflow_context.burst_folder = original
    shell._refresh_workflow_context()
    assert shell.workflow_context.burst_folder == original
