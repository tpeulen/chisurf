"""Qt-free potential registry for the native Potential-Energy app.

The Qt tool builds its potentials from :data:`chisurf.gui.widgets.structure.potentialDict`,
whose editor widgets double as the potential objects. Importing that registry pulls in
Qt, so the native app cannot use it. This module mirrors the same potential set over the
Qt-free core classes in :mod:`chisurf.core.structure.potential.potentials` (the same
classes the Qt editors subclass) together with the parameters each Qt editor exposes.

The defaults are the *effective* values the Qt path computes with (which is not always
what its spinboxes display — the Iso-UNRES CA-cutoff spinbox shows 20.0 while the
constructor passes 25.0, and the ASA probe field shows 3.5 while the core constructor
resets it to 1.0), so energies scored with untouched defaults match the Qt tool.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass


def _database(name: str) -> str:
    """The bundled potential table *name* -- the path the Qt editors show by default."""
    from chisurf.core.settings.path_utils import get_path

    return str(get_path("chisurf") / "core/structure/potential/database" / name)


@dataclass(frozen=True)
class PotentialParam:
    """One editable constructor parameter of a potential."""

    attr: str
    label: str
    kind: str  # "float", "int", "bool" or "file"
    default: float | int | bool | str
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    tip: str = ""


@dataclass(frozen=True)
class PotentialSpec:
    """A potential type constructible without Qt."""

    name: str
    cls_path: str
    params: tuple[PotentialParam, ...] = ()


_SPECS: dict[str, PotentialSpec] = {
    spec.name: spec
    for spec in (
        PotentialSpec(
            "H-Bond",
            "chisurf.core.structure.potential.potentials:HPotential",
            (
                PotentialParam(
                    "cutoff_ca",
                    "Cutoff CA",
                    "float",
                    8.0,
                    0.0,
                    100.0,
                    0.5,
                    "C-alpha distance cutoff in Å below which residues pair.",
                ),
                PotentialParam(
                    "cutoff_hbond",
                    "Cutoff H",
                    "float",
                    3.0,
                    0.0,
                    20.0,
                    0.25,
                    "Heavy-atom distance cutoff in Å for a hydrogen bond.",
                ),
                PotentialParam("oh", "OH", "bool", True, tip="Include O···H pair interactions."),
                PotentialParam("on", "ON", "bool", True, tip="Include O···N pair interactions."),
                PotentialParam("cn", "CN", "bool", True, tip="Include C···N pair interactions."),
                PotentialParam("ch", "CH", "bool", True, tip="Include C···H pair interactions."),
                PotentialParam(
                    "potential",
                    "Potential",
                    "file",
                    _database("hb.npy"),
                    tip="NumPy table of the hydrogen-bond potential (the bundled hb.npy by default).",
                ),
            ),
        ),
        PotentialSpec(
            "AV-Potential",
            "chisurf.core.structure.potential.av_potential:AvPotential",
            (
                PotentialParam(
                    "av_samples",
                    "nSamples",
                    "int",
                    10000,
                    1,
                    999999,
                    1000,
                    "Number of Monte-Carlo samples per accessible volume.",
                ),
                PotentialParam(
                    "min_av",
                    "MinAV",
                    "int",
                    150,
                    0,
                    999999,
                    50,
                    "Minimum number of accessible-volume points.",
                ),
                PotentialParam(
                    "labeling_file",
                    "Labeling file",
                    "file",
                    "",
                    tip="FPS JSON naming the labeling positions and distances; empty uses none.",
                ),
            ),
        ),
        PotentialSpec(
            "Iso-UNRES",
            "chisurf.core.structure.potential.potentials:CEPotential",
            (
                PotentialParam(
                    "ca_cutoff",
                    "CA-cutoff",
                    "float",
                    25.0,
                    10.0,
                    27.0,
                    0.5,
                    "C-alpha cutoff in Å for residue contacts (10–27).",
                ),
                PotentialParam(
                    "potential",
                    "Potential",
                    "file",
                    _database("unres.npy"),
                    tip="NumPy table of the contact potential (the bundled unres.npy by default).",
                ),
            ),
        ),
        PotentialSpec(
            "Miyazawa-Jernigan",
            "chisurf.core.structure.potential.potentials:MJPotential",
            (
                # The core kwarg really is spelled `ca_cutcoff`.
                PotentialParam(
                    "ca_cutcoff",
                    "CA-cutoff",
                    "float",
                    6.5,
                    0.0,
                    100.0,
                    0.5,
                    "C-alpha cutoff in Å for the statistical contact potential.",
                ),
                PotentialParam(
                    "filename",
                    "Potential",
                    "file",
                    _database("mj.npy"),
                    tip="NumPy table of the Miyazawa-Jernigan potential (the bundled mj.npy by default).",
                ),
            ),
        ),
        PotentialSpec(
            "Go-Potential",
            "chisurf.core.structure.potential.potentials:GoPotential",
            (
                PotentialParam(
                    "epsilon", "epsilon", "float", 1.0, 0.0, 1000.0, 0.1, "Contact energy scale."
                ),
                PotentialParam(
                    "cutoff",
                    "Native cutoff [A]",
                    "float",
                    6.5,
                    0.0,
                    100.0,
                    0.5,
                    "Native-contact distance cutoff in Å.",
                ),
                PotentialParam(
                    "native_cutoff_on",
                    "Native cutoff on",
                    "bool",
                    True,
                    tip="Apply the native-contact distance cutoff.",
                ),
                PotentialParam(
                    "nnEFactor",
                    "Non-native / scale",
                    "float",
                    0.7,
                    0.0,
                    10.0,
                    0.05,
                    "Energy scale of non-native contacts.",
                ),
                PotentialParam(
                    "non_native_contact_on",
                    "Non-native on",
                    "bool",
                    True,
                    tip="Include non-native contacts.",
                ),
            ),
        ),
        PotentialSpec(
            "ASA-Calpha",
            "chisurf.core.structure.potential.potentials:ASA",
            (
                PotentialParam(
                    "n_sphere_point",
                    "sphere-points",
                    "int",
                    590,
                    1,
                    100000,
                    10,
                    "Number of points on the test sphere.",
                ),
                PotentialParam(
                    "probe",
                    "Probe-radius [A]",
                    "float",
                    1.0,
                    0.0,
                    20.0,
                    0.1,
                    "Solvent probe radius in Å.",
                ),
                PotentialParam(
                    "radius",
                    "Radius [A]",
                    "float",
                    2.5,
                    0.0,
                    20.0,
                    0.1,
                    "Extended-atom radius in Å.",
                ),
            ),
        ),
        PotentialSpec(
            "Clash potential",
            "chisurf.core.structure.potential.potentials:ClashPotential",
            (
                PotentialParam(
                    "clash_tolerance",
                    "Clash-tolerance",
                    "float",
                    2.0,
                    0.01,
                    100.0,
                    0.25,
                    "Distance by which van-der-Waals overlaps are tolerated.",
                ),
                PotentialParam(
                    "covalent_radius",
                    "Bond length",
                    "float",
                    1.5,
                    0.25,
                    10.0,
                    0.25,
                    "Covalent bond length in Å used to exclude bonded pairs.",
                ),
            ),
        ),
        PotentialSpec(
            "Ramachandran",
            "chisurf.core.structure.potential.potentials:Ramachandran",
            (
                PotentialParam(
                    "filename",
                    "Ramachandran file",
                    "file",
                    "",
                    tip="NumPy Ramachandran potential file; empty uses the built-in database.",
                ),
            ),
        ),
        PotentialSpec(
            "Radius of Gyration",
            "chisurf.core.structure.potential.potentials:RadiusGyration",
            (),
        ),
    )
}


def potential_names() -> list[str]:
    """Names of the available potential types, in registry order."""
    return list(_SPECS)


def get_spec(name: str) -> PotentialSpec | None:
    """Return the spec registered under *name*, or ``None``."""
    return _SPECS.get(name)


def make_potential(name: str, values: dict | None = None, structure=None):
    """Instantiate the core potential *name* with editor *values*.

    ``structure`` may be ``None``; the universe injects the structure being scored
    into every potential before calling ``getEnergy``.
    """
    spec = _SPECS.get(name)
    if spec is None:
        raise KeyError(f"No potential spec for '{name}'")
    module_name, _, cls_name = spec.cls_path.partition(":")
    cls = getattr(importlib.import_module(module_name), cls_name)
    kwargs = {}
    for param in spec.params:
        value = (values or {}).get(param.attr, param.default)
        if param.kind == "file" and not value:
            value = None
        kwargs[param.attr] = value
    return cls(structure=structure, **kwargs)


__all__ = ["PotentialParam", "PotentialSpec", "get_spec", "make_potential", "potential_names"]
