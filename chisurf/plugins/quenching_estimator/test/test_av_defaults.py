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


def test_the_allowed_sphere_is_imp_bffs_and_on():
    """Owner, 2026-10-12: "allowed sphere radius must be enabled by default".

    QuEst restates IMP.bff's ``AV_DEFAULT_ALLOWED_SPHERE`` (FPS's 2.25 A) because
    a module-level default argument cannot import IMP lazily; it was its own
    2.1 A until then. The form shows it when a project does not carry one.
    """
    from chisurf.plugins.quenching_estimator.core.av import (
        DEFAULT_ALLOWED_SPHERE_RADIUS,
        av_defaults,
    )
    from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

    assert DEFAULT_ALLOWED_SPHERE_RADIUS == bff.AV_DEFAULT_ALLOWED_SPHERE == 2.25
    assert av_defaults()["allowed_sphere_radius"] == DEFAULT_ALLOWED_SPHERE_RADIUS
    model = ProjectFormModel()
    assert model.av_allowed_sphere_radius == DEFAULT_ALLOWED_SPHERE_RADIUS
    model.av_allowed_sphere_radius = 3.0
    assert model.project["av_parameter"]["allowed_sphere_radius"] == 3.0


def test_the_obstacle_radius_scale_is_imp_bffs_and_reaches_the_volume():
    """Owner, 2026-10-12: one scale factor on IMP's radii to match FPS's.

    QuEst restates IMP.bff's ``AV_DEFAULT_RADIUS_SCALE`` (fitted to FPS's Bondi
    radii) and, because it hands IMP's radii to the array door itself, applies
    it there: the volume at the default is the volume at an explicit
    ``radius_scale`` of the same value, and 1.0 -- IMP's radii as they are --
    gives a smaller one (148L E96 CB, AV1 at IMP.bff's defaults).
    """
    from chisurf.plugins.quenching_estimator.core.av import (
        AV,
        DEFAULT_RADIUS_SCALE,
        av_defaults,
    )
    from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

    assert DEFAULT_RADIUS_SCALE == bff.AV_DEFAULT_RADIUS_SCALE
    assert av_defaults()["radius_scale"] == DEFAULT_RADIUS_SCALE
    model = ProjectFormModel()
    assert model.av_radius_scale == DEFAULT_RADIUS_SCALE
    model.av_radius_scale = 1.0
    assert model.project["av_parameter"]["radius_scale"] == 1.0

    pdb = str(REPO / "test" / "148l.pdb")
    site = dict(residue_seq_number=96, atom_name="CB", chain_identifier="E")
    default = AV(pdb, **site)
    explicit = AV(pdb, radius_scale=DEFAULT_RADIUS_SCALE, **site)
    unscaled = AV(pdb, radius_scale=1.0, **site)
    assert len(default.points) == len(explicit.points) > len(unscaled.points)
    with pytest.raises(ValueError):
        AV(pdb, radius_scale=0.0, **site)
