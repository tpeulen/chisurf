"""Optional fast backends must be *on* where their dependency is installed.

A backend that is missing is meant to degrade: the caller takes a slower path and
carries on. That is the right design and it has one failure mode, which is not
theoretical — it happened.

The gates are written as

    HAVE_TTTRLIB = hasattr(tttrlib, "H2MM")

so when the library renamed ``H2MM`` to ``HMM`` the gate turned **False**, every
caller took the documented fallback, the tests that exercise the fast path
skipped themselves, and the suite stayed green. The plugin was quietly running
its slow engine and nothing anywhere said so. A symbol rename does not touch a
string, which is exactly how a guard drifts away from the thing it guards.

So: where the dependency imports, the backend that depends on it must report
available. Anything else is a downgrade nobody asked for, and this is the test
that refuses to let it be silent. Where the dependency is genuinely absent these
skip, which is the case the fallback exists for.
"""

from __future__ import annotations

import importlib

import pytest

tttrlib = pytest.importorskip("tttrlib")


#: ``(module, flag, the tttrlib feature it needs)``. Each flag is a gate that
#: silently selects a slow path, so each one is a place this can happen again.
TTTRLIB_BACKENDS = [
    ("chisurf.plugins.burst.burst_h2mm.core.h2mm_tttrlib", "HAVE_TTTRLIB", "HMM"),
    ("chisurf.plugins.burst.burst_h2mm.core.surrogate_tttrlib", "HAVE_TTTRLIB",
     "HmmSurrogate"),
    ("chisurf.core.fluorescence.mle.fit2x", "HAVE_TTTRLIB", "TTTR"),
]


@pytest.mark.parametrize("module_name,flag,feature", TTTRLIB_BACKENDS)
def test_a_present_backend_reports_itself_present(module_name, flag, feature):
    """The gate must agree with the library, not with a stale spelling of it."""
    if not hasattr(tttrlib, feature):
        pytest.skip(f"this tttrlib build has no {feature}")

    module = importlib.import_module(module_name)
    assert getattr(module, flag) is True, (
        f"{module_name}.{flag} is False although tttrlib.{feature} exists. "
        "The gate has drifted from the library — a renamed symbol leaves the "
        "hasattr string behind — and every caller is silently taking the "
        "fallback path."
    )


def test_the_h2mm_engine_selector_picks_the_compiled_backend():
    """The selector, not just the module flag.

    ``engines`` re-exports the gate through its own name, so it can disagree with
    the module it imported from — and it is the selector callers actually reach.
    """
    if not hasattr(tttrlib, "HMM"):
        pytest.skip("this tttrlib build has no HMM")

    engines = importlib.import_module(
        "chisurf.plugins.burst.burst_h2mm.core.engines"
    )
    assert engines._HAVE_TTTRLIB is True
    assert engines._HAVE_TTTRLIB_SURROGATE is True


def test_the_photon_simulator_is_available_to_the_shim():
    """The simulation shim's one availability gate, for the same reason.

    Every simulator in the tree asks this question through
    :func:`~chisurf.core.fluorescence.simulation.have_simulator`. If it answered
    False on a build that has the simulator, they would all quietly refuse to
    simulate rather than fail.
    """
    from chisurf.core.fluorescence.simulation import have_simulator

    assert have_simulator() is hasattr(tttrlib, "SimEngine")
    if hasattr(tttrlib, "SimEngine"):
        assert have_simulator() is True
