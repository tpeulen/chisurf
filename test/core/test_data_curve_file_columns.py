"""A ``DataCurve`` built from a file keeps the file's uncertainty columns.

``DataCurve.__init__`` loads the file and initialises ``ex``/``ey``/``mask``
from its own arguments. Those arguments default to ``None``, so doing it in
that order replaced every loaded uncertainty column with the defaults — most
damagingly ``ey``, the weights every chi2 is computed from, which came out as
ones for a file that carried real per-point errors.
"""

import pathlib
import tempfile

import numpy as np
import pytest

import chisurf.core.data


@pytest.fixture
def five_column_csv():
    """Write a 5-column ``(x, y, ex, ey, mask)`` CSV and yield its path."""
    with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
        f.write("1.0,10.0,0.1,0.5,0.0\n")
        f.write("2.0,20.0,0.1,0.5,0.0\n")
        f.write("3.0,30.0,0.1,0.5,1.0\n")
        tmpname = f.name
    try:
        yield tmpname
    finally:
        pathlib.Path(tmpname).unlink(missing_ok=True)


def test_the_constructor_keeps_the_loaded_uncertainty_columns(five_column_csv):
    """``DataCurve(filename=...)`` must agree with ``DataCurve().load(...)``."""
    constructed = chisurf.core.data.DataCurve(filename=five_column_csv)

    np.testing.assert_array_almost_equal(constructed.x, [1.0, 2.0, 3.0])
    np.testing.assert_array_almost_equal(constructed.y, [10.0, 20.0, 30.0])
    np.testing.assert_array_almost_equal(constructed.ex, [0.1, 0.1, 0.1])
    np.testing.assert_array_almost_equal(constructed.ey, [0.5, 0.5, 0.5])
    np.testing.assert_array_almost_equal(constructed.mask, [0.0, 0.0, 1.0])

    loaded = chisurf.core.data.DataCurve()
    loaded.load(five_column_csv)
    np.testing.assert_array_almost_equal(constructed.data, loaded.data)


def test_a_four_column_file_keeps_its_errors(five_column_csv):
    """The 4-column form carries ``ex``/``ey`` but no mask; both must survive."""
    path = pathlib.Path(five_column_csv).with_suffix(".4col.csv")
    path.write_text("1.0,10.0,0.1,0.5\n2.0,20.0,0.1,0.5\n")
    try:
        c = chisurf.core.data.DataCurve(filename=str(path))
        np.testing.assert_array_almost_equal(c.ex, [0.1, 0.1])
        np.testing.assert_array_almost_equal(c.ey, [0.5, 0.5])
        np.testing.assert_array_almost_equal(c.mask, [1.0, 1.0])
    finally:
        path.unlink(missing_ok=True)


def test_a_three_column_file_keeps_its_y_errors(five_column_csv):
    """The 3-column form is ``(x, y, ey)`` — the third column is the weight."""
    path = pathlib.Path(five_column_csv).with_suffix(".3col.csv")
    path.write_text("1.0,10.0,0.5\n2.0,20.0,0.25\n")
    try:
        c = chisurf.core.data.DataCurve(filename=str(path))
        np.testing.assert_array_almost_equal(c.ey, [0.5, 0.25])
    finally:
        path.unlink(missing_ok=True)


def test_an_in_memory_curve_still_gets_the_defaults():
    """Without a file the arguments (or their defaults) still define the columns."""
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([3.0, 4.0, 5.0])

    plain = chisurf.core.data.DataCurve(x=x, y=y)
    np.testing.assert_array_almost_equal(plain.ex, np.zeros(3))
    np.testing.assert_array_almost_equal(plain.ey, np.ones(3))
    np.testing.assert_array_almost_equal(plain.mask, np.ones(3))

    given = chisurf.core.data.DataCurve(
        x=x, y=y, ex=np.full(3, 0.2), ey=np.full(3, 0.7), mask=np.zeros(3)
    )
    np.testing.assert_array_almost_equal(given.ex, np.full(3, 0.2))
    np.testing.assert_array_almost_equal(given.ey, np.full(3, 0.7))
    np.testing.assert_array_almost_equal(given.mask, np.zeros(3))
