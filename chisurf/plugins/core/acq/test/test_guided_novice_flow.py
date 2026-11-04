"""Novice-first guided workflow: fewer clicks, user power setup, FCS-first, sample loop.

The wizard merges the optics checks into one step, chains laser heads after a single
allow-light gesture, lets the user set the session target powers, adds an FCS-first
concentration stage with explicit µL dilution instructions, loops over multiple
samples with one calibration, and shows a green/yellow/red traffic light with
concrete improvement guidance.
"""
from types import SimpleNamespace
import numpy as np
import pytest


def config(kind='fret', targets=None):
    return {'name': 'Test approved setup', 'kind': kind,
            'filters': 'TEST green filter A / red filter B', 'splitter': 'TEST color splitter C',
            'dyes': 'TEST donor / acceptor',
            'laser_targets_uw': targets if targets is not None else {'green head': 1, 'red head': 2},
            'seconds': 1, 'min_photons': 10, 'irf_fwhm_max_ns': .5,
            'background_max_khz': 10}


class FakeBook:
    def __init__(self):
        self.calls = []
        self.curves = {'green head': [(20., 0.), (1020., 10.)],
                       'red head': [(20., 0.), (820., 10.)]}

    def points(self, laser):
        return list(self.curves.get(laser, []))

    def raw_target(self, laser, uw, today=None):
        max_uw = max(u for _, u in self.curves.get(laser, [(0, 0)]))
        if not 0. < float(uw) <= max_uw:
            raise ValueError(f'{laser}: {uw} µW is outside the calibrated range')
        self.calls.append((laser, float(uw)))


class FakeServo:
    def __init__(self, status='reached', message='Verified target reached'):
        self.active = False
        self.status = status
        self.message = message


def power_record(tmp_path):
    book = FakeBook()
    head_calls, emissions, shutters = [], [], {'reported_excitation': 0.}
    r = SimpleNamespace(
        output_dir=tmp_path, running=False, source_kind='device', device=object(),
        operator_name='TP', project_name='p', sample_name='s',
        power_book=book, power_servo=None, power_selected_slot=None, power_target_uw=0.,
        laser=SimpleNamespace(state=lambda: SimpleNamespace(emission_blocked=True),
                              set_head=lambda slot, intensity_pct=0.: head_calls.append((slot, intensity_pct)),
                              set_emission=lambda on: emissions.append(on)),
        shutters=SimpleNamespace(get_parameter=lambda name, ch=-1: shutters.get(name, -1.)),
        set_shutter=lambda name, open_: shutters.__setitem__('reported_excitation', 1. if open_ else 0.),
        laser_off=lambda: None, _shutters_at_end=lambda: None,
        cancel_power_target=lambda: None, power_poll=lambda force=False: None,
        power_head_options=lambda: [(200, 'green head'), (300, 'red head')],
        power_head=lambda: SimpleNamespace(intensity_pct=20.),
        set_power_target=lambda: (setattr(r, 'power_servo', FakeServo()), True)[1],
        power_message='')
    r._head_calls, r._emissions, r._book = head_calls, emissions, book
    return r


def model_for(tmp_path, kind='fret', targets=None):
    from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizardModel
    r = power_record(tmp_path)
    w = MeasurementWizardModel(r)
    w.protocol = config(kind, targets)
    return w, r


def force_to(w, step_id):
    w._index = w.STEPS.index(step_id)


# -- 1. one merged optics step instead of separate filter/splitter confirmations ------------------

def test_optics_checks_are_merged_into_one_step(tmp_path):
    w, _ = model_for(tmp_path)
    assert w.STEPS == ('setup', 'optics', 'power', 'water', 'buffer', 'fcs',
                       'green_reference', 'red_reference', 'dna', 'sample', 'done')
    force_to(w, 'setup')
    assert w.next_step()
    assert w.step_id == 'optics'
    text = w.instructions()
    assert 'green filter A' in text and 'color splitter C' in text
    assert not w.next_step()
    w.physical_done = True
    assert w.next_step()
    assert w.step_id == 'power'


# -- 2. power: user-set targets, one allow-light gesture chains every head -----------------------

