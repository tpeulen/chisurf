"""The two directions of a transition are drawn apart, in the plot's own y units.

The arrows sit above the dwell-E histogram, whose y axis counts dwells (tens of
thousands on a real folder). Their sideways offset was a fraction of the *E*
span, so on that axis it was invisible and S0->S1 covered S1->S0.
"""

from types import SimpleNamespace

import numpy as np

from chisurf.plugins.burst.burst_h2mm.gui import result_view


def test_opposite_directions_are_separated_on_the_count_axis():
    ana = SimpleNamespace(
        fret=np.array([0.03, 0.42]), trans_rates=np.array([[0.0, 33.0], [45.0, 0.0]])
    )
    y_node = 45_000.0
    arrows = {
        (i, j): (y0, y1)
        for i, j, _x0, y0, _x1, y1, _w in result_view.transition_arrows(ana, y_node)
    }
    forward, back = arrows[(0, 1)], arrows[(1, 0)]
    assert forward[0] == forward[1] and back[0] == back[1]  # horizontal
    # apart by a visible fraction of the axis, one above and one below the node line
    assert abs(forward[0] - back[0]) > 0.02 * y_node
    assert min(forward[0], back[0]) < y_node < max(forward[0], back[0])
