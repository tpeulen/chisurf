"""Per-laser average-power calibration and bounded readback control.

A calibration consists only of manually measured (diode raw, objective µW)
pairs for a laser. Repetition rate and pulse timing are not calibration keys.
Feedback uses a fresh diode average after each drive edit, never enables emission,
and refuses mixed-laser readings or extrapolation.
"""
from __future__ import annotations

import calendar
from datetime import date
import json
import math
import os
from pathlib import Path
import time


def _number(value):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('Readings must be finite, non-negative numbers.')
    return value


def _expiry(day):
    idx = day.year * 12 + day.month - 1 + 3
    year, month0 = divmod(idx, 12)
    month = month0 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class PowerBook:
    """A JSON book of independent, manually measured laser calibrations."""
    schema = 'chisurf.average-power/1'

    def __init__(self, path):
        self.path = Path(path)
        self.records = {}

    def lasers(self):
        return sorted(self.records)

    def points(self, laser):
        return list(self.records.get(str(laser), {}).get('points', []))

    def reset(self, laser):
        if not str(laser).strip():
            raise ValueError('Select a laser first.')
        self.records[str(laser)] = {'measured': date.today().isoformat(), 'points': []}

    @staticmethod
    def _validate(points):
        pairs = sorted([[_number(p[0]), _number(p[1])] for p in points])
        for previous, current in zip(pairs, pairs[1:]):
            if current[0] <= previous[0] or current[1] <= previous[1]:
                raise ValueError('Diode and µW values must both increase; recheck duplicate or inconsistent readings.')
        return pairs

    def add(self, laser, raw, uw):
        laser = str(laser).strip()
        if not laser:
            raise ValueError('Select a laser first.')
        if laser in self.records and self.points(laser):
            self._record(laser, require_pair=False)
        pairs = self._validate(self.points(laser) + [[raw, uw]])
        self.records[laser] = {'measured': date.today().isoformat(), 'points': pairs}

    def remove(self, laser, row):
        points = self.points(laser)
        index = int(row)
        if not 0 <= index < len(points):
            raise ValueError('Select a measured row first.')
        del points[index]
        self.records[str(laser)]['points'] = points

    def _record(self, laser, today=None, require_pair=True):
        rec = self.records.get(str(laser))
        if not rec:
            raise ValueError('No measured power calibration for this laser.')
        measured = date.fromisoformat(rec['measured'])
        today = today or date.today()
        if measured > today:
            raise ValueError('Calibration date is in the future.')
        if today >= _expiry(measured):
            raise ValueError('Calibration expired: start a new measured set (three-calendar-month limit).')
        points = self._validate(rec['points'])
        if require_pair and len(points) < 2:
            raise ValueError('Enter at least two measured points for this laser.')
        return points

    @staticmethod
    def _interpolate(points, value, axis):
        value = _number(value)
        xs = [p[axis] for p in points]
        ys = [p[1-axis] for p in points]
        if not xs[0] <= value <= xs[-1]:
            raise ValueError(f'Outside measured calibration range {xs[0]:g}–{xs[-1]:g}; no extrapolation.')
        for i in range(1, len(xs)):
            if value <= xs[i]:
                f = (value-xs[i-1])/(xs[i]-xs[i-1])
                return ys[i-1] + f*(ys[i]-ys[i-1])
        return ys[-1]

    def power(self, laser, raw, today=None):
        return self._interpolate(self._record(laser, today), raw, 0)

    def raw_target(self, laser, uw, today=None):
        return self._interpolate(self._record(laser, today), uw, 1)

    def save(self):
        for rec in self.records.values():
            self._validate(rec['points'])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + '.part')
        with tmp.open('w', encoding='utf-8') as f:
            json.dump({'schema': self.schema, 'lasers': self.records}, f, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def load(self):
        doc = json.loads(self.path.read_text(encoding='utf-8'))
        if doc.get('schema') != self.schema or not isinstance(doc.get('lasers'), dict):
            raise ValueError('Not an average-power calibration book.')
        staged = {}
        for laser, rec in doc['lasers'].items():
            date.fromisoformat(rec['measured'])
            staged[str(laser)] = {'measured': rec['measured'], 'points': self._validate(rec['points'])}
        self.records = staged


class PowerServo:
    """A frame-polled, bounded feedback loop; hardware collaborators are injected.

    ``mark`` resets the diode mean. ``mean`` returns -1 until a NEW sample has
    arrived. Safety checks and shutdown execute on the same UI thread as controls.
    Step limit, convergence, time limit and missing-response checks are engineering
    guards, not sample-specific guarantees against bleaching or damage.
    """
    def __init__(self, book, get_drive, set_drive, mark, mean, safe, off,
                 *, settle_s=.25, timeout_s=15, max_step_pct=2, context_offset=None):
        self.book = book
        self.get_drive, self.set_drive = get_drive, set_drive
        self.mark, self.mean, self.safe, self.off = mark, mean, safe, off
        self.settle_s, self.timeout_s, self.max_step_pct = settle_s, timeout_s, max_step_pct
        #: Net diode contribution of the OTHER heads (alone raw minus shared dark),
        #: subtracted before the calibration book is consulted and for the error;
        #: raw differences stay unshifted for slope and no-response checks.
        #: ``None`` (the default) keeps the historical single-head behaviour (offset 0).
        self.context_offset = 0. if context_offset is None else float(context_offset)
        self.active = False
        self.status = 'idle'
        self.message = 'No target requested.'
        self.power_uw = None
        self.raw = None
        self.verified_raw = None

    def start(self, laser, target_uw):
        if self.active:
            raise ValueError('Cancel the current power adjustment first.')
        raw_target = self.book.raw_target(laser, target_uw)
        if not self.safe():
            raise ValueError('Power adjustment blocked: select one emitting laser, close other laser outputs and verify the excitation shutter.')
        self.laser, self.target_uw, self.target_raw = str(laser), float(target_uw), raw_target
        self.started_at = self.last_change = time.monotonic()
        self.active, self.status = True, 'adjusting'
        self.message = 'Waiting for a fresh diode reading…'
        self.previous = None
        self.raw = self.verified_raw = None
        self.iterations = self.no_response = self.stable = 0
        try:
            self.mark()
        except Exception as exc:
            self.fail(str(exc))
            raise ValueError(self.message) from exc

    def fail(self, reason):
        self.active, self.status = False, 'failed'
        self.message = str(reason) + ' Laser emission blocked.'
        self.off()

    def cancel(self):
        if self.active:
            self.fail('Power adjustment cancelled.')

    def poll(self, now=None):
        if not self.active:
            return
        now = time.monotonic() if now is None else now
        try:
            if not self.safe():
                raise ValueError('Laser isolation or shutter readback changed.')
            if now-self.started_at > self.timeout_s:
                raise ValueError('Power adjustment timed out; no verified target reached.')
            if now-self.last_change < self.settle_s:
                return
            raw = float(self.mean())
            if raw < 0:
                return  # no fresh diode callback since mark
            self.raw = raw
            # With attributed other heads the combined reading is shifted by their
            # verified net contribution before the calibration is consulted; slope,
            # no-response and negative-slope checks stay on the unshifted differences.
            effective = raw - self.context_offset
            self.power_uw = self.book.power(self.laser, effective)
            error = self.target_raw-effective
            tolerance = max(1., .01*abs(self.target_raw))
            if abs(error) <= tolerance:
                self.stable += 1
                if self.stable >= 2:
                    self.active, self.status = False, 'reached'
                    # the fresh, converged combined reading that verified the target
                    self.verified_raw = raw
                    self.message = f'Target verified: {self.power_uw:.3g} µW.'
                    return
                self.mark()
                self.last_change = now
                return
            self.stable = 0
            drive = _number(self.get_drive())
            step = self.max_step_pct if error > 0 else -self.max_step_pct
            if self.previous is not None:
                old_drive, old_raw = self.previous
                delta_drive = drive-old_drive
                delta_raw = raw-old_raw
                self.no_response = self.no_response+1 if abs(delta_raw) < .5 else 0
                if self.no_response >= 2:
                    raise ValueError('Diode did not respond to drive changes; check shutter, selected head and sensor.')
                if abs(delta_drive) > 1e-6 and abs(delta_raw) >= .5:
                    slope = delta_raw/delta_drive
                    if slope <= 0:
                        raise ValueError('Diode moved opposite to the commanded drive; adjustment stopped.')
                    step = max(-self.max_step_pct, min(self.max_step_pct, .8*error/slope))
            value = max(0., min(100., drive+step))
            if abs(value-drive) < 1e-6:
                raise ValueError('Drive limit reached without reaching the requested µW.')
            self.previous = (drive, raw)
            self.set_drive(value)
            self.mark()
            self.last_change = now
            self.iterations += 1
            if self.iterations > 50:
                raise ValueError('Maximum adjustment steps reached.')
            self.message = f'Adjusting: {self.power_uw:.3g} µW; target {self.target_uw:g} µW.'
        except Exception as exc:
            self.fail(str(exc))
