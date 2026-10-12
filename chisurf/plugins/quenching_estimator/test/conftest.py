"""Markers the QuEst engine tests use.

``needs_av`` marks a test that computes an accessible volume through IMP.bff. In
ChiSurf IMP.bff is a hard dependency, so the marker only documents the need; it
skips nothing.
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "needs_av: computes an accessible volume through IMP.bff (a hard dependency)"
    )
