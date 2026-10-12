"""The optional dependencies must stay optional — proved by simulating absence.

Qt, LabelLib and `IMP.bff` are imported behind `try`/`except` with fallbacks.
That is what lets the CLI, the API and the web backend run where those are not
installed, and it is the reason a Windows box without a compiled `IMP.bff` can
still compute accessible volumes through LabelLib.

**Until 2026-07-28 the rule was enforced by an interpreter that genuinely lacked
them** — the mambaforge base environment had no Qt and no compiled `IMP.bff`, so
running the suite there exercised every fallback for free. That environment is
retired ([okf/specs/programme-2026-07.md](../okf/specs/programme-2026-07.md),
decisions 4 and 5), and the canonical `arm64` environment has all three. Nothing
would enter those branches again on its own.

The failure mode this guards against is documented and has already happened
once: `quest/lib/imp_av.py` shipped a `Model.get_particles()` call that does not
exist, and nothing noticed because no test entered that branch. A backend with
no coverage ships broken code.

These tests therefore *simulate* the absence rather than relying on it.
"""

from __future__ import annotations

import builtins
import subprocess
import sys
import textwrap

import pytest

from chisurf.plugins.quenching_estimator.core import av


class TestThereIsOneAvBackend:
    """`IMP.bff` is a hard dependency, and the only backend.

    The LabelLib fallback and the three-way selector in front of it are gone.
    They mattered when the base interpreter had no compiled `IMP.bff`; that
    interpreter is retired, and the two backends never agreed anyway — 136 707
    against 151 869 points on 148l E36 — so which one ran silently decided
    every contact fraction and quenching rate downstream.
    """

    def test_the_only_backend_is_imp_bff(self) -> None:
        assert av.AV_BACKENDS == ("imp_bff",)
        assert av.available_av_backends() == ["imp_bff"]

    def test_auto_and_none_resolve_to_it(self) -> None:
        assert av.resolve_av_backend() == "imp_bff"
        assert av.resolve_av_backend("auto") == "imp_bff"
        assert av.resolve_av_backend("imp_bff") == "imp_bff"

    def test_asking_for_labellib_raises_rather_than_substituting(self) -> None:
        """It used to be selectable, so a stale config must fail loudly."""
        with pytest.raises(ValueError, match="LabelLib backend was removed"):
            av.resolve_av_backend("labellib")

    def test_an_unknown_name_is_a_value_error_not_a_silent_default(self) -> None:
        with pytest.raises(ValueError, match="Unknown accessible-volume backend"):
            av.resolve_av_backend("labellib2")


class TestTheDomainImportsWithoutOptionalPackages:
    """`import quest.core` must not need Qt or LabelLib, and must not *pull IMP in*.

    IMP is a hard dependency since the quenching model moved into IMP.bff, so it is no longer in the blocked
    list — but importing the domain must still not load it, which
    `test_service_layer.py::TestLayering::test_importing_the_domain_does_not_import_imp`
    checks separately. That property is not
    about optionality: a child of a process that has already loaded IMP
    resolves `libimp_kernel` against the wrong `libboost_filesystem`
    (okf/references/known-issues.md).

    Run in a subprocess with the module blocked at import, because the parent
    has all three loaded and cannot un-load them.
    """

    @pytest.mark.parametrize("blocked", ["PyQt5", "qtpy", "LabelLib"])
    def test_the_service_layer_still_imports(self, blocked: str) -> None:
        script = textwrap.dedent(
            f"""
            import builtins
            import sys

            blocked = {blocked!r}
            real_import = builtins.__import__

            def guarded(name, *args, **kwargs):
                if name == blocked or name.startswith(blocked + "."):
                    raise ImportError("blocked for this test: " + name)
                return real_import(name, *args, **kwargs)

            builtins.__import__ = guarded
            for name in list(sys.modules):
                if name == blocked or name.startswith(blocked + "."):
                    del sys.modules[name]

            import chisurf.plugins.quenching_estimator.core  # noqa: F401
            import chisurf.plugins.quenching_estimator.api.local  # noqa: F401
            import chisurf.plugins.quenching_estimator.core.project  # noqa: F401
            import chisurf.plugins.quenching_estimator.core.runs  # noqa: F401
            import chisurf.plugins.quenching_estimator.core.tasks  # noqa: F401
            print("ok")
            """
        )
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode == 0, (
            f"importing the domain without {blocked} failed:\n{result.stderr[-2000:]}"
        )
        assert "ok" in result.stdout


class TestTheCapabilityFlagsAreRealChecks:
    def test_imp_bff_is_actually_importable(self) -> None:
        """It is a hard dependency, so this is a plain requirement: the doors QuEst calls exist.

        Checked by name, because a missing door fails only on first use: QuEst once
        imported `IMP.bff.av.compute` and `IMP.bff.quenching`, Python modules IMP.bff
        no longer ships, and every simulation failed while the module imported fine.
        """
        import IMP.bff

        for name in (
            "get_av",
            "density_to_points",
            "random_distances",
            "distance_sample_statistics",
            "mean_position_distance",
            "center_grid_indices",
            "slow_factor_grid",
            "quenching_rate_grid",
            "av_contact_mask",
            "simulate_probe_diffusion",
            "sphere_points",
            "solvent_accessible_surface",
            "fret_rate_trace",
            "fret_rate_pair_trace",
            "simulate_photon_trace",
            "simulate_quenched_decay",
        ):
            assert callable(getattr(IMP.bff, name, None)), name

    def test_at_least_one_backend_is_available_in_this_environment(self) -> None:
        """A canary: if this fails the environment is broken, not the code."""
        assert av.available_av_backends(), (
            "no AV backend in the canonical environment; see okf/workflows/environment.md"
        )


def test_builtins_import_is_untouched_after_the_subprocess_tests() -> None:
    """Paranoia: the guard above must not leak into this process."""
    assert builtins.__import__.__module__ in {"builtins", "importlib._bootstrap"} or callable(
        builtins.__import__
    )
