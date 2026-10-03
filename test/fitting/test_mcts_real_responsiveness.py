"""Real native cancellation/heartbeat contracts for ChiSurf's MCTS bridge."""

from __future__ import annotations

import threading
import time

import pytest

bff = pytest.importorskip("IMP.bff")

from chisurf.core.fitting.mcts.execution import NativeSearchSettings, run_native_search


def _long_tabular_problem():
    problem = bff.TabularModelSearchProblem()
    problem.add_state("root", 0.0, False)
    problem.add_state("winner", 3.0, True)
    problem.set_initial_state("root")
    problem.add_action("root", "improve", "winner", 1.0)
    problem.add_action("winner", "terminate", "winner", 1.0, True)
    return problem


def test_real_run_native_search_releases_gil_for_cancellation():
    cancelled = threading.Event()

    def trigger():
        time.sleep(0.02)
        cancelled.set()

    trigger_thread = threading.Thread(target=trigger, daemon=True)
    trigger_thread.start()
    start = time.perf_counter()
    result = run_native_search(
        _long_tabular_problem(),
        NativeSearchSettings(simulations=10_000_000, seed=41, dirichlet_fraction=0.0),
        should_cancel=cancelled.is_set,
    )
    elapsed = time.perf_counter() - start
    trigger_thread.join(1.0)

    assert cancelled.is_set()
    assert result.get_cancelled()
    assert result.get_number_of_simulations() < 10_000_000
    assert elapsed < 1.0


def test_real_native_run_reacquires_gil_for_director_and_translates_errors():
    # A Python GraphNode director is entered from the native objective path.
    from IMP.bff import GraphNode, GraphPort, MCMCSampler

    class DirectorNode(GraphNode):
        def __init__(self, fail=False):
            super().__init__("director")
            self.fail = fail
            self.calls = 0
            self.add_input_port("x", GraphPort(0.0))
            self.add_output_port("chi2", GraphPort(0.0, False, True))

        def evaluate(self):
            self.calls += 1
            if self.fail:
                raise RuntimeError("director callback sentinel")
            self.outputs["chi2"].value = self.inputs["x"].value ** 2
            self.set_valid(True)

    node = DirectorNode()
    sampler = MCMCSampler("metropolis", 5)
    sampler.set_parameter_ports([node.inputs["x"]])
    sampler.set_initial_values([0.0])
    sampler.set_n_adapt(0)
    sampler.set_step_size(0.01)
    sampler.set_blocks([0], [1])
    sampler.set_objective(node, "chi2")
    sampler.run(4)
    assert node.calls > 0

    failing = DirectorNode(fail=True)
    broken = MCMCSampler("metropolis", 5)
    broken.set_parameter_ports([failing.inputs["x"]])
    broken.set_initial_values([0.0])
    broken.set_n_adapt(0)
    broken.set_step_size(0.01)
    broken.set_blocks([0], [1])
    broken.set_objective(failing, "chi2")
    with pytest.raises(RuntimeError, match="director callback sentinel"):
        broken.run(1)


def test_real_mcmc_run_releases_gil_for_background_heartbeat():
    from IMP.bff import GraphNode, GraphPort, MCMCSampler

    parameter = GraphPort(0.0, name="x")
    objective = GraphNode("chi2")
    objective.add_input_port("x", parameter)
    objective.add_input_port("one", GraphPort(1.0))
    objective.add_output_port("chi2", GraphPort(0.0, False, True))
    objective.set_callback("multiply_double", "C")

    sampler = MCMCSampler("stretch", 9)
    sampler.set_parameter_ports([parameter])
    sampler.set_objective(objective, "chi2")
    sampler.set_number_of_walkers(4)
    sampler.set_n_adapt(0)
    ticks = []
    done = threading.Event()

    def heartbeat():
        while not done.is_set():
            ticks.append(time.perf_counter())
            time.sleep(0.001)

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    start = time.perf_counter()
    sampler.run(200_000)
    elapsed = time.perf_counter() - start
    done.set()
    thread.join(1.0)

    assert len(ticks) >= 10
    assert elapsed < 10.0
