import unittest
import numpy as np

import chisurf.core.math.signal
from chisurf.core.math.signal import shift_array


class Tests(unittest.TestCase):

    def test_math_signal_shift_array(self):
        x = np.arange(10)
        input_results = [
            ((x, 0,), np.array([0., 1., 2., 3., 4., 5., 6., 7., 8., 9.])),
            ((x, 1,), np.array([0., 0., 1., 2., 3., 4., 5., 6., 7., 8.])),
            ((x, 1.5,), np.array([0. , 0. , 0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5])),
            ((x, 2.0,), np.array([0., 0., 0., 1., 2., 3., 4., 5., 6., 7.])),
            ((x, -1.0,), np.array([1., 2., 3., 4., 5., 6., 7., 8., 9., 0.])),
            # Fractional negative shifts: these used to expect v[k + 0.5] for a
            # shift of -1.5 -- i.e. a shift of -0.5 -- because ts_i truncated
            # toward zero while ts_f used floor(). Integer shifts were correct,
            # which hid it. The values below are v[k - ts].
            ((x, -1.5,), np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 4.5, 0. ])),
            ((x, -2.0,), np.array([2., 3., 4., 5., 6., 7., 8., 9., 0., 0.])),
            ((x, -2.0, True, 33.), np.array([ 2.,  3.,  4.,  5.,  6.,  7.,  8.,  9., 33., 33.])),
            ((x, 2.0, True, 33.), np.array([33., 33.,  0.,  1.,  2.,  3.,  4.,  5.,  6.,  7.])),
            # Index 8 blends the last sample with `outside_value` in the same
            # 0.5/0.5 ratio the interpolation uses, rather than being blanked
            # outright -- that is what makes the result continuous in `shift`.
            ((x, -1.5, True, 33.), np.array([ 1.5,  2.5,  3.5,  4.5,  5.5,  6.5,  7.5,  8.5, 21.0, 33. ])),
            ((x, -2.0, False, 33.), np.array([2., 3., 4., 5., 6., 7., 8., 9., 0., 1.])),
            ((x, -1.5, False, 33.), np.array([1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 4.5, 0.5]))
        ]
        for args, result in input_results:
            self.assertEqual(
                np.allclose(
                    result,
                    shift_array(*args)
                ),
                True
            )
