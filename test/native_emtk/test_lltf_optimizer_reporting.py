"""LLTF's GUI distinguishes optimizer convergence from successful result export."""

import json

import pytest


@pytest.mark.parametrize("converged", [False, True])
def test_completed_process_reports_optimizer_outcome(tmp_path, converged):
    """An exit-zero result remains available while nonconvergence is visible in the status."""
    from chisurf.plugins.fluorescence_decay.lltf.gui.model import LLTFModel

    model = LLTFModel()
    output = tmp_path / "fit.json"
    result = {
        "converged": converged,
        "optimizer_status": 1 if converged else 5,
        "optimizer_message": "Converged." if converged else "Iteration limit reached.",
    }
    output.write_text(json.dumps(result))
    model.output_file = str(output)

    class CompletedProcess:
        """Represent the process-completion boundary without running or simulating a fit."""

        returncode = 0

        def poll(self):
            """Report successful process exit independently of optimizer status."""
            return self.returncode

    model.process = CompletedProcess()
    assert model.poll()
    assert model.result == result
    assert ("warning" in model.status.lower()) is (not converged)
    assert "completed" in model.status.lower()


@pytest.mark.parametrize("converged", [False, True])
def test_results_summary_exposes_optimizer_outcome(converged):
    """The Results panel retains the mathematical scores and adds truthful optimizer provenance."""
    from chisurf.plugins.fluorescence_decay.lltf.gui.model import LLTFModel

    model = LLTFModel()
    model.result = {
        "chi_square": 12.0,
        "reduced_chi_square": 1.2,
        "converged": converged,
        "optimizer_message": "Iteration limit reached.",
    }
    text = model.results_summary()
    assert "Chi-square: 12.000" in text
    assert "Reduced chi-square: 1.200" in text
    if converged:
        assert "Optimizer converged" in text
    else:
        assert "Optimizer warning" in text
        assert "Iteration limit reached." in text
