"""Shared fixtures of the BVA suite."""

import pytest


@pytest.fixture(autouse=True)
def _advanced_controls():
    """The detector/channel tabs are advanced controls now: on for this suite
    (it drives them), off again afterwards. Simple mode has its own test."""
    from chisurf.emtk import advanced

    advanced.set_advanced_mode(True)
    yield
    advanced.set_advanced_mode(False)
