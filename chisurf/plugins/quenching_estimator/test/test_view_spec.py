"""`quest.view.json` is generated, and must stay that way.

The form's layout is derived from `quest/settings/parameter_catalog.json` by
`quest/gui/generate_view_spec.py`, exactly as `doc/parameters.md` is. The
generated file is committed so it can be read and diffed — which only helps if
it actually matches the generator, so this regenerates it in memory and
compares.

Runs without Qt: a view spec is data.
"""

from __future__ import annotations

import json

import pytest

from chisurf.plugins.quenching_estimator.core.i18n import (
    DEFAULT_LOCALE,
    available_locales,
    ui_strings,
)
from chisurf.plugins.quenching_estimator.gui.form_model import FIELD_PATHS
from chisurf.plugins.quenching_estimator.gui.generate_view_spec import (
    VIEW_SPEC_PATH,
    build_view_spec,
    view_spec_path,
    write_view_spec,
)

LOCALES = sorted(available_locales())


@pytest.fixture(scope="module")
def spec() -> dict:
    return build_view_spec()


def _walk(sections):
    for section in sections:
        yield section
        yield from _walk(section.get("sections", []))


@pytest.mark.parametrize("locale", LOCALES)
def test_the_committed_file_is_up_to_date(locale: str) -> None:
    path = view_spec_path(locale)
    assert path.is_file(), f"no view spec for {locale}"
    committed = json.loads(path.read_text(encoding="utf8"))
    assert committed == build_view_spec(locale), (
        f"{path.name} is stale — run `python -m quest.gui.generate_view_spec` "
        "(and never hand-edit it; edit the catalog or the locale file)"
    )


def test_regenerating_is_idempotent(tmp_path) -> None:
    first = write_view_spec(tmp_path / "a.json").read_text(encoding="utf8")
    second = write_view_spec(tmp_path / "b.json").read_text(encoding="utf8")
    assert first == second


class TestEveryLanguageGetsTheSameForm:
    """Translation changes the words. It must not change the form."""

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_bound_fields_are_identical(self, locale: str) -> None:
        english = {s["attr"] for s in _walk(build_view_spec()["sections"]) if s.get("attr")}
        other = {s["attr"] for s in _walk(build_view_spec(locale)["sections"]) if s.get("attr")}
        assert english == other

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_section_types_are_identical(self, locale: str) -> None:
        def shape(spec):
            return [s.get("type") for s in _walk(spec["sections"])]

        assert shape(build_view_spec(locale)) == shape(build_view_spec())

    @pytest.mark.parametrize("locale", LOCALES)
    def test_numeric_bounds_are_identical(self, locale: str) -> None:
        """A German spin box must not accept a different range."""

        def bounds(spec):
            return {
                s["attr"]: (s.get("minimum"), s.get("maximum"))
                for s in _walk(spec["sections"])
                if s.get("attr")
            }

        assert bounds(build_view_spec(locale)) == bounds(build_view_spec())

    @pytest.mark.parametrize("locale", [c for c in LOCALES if c != DEFAULT_LOCALE])
    def test_the_visible_text_actually_changed(self, locale: str) -> None:
        """Otherwise the whole thing silently renders in English."""
        spec = build_view_spec(locale)
        labels = [s.get("label") for s in _walk(spec["sections"]) if s.get("label")]
        english = [s.get("label") for s in _walk(build_view_spec()["sections"]) if s.get("label")]
        differing = sum(1 for a, b in zip(labels, english) if a != b)
        assert differing > len(labels) // 2, f"{locale} looks untranslated"

    @pytest.mark.parametrize("locale", LOCALES)
    def test_it_records_which_language_it_is(self, locale: str) -> None:
        assert build_view_spec(locale)["locale"] == locale

    @pytest.mark.parametrize("locale", LOCALES)
    def test_the_help_text_is_the_locale_s(self, locale: str) -> None:
        spec = build_view_spec(locale)
        help_section = next(s for s in _walk(spec["sections"]) if s.get("key") == "help")
        assert help_section["options"]["text"] == ui_strings(locale)["help.text"]


def test_it_says_it_is_generated() -> None:
    committed = json.loads(VIEW_SPEC_PATH.read_text(encoding="utf8"))
    assert "GENERATED" in committed["_comment"]


class TestEveryControlIsBound:
    def test_each_field_binds_to_a_real_model_attribute(self, spec) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        model = ProjectFormModel()
        for section in _walk(spec["sections"]):
            attr = section.get("attr")
            if attr:
                assert hasattr(model, attr), f"{attr} is bound but does not exist"

    def test_each_scalar_field_appears_exactly_once(self, spec) -> None:
        """Two controls for one value disagree the moment one is edited."""
        bound = [s["attr"] for s in _walk(spec["sections"]) if s.get("attr")]
        duplicates = {a for a in bound if bound.count(a) > 1}
        assert not duplicates, duplicates

    def test_every_declared_field_is_on_the_form(self, spec) -> None:
        bound = {s["attr"] for s in _walk(spec["sections"]) if s.get("attr")}
        # `status` and `fret_R0` are bound too, hence the subset direction.
        missing = set(FIELD_PATHS) - bound
        assert not missing, f"declared but not shown anywhere: {sorted(missing)}"

    def test_actions_and_sources_resolve(self, spec) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        model = ProjectFormModel()
        for section in _walk(spec["sections"]):
            for key in ("source", "update_call"):
                name = section.get(key)
                if name:
                    assert callable(getattr(model, name, None)), name
            for button in section.get("buttons", ()):
                assert callable(getattr(model, button["action"], None)), button


class TestItIsUsable:
    def test_every_field_has_help_text(self, spec) -> None:
        """The catalog's description is the tooltip; a blank one is a gap."""
        for section in _walk(spec["sections"]):
            if section.get("attr"):
                assert section.get("description"), section["attr"]

    def test_units_are_in_the_labels(self, spec) -> None:
        labels = {s["attr"]: s.get("label", "") for s in _walk(spec["sections"]) if s.get("attr")}
        # The Förster radius is the one that has actually been wrong; a label
        # without its unit is how 5.5 nm got read as 5.5 Å.
        assert "Å" in labels["fret_R0"]
        assert "ns" in labels["tau0"]

    def test_the_toolbar_can_run_save_and_load(self, spec) -> None:
        actions = {
            button["action"]
            for section in _walk(spec["sections"])
            for button in section.get("buttons", ())
        }
        assert {
            "run_simulation",
            "load_example",
            "save_project_dialog",
            "load_project_dialog",
        } <= actions

    def test_the_results_panel_plots_what_a_run_produces(self, spec) -> None:
        sources = {s["source"] for s in _walk(spec["sections"]) if s.get("type") == "plot"}
        assert sources == {
            "decay_series",
            "trajectory_series",
            "autocorrelation_series",
        }
