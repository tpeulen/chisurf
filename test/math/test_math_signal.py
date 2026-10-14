import unittest

import numpy as np

from chisurf.core.math.signal import shift_array


class Tests(unittest.TestCase):
    def test_math_signal_shift_array(self):
        x = np.arange(10)
        input_results = [
            (
                (
                    x,
                    0,
                ),
                np.array([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]),
            ),
            (
                (
                    x,
                    1,
                ),
                np.array([0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]),
            ),
            (
                (
                    x,
                    1.5,
                ),
                np.array([0.0, 0.0, 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5]),
            ),
            (
                (
                    x,
                    2.0,
                ),
                np.array([0.0, 0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]),
            ),
            (
                (
                    x,
                    -1.0,
                ),
                np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 0.0]),
            ),
            # Fractional negative shifts: these used to expect v[k + 0.5] for a
            # shift of -1.5 -- i.e. a shift of -0.5 -- because ts_i truncated
            # toward zero while ts_f used floor(). Integer shifts were correct,
            # which hid it. The values below are v[k - ts].
            (
                (
                    x,
                    -1.5,
                ),
                np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 4.5, 0.0]),
            ),
            (
                (
                    x,
                    -2.0,
                ),
                np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 0.0, 0.0]),
            ),
            ((x, -2.0, True, 33.0), np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 33.0, 33.0])),
            ((x, 2.0, True, 33.0), np.array([33.0, 33.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0])),
            # Index 8 blends the last sample with `outside_value` in the same
            # 0.5/0.5 ratio the interpolation uses, rather than being blanked
            # outright -- that is what makes the result continuous in `shift`.
            ((x, -1.5, True, 33.0), np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 21.0, 33.0])),
            ((x, -2.0, False, 33.0), np.array([2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 0.0, 1.0])),
            ((x, -1.5, False, 33.0), np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 4.5, 0.5])),
        ]
        for args, result in input_results:
            self.assertEqual(np.allclose(result, shift_array(*args)), True)


def test_xcorr_fft_works_along_any_axis():
    """Correlating along axis 1 is the transpose of correlating along axis 0.

    The lag slice and the zero-lag normaliser were applied to axis 0 whatever
    ``axis`` was, and the mean was not kept as a column, so axis=1 failed.
    """
    from chisurf.core.math.signal import xcorr_fft

    rng = np.random.default_rng(1)
    a = rng.normal(size=(64, 3))
    b = rng.normal(size=(64, 3))
    along_rows = xcorr_fft(a, b, axis=0)
    along_columns = xcorr_fft(a.T, b.T, axis=1)
    assert along_columns.shape == (3, 64)
    np.testing.assert_allclose(along_columns, along_rows.T)
    np.testing.assert_allclose(along_rows[0], 1.0)
