"""Additive-offset mixed-laser power adjustment through the routine target gesture.

The diode sees every head summed over one shared dark level D. A head's net
contribution is ``alone_raw - D``; with the other heads' contributions verified
against live readback, a combined reading minus their sum attributes the selected
head's alone raw, which the existing calibration book converts to µW. An unknown
or changed contribution is a named refusal, never a guessed power.

Derived from the actual simulator rig (``SimShutters``:
``raw = 20 + 10*green_drive_pct + 8*red_drive_pct``; seeded curves
Green ``(20,0),(1020,10)`` and Red ``(20,0),(820,10)``): Green at 2 µW sits at
drive 20 % / alone raw 220, Red at 3 µW at drive 30 % / alone raw 260; the
combined raw is then 460 and ``460 - (220 - 20) = 260`` reads back 3 µW for Red.
"""
import time

import pytest


# -- slice 1: the shared dark is counted once and the offset servo is correct ---------------

class SummedRig:
    """Two heads behind one diode: raw = 20 + 10*drive200 + 8*drive300."""

    def __init__(self):
        self.drives = {200: 0., 300: 0.}
        self.marked = False
        self.blocked = False
        self.writes = []

    def mark(self):
        self.marked = True

    def mean(self):
        assert self.marked
        if self.blocked:
            return -1.
        raw = 20. + 10. * self.drives[200] + 8. * self.drives[300]
        return raw

    def set(self, slot, value):
        assert 0. <= value <= 100.
        self.writes.append((slot, value))
        self.drives[slot] = value

    def safe(self):
        return not self.blocked

    def off(self):
        self.blocked = True


