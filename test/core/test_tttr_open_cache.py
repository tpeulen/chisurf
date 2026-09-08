"""One open per measurement, and the exact condition that must disable it.

Every step of a burst workflow reads the same file — the diagnostics preview,
each move of the visible window, the burst search, the background estimate. Four
opens of the same measurement, no step aware of the others.

The cache lives at ``open_tttr`` because that is already the single seam every
reader goes through. Its danger is that the handle is *shared*: a read whose
object gets mutated must never be, and the subtle part is which reads those are.
"""

from __future__ import annotations

import numpy as np
import pytest

from chisurf.core.fio import staging
from chisurf.core.fio.lut_context import clear_active_setup_lut, set_active_setup_lut


@pytest.fixture
def measurement(tmp_path, monkeypatch):
    """A stand-in file plus a reader that counts how often it is opened."""
    path = tmp_path / "m.ptu"
    path.write_bytes(b"x" * 64)
    opens = {"n": 0}

    class _Tttr:
        def __init__(self, *_a, **_k):
            opens["n"] += 1
            self.macro_times = np.arange(1000, dtype=np.int64)
            self.micro_times = np.zeros(1000, dtype=np.int64)

        def __len__(self):
            return 1000

        # The LUT path mutates through these; a stub needs them to exist.
        def apply_channel_luts(self, *_a, **_k):
            pass

        def apply_luts_and_shifts(self, *_a, **_k):
            pass

    import sys
    import types

    fake = types.ModuleType("tttrlib")
    fake.TTTR = _Tttr
    monkeypatch.setitem(sys.modules, "tttrlib", fake)
    staging.clear_tttr_cache()
    clear_active_setup_lut()
    yield path, opens
    staging.clear_tttr_cache()
    clear_active_setup_lut()


def test_the_same_measurement_is_opened_once(measurement):
    path, opens = measurement
    first = staging.open_tttr(str(path))
    again = staging.open_tttr(str(path))
    assert opens["n"] == 1, "the measurement was read twice"
    assert first is again, "a second reader got a different object"


def test_an_active_setup_without_luts_still_shares(measurement):
    """The case the workflow always runs in, and the one that was broken.

    Selecting *any* detector setup turns ``apply_lut`` on, but most setups carry
    no LUT, so ``apply_setup_lut`` does nothing at all. Keying the "is this
    object mutated" decision on the flag rather than on whether a LUT exists
    turned the whole cache off for every real session.
    """
    path, opens = measurement
    set_active_setup_lut(channel_luts={}, apply_lut=True)
    first = staging.open_tttr(str(path))
    again = staging.open_tttr(str(path))
    assert opens["n"] == 1
    assert first is again


def test_a_real_lut_is_never_shared(measurement):
    """Applying one rewrites the micro times in place: the object is mutated."""
    path, opens = measurement
    set_active_setup_lut(channel_luts={0: np.linspace(0.0, 1.0, 8)}, apply_lut=True)
    first = staging.open_tttr(str(path))
    again = staging.open_tttr(str(path))
    assert opens["n"] == 2, "a LUT-corrected read was shared"
    assert first is not again


def test_a_caller_can_opt_out(measurement):
    """``alex_to_microtime`` folds in place; such a caller needs its own object."""
    path, opens = measurement
    staging.open_tttr(str(path))
    mine = staging.open_tttr(str(path), cache=False)
    assert opens["n"] == 2
    assert mine is not staging.open_tttr(str(path))


def test_a_rewritten_measurement_is_read_again(measurement):
    """Keyed on mtime and size, so a file replaced on disk is not served stale."""
    path, opens = measurement
    staging.open_tttr(str(path))
    path.write_bytes(b"y" * 128)          # different size -> different key
    staging.open_tttr(str(path))
    assert opens["n"] == 2


def test_the_cache_is_bounded(measurement, monkeypatch):
    """Bounded by BYTES, not entries and not photons.

    Measured rather than assumed: a container costs ~35 bytes per photon, so a
    budget counted in photons was worth 2.2 GB in a GUI process.
    """
    path, _ = measurement
    monkeypatch.setattr(staging, "_TTTR_CACHE_BYTES", 2500 * staging._BYTES_PER_PHOTON)
    for i in range(5):
        p = path.parent / f"m{i}.ptu"
        p.write_bytes(b"z" * (10 + i))
        staging.open_tttr(str(p))
    stats = staging.tttr_cache_stats()
    assert stats["bytes"] <= 2500 * staging._BYTES_PER_PHOTON, stats
    assert stats["entries"] <= 3, stats
