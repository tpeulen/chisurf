"""Regression tests for the parameter-registry scoping fix (PRD-62).

Two unrelated classes constructing a ``FittingParameter`` with the same bare
name (e.g. FRET's Foerster-radius ``R0`` vs. an unrelated model's own ``R0``)
must never cross-contaminate descriptions. See ``chisurf/core/parameter.py``
(``Parameter.__init__``'s registry lookup) and
``build_tools/dev_utils/export_fitting_parameters.py`` (the registry generator).
"""

from __future__ import annotations

import chisurf.core.settings
import chisurf.core.fitting.parameter as fp


def _install_fake_registry():
    """Install a small, self-contained fake registry for hermetic assertions."""
    fake = {
        "version": 2,
        "parameters": {
            "R0": {
                "description": "Forster radius R0 of the donor-acceptor pair.",
                "ambiguous": True,
                "aliases": [],
                "label_texts": [],
                "sources": [
                    {"class": "FakeFretParameters"},
                    {"class": "FakeUnrelatedModel"},
                ],
            },
        },
        "by_qualified_id": {
            "FakeFretParameters.R0": {
                "description": "Forster radius R0 of the donor-acceptor pair.",
            },
            "FakeUnrelatedModel.R0": {
                "description": "Unrelated model's own R0, nothing to do with FRET.",
            },
        },
    }
    original = getattr(chisurf.core.settings, "parameter_registry", None)
    chisurf.core.settings.parameter_registry = fake
    return original


def _restore_registry(original):
    if original is None:
        if hasattr(chisurf.core.settings, "parameter_registry"):
            del chisurf.core.settings.parameter_registry
    else:
        chisurf.core.settings.parameter_registry = original


class FakeFretParameters:
    """Stand-in for chisurf.core.models.fret_parameters.FRETParameters."""

    def __init__(self):
        self.r0 = fp.FittingParameter(name="R0", value=52.0)


class FakeUnrelatedModel:
    """Stand-in for an FCS-style model that happens to reuse the name 'R0'."""

    def __init__(self):
        self.r0 = fp.FittingParameter(name="R0", value=0.25)


def test_same_bare_name_scoped_by_owning_class():
    """Two classes sharing a bare parameter name get their own descriptions."""
    original = _install_fake_registry()
    try:
        fret = FakeFretParameters()
        other = FakeUnrelatedModel()
        assert "Forster" in fret.r0.description
        assert "Unrelated" in other.r0.description
        assert fret.r0.description != other.r0.description
    finally:
        _restore_registry(original)


def test_explicit_registry_id_overrides_class_scoping():
    """An explicit registry_id is honored even when the class-scoped id would differ."""
    original = _install_fake_registry()
    try:
        p = fp.FittingParameter(name="anything", value=1.0, registry_id="FakeUnrelatedModel.R0")
        assert "Unrelated" in p.description
    finally:
        _restore_registry(original)


def test_ambiguous_bare_name_without_class_context_does_not_guess():
    """A name only resolvable via the ambiguous bare-name index gets no description."""
    original = _install_fake_registry()
    try:
        # Constructed at module scope (no owning-class frame), and the only
        # bare-name entry for "R0" is flagged ambiguous, so no class-scoped
        # match exists either: the lookup must not silently guess one class's
        # meaning for the other's parameter.
        p = fp.FittingParameter(name="R0", value=1.0)
        assert p.description == ""
    finally:
        _restore_registry(original)
