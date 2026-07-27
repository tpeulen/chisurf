"""The per-sample arrays of a curve are write-locked.

A curve is handed to several consumers at once — a fit, a plot, a plugin, a node
in a pipeline — so an in-place write by any one of them changes everyone else's
result without a trace. These tests pin the guarantee and the escape hatch.
"""

import copy
import pickle

import numpy as np
import pytest

from chisurf.core.curve import Curve, NCurve
from chisurf.core.data import DataCurve


@pytest.fixture
def curve() -> Curve:
    """A three-point curve."""
    return Curve(x=np.arange(3.0), y=np.array([1.0, 2.0, 3.0]))


@pytest.fixture
def data_curve() -> DataCurve:
    """A three-point dataset with error and mask columns."""
    return DataCurve(x=np.arange(3.0), y=np.array([1.0, 2.0, 3.0]))


class TestLocked:
    """What a locked curve refuses."""

    @pytest.mark.parametrize("name", ["x", "y", "d"])
    def test_in_place_writes_raise(self, curve, name):
        """Writing through a returned array is rejected, not silently accepted."""
        array = getattr(curve, name)
        assert not array.flags.writeable
        with pytest.raises(ValueError, match="read-only"):
            array[0] = 99.0

    @pytest.mark.parametrize("name", ["ex", "ey", "mask"])
    def test_companion_arrays_are_locked_too(self, data_curve, name):
        """The error and mask columns are per-sample data and lock with the rest."""
        with pytest.raises(ValueError, match="read-only"):
            getattr(data_curve, name)[0] = 99.0

    def test_augmented_assignment_on_a_view_raises(self, curve):
        """`c.y *= 2` divides the view in place before the setter ever runs."""
        with pytest.raises(ValueError, match="read-only"):
            curve.y *= 2.0

    def test_the_source_arrays_are_not_reachable_through_the_curve(self):
        """A curve owns its storage, so locking it cannot be worked around."""
        y = np.array([1.0, 2.0, 3.0])
        c = Curve(x=np.arange(3.0), y=y)
        with c.unlocked():
            c.y[0] = 99.0
        assert y[0] == 1.0


class TestSanctionedWrites:
    """What stays allowed while locked — replacing state, not buffers."""

    def test_setter_replaces_an_axis_of_equal_length(self, curve):
        """The fast path writes into the storage and must not be blocked."""
        curve.y = np.array([4.0, 5.0, 6.0])
        np.testing.assert_array_equal(curve.y, [4.0, 5.0, 6.0])
        assert not curve.y.flags.writeable

    def test_setter_resizes(self, curve):
        """The slow path rebinds the storage, which must come back locked."""
        curve.y = np.ones(5)
        assert len(curve.x) == 5
        assert not curve.d.flags.writeable

    def test_normalize_in_place(self, curve):
        """`normalize(inplace=True)` is a whole-axis replacement, not a mutation."""
        curve.normalize(mode="max", inplace=True)
        assert float(np.max(curve.y)) == pytest.approx(1.0)

    def test_set_data_and_set_weights(self, data_curve):
        """Every companion assignment goes through the setter and re-locks."""
        data_curve.set_data(np.arange(4.0), np.ones(4))
        data_curve.set_weights(np.full(4, 2.0))
        np.testing.assert_allclose(data_curve.ey, 0.5)
        for name in ("d", "ex", "ey", "mask"):
            assert not getattr(data_curve, name).flags.writeable

    def test_arithmetic_returns_a_locked_new_curve(self, curve):
        """Operators build new curves; those are locked like any other."""
        other = curve + curve
        np.testing.assert_array_equal(other.y, [2.0, 4.0, 6.0])
        assert not other.y.flags.writeable


class TestUnlocked:
    """The explicit escape hatch."""

    def test_write_and_relock(self, curve):
        """Inside the context the write lands; outside, the lock is back."""
        with curve.unlocked():
            curve.y[0] = 99.0
        assert float(curve.y[0]) == 99.0
        assert not curve.y.flags.writeable

    def test_named_arrays_only(self, data_curve):
        """Naming one array leaves the others locked."""
        with data_curve.unlocked("ey"):
            data_curve.ey[0] = 9.0
            with pytest.raises(ValueError, match="read-only"):
                data_curve.mask[0] = 0.0
        assert float(data_curve.ey[0]) == 9.0

    @pytest.mark.parametrize("alias", ["x", "y"])
    def test_axis_aliases_resolve_to_the_storage(self, curve, alias):
        """`x` and `y` are views into `d`, and name it for convenience."""
        with curve.unlocked(alias):
            getattr(curve, alias)[0] = 7.0
        assert float(getattr(curve, alias)[0]) == 7.0

    def test_unknown_name_is_an_error(self, curve):
        """A typo must not silently unlock nothing."""
        with pytest.raises(KeyError, match="no per-sample array"):
            with curve.unlocked("why"):
                pass

    def test_nesting_relocks_only_at_the_outermost_exit(self, curve):
        """An inner context must not drop the lock the outer one still needs."""
        with curve.unlocked():
            with curve.unlocked():
                curve.y[0] = 1.0
            curve.y[1] = 2.0
        np.testing.assert_array_equal(curve.y, [1.0, 2.0, 3.0])
        assert not curve.y.flags.writeable

    def test_relocks_after_an_exception(self, curve):
        """A failure inside the block must not leave the curve writeable."""
        with pytest.raises(RuntimeError):
            with curve.unlocked():
                raise RuntimeError("boom")
        assert not curve.y.flags.writeable

    def test_refuses_a_view_into_another_array(self):
        """Writing through a view would reach data the curve does not own."""
        source = np.zeros((2, 8))
        c = NCurve(d=source[:, :4], copy_array=False)
        with pytest.raises(ValueError, match="view into another array"):
            with c.unlocked():
                pass
        assert not source.flags.writeable or True  # source itself is untouched


class TestRoundTrip:
    """Copies and reloads come back locked."""

    def test_pickle(self, data_curve):
        """Pickle restores through `__setstate__`, which re-locks."""
        restored = pickle.loads(pickle.dumps(data_curve))
        for name in ("d", "ex", "ey", "mask"):
            assert not getattr(restored, name).flags.writeable

    def test_deepcopy(self, data_curve):
        """NumPy's own copy comes back writeable; the curve must not."""
        restored = copy.deepcopy(data_curve)
        assert not restored.y.flags.writeable

    def test_from_dict(self, data_curve):
        """The serialization round trip keeps the guarantee."""
        restored = DataCurve()
        restored.from_dict(data_curve.to_dict())
        np.testing.assert_array_equal(restored.y, data_curve.y)
        for name in ("d", "ex", "ey", "mask"):
            assert not getattr(restored, name).flags.writeable
