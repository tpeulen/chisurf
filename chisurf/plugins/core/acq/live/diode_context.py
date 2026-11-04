"""Session-only attribution ledger for the summed average-power diode.

The diode sees every head summed over ONE shared dark level D, so a head's net
contribution is ``alone_raw - D``. When a head was measured alone (its routine
power request converged with every other head at zero), the verified point and
the full operating signature are stored here. A later power request on another
head may then subtract the stored net contributions instead of zeroing the
other heads -- but only while EVERY condition of every stored entry still
matches the live readback: drive, pulsed mode, oscillator (clock, divider,
sequencer bursts and output mapping), shutter/beam geometry and the power
calibration. Any deviation is a named :class:`UnknownContribution`, never a
guessed number.

The ledger is session-only: it lives in memory, clears when the head identity
list (slot, name, sequencer output mapping) changes, and a RISING global
emission block invalidates the attributions while the dark survives -- the
dark is re-captured passively anyway.
"""

from __future__ import annotations

import math


class UnknownContribution(Exception):
    """A head's diode contribution cannot be attributed; the message names it."""


def _finite_non_negative(raw) -> bool:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return False
    return math.isfinite(value) and value >= 0.


class DiodeContext:
    """Verified alone entries per head slot, attributed over one shared dark."""

    def __init__(self):
        #: The one shared dark level (raw counts), or None until captured.
        self.dark = None
        #: Verified alone entries keyed by head slot.
        self.entries = {}
        self._head_identity = None
        self._blocked = False

    # -- session bookkeeping --------------------------------------------------------------------
    def bind_heads(self, state) -> bool:
        """Track the head identity list (slot, name, sequencer output mapping).

        Returns True exactly when the identity CHANGED against the last binding;
        the entries AND the dark are cleared then. An unchanged list returns
        False and clears nothing. The first binding never clears.
        """
        identity = tuple((h.slot, str(h.name), int(h.output)) for h in state.heads)
        if self._head_identity is not None and identity != self._head_identity:
            self._head_identity = identity
            self.entries = {}
            self.dark = None
            return True
        self._head_identity = identity
        return False

    def invalidate_blocked(self, blocked) -> bool:
        """A RISING global emission block invalidates attributions; the dark stays.

        Returns True exactly on the False->True edge; staying blocked clears
        nothing new."""
        blocked = bool(blocked)
        rose = blocked and not self._blocked
        self._blocked = blocked
        if rose:
            self.entries = {}
        return rose

    def offer_dark(self, raw) -> bool:
        """Accept a finite, non-negative reading as the shared dark level.

        Passivity (every drive at zero) is the CALLER's contract: the poll only
        offers readings taken while nothing was driven. A later passive reading
        refreshes the dark."""
        if not _finite_non_negative(raw):
            return False
        self.dark = float(raw)
        return True

    # -- recording and attribution ----------------------------------------------------------------
    def record(self, state, shutters, head, alone_raw, uw, calibration):
        """Store a verified alone point for *head* with its full operating signature.

        ``alone_raw`` is the head's alone diode reading at the verified point (a
        combined reading minus the attributed offsets), ``uw`` its calibrated
        power there, ``calibration`` the fingerprint of the power calibration
        used. The signature is read back from ``state``/``shutters``."""
        raw = float(alone_raw)
        if not math.isfinite(raw) or raw < 0:
            raise ValueError('alone_raw must be a finite, non-negative diode reading.')
        self.entries[head.slot] = {
            'head': str(head.name or f'Laser slot {head.slot}'),
            'slot': head.slot,
            'alone_raw': raw,
            'uw': float(uw),
            'drive_pct': float(head.intensity_pct),
            'pulsed': bool(head.pulsed),
            'oscillator': self.oscillator_signature(state.oscillator),
            'shutters': self.shutter_signature(shutters),
            'calibration': str(calibration),
        }

    def offset(self, *, state, shutters, calibration_of, exclude_slot) -> float:
        """The verified net contribution of the OTHER heads over the shared dark.

        Sum of ``alone_raw - dark`` over the non-excluded heads that are
        emitting AND have a verified, unchanged entry. Raises
        :class:`UnknownContribution` naming the head and the reason when the
        attribution is not certain."""
        reason = self.mismatch_reason(state=state, shutters=shutters,
                                      calibration_of=calibration_of,
                                      exclude_slot=exclude_slot)
        if reason is not None:
            raise UnknownContribution(reason)
        total = 0.
        for head in state.heads:
            if head.slot == exclude_slot:
                continue
            entry = self.entries.get(head.slot)
            if entry is None or not self.head_emitting(head, state):
                continue
            total += entry['alone_raw'] - self.dark
        return total

    def mismatch_reason(self, *, state, shutters, calibration_of, exclude_slot):
        """The first reason the attribution is uncertain, or None when verified.

        The excluded head (the one being driven) is skipped entirely: its
        contribution is what the requested power accounts for. Stored entries
        are re-validated even while their head reads zero drive, so a stale
        entry is caught the moment its conditions stop holding."""
        if self.dark is None:
            return ('No shared dark level was captured for this session; block '
                    'every head at zero drive and let the passive reading settle.')
        oscillator = self.oscillator_signature(state.oscillator)
        shutters_signature = self.shutter_signature(shutters)
        for head in state.heads:
            if head.slot == exclude_slot:
                continue
            name = str(head.name or f'Laser slot {head.slot}')
            entry = self.entries.get(head.slot)
            if entry is None:
                if self.head_emitting(head, state):
                    return (f'{name}: no verified alone contribution for this '
                            'session; verify this head alone first.')
                continue
            drive = float(head.intensity_pct)
            if abs(drive - entry['drive_pct']) > 1e-6:
                return (f'{name}: drive changed from {entry["drive_pct"]:g} % to '
                        f'{drive:g} % since its verified alone measurement.')
            if bool(head.pulsed) != entry['pulsed']:
                return (f'{name}: pulse mode changed (pulsed/CW) since its '
                        'verified alone measurement.')
            if self._differs(oscillator, entry['oscillator']):
                return (f'{name}: oscillator changed (clock, divider or sequencer '
                        'outputs) since its verified alone measurement.')
            if self._differs(shutters_signature, entry['shutters']):
                return (f'{name}: shutter/beam geometry changed (reported '
                        'excitation/green/red) since its verified alone measurement.')
            if str(calibration_of(entry['head'])) != entry['calibration']:
                return (f'{name}: power calibration changed since its verified '
                        'alone measurement.')
        return None

    # -- signatures ---------------------------------------------------------------------------------
    @staticmethod
    def head_emitting(head, state) -> bool:
        """Readback: the head is driven AND its sequencer output is enabled."""
        if head.intensity_pct <= 0:
            return False
        oscillator = state.oscillator
        if oscillator is None or not 0 <= head.output < len(oscillator.output_enabled):
            return True
        return bool(oscillator.output_enabled[head.output])

    @staticmethod
    def oscillator_signature(oscillator):
        """(base clock, divider, sequencer bursts, output mapping) or None."""
        if oscillator is None:
            return None
        return (round(float(oscillator.base_hz), 3), int(oscillator.divider),
                tuple(int(n) for n in oscillator.burst_lengths),
                tuple(bool(b) for b in oscillator.output_enabled))

    @staticmethod
    def shutter_signature(shutters):
        """The reported excitation/green/red shutter geometry as a tuple."""
        if shutters is None:
            return None
        return tuple(round(float(shutters.get_parameter(name, -1.)), 6) for name in
                     ('reported_excitation', 'reported_green', 'reported_red'))

    @staticmethod
    def _differs(current, recorded) -> bool:
        if current is None or recorded is None:
            return current is not recorded
        if isinstance(current, (tuple, list)) or isinstance(recorded, (tuple, list)):
            return list(current) != list(recorded) or any(
                DiodeContext._differs(c, r) for c, r in zip(current, recorded))
        if isinstance(current, bool) or isinstance(recorded, bool):
            return bool(current) != bool(recorded)
        try:
            return abs(float(current) - float(recorded)) > 1e-9
        except (TypeError, ValueError):
            return current != recorded
