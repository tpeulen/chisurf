"""The burst fit chops a measurement's bursts across every core and gives the one-job answer.

One job per file left the usual case -- one measurement -- on one core; the chunks are merged in
burst order, so the rows (and the companions written position by position) do not change.
"""

from __future__ import annotations

import math

from chisurf.plugins.burst.burst_mle_analysis import engine

from .test_mle_restored_inputs import fresh_session, inputs, set_window  # noqa: F401 - fixture


def test_chunks_keep_files_and_burst_order():
    jobs = [("a", [(i, i + 1) for i in range(10)], "x"), ("b", [(0, 1)], "y")]
    old = engine.MIN_CHUNK_BURSTS
    engine.MIN_CHUNK_BURSTS = 3
    try:
        chopped = engine._chop_jobs(jobs, workers=1)
    finally:
        engine.MIN_CHUNK_BURSTS = old
    assert [job[0] for job in chopped] == ["a", "a", "a", "a", "b"]
    assert [b for job in chopped if job[0] == "a" for b in job[1]] == jobs[0][1]
    assert all(job[2] == ("x" if job[0] == "a" else "y") for job in chopped)


def _rows(session, monkeypatch, chunk: int, workers: int):
    monkeypatch.setattr(engine, "MIN_CHUNK_BURSTS", chunk)
    return session.run_batch(max_workers=workers)


def test_chopped_and_whole_batches_agree(inputs, monkeypatch):  # noqa: F811 - the fixture
    session = fresh_session(inputs["bur"])
    session.set_binning(1)
    session.set_pattern_files("bg", "synthetic", [inputs["bg"]])
    set_window(session)
    session.set_model(engine.TAIL_MODEL)
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