def red_book(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerBook
    book = PowerBook(tmp_path / 'p.json')
    book.add('Red 640 nm', 20, 0)
    book.add('Red 640 nm', 820, 10)
    return book


def run_servo(servo, limit=80):
    for _ in range(limit):
        servo.poll()
        if not servo.active:
            break
    return servo


def test_offset_servo_subtracts_the_shared_dark_once(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerServo
    book = red_book(tmp_path)
    rig = SummedRig()
    rig.drives[200] = 20.  # Green emitting alone at its verified 2 µW point: alone raw 220
    dark, green_alone = 20., 220.
    servo = PowerServo(book, lambda: rig.drives[300], lambda v: rig.set(300, v),
                       rig.mark, rig.mean, rig.safe, rig.off,
                       settle_s=0, timeout_s=5, context_offset=green_alone - dark)
    servo.start('Red 640 nm', 3)  # target raw 260 (drive 30 %)
    run_servo(servo)
    assert servo.status == 'reached', servo.message
    assert rig.drives[300] == pytest.approx(30, abs=.5)
    assert rig.drives[200] == 20., 'the attributed head must stay untouched'
    assert servo.power_uw == pytest.approx(3, abs=.05)
    # the verified combined reading at convergence, kept for ledger attribution
    assert servo.verified_raw == pytest.approx(20. + 10. * 20. + 8. * rig.drives[300], rel=1e-3)


def test_default_servo_without_offset_is_backwards_compatible(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerServo
    book = red_book(tmp_path)  # Red curve (20,0),(820,10): gain 8 per drive %, like the rig
    rig = SummedRig()
    rig.drives[200] = 0.
    servo = PowerServo(book, lambda: rig.drives[300], lambda v: rig.set(300, v),
                       rig.mark, rig.mean, rig.safe, rig.off, settle_s=0, timeout_s=5)
    servo.start('Red 640 nm', 2)  # target raw 180 → drive 20 % on the gain-8 head
    run_servo(servo)
    assert servo.status == 'reached', servo.message
    assert rig.drives[300] == pytest.approx(20, abs=.5)
    assert servo.power_uw == pytest.approx(2, abs=.05)


# -- slice 2: the session-only attribution ledger ----------------------------------------------

def make_state(green_drive=20., red_drive=0., blocked=False, divider=1, outputs=(True, True)):
    from chisurf.plugins.core.acq.live.laser import LaserState, HeadState, OscillatorState
    osc = OscillatorState(slot=100, base_hz=20e6, divider=divider,
                          burst_lengths=[1, 1, 0, 0, 0, 0, 0, 0],
                          output_enabled=list(outputs) + [False] * (8 - len(outputs)))
    heads = [HeadState(slot=200, name='Green 488 nm', output=0, intensity_pct=green_drive),
             HeadState(slot=300, name='Red 640 nm', output=1, intensity_pct=red_drive)]
    return LaserState(model='sim', heads=heads, oscillator=osc, emission_blocked=blocked)


class FakeShutters:
    def __init__(self, excitation=1.):
        self.excitation = excitation

    def get_parameter(self, name, channel=-1):
        return {'reported_excitation': self.excitation,
                'reported_green': 1., 'reported_red': 1.}.get(name, -1.)


def fingerprint(name):
    return f'fp:{name}'


def attributed_context(state=None):
    """A ledger with a passive dark and a verified Green-alone entry (220 raw, 2 µW)."""
    from chisurf.plugins.core.acq.live.diode_context import DiodeContext
    state = state or make_state()
    ctx = DiodeContext()
    ctx.bind_heads(state)
    assert ctx.offer_dark(20.)
    green = state.heads[0]
    ctx.record(state=state, shutters=FakeShutters(), head=green,
               alone_raw=220., uw=2., calibration=fingerprint(green.name))
    return ctx


def test_offset_is_the_other_heads_net_contribution_over_the_shared_dark():
    from chisurf.plugins.core.acq.live.diode_context import UnknownContribution
    state = make_state(red_drive=30.)
    ctx = attributed_context(state)
    assert ctx.offset(state=state, shutters=FakeShutters(),
                      calibration_of=fingerprint, exclude_slot=300) == pytest.approx(200.)
    # the dark is counted once, not per head: a second attributed head adds its net, not its alone raw
    red = state.heads[1]
    ctx.record(state=state, shutters=FakeShutters(), head=red,
               alone_raw=260., uw=3., calibration=fingerprint(red.name))
    assert ctx.offset(state=state, shutters=FakeShutters(),
                      calibration_of=fingerprint, exclude_slot=200) == pytest.approx(240.)


def test_unknown_or_changed_contribution_is_a_named_refusal_not_a_number():
    from chisurf.plugins.core.acq.live.diode_context import DiodeContext, UnknownContribution
    empty = DiodeContext()
    state = make_state(red_drive=30.)
    empty.bind_heads(state)
    with pytest.raises(UnknownContribution, match='dark'):
        empty.offset(state=state, shutters=FakeShutters(),
                     calibration_of=fingerprint, exclude_slot=300)
    ctx = attributed_context(state)
    with pytest.raises(UnknownContribution, match='no verified'):
        ctx.offset(state=state, shutters=FakeShutters(),
                   calibration_of=fingerprint, exclude_slot=200)  # Red has no entry


def test_changed_drive_pulse_clock_shutters_or_calibration_refuses_with_the_head_named():
    from chisurf.plugins.core.acq.live.diode_context import UnknownContribution
    # The entry is recorded under the default state; each case then changes ONE
    # condition before the attribution, and the ledger must refuse with the head
    # named instead of attributing through changed conditions.
    for drive in (25., 0.):
        ctx = attributed_context()
        with pytest.raises(UnknownContribution, match='Green 488 nm'):
            ctx.offset(state=make_state(green_drive=drive), shutters=FakeShutters(),
                       calibration_of=fingerprint, exclude_slot=300)
    from chisurf.plugins.core.acq.live.laser import HeadState
    pulsed = make_state()
    pulsed.heads[0] = HeadState(slot=200, name='Green 488 nm', output=0,
                                intensity_pct=20., pulsed=False)
    ctx = attributed_context()
    with pytest.raises(UnknownContribution, match='pulse'):
        ctx.offset(state=pulsed, shutters=FakeShutters(),
                   calibration_of=fingerprint, exclude_slot=300)
    clocked = make_state(divider=2)
    ctx = attributed_context()
    with pytest.raises(UnknownContribution, match='clock|oscillator'):
        ctx.offset(state=clocked, shutters=FakeShutters(),
                   calibration_of=fingerprint, exclude_slot=300)
    ctx = attributed_context()
    with pytest.raises(UnknownContribution, match='shutter|beam'):
        ctx.offset(state=make_state(), shutters=FakeShutters(excitation=0.),
                   calibration_of=fingerprint, exclude_slot=300)
    ctx = attributed_context()
    with pytest.raises(UnknownContribution, match='calibration'):
        ctx.offset(state=make_state(), shutters=FakeShutters(),
                   calibration_of=lambda name: 'fp:changed',
                   exclude_slot=300)


def test_head_list_change_and_rising_block_invalidate_the_ledger():
    state = make_state()
    ctx = attributed_context(state)
    moved = make_state()
    moved.heads[1].output = 0  # the sequencer mapping is part of head identity
    assert ctx.bind_heads(moved) is True
    assert not ctx.entries and ctx.dark is None
    ctx = attributed_context(state)
    assert ctx.bind_heads(make_state()) is False, 'an unchanged list must not clear'
    ctx = attributed_context(state)
    assert ctx.invalidate_blocked(False) is False
    assert ctx.invalidate_blocked(False) is False
    assert ctx.invalidate_blocked(True) is True, 'a rising global block invalidates attributions'
    assert not ctx.entries
    assert ctx.dark is not None, 'the dark stays valid: it is re-captured passively anyway'
    assert ctx.invalidate_blocked(True) is False, 'staying blocked clears nothing new'


def test_dark_is_only_accepted_from_passive_states_and_mismatch_reason_reads_it():
    from chisurf.plugins.core.acq.live.diode_context import DiodeContext
    state = make_state(green_drive=0., red_drive=0.)
    ctx = DiodeContext()
    ctx.bind_heads(state)
    assert ctx.offer_dark(-1.) is False, 'a missing reading is not a dark'
    assert ctx.offer_dark(20.) is True
    assert ctx.dark == 20.
    assert ctx.offer_dark(25.) is True, 'a later passive reading refreshes the dark'
    reason = ctx.mismatch_reason(state=make_state(red_drive=30.), shutters=FakeShutters(),
                                 calibration_of=fingerprint, exclude_slot=300)
    assert reason and 'Green 488 nm' in reason and 'no verified' in reason


# -- slice 3: the routine gesture on the simulated rig ------------------------------------------
# The rig (SimShutters): raw = 20 + 10*green% + 8*red%; seeded book curves
# Green (20,0),(1020,10) and Red (20,0),(820,10). Green 2 µW sits at drive
# 20 % / alone raw 220, Red 3 µW at drive 30 % / alone raw 260.

def make_model(tmp_path):
    from chisurf.plugins.core.acq.gui.record_app import RecordModel
    m = RecordModel(output_dir=tmp_path, realtime=False)
    assert m.connect_instrument_simulator()
    return m


def settle(m):
    assert m.power_servo is not None
    m.power_servo.settle_s = 0
    end = time.monotonic() + 6
    while m.power_servo.active and time.monotonic() < end:
        m.power_poll(force=True)
        time.sleep(.005)
    assert m.power_servo.status == 'reached', m.power_message


def capture_dark(m):
    """The UI's idle polling: two passive polls populate the shared dark."""
    m.power_poll(force=True)
    m.power_poll(force=True)
    assert m.diode_context.dark is not None


def drive(m, slot):
    return next(h.intensity_pct for h in m.laser.state().heads if h.slot == slot)


def test_attributed_request_reaches_target_without_touching_the_other_head(tmp_path):
    m = make_model(tmp_path)
    try:
        capture_dark(m)
        m.power_selected_slot = 200
        assert m.request_power_target(200.), m.power_message   # Green alone: isolated path
        settle(m)
        assert drive(m, 200) == pytest.approx(47.9, abs=.5)
        assert 200 in m.diode_context.entries, 'the verified alone point entered the ledger'
        events = list(m.laser.events)
        excitation_before = m.shutters.get_parameter('open_excitation')
        osc_before = list(m.laser.state().oscillator.output_enabled)
        m.power_selected_slot = 300
        assert m.request_power_target(300.), m.power_message   # Green emitting, verified
        settle(m)
        assert drive(m, 300) == pytest.approx(62.8, abs=.5)
        assert drive(m, 200) == pytest.approx(47.9, abs=.5), 'the attributed head stays untouched'
        assert m.power_servo.power_uw == pytest.approx(300, abs=5.0)
        # the ledger stores what the servo verified; its convergence tolerance on
        # raw is max(1, 1% of the target raw), so the offset is 200 within ~2.6
        assert m.power_servo.context_offset == pytest.approx(200., abs=2.6), \
            'the Green net contribution is subtracted'
        assert m.laser.events == events, 'no emission/shutter/oscillator cycling'
        assert m.shutters.get_parameter('open_excitation') == excitation_before
        assert list(m.laser.state().oscillator.output_enabled) == osc_before
        red = m.diode_context.entries[300]
        # alone raw = verified combined - attributed offset, exact by construction,
        # 260 within the servo's raw tolerance
        assert red['alone_raw'] + m.power_servo.context_offset \
            == pytest.approx(m.power_servo.verified_raw, rel=1e-9)
        assert red['alone_raw'] == pytest.approx(260., abs=2.6)
        assert red['uw'] == pytest.approx(300, abs=5.0)
    finally:
        m.close()


def test_unknown_mixture_needs_consent_and_cancel_touches_nothing(tmp_path):
    m = make_model(tmp_path)
    try:
        capture_dark(m)
        # Green is uncalibrated and has no entry in ledger: the mixture is unknown
        m.power_book.records.pop('Green 488 nm', None)
        m.laser.set_head(200, intensity_pct=20.)
        m.set_shutter('Excitation', True)
        m.laser.set_emission(True)
        events = list(m.laser.events)
        m.power_selected_slot = 300
        assert not m.request_power_target(300.)
        assert m.power_change_state == 'pending'
        assert 'Green 488 nm' in m.power_change_warning, m.power_change_warning
        assert 'no calibration' in m.power_change_warning or 'no verified' in m.power_change_warning
        assert 'zero' in m.power_change_warning.lower()
        assert drive(m, 200) == 20. and drive(m, 300) == 0., 'no drive changed before confirmation'
        assert m.laser.events == events, 'nothing was touched before confirmation'
        assert m.cancel_power_change()
        assert m.pending_power_change is None
        assert drive(m, 200) == 20. and drive(m, 300) == 0.
        assert m.laser.events == events
    finally:
        m.close()


def test_drive_change_on_other_head_calculates_offset_and_adjusts_without_zeroing(tmp_path):
    m = make_model(tmp_path)
    try:
        capture_dark(m)
        m.power_selected_slot = 200
        assert m.request_power_target(200.), m.power_message
        settle(m)
        m.laser.set_head(200, intensity_pct=50.)   # manual edit on Green: 50% drive (offset ~232.4)
        events = list(m.laser.events)
        m.power_selected_slot = 300
        assert m.request_power_target(300.), m.power_message   # Adjusting Red works!
        settle(m)
        assert drive(m, 200) == 50., 'other head stays emitting at 50%'
        assert drive(m, 300) == pytest.approx(62.8, abs=.5)
        assert m.power_servo.power_uw == pytest.approx(300, abs=5.0)
        assert m.power_servo.context_offset == pytest.approx(232.4, abs=3.5)
    finally:
        m.close()


def test_passive_dark_is_captured_without_extra_emissions(tmp_path):
    m = make_model(tmp_path)   # connecting already polled once: one passive sample
    try:
        events = list(m.laser.events)
        assert all(e != 'emission on' for e in events), 'nothing was allowed to emit'
        assert all(drive(m, slot) == 0. for slot in (200, 300))
        assert m.diode_context.dark is None, 'one passive poll is not a dark yet'
        m.power_poll(force=True)   # the second passive poll completes the capture
        assert m.diode_context.dark == pytest.approx(20.)
        assert m.laser.events == events, 'the passive capture emitted nothing'
        assert all(drive(m, slot) == 0. for slot in (200, 300))
    finally:
        m.close()
