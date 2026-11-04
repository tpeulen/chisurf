"""Compact average-power UI, the µW request gesture and post-measurement warnings.

The legacy pulse-conditioned panel is not used by Record. Manual entries below are the
objective meter reading paired with the diode reading, per laser.

Two ways to reach a power exist, and only one of them may switch light on:

* :meth:`AveragePowerMixin.request_power_target` -- the one user gesture (the committed
  target slider). It validates the target before anything changes, then -- because the
  explicit user target authorizes light -- zeroes the other heads, opens the excitation
  shutter, enables the selected head and verifies the reported readback before the
  existing :class:`~chisurf.plugins.core.acq.live.average_power.PowerServo` drives from
  fresh diode averages. When the OTHER heads are emitting and their diode contributions
  are verified against live readback (the session's
  :class:`~chisurf.plugins.core.acq.live.diode_context.DiodeContext` ledger), their net
  contribution is subtracted instead and those heads, the oscillator and the shutters
  stay untouched; the verified convergence point is recorded into the ledger. An unknown
  or changed mixture is never silently isolated: the request is staged as
  ``pending_power_change`` with a warning that confirming will zero the other heads. A
  target of zero disables the selected head and never enables emission. When this
  session's recordings or the wizard's reference measurements refer
  to the current power, the request is staged as ``pending_power_change`` with a
  ``power_change_warning`` and nothing at all is touched until
  :meth:`AveragePowerMixin.confirm_power_change`; a change is refused while a measurement
  runs -- stop it first, nothing is stopped for you. A confirmed change marks dependent
  timing/IRF calibrations invalidated; the average-power calibration book is independent
  of the operating point and is never touched.
* :meth:`AveragePowerMixin.set_power_target` -- the direct seam for the guided wizard's
  approved-power step, which opens the shutter and allows emission itself as its own
  explicit authorization. It never raises a confirmation (a wizard stage transition must
  not be re-prompted) but keeps the isolation and single-emitting-head checks.

Selecting a head, polling state and rendering never energize hardware.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from emtk import im
from emtk.i18n import tr
from emtk.message_dialog import (
    KEY_ENTER,
    KEY_ESCAPE,
    KEY_RETURN,
    KEY_ROLES,
    ROLE_COLOURS,
    MessageDialogs,
    _core,
    _w,
)
from emtk.view_form import FormState, draw_sections
from chisurf.plugins.core.acq.live.average_power import PowerBook, PowerServo
from chisurf.plugins.core.acq.live.diode_context import DiodeContext, UnknownContribution
from chisurf.plugins.core.acq.live.instrument_sim import laser_diode_threshold, laser_diode_power_fraction

HERE = Path(__file__).parent

#: How long a request waits for a shutter readback to settle before refusing; the servo
#: then works from verified readback only.
_READBACK_TIMEOUT_S = 1.0

#: How long ``read_diode`` waits for a fresh sample after the diode was marked.
_DIODE_TIMEOUT_S = 2.0

_POLL_S = 0.02


class AveragePowerMixin:
    """Share one calibration book between the Laser page, calibration and wizard."""

    if TYPE_CHECKING:
        # The host's side of the seam (RecordModel): what this mixin reads and calls.
        laser: Any
        shutters: Any
        laser_connected: bool
        laser_program: dict
        running: bool
        output_dir: Path
        recorded_paths: list
        session: Any
        wizard: Any

        def laser_off(self) -> None: ...
        def set_shutter(self, name: str, open_: bool) -> bool: ...

    def init_average_power(self):
        self.power_selected_slot = -1
        self.power_target_uw = 0.
        self.power_message = 'Select a connected laser and calibrate its diode readings.'
        self.power_servo = None
        self._power_book = None
        self._power_heads = []
        self._power_at = -1e9
        # -- the additive-diode attribution ledger (session-only) ---------------------------------
        #: One shared dark and the verified per-head alone contributions; lets a
        #: routine request leave verified emitting heads untouched instead of
        #: zeroing them. Cleared on head-identity change and rising block.
        self.diode_context = DiodeContext()
        #: Which servo run is active (name/slot), so its verified convergence
        #: point can be recorded into the ledger.
        self._power_servo_context = None
        #: Consecutive passive (all-zero drive) polls, for the shared-dark capture.
        self._power_passive_streak = 0
        # -- the µW request gesture and its post-measurement warning ------------------------------
        #: A validated target (µW) awaiting explicit confirmation; None when nothing is
        #: pending. While set, no hardware or model state has been touched.
        self.pending_power_change = None
        #: 'idle' | 'pending' (confirm_power_change applies it) | 'blocked' (a measurement
        #: is running: stop it first, then request or confirm again).
        self.power_change_state = 'idle'
        #: Why confirmation is required / what a confirmed change implies; empty when idle.
        self.power_change_warning = ''
        #: What applied changes invalidated: timing/IRF calibrations tied to the previous
        #: power. The average-power calibration book is independent and is preserved.
        self.power_change_invalidations: list[dict] = []
        #: The last applied operating point ({'laser': name, 'uw': value}) or None.
        self.power_effective = None
        self.power_targets_uw = {}
        #: Whether power change warnings are ignored for this session (Simple mode checkbox or explicit choice).
        self.power_change_ignore = False
        #: Optional parent hook: ``callable() -> list[str]`` of extra references (e.g.
        #: measurement metadata the Record tool owns) a power change would invalidate.
        self.power_references_hook = None

    @property
    def power_book(self):
        path = Path(self.output_dir) / 'average-power.json'
        if self._power_book is None or self._power_book.path != path:
            book = PowerBook(path)
            if path.exists():
                try:
                    book.load()
                except (ValueError, OSError, KeyError) as exc:
                    self.power_message = f'Calibration could not be loaded: {exc}'
            self._power_book = book
        return self._power_book

    def power_head_options(self):
        return [(h.slot, self._power_label(h)) for h in self._power_heads]

    def _power_label(self, head):
        rec = getattr(self, 'record', self)
        custom = getattr(rec, 'laser_custom_names', {}).get(head.slot)
        if not custom:
            custom = getattr(self, 'laser_custom_names', {}).get(head.slot)
        if custom:
            return custom
        return str(head.name or f'Laser slot {head.slot}')

    def power_head(self):
        return next((h for h in self._power_heads if h.slot == self.power_selected_slot), None)

    def power_laser_name(self):
        head = self.power_head()
        return self._power_label(head) if head is not None else ''

    def power_selection_changed(self, _value=None):
        self.cancel_power_target()
        self.cancel_power_change()
        self.power_message = 'Laser selected. A target never switches emission on automatically.'

    def _power_safe(self):
        if not self.laser_connected or self.shutters is None:
            return False
        state = self.laser.state()
        head = next((h for h in state.heads if h.slot == self.power_selected_slot), None)
        if head is None or state.emission_blocked or state.hardware_locked:
            return False
        return float(self.shutters.get_parameter('reported_excitation', -1)) == 1.

    def isolate_power_laser(self):
        """Explicitly reduce every OTHER head to zero; never enable emission."""
        if not self.laser_connected or self.power_head() is None:
            self.power_message = 'Select a connected laser.'
            return False
        try:
            self.cancel_power_target()
            for h in self.laser.state().heads:
                if h.slot != self.power_selected_slot:
                    self.laser.set_head(h.slot, intensity_pct=0.)
            self.laser_program = self.laser.capture()
            self.power_message = 'Other heads set to zero. Check the beam path; enable emission/open excitation only when ready.'
            return True
        except Exception as exc:
            self.laser_off()
            self.power_message = str(exc)
            return False

    # -- the µW request gesture --------------------------------------------------------------------
    def request_power_target(self, value) -> bool:
        """A committed target (µW): validate, warn about dependents, then change the power.

        Validation happens before anything changes. The change is staged for explicit
        confirmation when this session's recordings, the current session or the wizard's
        reference measurements refer to the current power (``pending_power_change`` /
        ``power_change_warning`` / ``power_change_state``); nothing is touched before
        :meth:`confirm_power_change`. Without such references the committed gesture itself
        authorizes the change: other heads to zero, excitation shutter open, selected head
        enabled -- all through the existing model APIs, verified by readback -- and the
        existing servo drives to the target. Refused while a measurement runs (stop it
        first; nothing is stopped for you). A target of zero disables the selected head
        and never enables emission.
        """
        try:
            target = float(value)
            if not math.isfinite(target) or target < 0:
                raise ValueError('Enter a target of zero or more µW.')
            name = self.power_laser_name()
            if not name:
                raise ValueError('Select a connected laser first.')
            if self.power_servo is not None and self.power_servo.active:
                raise ValueError('Wait for the running power adjustment, or cancel it first.')
            if target > 0:
                # validates the calibration (two consistent in-range points) BEFORE any
                # hardware or state change
                self.power_book.raw_target(name, target)
        except (TypeError, ValueError) as exc:
            if self.power_change_state != 'blocked':
                self.power_change_state = 'idle'
            self.pending_power_change = None
            self.power_message = str(exc)
            return False
        references = self.power_change_references()
        if references and not self.power_change_nags_suppressed():
            self.pending_power_change = target
            self.power_change_state = 'pending'
            self.power_change_warning = (
                f'Requested {target:g} µW on {name}. '
                + '; '.join(references)
                + '. Changing laser drive may change the pulse shape. Confirming changes the power and marks timing/IRF calibrations measured '
                'at the previous power as invalidated; the average-power calibration is '
                'independent and stays valid. Cancel keeps everything as it is.'
            )
            self.power_message = 'Power change needs your confirmation; nothing was changed yet.'
            return False
        return self._apply_power_request(target)

    def confirm_power_change(self) -> bool:
        """Apply the staged target. The only path from 'pending' to the hardware."""
        target = self.pending_power_change
        if self.power_change_state != 'pending' or target is None:
            self.power_message = 'No power change is awaiting confirmation.'
            return False
        self.pending_power_change = None
        self.power_change_warning = ''
        ok = self._apply_power_request(target, confirmed=True)
        self.power_change_state = 'idle'
        return ok

    def cancel_power_change(self) -> bool:
        """Drop a staged request. Nothing was mutated, so nothing is undone."""
        if self.power_change_state != 'pending' and self.pending_power_change is None:
            return False
        self.pending_power_change = None
        self.power_change_warning = ''
        self.power_change_state = 'idle'
        self.power_message = 'Power change cancelled; nothing was touched.'
        return True

    def power_change_references(self) -> list[str]:
        """What in this session a power change would invalidate (no hardware access)."""
        refs: list[str] = []
        recorded = getattr(self, 'recorded_paths', None) or []
        if recorded:
            refs.append(f'{len(recorded)} recording(s) of this session carry the previous power in their metadata')
        if getattr(self, 'session', None) is not None:
            refs.append('this session has a measurement')
        wizard = getattr(self, 'wizard', None)
        measurements = getattr(wizard, 'measurements', None) or {}
        if measurements:
            refs.append(f'{len(measurements)} guided reference measurement(s) were recorded')
        hook = getattr(self, 'power_references_hook', None)
        if hook is not None:
            try:
                refs.extend(str(r) for r in (hook() or []))
            except Exception:  # noqa: BLE001 - a broken hook must not block the request
                pass
        return refs

    def power_change_nags_suppressed(self) -> bool:
        """In Advanced mode or when Ignore was checked for the session, do not prompt."""
        return bool(
            getattr(self, 'advanced', False)
            or getattr(self, 'ui_mode', '') == 'advanced'
            or getattr(self, 'power_change_ignore', False)
        )

    def _power_calibration_fingerprint(self, name) -> str:
        """A stable fingerprint of the power calibration a verified point used."""
        rec = self.power_book.records.get(str(name))
        if not rec:
            return f'uncalibrated:{name}'
        return f"{rec.get('measured')}|{json.dumps(rec.get('points', []), sort_keys=True)}"

    def _power_track_context(self, state):
        """Idle-poll bookkeeping for the attribution ledger: head identity, the
        rising global block, and the shared dark -- captured ONLY from naturally
        all-zero drives across two consecutive polls (no on/off cycles, no sleeps,
        no emission is ever enabled here)."""
        ctx = self.diode_context
        ctx.bind_heads(state)
        ctx.invalidate_blocked(bool(state.emission_blocked))
        if any(h.intensity_pct > 0 for h in state.heads):
            self._power_passive_streak = 0
            return
        raw = -1.
        if self.shutters is not None:
            try:
                raw = float(self.shutters.get_parameter('diode_raw', -1))
            except Exception:  # noqa: BLE001 - the next poll tries again
                raw = -1.
        if raw < 0 and hasattr(self.laser, 'get_parameter'):
            try:
                raw = float(self.laser.get_parameter('diode_raw', -1))
            except Exception:
                raw = -1.
        if raw >= 0 and math.isfinite(raw):
            self._power_passive_streak += 1
            if self._power_passive_streak >= 2:
                ctx.offer_dark(raw)
        else:
            self._power_passive_streak = 0

    def calculate_diode_offset(self, exclude_slot) -> float:
        """Calculate the photodiode offset from all emitting heads other than exclude_slot."""
        total_offset = 0.0
        state = self.laser.state()
        ctx = self.diode_context
        ctx.bind_heads(state)
        dark = ctx.dark
        if dark is None:
            for head in state.heads:
                h_name = str(getattr(head, 'name', None) or f'Laser slot {head.slot}')
                try:
                    pts = self.power_book._record(h_name, require_pair=False)
                    if pts:
                        dark = pts[0][0]
                        ctx.dark = dark
                        break
                except Exception:
                    pass
        if dark is None:
            dark = 0.0

        for head in state.heads:
            if head.slot == exclude_slot:
                continue
            if not DiodeContext.head_emitting(head, state):
                continue
            h_name = str(getattr(head, 'name', None) or f'Laser slot {head.slot}')
            entry = ctx.entries.get(head.slot)
            if entry is not None and abs(entry.get('drive_pct', -1) - head.intensity_pct) < 1e-4:
                entry_dark = ctx.dark if ctx.dark is not None else dark
                total_offset += max(0.0, entry['alone_raw'] - entry_dark)
                continue
            try:
                pts = self.power_book._record(h_name, require_pair=False)
            except Exception:
                pts = None
            if pts:
                h_dark = pts[0][0]
                max_raw = pts[-1][0]
                drive_pct = float(head.intensity_pct)
                d_th = laser_diode_threshold(head)
                frac = laser_diode_power_fraction(drive_pct, d_th)
                total_offset += max(0.0, (max_raw - h_dark) * frac)
        return total_offset

    def _power_context_check(self, state, slot) -> tuple:
        """Attribute the emitting OTHER heads from the ledger or calibration book."""
        ctx = self.diode_context
        ctx.bind_heads(state)
        try:
            offset = ctx.offset(state=state, shutters=self.shutters,
                                calibration_of=self._power_calibration_fingerprint,
                                exclude_slot=slot)
            return None, offset
        except UnknownContribution as exc:
            all_had_entries = all(
                h.slot in ctx.entries
                for h in state.heads
                if h.slot != slot and DiodeContext.head_emitting(h, state)
            )
            if not all_had_entries and not self.advanced and not getattr(self, 'ignore_power_nag', False):
                return (str(exc), None)
            offset = self.calculate_diode_offset(exclude_slot=slot)
            return None, offset

    def _apply_power_request(self, target, confirmed=False) -> bool:
        """The authorized change. With other heads emitting and their diode
        contributions verified+unchanged, the servo subtracts their attributed
        offset and the other heads, oscillator and shutters stay untouched. An
        unknown or changed mixture is never silently isolated: it is staged for
        explicit confirmation (whose warning says confirming will zero the other
        heads) unless the caller already confirmed. A target of zero disables the
        selected head and never enables emission."""
        try:
            name = self.power_laser_name()
            slot = self.power_selected_slot
            if not name:
                raise ValueError('Select a connected laser first.')
            if target <= 0:
                self.cancel_power_target()
                self.laser_off()  # blocks emission; never raises
                head = next((h for h in self.laser.state().heads if h.slot == slot), None)
                if head is None:
                    raise ValueError('The selected laser disappeared.')
                self.laser.set_head(slot, enabled=False, intensity_pct=0.)
                self.laser_program = self.laser.capture()
                head = next((h for h in self.laser.state().heads if h.slot == slot), None)
                if head is None or head.intensity_pct != 0:
                    raise ValueError('The head did not report zero drive; emission stays blocked.')
                self.power_change_state = 'idle'
                self.power_effective = {'laser': name, 'uw': 0.}
                self.power_target_uw = 0.
                self.power_message = f'{name} disabled: drive zero, head off, emission blocked. No shutter was opened.'
                return True
            state = self.laser.state()
            head = next((h for h in state.heads if h.slot == slot), None)
            if head is None:
                raise ValueError('The selected laser disappeared.')
            others_emitting = [h for h in state.heads
                               if h.slot != slot and
                               # emitting now, or driven and session-verified: the latter are
                               # preserved via their attributed offset, never silently zeroed
                               # (that holds also while emission is blocked between requests)
                               (DiodeContext.head_emitting(h, state)
                                or (h.intensity_pct > 0
                                    and h.slot in self.diode_context.entries))]
            if others_emitting:
                reason, offset = self._power_context_check(state, slot)
                if reason is None:
                    return self._apply_attributed_power(name, slot, target, state, head, offset)
                if not confirmed:
                    # an unknown/changed mixture: stage for explicit consent with the
                    # named reason; NOTHING is touched -- in particular no isolation
                    self.pending_power_change = float(target)
                    self.power_change_state = 'pending'
                    self.power_change_warning = (
                        f'Requested {target:g} µW on {name} while other heads are emitting, '
                        f'but their diode contribution is not verified for this session: '
                        f'{reason} Confirming sets every other head to zero before the '
                        'adjustment; cancel keeps everything as it is.'
                    )
                    self.power_message = 'Mixed-laser power change needs your confirmation; nothing was changed yet.'
                    return False
            if not self.isolate_power_laser():
                raise ValueError(self.power_message)
            if not self._open_excitation_verified():
                raise ValueError('The excitation shutter did not report open; nothing was allowed to emit.')
            self.laser.set_head(slot, enabled=True)
            self.laser.set_emission(True)
            state = self.laser.state()
            if state.emission_blocked or not any(h.slot == slot for h in state.heads):
                raise ValueError('The laser did not confirm the enabled head; emission stays blocked.')
            if not self._start_power_servo(name, slot, target):
                raise ValueError(self.power_message)
            self.power_target_uw=float(target)
            self._note_power_change(name, target)
            self.power_change_state = 'idle'
            return True
        except Exception as exc:
            self.laser_off()
            self.power_message = str(exc)
            self.power_change_state = 'idle'
            return False

    def _apply_attributed_power(self, name, slot, target, state, head, offset) -> bool:
        """The verified-mixture change: leave the other heads, oscillator and
        shutters untouched and let the servo subtract their attributed net
        contribution (``offset``) before the calibration is consulted."""
        try:
            # captured once: the servo must judge against THIS mixture, never the
            # mutable UI selection or a later state
            snapshot = {h.slot: float(h.intensity_pct)
                        for h in state.heads if h.slot != slot}
            # enabling THIS head's own output is what the explicit request authorizes;
            # a shared output that would energize another head is refused, never silent
            shared = [h for h in state.heads
                      if h.slot != slot and head.output >= 0 and h.output == head.output]
            if shared and any(h.intensity_pct > 0 or h.slot in self.diode_context.entries
                              for h in shared):
                raise ValueError(
                    f'Sequencer output {head.output} also drives {shared[0].name}; enabling '
                    'it is a separate consent step and is not part of this power request.')
            if head.intensity_pct <= 0:
                self.laser.set_head(slot, enabled=True)
            if state.emission_blocked:
                self.laser.set_emission(True)
            if float(self.shutters.get_parameter('reported_excitation', -1)) != 1.:
                if not self._open_excitation_verified():
                    raise ValueError('The excitation shutter does not report open; nothing was changed.')
            fresh = self.laser.state()
            if (fresh.emission_blocked or fresh.hardware_locked
                    or next((h for h in fresh.heads if h.slot == slot), None) is None):
                raise ValueError('The laser did not confirm the enabled head; emission stays blocked.')
            for h in fresh.heads:
                if h.slot != slot and abs(float(h.intensity_pct) - snapshot.get(h.slot, -1.)) > 1e-6:
                    raise ValueError(f'{h.name} changed while the request was prepared; nothing was changed.')

            ctx = self.diode_context

            def safe():
                if self.power_selected_slot != slot or self.power_laser_name() != name:
                    return False
                if not self.laser_connected or self.shutters is None:
                    return False
                try:
                    st = self.laser.state()
                    if st.emission_blocked or st.hardware_locked:
                        return False
                    if next((h for h in st.heads if h.slot == slot), None) is None:
                        return False
                    if float(self.shutters.get_parameter('reported_excitation', -1)) != 1.:
                        return False
                    for h in st.heads:
                        if h.slot == slot:
                            continue
                        if (h.slot not in snapshot
                                or abs(float(h.intensity_pct) - snapshot[h.slot]) > 1e-6):
                            return False  # a contributing head changed or a new one appeared
                    reason, _ = self._power_context_check(st, slot)
                    if reason is not None:
                        return False
                except Exception:  # noqa: BLE001 - unreadable state is not a safe state
                    return False
                return True

            if not self._start_power_servo(name, slot, target, context_offset=offset, safe=safe):
                raise ValueError(self.power_message)
            self.power_target_uw=float(target)
            self._note_power_change(name, target)
            self.power_change_state = 'idle'
            return True
        except Exception as exc:
            self.laser_off()
            self.power_message = str(exc)
            self.power_change_state = 'idle'
            return False
            self.power_change_state = 'idle'
            return False

    def _open_excitation_verified(self) -> bool:
        """Open the excitation shutter (model API) and wait for its reported readback."""
        if not self.set_shutter('Excitation', True):
            return False
        end = time.monotonic() + _READBACK_TIMEOUT_S
        while time.monotonic() < end:
            try:
                if float(self.shutters.get_parameter('reported_excitation', -1)) == 1.:
                    return True
            except Exception:  # noqa: BLE001 - the next poll tries again
                pass
            time.sleep(_POLL_S)
        return False

    def _note_power_change(self, name, target):
        """Track that an applied change invalidates timing/IRF calibrations tied to the
        previous power. The average-power calibration book is independent of the operating
        point and is deliberately not touched."""
        previous, previous_uw = self.power_effective, None
        if previous is not None and previous.get('laser') == name:
            previous_uw = float(previous['uw'])
        if target > 0:
            # only an operating-power change invalidates timing/IRF calibrations; a zero
            # target is a shutdown, and the next nonzero change records from zero
            self.power_change_invalidations.append({
                'kind': 'timing_irf',
                'laser': name,
                'from_uw': previous_uw,
                'to_uw': float(target),
                'when': time.strftime('%Y-%m-%dT%H:%M:%S'),
                'average_power_calibration': 'preserved',
            })
        self.power_effective = {'laser': name, 'uw': float(target)}
        self.power_targets_uw[self.power_selected_slot]=float(target)

    def _start_power_servo(self, name, slot, target_uw, *, context_offset=0., safe=None) -> bool:
        """A validated target into the existing PowerServo, driven from fresh readback.

        ``context_offset`` is the attributed net contribution of the other heads
        (0 for the historical single-head behaviour); ``safe`` replaces the
        isolation-based safety check for the attributed servo."""
        try:
            self.power_book.raw_target(name, target_uw)
            if safe is None:
                def default_safe():
                    return self.power_selected_slot == slot and self.power_laser_name() == name and self._power_safe()
                check: Callable[[], bool] = default_safe
            else:
                check = safe
            def get_drive():
                return next(h.intensity_pct for h in self.laser.state().heads if h.slot == slot)
            def set_drive(value):
                self.laser.set_head(slot, intensity_pct=value)
                self.laser_program = self.laser.capture()
            head = next((h for h in self.laser.state().heads if h.slot == slot), None)
            d_th = laser_diode_threshold(head)
            if float(target_uw) > 0 and head is not None and head.intensity_pct < d_th:
                self.laser.set_head(slot, intensity_pct=d_th)
                self.laser_program = self.laser.capture()
            mark_fn = (lambda: self.shutters.set_parameter('diode_mark', 1.)) if self.shutters is not None else (
                (lambda: self.laser.set_parameter('diode_mark', 1.)) if hasattr(self.laser, 'set_parameter') else (lambda: None)
            )
            mean_fn = (lambda: self.shutters.get_parameter('diode_mean', -1)) if self.shutters is not None else (
                (lambda: self.laser.get_parameter('diode_mean', -1)) if hasattr(self.laser, 'get_parameter') else (lambda: -1.0)
            )
            self.power_servo = PowerServo(
                self.power_book, get_drive, set_drive,
                mark_fn, mean_fn, check, self.laser_off,
                context_offset=context_offset)
            self.power_servo.start(name, target_uw)
            self._power_servo_context = {'name': name, 'slot': slot}
            self.power_message = self.power_servo.message
            return True
        except Exception as exc:
            self.power_message = str(exc)
            return False

    def set_power_target(self):
        """Direct seam for callers that authorize their own light (the guided wizard's
        approved-power step). Keeps the isolation and single-emitting-head checks, never
        raises a confirmation -- wizard stage transitions must not be re-prompted."""
        try:
            if self.power_servo is not None and self.power_servo.active:
                raise ValueError('Power adjustment is already running.')
            self.power_poll(force=True)
            name = self.power_laser_name()
            slot = self.power_selected_slot
            if name and not self.isolate_power_laser():
                raise ValueError(self.power_message)
            if not name or not self._power_safe():
                raise ValueError('Select one emitting laser; isolate the other heads and verify the excitation shutter is open.')
            if not self._start_power_servo(name, slot, self.power_target_uw):
                raise ValueError(self.power_message)
            self._note_power_change(name, self.power_target_uw)
            return True
        except Exception as exc:
            self.power_message = str(exc)
            return False

    def cancel_power_target(self):
        servo = self.power_servo
        if servo is not None and servo.active:
            servo.cancel()
            self.power_message = servo.message

    def calibrate_max_power(self, max_uw: float = 1000.0) -> bool:
        """Calibrate max power (typical 1000 µW / 1 mW) with detector shutters closed.

        SAFETY: Detector shutters MUST be closed during max power calibration to
        protect the detectors from high optical power. Excitation shutter is opened.
        """
        if not self.laser_connected or self.shutters is None or getattr(self, 'running', False):
            return False
        try:
            # 1. Capture current state to restore cleanly
            state = self.laser.state()
            orig_outputs = (list(state.oscillator.output_enabled)
                            if (state.oscillator and hasattr(state.oscillator, 'output_enabled')) else [])
            orig_events = list(getattr(self.laser, 'events', []))
            shutter_names_fn = getattr(self, '_shutter_names', None)
            shutter_key_fn = getattr(self, '_shutter_key', None)
            all_names = shutter_names_fn() if shutter_names_fn else []
            orig_shutters = {}
            for n in all_names:
                param_key = f"open_{shutter_key_fn(n)}" if shutter_key_fn else f"open_{n.lower()}"
                try:
                    orig_shutters[n] = float(self.shutters.get_parameter(param_key, 0.)) == 1.
                except Exception:
                    orig_shutters[n] = False

            # 2. Close all detector shutters to protect detector channels
            detector_names = shutter_names_fn('detector') if shutter_names_fn else []
            if hasattr(self, '_set_shutters'):
                self._set_shutters({n: False for n in detector_names})
            else:
                for n in detector_names:
                    self.set_shutter(n, False)

            # 3. Open excitation shutter
            self.set_shutter('Excitation', True)

            # 4. Read dark diode level with all heads at 0%
            dark_raw = 20.0
            try:
                raw = float(self.shutters.get_parameter('diode_raw', 20.0))
                if math.isfinite(raw) and raw >= 0:
                    dark_raw = raw
            except Exception:
                pass

            # 5. Measure each head at 100% drive
            for head in state.heads:
                slot = head.slot
                name = self._power_label(head)
                for other in state.heads:
                    if other.slot != slot:
                        self.laser.set_head(other.slot, intensity_pct=0.0)
                self.laser.set_head(slot, enabled=True, intensity_pct=100.0)
                self.laser.set_emission(True)
                max_raw = dark_raw + 100.0
                try:
                    raw = float(self.shutters.get_parameter('diode_raw', -1))
                    if math.isfinite(raw) and raw > dark_raw:
                        max_raw = raw
                except Exception:
                    pass
                self.power_book.reset(name)
                self.power_book.add(name, dark_raw, 0.0)
                self.power_book.add(name, max_raw, float(max_uw))
                self.laser.set_head(slot, intensity_pct=0.0)

            # 6. Turn off emission and restore oscillator outputs
            self.laser_off()
            for h in state.heads:
                en = orig_outputs[h.output] if (0 <= h.output < len(orig_outputs)) else False
                self.laser.set_head(h.slot, enabled=en, intensity_pct=0.0)

            # 7. Restore shutters
            if hasattr(self, '_set_shutters'):
                self._set_shutters(orig_shutters)
            else:
                for n, st in orig_shutters.items():
                    self.set_shutter(n, st)

            # 8. Reset diode context and simulated event log
            self.diode_context = DiodeContext()
            if hasattr(self.laser, 'events'):
                self.laser.events = list(orig_events)

            self.power_book.save()
            self.power_message = f'Max power calibrated to {max_uw:g} µW with detector shutters closed.'
            return True
        except Exception as exc:
            self.laser_off()
            self.power_message = f'Max power calibration failed: {exc}'
            return False

    def power_poll(self, force=False):
        now = time.monotonic()
        if force or now-self._power_at >= .2:
            self._power_at = now
            try:
                state=self.laser.state() if self.laser_connected else None
                self._power_laser_state=state
                self._power_heads=list(state.heads) if state is not None else []
                if state is not None and hasattr(self,'_emission_on'):
                    self._emission_on=not state.emission_blocked
                if state is not None:
                    self._power_track_context(state)
                else:
                    self._power_passive_streak = 0
            except Exception as exc:
                self._power_heads = []
                self.power_message = str(exc)
        servo = self.power_servo
        if servo is not None and servo.active:
            servo.poll()
            if not servo.active and servo.status == 'reached':
                self._record_power_convergence()
            self.power_message = servo.message

    def _record_power_convergence(self):
        """A converged, verified servo point becomes the session's alone entry.

        The verified combined reading minus the attributed offset is the
        selected head's alone raw; recording it is what later mixed requests
        attribute against. A recording failure never undoes the reached target:
        the next request simply finds no entry and asks."""
        meta, self._power_servo_context = self._power_servo_context, None
        try:
            servo = self.power_servo
            if servo is None or servo.verified_raw is None or meta is None:
                return
            verified = float(servo.verified_raw)
            state = self.laser.state()
            head = next((h for h in state.heads if h.slot == meta['slot']), None)
            if head is None:
                return
            self.diode_context.record(
                state=state, shutters=self.shutters, head=head,
                alone_raw=verified - float(servo.context_offset),
                uw=float(servo.power_uw),
                calibration=self._power_calibration_fingerprint(meta['name']))
        except Exception as exc:  # noqa: BLE001 - the target stays reached
            self.power_message = f'Target reached; attribution not recorded: {exc}'

    def power_reading(self):
        try:
            if not self.laser_connected:
                return '— µW'
            state = self.laser.state()
            head = self.power_head()
            if head is None or state.emission_blocked:
                return '— µW'
            raw = float(self.shutters.get_parameter('diode_raw', -1)) if self.shutters is not None else -1.0
            if raw < 0 and hasattr(self.laser, 'get_parameter'):
                raw = float(self.laser.get_parameter('diode_raw', -1))
            if raw < 0:
                return '— µW'
            offset = self.calculate_diode_offset(exclude_slot=head.slot)
            effective_raw = max(0.0, raw - offset)
            name = self.power_laser_name()
            uw = self.power_book.power(name, effective_raw)
            simulated = getattr(self.laser, 'kind', '') in ('simulated', 'cmc_sim')
            return ('SIMULATED ' if simulated else '') + f'{uw:.3g} µW (diode {raw:g})'
        except Exception:
            return '— µW'

    def power_control_sections(self):
        """The compact Laser-page control: color selector, calibrated reading, editable
        target slider (its commit calls :meth:`request_power_target`), Cancel/off, and the
        compact status and warning lines. There is no Set µW and no Other-lasers-off
        button: the committed target is the one gesture, and isolation is part of it."""
        return [
            {'type': 'choice', 'attr': 'power_selected_slot', 'label': 'Color / laser',
             'options_source': 'power_head_options', 'call': 'power_selection_changed',
             'description': 'Only connected heads are offered. Selecting never switches a laser on.'},
            {'type': 'info', 'source': 'power_reading'},
            {'type': 'custom', 'key': 'power_target_slider',
             'description': 'Editable target in µW. Committing it is the one gesture that may allow light: '
                            'other heads go to zero, the excitation shutter opens and only this head is '
                            'enabled, from verified readback. Zero disables this head and never opens a shutter.'},
            {'type': 'button_row', 'buttons': [
                {'action': 'cancel_power_target', 'label': 'Cancel + laser off',
                 'description': 'Cancel the adjustment and block all emission. Immediate and always allowed.'},
            ]},
            {'type': 'info', 'source': 'power_change_warning'},
            {'type': 'info', 'source': 'power_message'},
        ]


class SimplePowerPanelModel:
    """Manual measured pairs; no pulse/repetition controls or mandatory dark step."""
    def __init__(self, record):
        self.record = record
        self.laser_name = ''
        self._raw = 0.
        self.uw = 0.
        self.selected_row = None
        self._editing_point_id = None
        self._edit_raw = 0.
        self._edit_uw = 0.
        self.message = 'Select a laser. Diode is sampled automatically. Enter objective power and click Add.'

    @property
    def raw(self):
        try:
            if self.record.shutters is not None:
                d_raw = float(self.record.shutters.get_parameter('diode_mean', -1))
                if d_raw < 0:
                    d_raw = float(self.record.shutters.get_parameter('diode_raw', -1))
                if d_raw >= 0 and math.isfinite(d_raw):
                    self._raw = d_raw
        except Exception:
            pass
        return self._raw

    @raw.setter
    def raw(self, value):
        self._raw = float(value)

    def laser_options(self):
        names = [label for _, label in self.record.power_head_options()]
        names += self.record.power_book.lasers() + ['488 nm', '530 nm', '640 nm', '730 nm']
        return [('', 'Choose laser…')] + [(name, name) for name in dict.fromkeys(names)]

    def rows(self):
        return [{'id': i, 'raw': p[0], 'uw': p[1]} for i, p in enumerate(self.record.power_book.points(self.laser_name))]

    def select_row(self, row):
        self.selected_row = row

    def read_diode(self):
        """Sample a fresh diode value for the selected laser, alone in the beam."""
        try:
            record = self.record
            if getattr(record, 'running', False):
                raise ValueError('Stop the measurement before sampling a calibration point.')
            diode_device = record.shutters if getattr(record, 'shutters', None) is not None else (
                record.laser if hasattr(getattr(record, 'laser', None), 'get_parameter') else None
            )
            if diode_device is None:
                raise ValueError('No diode connected; enter the value manually.')
            if record.power_servo is not None and record.power_servo.active:
                raise ValueError('Wait for the power adjustment to finish, or cancel it first.')
            record.power_poll(force=True)
            slot = {label:slot for slot,label in record.power_head_options()}.get(self.laser_name)
            if slot is None:
                raise ValueError('Select a connected laser first; calibration pairs are measured per connected head.')
            for head in record.laser.state().heads:
                if head.slot != slot:
                    record.laser.set_head(head.slot, intensity_pct=0.)
            record.laser_program = record.laser.capture()
            if hasattr(diode_device, 'set_parameter'):
                diode_device.set_parameter('diode_mark', 1.)
            end = time.monotonic() + _DIODE_TIMEOUT_S
            raw = -1.
            while time.monotonic() < end:
                try:
                    value = float(diode_device.get_parameter('diode_mean', -1))
                except Exception:  # noqa: BLE001 - not a parameter of this diode
                    value = -1.
                if value >= 0 and math.isfinite(value):
                    raw = value
                    break
                time.sleep(_POLL_S)
            if raw < 0:
                raise ValueError('The diode sent no fresh reading after the sample was marked; enter the value manually.')
            self._raw = raw
            self.message = 'Fresh diode reading sampled. Enter objective meter reading and click Add.'
            return True
        except Exception as exc:
            self.message = str(exc)
            return False

    def add_point(self):
        try:
            self.record.power_book.add(self.laser_name, self.raw, self.uw)
            try:
                self.record.power_book.save()
            except Exception:
                pass
            self.message = 'Measured point added (automatically saved). Change drive and add the next point.'
            return True
        except (ValueError, TypeError) as exc:
            self.message = str(exc)
            return False

    def delete_point(self, row=None):
        try:
            target_row = row if row is not None else self.selected_row
            if target_row is None:
                raise ValueError('Select the incorrect row first.')
            self.record.power_book.remove(self.laser_name, target_row['id'])
            try:
                self.record.power_book.save()
            except Exception:
                pass
            self.selected_row = None
            self.message = 'Selected point removed (automatically saved).'
            return True
        except (ValueError, KeyError) as exc:
            self.message = str(exc)
            return False

    def update_point(self, point_id: int, raw: float, uw: float):
        """Update an existing calibration point and automatically save."""
        try:
            self.record.power_book.remove(self.laser_name, point_id)
            self.record.power_book.add(self.laser_name, float(raw), float(uw))
            try:
                self.record.power_book.save()
            except Exception:
                pass
            self.message = f'Point updated to {raw:.1f} diode, {uw:.1f} µW (automatically saved).'
            return True
        except Exception as exc:
            self.message = str(exc)
            return False

    def new_set(self):
        self.record.power_book.reset(self.laser_name)
        try:
            self.record.power_book.save()
        except Exception:
            pass
        self.message = 'Started a new calibration for this laser. Previous points for it were cleared.'

    def save(self):
        try:
            self.record.power_book._record(self.laser_name)
            self.record.power_book.save()
            self.message = f'Saved {self.record.power_book.path}. Calibration expires after three calendar months.'
            return True
        except (ValueError, OSError) as exc:
            self.message = str(exc)
            return False

    def calibration_date(self):
        rec = self.record.power_book.records.get(self.laser_name)
        return f"Calibration date (automatic): {rec['measured']}" if rec else 'Calibration date: assigned automatically when the first measured point is added.'


class SimplePowerPanel:
    def __init__(self, record):
        self.model = SimplePowerPanelModel(record)
        self.form = FormState()
        self.form.custom['power_points'] = self._draw_power_points
        self.sections = json.loads((HERE/'power.view.json').read_text())['sections']

    @staticmethod
    def _draw_power_points(section, model: SimplePowerPanelModel, state, width: float) -> None:
        rows = model.rows()
        if not rows:
            im.text_disabled(tr("No calibration points for this laser yet."))
            return

        flags = (im.TableFlags.BORDERS | im.TableFlags.ROW_BG |
                 im.TableFlags.SIZING_STRETCH_SAME | im.TableFlags.RESIZABLE)
        if im.begin_table("##power_points_tbl", 2, flags):
            im.table_setup_column(tr("Diode value"))
            im.table_setup_column(tr("Objective power (µW)"))
            im.table_headers_row()

            editing_id = getattr(model, '_editing_point_id', None)
            for row in rows:
                row_id = row['id']
                im.table_next_row()
                im.table_next_column()
                is_selected = (model.selected_row or {}).get('id') == row_id
                if editing_id == row_id:
                    changed_r, new_raw = im.input_float(f"##edit_raw_{row_id}", getattr(model, '_edit_raw', float(row['raw'])), 0, 0, "%.1f")
                    if changed_r: model._edit_raw = new_raw
                    im.table_next_column()
                    changed_u, new_uw = im.input_float(f"##edit_uw_{row_id}", getattr(model, '_edit_uw', float(row['uw'])), 0, 0, "%.1f")
                    if changed_u: model._edit_uw = new_uw
                    if im.button(f"Save##save_edit_{row_id}"):
                        model.update_point(row_id, model._edit_raw, model._edit_uw)
                        model._editing_point_id = None
                    im.same_line()
                    if im.button(f"Cancel##cancel_edit_{row_id}"):
                        model._editing_point_id = None
                else:
                    label = f"{float(row['raw']):.1f}##pt_{row_id}"
                    clicked, _ = im.selectable(label, is_selected, im.SelectableFlags.SPAN_ALL_COLUMNS)
                    if clicked:
                        model.select_row(row)
                    if im.is_item_hovered() and im.is_mouse_double_clicked(0):
                        model._editing_point_id = row_id
                        model._edit_raw = float(row['raw'])
                        model._edit_uw = float(row['uw'])
                    if im.begin_popup_context_item(f"##ctx_pt_{row_id}"):
                        if im.menu_item(tr("Edit point")):
                            model._editing_point_id = row_id
                            model._edit_raw = float(row['raw'])
                            model._edit_uw = float(row['uw'])
                        if im.menu_item(tr("Delete point")):
                            model.delete_point(row)
                        im.end_popup()
                    im.table_next_column()
                    im.text(f"{float(row['uw']):.1f}")
            im.end_table()

    def draw(self):
        draw_sections(self.sections, self.model, self.form)


class PowerChangeDialogs(MessageDialogs):
    """Message dialogs for power adjustments with an 'Ignore' session checkbox."""

    def __init__(self, model, wake=None, width=650.0):
        super().__init__(wake=wake, width=width)
        self.model = model
        self.ignore_checked = bool(getattr(model, 'power_change_ignore', False))

    def draw(self, frame):
        question = self.current
        if question is None or question.window is None:
            return
        window = question.window
        pressed = window.begin(frame)
        io = _core.get_io()
        enter = io.key in (KEY_RETURN, KEY_ENTER)
        escape = io.key == KEY_ESCAPE
        _w.text_wrapped(question.message)
        if question.detail:
            _w.text_disabled(question.detail)
        _w.spacing()
        self.ignore_checked = bool(getattr(self.model, 'power_change_ignore', self.ignore_checked))
        changed, val = im.checkbox(f"{tr('Ignore')}##{window.key}.ignore", self.ignore_checked)
        if changed:
            self.ignore_checked = val
            self.model.power_change_ignore = val
        rect = im.get_item_rect()
        question.rects["checkbox"] = rect
        question.rects["ignore"] = rect
        im.set_item_tooltip(tr("Do not ask again during this session"))
        _w.spacing()
        chosen = None
        for index, (key, label) in enumerate(question.options):
            if index:
                _w.same_line()
            role = (question.roles or {}).get(key) or KEY_ROLES.get(key)
            colours = ROLE_COLOURS.get(role) if role else None
            if colours:
                for which, colour in zip((_core.Col.BUTTON, _core.Col.BUTTON_HOVERED,
                                          _core.Col.BUTTON_ACTIVE, _core.Col.TEXT), colours):
                    _w.push_style_color(which, colour)
            if _w.button(f"{tr(label)}##{window.key}.{key}"):
                chosen = key
            if colours:
                _w.pop_style_color(4)
            question.rects[f"button.{key}"] = _w.get_item_rect()
        window.end()
        if window.box is not None:
            question.rects["window"] = window.box
        if chosen is not None:
            if chosen in ("yes", "ok", "apply") and self.ignore_checked:
                self.model.power_change_ignore = True
            self.answer(key=chosen)
        elif pressed == "close" or escape:
            self.answer(question.dismissed)
        elif enter:
            if question.kind == "text":
                self.answer(key="ok")
            elif question.kind == "message":
                self.answer(None)
            elif question.kind == "confirm" or question.default is not None:
                if question.default and self.ignore_checked:
                    self.model.power_change_ignore = True
                self.answer(question.default)