def test_power_step_chains_heads_after_one_allow_light(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'power')
    w.power_session_targets_uw = {'red head': 1.5}  # the user lowers the red target
    assert w.set_approved_power()
    assert r._book.calls == [('green head', 1.)]
    w.poll()  # servo finished for head 1 -> the next head starts without another click
    assert ('red head', 1.5) in r._book.calls
    assert w.power_index == 1
    w.poll()  # servo finished for head 2 -> stage complete
    assert w.power_index == 2
    assert w.enabled('next_step')


def test_user_target_outside_calibration_is_refused_before_any_light(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'power')
    assert not w.set_session_target('green head', 99.)
    assert 'calibrated' in w.message.lower()
    assert not r._emissions and not r._book.calls


# -- 3. FCS-first: five-minute recommendation, N estimate, explicit µL dilution ------------------

def accepted_session(n_estimate=64.):
    metrics = {0: {'n_amplitude_estimate': n_estimate}}
    snap = {'reference_live': {'metrics': metrics, 'quality': []},
            'photons': 5000, 'elapsed_s': 300., 'bursts': 0,
            'source_error': '', 'dropped': 0}
    result = SimpleNamespace(ptu=None, photons=5000, stop_reason='duration reached',
                             elapsed_s=300., analysis_complete=True)
    session = SimpleNamespace(result=result, snapshot=lambda: snap)
    return session, snap


class _Photons:
    def __init__(self, channel, macro, micro):
        self.channel, self.macro, self.micro = channel, macro, micro

    def __len__(self):
        return self.macro.size


def test_fcs_stage_defaults_to_five_minutes_and_guides_novices(tmp_path):
    w, _ = model_for(tmp_path)
    assert w.fcs_seconds == 300.
    force_to(w, 'fcs')
    text = w.instructions()
    assert 'low' in text.lower() and 'correlation' in text.lower()


def test_fcs_measurement_produces_explicit_microliter_dilution(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'fcs')
    session, snap = accepted_session(64.)
    r.session = session
    r.running = False
    w._owned_session = session
    w._owned_step = 'fcs'
    monkey_patch = pytest.MonkeyPatch()
    monkey_patch.setattr(w, '_read_saved_result', lambda *a: None)  # skip file re-read in unit test
    assert w.accept_measurement()
    plan = w.fcs_plan
    assert plan and plan['ok']
    lines = ' '.join(plan['instructions'])
    assert 'µL' in lines or 'uL' in lines
    volumes = [v for line in plan['instructions'] for v in __import__('re').findall(r'([\d.]+)\s*[µu]L', line)]
    assert volumes
    assert w.measurements['fcs']['n_estimate'] == pytest.approx(64.)
    assert w.measurements['fcs']['dilution'] == plan['instructions']


# -- 4. sample loop: one calibration, many samples ----------------------------------------------

def test_fcs_repeats_until_correlation_is_usable_and_power_is_adjustable(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'fcs')
    w.physical_done = True
    # power is adjusted from inside the modal FCS stage: explicit allow-light per change
    w.power_session_targets_uw = {'green head': .4}
    assert w.set_stage_power()
    assert r._book.calls[-1] == ('green head', .4)
    session, snap = accepted_session(None)  # no usable amplitude
    r.session, r.running = session, False
    w._owned_session, w._owned_step = session, 'fcs'
    monkey = pytest.MonkeyPatch()
    monkey.setattr(w, '_read_saved_result', lambda *a: None)
    assert not w.accept_measurement()
    assert 'fcs' not in w.measurements, 'an unusable FCS curve must be repeatable'
    assert 'power' in w.message.lower() or 'correlation' in w.message.lower()


def test_already_single_molecule_concentration_needs_no_dilution(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'fcs')
    session, snap = accepted_session(0.6)  # below the target of ~1 molecule in focus
    r.session, r.running = session, False
    w._owned_session, w._owned_step = session, 'fcs'
    monkey = pytest.MonkeyPatch()
    monkey.setattr(w, '_read_saved_result', lambda *a: None)
    assert w.accept_measurement()
    plan = w.fcs_plan
    assert plan and plan['ok']
    assert 'directly' in ' '.join(plan['instructions'])


def test_sample_loop_repeats_with_one_calibration(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'sample')
    w.measurements['sample'] = {'path': 'a.ptu'}
    w.measurements['dna'] = {'path': 'dna.ptu'}
    assert w.next_sample()
    assert 'sample' not in w.measurements
    assert 'dna' in w.measurements, 'references stay valid for every sample'
    assert w.sample_count == 2
    w.measurements['sample'] = {'path': 'b.ptu'}
    assert w.finish_session()
    assert w.step_id == 'done'


