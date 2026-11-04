"""Tests for nag-free laser power adjustments in advanced mode and ignore checkbox in simple mode."""
from pathlib import Path
import time
import pytest
from chisurf.plugins.core.acq.gui.laser_cards import _confirm_or_apply
from chisurf.plugins.core.acq.gui.record_app import RecordApp, RecordModel
from chisurf.plugins.microscopy.imaging_emtk.testing import Driver


def make_model(tmp_path):
    m = RecordModel(output_dir=tmp_path, realtime=False)
    assert m.connect_instrument_simulator()
    return m


def settle(m):
    assert m.power_servo is not None
    m.power_servo.settle_s = 0
    end = time.monotonic() + 6
    while m.power_servo.active and time.monotonic() < end:
        m.power_poll(force=True)
        time.sleep(0.005)
    assert m.power_servo.status == 'reached', m.power_message


def test_advanced_mode_power_target_does_not_nag(tmp_path):
    m = make_model(tmp_path)
    try:
        m.recorded_paths.append(Path('prior-measurement.ptu'))
        m.advanced = True
        assert m.power_change_nags_suppressed()

        # In advanced mode, adjusting power target directly applies without confirmation
        assert m.request_power_target(3)
        assert m.pending_power_change is None
        assert m.power_change_state == 'idle'
        settle(m)
        assert m.power_target_uw == 3
        assert len(m.power_change_invalidations) == 1
        assert m.power_change_invalidations[0]['kind'] == 'timing_irf'
    finally:
        m.close()


def test_ui_mode_advanced_power_target_does_not_nag(tmp_path):
    m = make_model(tmp_path)
    try:
        m.recorded_paths.append(Path('prior-measurement.ptu'))
        m.ui_mode = 'advanced'
        m.ui_mode_changed()
        assert m.advanced
        assert m.power_change_nags_suppressed()

        assert m.request_power_target(2.5)
        assert m.pending_power_change is None
        settle(m)
        assert m.power_target_uw == 2.5
    finally:
        m.close()


def test_simple_mode_nags_until_ignore_checked_then_persists_for_session(tmp_path):
    m = make_model(tmp_path)
    app = RecordApp(m)
    try:
        m.recorded_paths.append(Path('prior-measurement.ptu'))
        assert not m.advanced
        assert not m.power_change_ignore
        assert not m.power_change_nags_suppressed()

        # In simple mode, power target request stages confirmation
        assert not m.request_power_target(3)
        assert m.pending_power_change == 3

        ui = Driver(app, (1500, 950))
        ui.draw(3)
        strings = ui.strings()
        assert 'Change laser power?' in strings
        assert 'Ignore' in strings
        assert 'power_change.checkbox' in app.item_rects

        # Click the 'Ignore' checkbox and 'Yes'
        ui.click_text('Ignore')
        ui.click_text('Yes')
        assert m.power_change_ignore is True
        assert m.power_change_nags_suppressed() is True
        assert m.pending_power_change is None
        settle(m)
        assert m.power_target_uw == 3

        # Subsequent power adjustment in Simple mode must NOT nag (remembered for session)
        assert m.request_power_target(4)
        assert m.pending_power_change is None
        settle(m)
        assert m.power_target_uw == 4
    finally:
        app.close()


def test_simple_mode_without_ignore_continues_nagging(tmp_path):
    m = make_model(tmp_path)
    app = RecordApp(m)
    try:
        m.recorded_paths.append(Path('prior-measurement.ptu'))
        assert not m.request_power_target(3)
        assert m.pending_power_change == 3

        ui = Driver(app, (1500, 950))
        ui.draw(3)
        assert 'Change laser power?' in ui.strings()

        # Answer Yes WITHOUT checking Ignore
        ui.click_text('Yes')
        assert m.power_change_ignore is False
        assert m.pending_power_change is None
        settle(m)

        # Another change in simple mode must still nag
        assert not m.request_power_target(4)
        assert m.pending_power_change == 4
    finally:
        app.close()


def test_laser_cards_confirm_or_apply_suppressed_in_advanced_and_ignored(tmp_path):
    m = make_model(tmp_path)
    app = RecordApp(m)
    try:
        m.recorded_paths.append(Path('prior-measurement.ptu'))
        applied = []

        # 1. Advanced mode: applies immediately without dialog
        m.advanced = True
        _confirm_or_apply(app, m, lambda: applied.append('adv'))
        assert applied == ['adv']
        assert any(inv['reason'] == 'laser drive or pulse mode changed' for inv in m.power_change_invalidations)
        assert getattr(app, '_power_change_dialogs', None) is None or not app._power_change_dialogs.pending

        # 2. Simple mode without ignore: prompts dialog
        m.advanced = False
        m.power_change_ignore = False
        _confirm_or_apply(app, m, lambda: applied.append('simple'))
        assert app._power_change_dialogs is not None
        assert app._power_change_dialogs.pending
        assert 'Change laser drive / pulse mode?' in app._power_change_dialogs.pending[0].title

        # Check Ignore and answer Yes
        app._power_change_dialogs.ignore_checked = True
        app._power_change_dialogs.answer(key='yes')
        assert m.power_change_ignore is True
        assert applied == ['adv', 'simple']

        # 3. Simple mode with ignore: applies immediately without dialog
        _confirm_or_apply(app, m, lambda: applied.append('ignored'))
        assert applied == ['adv', 'simple', 'ignored']
    finally:
        app.close()
