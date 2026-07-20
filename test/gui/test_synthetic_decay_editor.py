"""Tests for the shared synthetic-decay editor (model + AutoForm view)."""

from __future__ import annotations


def _model(**kwargs):
    from chisurf.gui.widgets.synthetic_decay_editor import SyntheticDecayEditorModel

    return SyntheticDecayEditorModel(**kwargs)


def test_editor_builds_autoform(qapp, qtbot):
    from chisurf.gui.autoform import AutoForm

    m = _model()
    form = AutoForm(m)
    qtbot.addWidget(form)
    # The spectrum table and preview plot both render.
    from chisurf.gui.autoform.sections.builtin import InfoWidget, TableWidget
    from chisurf.gui.autoform.sections.help_section import HelpButton

    assert form.findChild(TableWidget) is not None
    # A ? help button is present; the redundant status info line was removed.
    assert form.findChildren(HelpButton)
    assert not form.findChildren(InfoWidget)


def test_spectrum_edit_updates_decay(qapp, qtbot):
    m = _model()
    before = m.decay()
    m.update_spectrum_cell(0, "lifetime", 8.0)
    after = m.decay()
    assert before.shape == after.shape
    # Changing a lifetime changes the decay shape.
    assert not (before == after).all()


def test_add_remove_rows():
    m = _model()
    n = len(m.spectrum_rows)
    m.add_spectrum_row()
    assert len(m.spectrum_rows) == n + 1
    m.remove_spectrum_row()
    assert len(m.spectrum_rows) == n
    # Never drop below one component.
    for _ in range(10):
        m.remove_spectrum_row()
    assert len(m.spectrum_rows) == 1


def test_irf_fwhm_broadens_rising_edge():
    import numpy as np

    ideal = _model()
    ideal.irf_fwhm_ns = 0.0
    y0 = ideal.decay()
    conv = _model()
    conv.irf_fwhm_ns = 0.5
    y1 = conv.decay()
    # The IRF pushes the peak away from bin 0.
    assert np.argmax(y1) > np.argmax(y0)


def test_shot_noise_is_reproducible():
    import numpy as np

    a = _model()
    a.shot_noise = True
    a.photon_count = 50_000
    a.noise_seed = 7
    b = _model()
    b.shot_noise = True
    b.photon_count = 50_000
    b.noise_seed = 7
    assert np.array_equal(a.decay(), b.decay())


def test_component_dict_roundtrip():
    m = _model()
    m.name = "donor"
    m.spectrum_rows = [{"amplitude": 0.6, "lifetime": 1.5}, {"amplitude": 0.4, "lifetime": 3.8}]
    comp = m.component()
    assert comp["name"] == "donor"
    assert comp["amplitudes"] == [0.6, 0.4]
    assert comp["lifetimes"] == [1.5, 3.8]
    assert comp["type"] == "synthetic"


def test_periodic_shift_wraps():
    import numpy as np

    from chisurf.core.fluorescence.tcspc.convolve import periodic_shift

    a = np.zeros(8)
    a[1] = 1.0
    # Integer shift moves the impulse; the tail wraps around.
    shifted = periodic_shift(a, 2.0)
    assert np.argmax(shifted) == 3
    wrapped = periodic_shift(a, -2.0)
    assert np.argmax(wrapped) == 7  # wrapped to the end


def test_skewed_irf_is_asymmetric():
    m = _model()
    m.irf_fwhm_ns = 0.5
    m.irf_skew = 0.0
    sym = m._irf()
    m.irf_skew = 3.0
    skew = m._irf()
    # A skewed IRF differs from the symmetric Gaussian of the same FWHM.
    assert sym is not None and skew is not None
    assert not (sym == skew).all()


def test_time_shift_delays_peak():
    import numpy as np

    m = _model()
    m.irf_fwhm_ns = 0.3
    base = np.argmax(m.decay())
    m.time_shift_ns = 1.0  # delay the IRF by 1 ns
    assert np.argmax(m.decay()) > base


def test_periodic_convolution_adds_interpulse_tail():
    import numpy as np

    from chisurf.core.fluorescence.decay import synthetic_decay

    m = _model()
    m.irf_fwhm_ns = 0.3
    irf = m._irf()
    kw = dict(amplitudes=[1.0], bin_width=0.05, irf=irf, normalize=False)
    aperiodic = synthetic_decay(256, [4.0], **kw)
    periodic = synthetic_decay(256, [4.0], period=12.5, **kw)
    # The finite laser period lifts the late-time baseline (earlier-pulse tail).
    assert periodic[-1] > aperiodic[-1]


def test_read_from_fit_populates_spectrum():
    def fake_fit():
        return [0.7, 1.0, 0.3, 4.0], "fit01", object()

    m = _model(read_fit=fake_fit)
    m.read_from_fit()
    assert m.spectrum_rows == [
        {"amplitude": 0.7, "lifetime": 1.0},
        {"amplitude": 0.3, "lifetime": 4.0},
    ]
    assert m.name == "fit01"
    assert m.selected_fit is not None
