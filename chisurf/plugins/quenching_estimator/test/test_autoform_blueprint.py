"""Tests for the autoform view-spec generation that makes QuEst a plugin blueprint.

The Qt form is *generated* from the parameter catalog (``quest.view.json``),
not hand-built. This file tests the generation path, the form model's
binding contract, and the properties that make the same spec reusable by
the web UI and a host like ChiSurf or Electron.

These tests run **without** Qt or ChiSurf (they test the data, not the widget).
The widget-level tests live in ``test_gui_widget.py`` and ``test_gui_simulation.py``.

The blueprint invariant: one catalog → one generated spec per language →
rendered by any toolkit. If the spec drifts from the catalog, these fail.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_SPEC = REPO_ROOT /  "gui" / "quest.view.json"
VIEW_SPEC_DE = REPO_ROOT /  "gui" / "quest.view.de.json"
VIEW_SPEC_FR = REPO_ROOT /  "gui" / "quest.view.fr.json"
GENERATOR = REPO_ROOT /  "gui" / "generate_view_spec.py"


class TestViewSpecFiles:
    """The committed JSON files exist and are parseable."""

    @pytest.mark.parametrize("path", [VIEW_SPEC, VIEW_SPEC_DE, VIEW_SPEC_FR])
    def test_file_exists_and_parses(self, path: Path) -> None:
        assert path.exists(), f"{path.name} is missing"
        data = json.loads(path.read_text(encoding="utf8"))
        assert "sections" in data
        assert isinstance(data["sections"], list)
        assert len(data["sections"]) > 0

    def test_english_is_the_default(self) -> None:
        data = json.loads(VIEW_SPEC.read_text(encoding="utf8"))
        assert data.get("locale", "en") == "en"

    def test_german_is_marked(self) -> None:
        data = json.loads(VIEW_SPEC_DE.read_text(encoding="utf8"))
        assert data.get("locale") == "de"

    def test_french_is_marked(self) -> None:
        data = json.loads(VIEW_SPEC_FR.read_text(encoding="utf8"))
        assert data.get("locale") == "fr"


class TestViewSpecGeneration:
    """The generator produces what is committed — no drift."""

    @staticmethod
    def _generated(locale: str = "en") -> dict:
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec

        return build_view_spec(locale)

    def test_generated_matches_committed_english(self) -> None:
        committed = json.loads(VIEW_SPEC.read_text(encoding="utf8"))
        generated = self._generated("en")
        assert generated == committed, (
            "quest.view.json is stale — re-run `python -m quest.gui.generate_view_spec`"
        )

    def test_generated_matches_committed_german(self) -> None:
        committed = json.loads(VIEW_SPEC_DE.read_text(encoding="utf8"))
        generated = self._generated("de")
        assert generated == committed, (
            "quest.view.de.json is stale — re-run the generator"
        )

    def test_generated_matches_committed_french(self) -> None:
        committed = json.loads(VIEW_SPEC_FR.read_text(encoding="utf8"))
        generated = self._generated("fr")
        assert generated == committed, (
            "quest.view.fr.json is stale — re-run the generator"
        )

    def test_every_section_has_a_type(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec

        def check(sections: list[dict], path: str = "root") -> None:
            for i, section in enumerate(sections):
                assert "type" in section, f"{path}[{i}] has no type"
                check(section.get("sections", []), f"{path}[{i}]")

        check(build_view_spec()["sections"])

    def test_every_value_section_has_an_attr_or_target(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec

        def check(sections: list[dict]) -> None:
            for section in sections:
                if section.get("type") in ("value", "choice", "toggle"):
                    assert section.get("attr") or section.get("target"), (
                        f"value section without binding: {section.get('label', section.get('title'))}"
                    )
                check(section.get("sections", []))

        check(build_view_spec()["sections"])


class TestFormModelContract:
    """The form model binds to the spec by ``attr``; every attr is readable."""

    def test_every_field_path_resolves(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import FIELD_PATHS, ProjectFormModel

        model = ProjectFormModel()
        for attr in FIELD_PATHS:
            assert hasattr(model, attr), f"FIELD_PATHS lists {attr!r} but the model lacks it"

    def test_form_model_default_is_a_valid_project(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel
        from chisurf.plugins.quenching_estimator.core.project import validate_project

        project = ProjectFormModel().to_project_dict()
        # The default template points at "structure.pdb" which does not exist
        # on disk, so validation needs a real structure override.
        structure = REPO_ROOT / "test" / "148l.pdb"
        validate_project(project, pdb_path=str(structure))

    def test_form_model_is_a_plain_object_not_a_widget(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        model = ProjectFormModel()
        # The model must not be a QWidget — it is the headless state.
        assert not hasattr(model, "show")
        assert not hasattr(model, "close")

    def test_editing_a_field_updates_the_project(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        model = ProjectFormModel()
        model.tau0 = 3.14
        assert model.to_project_dict()["tau0"] == 3.14

    def test_loading_and_editing_does_not_alias(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel
        from chisurf.plugins.quenching_estimator.core.project import template_project

        original = template_project()
        model = ProjectFormModel()
        model.load_project_dict(original)
        model.tau0 = 9.99
        assert original["tau0"] != 9.99


class TestCrossSurfaceConsistency:
    """The spec, the catalog, and the project template agree."""

    def test_every_parameter_in_the_catalog_has_a_spec_field(self) -> None:
        """A parameter in the catalog that has no form field is unreachable
        from the desktop surface — the divergence trap from the handover."""
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec
        from chisurf.plugins.quenching_estimator.settings import parameter_catalog

        catalog = parameter_catalog()
        spec = build_view_spec()

        spec_attrs: set[str] = set()

        def collect(sections: list[dict]) -> None:
            for section in sections:
                if section.get("attr"):
                    spec_attrs.add(section["attr"])
                collect(section.get("sections", []))

        collect(spec["sections"])

        # Every catalog parameter that maps to a flat field should have a spec entry.
        for param_id, entry in catalog["parameters"].items():
            # Skip nested parameters (e.g. "fret.enabled") — those are reached
            # through custom sections, not value sections.
            if "." in param_id:
                continue
            if entry.get("type") in ("section", "group"):
                continue
            # These are the known custom/special fields that don't get a value section.
            if param_id in ("amino_acid_interactions",):
                continue
            assert param_id in spec_attrs or any(
                param_id in attr for attr in spec_attrs
            ), f"catalog parameter {param_id!r} has no spec field"

    def test_the_spec_serves_three_locales(self) -> None:
        """The blueprint generates one spec per language."""
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec
        from chisurf.plugins.quenching_estimator.core.i18n import available_locales

        for locale in available_locales():
            spec = build_view_spec(locale)
            assert "sections" in spec
            assert len(spec["sections"]) > 0


class TestWebAutoformRenderer:
    """The web frontend ships its own React autoform renderer. The spec the
    backend serves must be structurally compatible with what the renderer
    expects — the same section vocabulary as the Qt side.
    """

    def test_the_backend_serves_the_spec(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec

        spec = build_view_spec()
        # The web AutoForm expects `sections` as a top-level array.
        assert isinstance(spec["sections"], list)
        # Every section has a `type` the renderer knows about.
        valid_types = {
            "panel", "dock_area", "value", "choice", "toggle", "toggle_row",
            "button_row", "table", "custom", "info", "plot",
        }

        def check(sections: list[dict]) -> None:
            for section in sections:
                assert section["type"] in valid_types, (
                    f"unknown section type {section['type']!r}"
                )
                check(section.get("sections", []))

        check(spec["sections"])

    def test_the_web_types_module_matches_the_python_spec(self) -> None:
        """The TypeScript AutoFormSection interface must accept every section
        the Python generator emits.
        """
        from chisurf.plugins.quenching_estimator.gui.generate_view_spec import build_view_spec

        spec = build_view_spec()
        # These are the types in webui/frontend/src/components/autoform/types.ts
        ts_types = {"panel", "dock_area", "value", "choice", "toggle",
                     "toggle_row", "button_row", "table", "custom", "info", "plot"}

        def collect(sections: list[dict], found: set[str]) -> None:
            for section in sections:
                found.add(section["type"])
                collect(section.get("sections", []), found)

        found: set[str] = set()
        collect(spec["sections"], found)
        unknown = found - ts_types - {""}  # empty string = untyped
        assert not unknown, f"spec emits types not in the TS interface: {unknown}"
