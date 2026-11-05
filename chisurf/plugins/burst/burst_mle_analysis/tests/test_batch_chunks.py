"""The burst fit chops a measurement's bursts into fit_many chunks on threads and gives the
one-chunk answer: the chunks are merged in burst order, so the rows (and the companions written
position by position) do not change.
"""

from __future__ import annotations

import math

from chisurf.plugins.burst.burst_mle_analysis import _mp_worker as worker
from chisurf.plugins.burst.burst_mle_analysis import engine

from .test_mle_restored_inputs import fresh_session, inputs, set_window  # noqa: F401 - fixture


def _rows(session, monkeypatch, chunk: int, workers: int):
    monkeypatch.setattr(worker, "CHUNK_ROWS", chunk)
    return session.run_batch(max_workers=workers)


def test_chopped_and_whole_batches_agree(inputs, monkeypatch):  # noqa: F811 - the fixture
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])
    set_window(session)
    session.set_model(engine.TAIL_MODEL)  # fit23's chunks: test_fit_many_equivalence
    whole = _rows(session, monkeypatch, chunk=10**9, workers=1)
    chopped = _rows(session, monkeypatch, chunk=1, workers=3)
    assert len(chopped) == len(whole) > 3

    def same(a, b):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return a == b

    for a, b in zip(whole, chopped):
        assert a.keys() == b.keys()
        assert all(same(a[k], b[k]) for k in a)