def test_auto_advance_skips_the_sample_loop_decision(tmp_path):
    w, r = model_for(tmp_path)
    force_to(w, 'water')
    session, snap = accepted_session()
    r.session, r.running = session, False
    w._owned_session, w._owned_step = session, 'water'
    monkey = pytest.MonkeyPatch()
    monkey.setattr(w, '_read_saved_result', lambda *a: None)

    def ok_accept():
        w.measurements[w.step_id] = {'path': 'x.ptu'}
        w._accepted = True
        return True
    monkey.setattr(w, 'accept_measurement', ok_accept)
    w.poll()
    assert w.step_id == 'buffer', 'a green stage advances without an extra Next click'


# -- 5. traffic light -----------------------------------------------------------------------------

def test_traffic_light_is_green_only_when_everything_passes():
    from chisurf.plugins.core.acq.gui.measurement_wizard import MeasurementWizardModel
    rows_pass = [{'metric': 'a', 'status': 'pass', 'guidance': ''}]
    level, text = MeasurementWizardModel.light_level(rows_pass)
    assert level == 'green'
    rows_fail = [{'metric': 'rate', 'status': 'fail', 'guidance': 'Lower the laser power.'},
                 {'metric': 'b', 'status': 'pass', 'guidance': ''}]
    level, text = MeasurementWizardModel.light_level(rows_fail)
    assert level == 'red' and 'Lower the laser power.' in text
    rows_watch = [{'metric': 'a', 'status': 'pass', 'guidance': ''},
                  {'metric': 'b', 'status': 'watch', 'guidance': 'Keep watching.'}]
    level, text = MeasurementWizardModel.light_level(rows_watch)
    assert level == 'yellow' and 'Keep watching.' in text
    rows_unverified = [{'metric': 'a', 'status': 'pass', 'guidance': ''},
                       {'metric': 'fit', 'status': 'unverified', 'guidance': 'No configured bound.'}]
    level, text = MeasurementWizardModel.light_level(rows_unverified)
    assert level == 'green', 'unconfigured checks are no-verdict, not warnings'


# -- 6. E/S marginals -----------------------------------------------------------------------------

def test_es_marginals_sum_to_the_histogram():
    from chisurf.plugins.core.acq.gui.guided_plots import es_marginals
    counts = np.arange(12, dtype=float).reshape(3, 4)
    x_edges = np.linspace(0., 1., 4)
    y_edges = np.linspace(0., .6, 5)
    m = es_marginals(counts, x_edges, y_edges)
    assert m['e_values'].shape == (3,) and m['s_values'].shape == (4,)
    assert m['e_values'].sum() == pytest.approx(counts.sum())
    assert m['s_values'].sum() == pytest.approx(counts.sum())
    assert m['e_centers'][0] == pytest.approx(x_edges[0] + (x_edges[1] - x_edges[0]) / 2)


# -- 7. FCS live diagnostics include the amplitude rows -------------------------------------------

def test_fcs_live_analysis_reports_amplitude():
    from chisurf.plugins.core.acq.live.guided_analysis import GuidedLiveAnalysis
    a = GuidedLiveAnalysis(1e-6, 1e-12, 16, 'fcs', {'amplitude': [0.001, 0.1]})
    macro = np.arange(4000)
    a.push(SimpleNamespace(photons=lambda: _Photons(np.zeros(4000, dtype=int), macro,
                                                    np.zeros(4000, dtype=int))))
    snap = a.snapshot()
    assert 0 in snap['metrics']
    assert any('amplitude' in row['metric'] for row in snap['quality'])


def test_incomplete_live_analysis_cannot_be_accepted_even_with_stale_fcs_metrics(tmp_path, monkeypatch):
    w, record = model_for(tmp_path)
    force_to(w, 'fcs')
    session, snap = accepted_session(64.)
    session.result.analysis_complete = False
    snap['analysis_gap'] = True
    record.session, record.running = session, False
    w._owned_session, w._owned_step = session, 'fcs'
    monkeypatch.setattr(w, '_read_saved_result', lambda *a: None)
    assert not w.accept_measurement()
    assert 'fcs' not in w.measurements
    assert any(row['metric'] == 'Live analysis complete' and row['status'] == 'fail'
               for row in w._quality)
