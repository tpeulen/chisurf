"""Kept process pools let their processes go once idle, and start them again on the next task.

Kept for the life of a window, the burst-fit workers (1-3 GB each) of a few ChiSurf processes ran
a 16 GB laptop out of memory (87 Python processes, 34 GB)."""

from __future__ import annotations

import time

from chisurf.core.runtime.idle_pool import IdlePool, idle_seconds


def _wait(predicate, timeout=20.0):
    end = time.monotonic() + timeout
    while not predicate() and time.monotonic() < end:
        time.sleep(0.05)
    return predicate()


def test_processes_go_after_the_idle_time_and_come_back_on_submit():
    pool = IdlePool(1, idle_s=0.4, name="test")
    assert not pool.started
    assert pool.submit(abs, -3).result(timeout=60) == 3
    assert pool.started
    assert _wait(lambda: not pool.started), "the idle pool kept its processes"
    # the next task starts them again; the caller never holds a dead executor
    assert pool.submit(abs, -4).result(timeout=60) == 4
    pool.shutdown()
    assert not pool.started


def test_a_running_task_keeps_the_pool():
    pool = IdlePool(1, idle_s=0.2, name="test")
    future = pool.submit(time.sleep, 1.0)
    time.sleep(0.6)
    assert pool.started and pool.idle_for() == 0.0
    future.result(timeout=60)
    pool.shutdown()


def test_idle_time_override(monkeypatch):
    monkeypatch.setenv("CHISURF_POOL_IDLE_S", "5")
    assert idle_seconds() == 5.0
    monkeypatch.setenv("CHISURF_POOL_IDLE_S", "x")
    assert idle_seconds() == 60.0


def test_fit_pool_is_an_idle_pool(monkeypatch):
    from chisurf.plugins.burst.burst_mle_analysis import engine

    monkeypatch.setenv("CHISURF_FIT_WORKERS", "1")
    try:
        assert isinstance(engine.fit_pool(), IdlePool)
    finally:
        engine._drop_fit_pool()
