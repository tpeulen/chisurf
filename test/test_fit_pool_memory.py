"""The burst-fit pool is sized by memory as well as cores: 7 kept workers per ChiSurf on a 16 GB
laptop, times a few ChiSurf processes, ran macOS out of memory (87 Python processes, 34 GB)."""

from __future__ import annotations

from types import SimpleNamespace

from chisurf.plugins.burst.burst_mle_analysis import engine


def test_workers_follow_available_memory(monkeypatch):
    import psutil

    monkeypatch.delenv("CHISURF_FIT_WORKERS", raising=False)
    monkeypatch.setattr("os.cpu_count", lambda: 48)
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=3.6e9))
    assert engine.fit_workers() == 1  # the laptop at the crash: 3.6 GB free
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=27e9))
    assert engine.fit_workers() == 9
    monkeypatch.setattr(psutil, "virtual_memory", lambda: SimpleNamespace(available=500e9))
    assert engine.fit_workers() == 47  # cores bound


def test_override_and_no_warm_pool_under_pytest(monkeypatch):
    monkeypatch.setenv("CHISURF_FIT_WORKERS", "3")
    assert engine.fit_workers() == 3
    started = []
    monkeypatch.setattr(engine, "warm_fit_pool", lambda: started.append(1))
    engine.warm_fit_pool_quietly()
    assert not started
