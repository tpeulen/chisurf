"""Reading PicoQuant SymPhoTime ``.pqres`` result files.

These tests used to *print* and ``return`` — pytest reported them as passing
while the FCS path raised a ``UnicodeDecodeError`` on the first byte, because
the reader's ``reader_name`` argument was dropped and the binary file went to
the text parser. They now assert what the file actually contains.
"""
from __future__ import annotations

import os

import numpy as np

import chisurf.core.experiments.fcs
import chisurf.core.experiments.tcspc

FCS_FILE = os.path.join('test', 'data', 'fcs', 'Al488_10uM-KI_150b_2_OFCS.pqres')
TCSPC_FILE = os.path.join('test', 'data', 'tcspc', 'Al488_10uM-KI_150b_2_OTCSPC.pqres')

#: The two autocorrelations and the cross-correlation the file holds. The same
#: file also stores their standard deviations, their weights and a 25 025-point
#: TCSPC decay, all as ``<base>X``/``<base>Y`` array pairs — none of which is a
#: correlation curve.
EXPECTED_CURVES = {'VarAutoFCSA', 'VarAutoFCSB', 'VarFCCSCurve'}


def test_read_fcs_pqres():
    """The FCS reader loads the correlation curves, and only those."""
    reader = chisurf.core.experiments.fcs.FCS()
    group = reader.read(filename=FCS_FILE, reader_name='pqres')

    assert {c.name for c in group} == EXPECTED_CURVES

    for curve in group:
        assert len(curve.x) == 54
        # Correlation times are lag times in seconds, strictly increasing.
        assert np.all(np.diff(curve.x) > 0)
        assert curve.x[0] > 0
        assert np.all(np.isfinite(curve.y))
        # The per-point errors come from the file's StdDev companion arrays and
        # must be usable as fit weights: finite and non-zero everywhere.
        assert np.all(np.isfinite(curve.ey))
        assert np.all(curve.ey > 0)


def test_pqres_fcs_keeps_the_measured_amplitudes():
    """The correlation amplitudes are read, not recomputed or rescaled."""
    from chisurf.core.fio.fluorescence.pqres import PQResReader, read_pqres_fcs

    raw = PQResReader(FCS_FILE).get_curves()
    curves = {c['measurement_id']: c for c in read_pqres_fcs(FCS_FILE)}

    assert set(curves) == EXPECTED_CURVES
    for name, curve in curves.items():
        np.testing.assert_array_equal(
            curve['correlation_amplitudes'], np.asarray(raw[name]['Y'])
        )
        np.testing.assert_array_equal(
            curve['correlation_times'], np.asarray(raw[name]['X'])
        )


def test_read_tcspc_pqres():
    """The TCSPC reader loads the decay with a nanosecond time axis."""
    reader = chisurf.core.experiments.tcspc.TCSPCReader()
    group = reader.read(filename=TCSPC_FILE)

    assert len(group) > 0
    for curve in group:
        assert len(curve.x) > 1
        assert np.all(np.diff(curve.x) > 0)
        assert np.all(curve.y >= 0)
