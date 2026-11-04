"""Average-power calibration and bounded fresh-readback feedback."""
from datetime import date
import pytest


def test_only_laser_and_manual_pairs_are_needed(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerBook
    book = PowerBook(tmp_path / 'power.json')
    book.add('488 nm', 100, 1)
    book.add('488 nm', 300, 3)
    book.save()
    loaded = PowerBook(book.path)
    loaded.load()
    assert loaded.power('488 nm', 200) == pytest.approx(2)
    assert loaded.raw_target('488 nm', 2) == pytest.approx(200)
    with pytest.raises(ValueError, match='range'):
        loaded.power('488 nm', 400)
    assert loaded.lasers() == ['488 nm']


def test_invalid_or_expired_calibration_is_not_used(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerBook
    b = PowerBook(tmp_path/'power.json')
    b.add('red', 0, 0)
    b.add('red', 100, 5)
    with pytest.raises(ValueError):
        b.add('red', 50, 8)
    with pytest.raises(ValueError):
        b.add('red', float('nan'), 1)
    with pytest.raises(ValueError, match='expired'):
        b.power('red', 50, today=date(2030, 1, 1))


class Rig:
    def __init__(self):
        self.drive = 10.
        self.marked = False
        self.blocked = False
        self.bad = False
        self.writes = []
    def mark(self):
        self.marked = True
    def mean(self):
        assert self.marked
        return -1 if self.bad else 10 * self.drive
    def set_drive(self, value):
        self.drive = value
        self.writes.append(value)
    def safe(self):
        return not self.blocked
    def off(self):
        self.blocked = True


def test_feedback_reaches_target_without_enabling_emission(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerBook, PowerServo
    b = PowerBook(tmp_path/'p.json')
    b.add('red', 0, 0);b.add('red', 1000, 10)
    rig = Rig()
    c = PowerServo(b, lambda: rig.drive, rig.set_drive, rig.mark, rig.mean, rig.safe, rig.off,
                   settle_s=0, timeout_s=5)
    c.start('red', 2)
    for _ in range(40):
        c.poll()
        if not c.active:break
    assert c.status == 'reached', c.message
    assert rig.drive == pytest.approx(20, abs=.5)
    assert all(0 <= x <= 100 for x in rig.writes)
    assert not rig.blocked


def test_feedback_fail_closed_on_stale_readback_or_lost_isolation(tmp_path):
    from chisurf.plugins.core.acq.live.average_power import PowerBook, PowerServo
    b = PowerBook(tmp_path/'p.json');b.add('red',0,0);b.add('red',1000,10)
    rig = Rig()
    c = PowerServo(b, lambda: rig.drive, rig.set_drive, rig.mark, rig.mean, rig.safe, rig.off, settle_s=0)
    c.start('red', 2)
    rig.blocked = True
    c.poll()
    assert c.status == 'failed'
    assert not rig.writes
    rig.blocked = False;rig.bad = True
    c.start('red', 2)
    c.poll(now=c.started_at+99)
    assert c.status == 'failed' and rig.blocked
    assert not rig.writes
