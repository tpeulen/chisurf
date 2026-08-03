"""The TTTR correlator tool correlates a real photon file end to end.

The previous version of this file asserted against ``doubleSpinBox_2`` and
``pushButton`` -- widget names from a different dialog entirely -- so it raised
``AttributeError`` on every run and never reached the correlator. Behind that
the tool had rotted: it called ``Correlator.set_n_bins`` and
``get_x_axis_normalized``, both removed from tttrlib; its ``weight`` method was
decorated ``@property`` and so could not be called with arguments; and the
dataset selector raised on a curve that has no experiment, which is exactly what
a correlation produces.

So the test drives the real path: load a Becker & Hickl SPC file, run the
correlator thread synchronously, and check the curve that comes out.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pytest

#: A short Becker & Hickl SPC measurement shipped with the tests.
SPC_FILE = pathlib.Path(__file__).resolve().parents[1] / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"


@pytest.fixture
def tool(qapp):
    """The correlator tool with the test photon file loaded."""
    from chisurf.plugins.tttr.tttr_correlate.gui import CorrelateTTTR

    widget = CorrelateTTTR()
    widget.fileWidget.onLoadSample(None, filenames=[str(SPC_FILE)], file_type="bh132")
    yield widget
    widget.close()


def test_defaults(tool) -> None:
    """The correlator starts on the settings file's defaults."""
    from chisurf.core.settings import cs_settings

    correlator = tool.correlator
    defaults = cs_settings["correlator"]
    assert correlator.B == defaults["B"]
    assert correlator.number_of_cascades == defaults["number_of_cascades"]
    assert correlator.split == defaults["split"]
    assert correlator.ch1 == [0]
    assert correlator.ch2 == [8]
    assert correlator.fine == 0


def test_channels_are_present_in_the_data(tool) -> None:
    """The default channels are ones the test file actually recorded."""
    routing = np.asarray(tool.fileWidget.photons.routing_channels)
    present = set(np.unique(routing).tolist())
    assert set(tool.correlator.ch1) <= present
    assert set(tool.correlator.ch2) <= present


def test_correlation_produces_a_usable_curve(tool) -> None:
    """Running the correlator yields one decaying, finite, weighted curve."""
    tool.correlator.correlator_thread.run()
    tool.add_curve()

    assert len(tool._curves) == 1
    curve = tool._curves[0]

    assert curve.x.size > 32
    assert np.all(np.diff(curve.x) > 0), "the lag axis must be strictly increasing"
    assert curve.x[0] > 0, "lag zero carries no information and must be dropped"
    assert np.isfinite(curve.y).all()
    assert np.isfinite(curve.ey).all()
    assert (curve.ey > 0).all(), "weights must be usable as fitting errors"

    # An autocorrelation of a real measurement decays: the short-lag amplitude
    # is above the long-lag baseline.
    assert curve.y[:5].mean() > curve.y[-20:].mean()


def test_splitting_averages_that_many_sub_correlations(tool) -> None:
    """Each of the ``split`` photon groups contributes one sub-correlation."""
    tool.correlator.split = 3
    tool.correlator.correlator_thread.run()

    assert len(tool.correlator.correlator_thread._results) == 3
