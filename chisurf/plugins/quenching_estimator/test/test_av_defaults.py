"""Generic accessible-volume values are IMP.bff's declaration.

Owner, 2026-10-11: "all use same defaults". IMP.bff declares them once
(``ProbeAccessibleVolumeDefaults.h``, ``IMP.bff.AV_DEFAULT_*``). Wherever QuEst
has a *generic* value -- the project template, a placeholder acceptor, an unset
constructor argument -- it reads that declaration. A named dye keeps the
geometry that is its own (linker length, dye radius); the linker width every
catalogue entry carried, 0.5 A, was one shared placeholder rather than a
per-dye measurement, so it is the declared width too, restated in the JSON
(which cannot import) and held to IMP.bff here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

bff = pytest.importorskip("IMP.bff")

REPO = Path(__file__).resolve().parents[1]


def test_av_defaults_are_imp_bffs():
    from chisurf.plugins.quenching_estimator.core.av import av1_parameter, av_defaults

    d = av_defaults()
    assert d["linker_length"] == bff.AV_DEFAULT_LINKER_LENGTH
    assert d["linker_width"] == bff.AV_DEFAULT_LINKER_WIDTH
    assert d["radius1"] == bff.AV_DEFAULT_RADIUS1
    assert d["simulation_grid_resolution"] == pytest.approx(
        bff.AV_DEFAULT_SIMULATION_GRID_RESOLUTION
    )
    assert av1_parameter() == {
        "linker_length": d["linker_length"],
        "linker_width": d["linker_width"],
        "radius1": d["radius1"],
    }


def test_the_template_project_takes_the_declared_defaults():
    from chisurf.plugins.quenching_estimator.core.av import av1_parameter, av_defaults
    from chisurf.plugins.quenching_estimator.core.project import template_project

    project = template_project(with_fret=True)
    assert project["dg"] == av_defaults()["simulation_grid_resolution"]
    assert project["av_parameter"] == av1_parameter()
    for dye in project["fret"]["dyes"]:
        assert dye["av_parameter"] == av1_parameter()


def test_an_unset_donor_decay_takes_the_declared_defaults():
    from chisurf.plugins.quenching_estimator.core.av import av1_parameter, av_defaults
    from chisurf.plugins.quenching_estimator.core.dye_diffusion import DonorDecay

    model = DonorDecay()
    assert model.dg == av_defaults()["simulation_grid_resolution"]
    assert model.av_parameter == av1_parameter()


def test_the_dye_catalogue_width_is_the_declared_width():
    catalogue = json.loads((REPO / "settings" / "dye_repository.json").read_text())
    assert catalogue
    for name, dye in catalogue.items():
        assert dye["av_parameter"]["linker_width"] == bff.AV_DEFAULT_LINKER_WIDTH, name
