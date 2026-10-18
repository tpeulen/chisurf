import chisurf.core.fluorescence.burst


def test_burst_imports():
    """Each search module is reachable and exposes its own ``*_filter``."""
    burst = chisurf.core.fluorescence.burst
    bocpd_func = burst.bocpd.bocpd_filter
    kalman_func = burst.kalman.kalman_filter
    assert bocpd_func is not None
    assert kalman_func is not None
    assert bocpd_func is not kalman_func
