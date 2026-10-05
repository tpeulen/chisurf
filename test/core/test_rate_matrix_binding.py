"""The rich matrix's edit semantics are independent of the GUI toolkit."""

from types import SimpleNamespace

import pytest


def test_cell_commit_uses_the_live_matrix_not_a_display_snapshot():
    """An independent renderer can apply exactly one source/target edit."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    host = SimpleNamespace(scheme=SimpleNamespace(n=2, values=[0.0, 123.456, 2_500_000.0, 0.0]))
    binding = RateMatrixBinding(host, "scheme.values", size_attr="scheme.n")
    displayed = binding.values()
    host.scheme.values[1] = 432.19876
    binding.commit_cell(1, 0, 70.0)
    assert displayed == [0.0, 123.456, 2_500_000.0, 0.0]
    assert binding.values() == [0.0, 432.19876, 70.0, 0.0]


def test_nested_matrix_binding_exposes_the_actual_fitting_parameter():
    """The data/action contract retains parameter identity and metadata."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding
    from chisurf.core.fitting.kinetics import RateMatrixParameters

    host = SimpleNamespace(scheme=RateMatrixParameters(n_states=3, default_rate=0.0))
    binding = RateMatrixBinding(host, "scheme.rate_values", size_attr="scheme.n_states")
    rate = host.scheme.rates_by_name()["k1_2"]
    assert binding.parameter(0, 1) is rate
    binding.commit_cell(0, 1, 432.19876)
    assert binding.parameter(0, 1) is rate
    assert rate.value == 432.19876


def test_cell_commit_notifies_its_scientific_fit_exactly_once():
    """Recompute the addressed owner, never an unrelated global selected fit."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    seen = []
    host = SimpleNamespace(n=2, values=[0.0, 1.0, 2.0, 0.0])
    host.fit = SimpleNamespace(update=lambda: seen.append(list(host.values)))
    binding = RateMatrixBinding(host, "values", size_attr="n")
    binding.commit_cell(0, 1, 3.0)
    assert seen == [[0.0, 3.0, 2.0, 0.0]]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_invalid_edits_do_not_mutate_or_notify(value):
    """Non-finite input is rejected before changing the scientific vector."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    seen = []
    host = SimpleNamespace(n=2, values=[0.0, 1.0, 2.0, 0.0], update=lambda: seen.append(True))
    original = host.values
    binding = RateMatrixBinding(host, "values", size_attr="n")
    with pytest.raises(ValueError, match="finite"):
        binding.commit_cell(0, 1, value)
    assert host.values is original and host.values == [0.0, 1.0, 2.0, 0.0]
    assert not seen


@pytest.mark.parametrize("cell", [(-1, 0), (0, -1), (2, 0), (0, 2)])
def test_outside_cells_do_not_mutate_the_matrix(cell):
    """An obsolete topology cannot redirect a cell edit to a different rate."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    host = SimpleNamespace(n=2, values=[0.0, 1.0, 2.0, 0.0])
    binding = RateMatrixBinding(host, "values", size_attr="n")
    with pytest.raises(IndexError, match="outside"):
        binding.commit_cell(*cell, 3.0)
    assert host.values == [0.0, 1.0, 2.0, 0.0]


def test_mismatched_dimensions_do_not_mutate_or_notify():
    """A matrix declaration cannot silently fabricate missing scientific cells."""
    from chisurf.core.dataspec.rate_binding import RateMatrixBinding

    seen = []
    host = SimpleNamespace(n=2, values=[0.0, 1.0, 2.0], update=lambda: seen.append(True))
    original = host.values
    binding = RateMatrixBinding(host, "values", size_attr="n")
    with pytest.raises(ValueError, match="3 cells, expected 4"):
        binding.commit_cell(0, 1, 3.0)
    assert host.values is original and host.values == [0.0, 1.0, 2.0]
    assert not seen


def test_binding_works_in_a_fresh_interpreter_with_qt_blocked():
    """A renderer's toolkit is not a dependency of the shared data/action API."""
    import subprocess
    import sys

    script = """
import sys
from importlib.abc import MetaPathFinder
from types import SimpleNamespace
class BlockQt(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'}:
            raise ImportError('Qt forbidden in the matrix binding: ' + fullname)
sys.meta_path.insert(0, BlockQt())
from chisurf.core.dataspec.rate_binding import RateMatrixBinding
host = SimpleNamespace(n=2, values=[0.0, 1.0, 2.0, 0.0])
RateMatrixBinding(host, 'values', size_attr='n').commit_cell(0, 1, 3.0)
assert host.values == [0.0, 3.0, 2.0, 0.0]
assert not any(name.split('.')[0] in {'qtpy', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6'} for name in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stdout + result.stderr
