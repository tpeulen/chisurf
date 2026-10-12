"""Translations are shared by every surface, so they are tested in one place.

QuEst describes each parameter once, in the catalog; the locale files translate
that one description. The desktop form, `doc/parameters.<code>.md` and the web
API are all generated from the result — so what these tests protect is the
property that makes that work: **a translation is complete, structurally
identical to English, and never changes what the software computes.**

No Qt and no browser: locale files are data.
"""

from __future__ import annotations

import json
import re

import pytest

from chisurf.plugins.quenching_estimator.core import i18n
from chisurf.plugins.quenching_estimator.settings import parameter_catalog

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

CATALOG_PATHS = set(parameter_catalog()["parameters"])
TRANSLATED = sorted(code for code in i18n.available_locales() if code != i18n.DEFAULT_LOCALE)


def test_the_expected_languages_are_there() -> None:
    assert {"en", "de", "fr"} <= set(i18n.available_locales())


def test_languages_name_themselves() -> None:
    """A picker that says "German" is unreadable to the reader who needs it."""
    names = i18n.available_locales()
    assert names["de"] == "Deutsch"
    assert names["fr"] == "Français"
    assert names["en"] == "English"


class TestResolvingALocale:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("de", "de"),
            ("de_DE.UTF-8", "de"),
            ("fr-CA", "fr"),
            ("DE", "de"),
            ("cs_CZ", "en"),
            ("", "en"),
            (None, None),
        ],
    )
    def test_it_normalizes_and_falls_back(self, value, expected, monkeypatch) -> None:
        monkeypatch.delenv(i18n.LOCALE_ENV_VAR, raising=False)
        if expected is None:  # None means "whatever the system says" — just valid
            assert i18n.resolve_locale(value) in i18n.available_locales()
        else:
            assert i18n.resolve_locale(value) == expected

    def test_the_environment_variable_is_honoured(self, monkeypatch) -> None:
        monkeypatch.setenv(i18n.LOCALE_ENV_VAR, "fr")
        assert i18n.resolve_locale() == "fr"

    def test_an_explicit_argument_wins(self, monkeypatch) -> None:
        monkeypatch.setenv(i18n.LOCALE_ENV_VAR, "fr")
        assert i18n.resolve_locale("de") == "de"

    def test_an_unknown_language_is_not_an_error(self, monkeypatch) -> None:
        """`LANG=cs_CZ` should start QuEst, not make it explain itself."""
        monkeypatch.setenv(i18n.LOCALE_ENV_VAR, "cs")
        assert i18n.resolve_locale() == "en"


class TestEveryTranslationIsComplete:
    """A half-translated form is worse than an English one: it looks broken."""

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_all_parameters_are_translated(self, code: str) -> None:
        translated = set(i18n.locale_data(code).get("parameters", {}))
        missing = CATALOG_PATHS - translated
        assert not missing, f"{code}: untranslated parameters {sorted(missing)}"

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_no_parameter_is_invented(self, code: str) -> None:
        translated = set(i18n.locale_data(code).get("parameters", {}))
        extra = translated - CATALOG_PATHS
        assert not extra, f"{code}: translations for unknown parameters {sorted(extra)}"

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_every_entry_has_both_fields(self, code: str) -> None:
        for path, entry in i18n.locale_data(code).get("parameters", {}).items():
            assert entry.get("label"), f"{code}/{path}: no label"
            assert entry.get("description"), f"{code}/{path}: no description"

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_all_ui_strings_are_translated(self, code: str) -> None:
        english = set(i18n.locale_data(i18n.DEFAULT_LOCALE)["ui"])
        translated = set(i18n.locale_data(code).get("ui", {}))
        assert not english - translated, f"{code}: missing {sorted(english - translated)}"
        assert not translated - english, f"{code}: unknown {sorted(translated - english)}"

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_all_categories_are_translated(self, code: str) -> None:
        categories = {
            entry["category"] for entry in parameter_catalog()["parameters"].values()
        }
        translated = set(i18n.locale_data(code).get("categories", {}))
        assert not categories - translated, sorted(categories - translated)

    @pytest.mark.parametrize("code", TRANSLATED)
    def test_placeholders_survive_translation(self, code: str) -> None:
        """`{name}` renamed to `{Name}` is a crash at the moment it is shown."""
        import re

        english = i18n.locale_data(i18n.DEFAULT_LOCALE)["ui"]
        translated = i18n.locale_data(code)["ui"]
        for key, source in english.items():
            expected = set(re.findall(r"\{(\w+)\}", source))
            actual = set(re.findall(r"\{(\w+)\}", translated.get(key, "")))
            assert expected == actual, f"{code}/{key}: {expected} vs {actual}"


class TestTranslatingTheCatalog:
    def test_english_is_the_catalog_itself(self) -> None:
        catalog = i18n.translate_catalog("en")
        assert catalog["parameters"] == parameter_catalog()["parameters"]

    def test_a_translation_replaces_the_text(self) -> None:
        german = i18n.translate_catalog("de")["parameters"]["tau0"]
        assert german["label"] == "Ungelöschte Lebensdauer"
        assert "Fluoreszenzlebensdauer" in german["description"]

    def test_the_structure_never_changes(self) -> None:
        """Only text is translated. Types, units and keys are the model."""
        english = parameter_catalog()["parameters"]
        for code in TRANSLATED:
            translated = i18n.translate_catalog(code)["parameters"]
            assert set(translated) == set(english)
            for path, entry in translated.items():
                assert entry.get("type") == english[path].get("type"), path
                assert entry.get("unit") == english[path].get("unit"), path
                assert entry.get("category") == english[path].get("category"), path

    def test_it_does_not_mutate_the_shared_catalog(self) -> None:
        i18n.translate_catalog("de")
        assert parameter_catalog()["parameters"]["tau0"]["label"] == "Unquenched lifetime"

    def test_an_unknown_language_returns_english(self) -> None:
        assert i18n.translate_catalog("cs")["parameters"]["tau0"]["label"] == (
            "Unquenched lifetime"
        )


class TestUiStrings:
    def test_they_fall_back_to_english_key_by_key(self, tmp_path, monkeypatch) -> None:
        """A partial translation is useful; it must not be an error."""
        monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
        (tmp_path / "en.json").write_text(
            json.dumps({"locale": "en", "name": "English",
                        "ui": {"a": "Alpha", "b": "Beta"}}),
            encoding="utf8",
        )
        (tmp_path / "xx.json").write_text(
            json.dumps({"locale": "xx", "name": "Test", "ui": {"a": "Alfa"}}),
            encoding="utf8",
        )
        i18n.clear_cache()
        try:
            strings = i18n.ui_strings("xx")
            assert strings["a"] == "Alfa"
            assert strings["b"] == "Beta", "an untranslated key must keep its English"
        finally:
            i18n.clear_cache()

    def test_an_unknown_key_returns_itself(self) -> None:
        assert i18n.ui("no.such.key", "de") == "no.such.key"

    def test_a_broken_locale_file_is_skipped(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setattr(i18n, "LOCALES_DIR", tmp_path)
        (tmp_path / "en.json").write_text('{"locale": "en", "name": "English", "ui": {}}',
                                          encoding="utf8")
        (tmp_path / "zz.json").write_text("{ not json", encoding="utf8")
        i18n.clear_cache()
        try:
            assert "zz" not in i18n.available_locales()
        finally:
            i18n.clear_cache()


class TestTheScienceIsNotTranslated:
    """Language changes what a user reads, never what QuEst computes."""

    def test_the_project_is_identical_in_every_language(self) -> None:
        from chisurf.plugins.quenching_estimator.gui.form_model import ProjectFormModel

        projects = [ProjectFormModel(locale=code).to_project_dict()
                    for code in ("en", "de", "fr")]
        assert projects[0] == projects[1] == projects[2]

    def test_units_stay_in_their_symbols(self) -> None:
        """Å is Å in every language; a translated unit would be a bug."""
        for code in TRANSLATED:
            parameters = i18n.translate_catalog(code)["parameters"]
            assert parameters["fret.R0_matrix"]["unit"] == "Å"
            assert parameters["tau0"]["unit"] == "ns"

    def test_project_keys_are_never_translated(self) -> None:
        """Descriptions name real keys (`critical_distance`); those must survive."""
        german = i18n.translate_catalog("de")["parameters"]
        assert "critical_distance" in german["amino_acid_interactions.quench_radius"][
            "description"
        ]
        assert "slow_factor" in german["amino_acid_interactions"]["description"]


class TestTheServiceLayerServesLanguages:
    def test_it_lists_them(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import local_client

        response = local_client().call("quest.locales", {})
        assert response["ok"]
        assert set(response["result"]["available"]) >= {"en", "de", "fr"}
        assert response["result"]["strings"]["button.simulate"]

    def test_it_translates_the_catalog(self) -> None:
        from chisurf.plugins.quenching_estimator.rpc.services import local_client

        response = local_client().call("quest.parameter_catalog", {"locale": "fr"})
        assert response["ok"]
        assert response["result"]["parameters"]["tau0"]["label"] == (
            "Durée de vie non éteinte"
        )

    def test_no_locale_means_english_not_the_servers_language(self, monkeypatch) -> None:
        """A shared backend must not answer in whatever the host is set to."""
        from chisurf.plugins.quenching_estimator.rpc.services import local_client

        monkeypatch.setenv(i18n.LOCALE_ENV_VAR, "de")
        i18n.clear_cache()
        try:
            response = local_client().call("quest.parameter_catalog", {})
            assert response["result"]["parameters"]["tau0"]["label"] == (
                "Unquenched lifetime"
            )
        finally:
            i18n.clear_cache()

    def test_the_manifest_declares_the_locale_parameter(self) -> None:
        from pathlib import Path

        manifest = json.loads(
            (Path(__file__).resolve().parents[1] /  "manifest.json").read_text(
                encoding="utf8"
            )
        )
        methods = {entry["name"]: entry for entry in manifest["rpc_methods"]}
        assert "locale" in methods["quest.parameter_catalog"]["params_schema"][
            "properties"
        ]
        assert "quest.locales" in methods


class TestTheSystemLanguage:
    """Read from the environment, not `locale.getdefaultlocale()`.

    That function is deprecated and slated for removal in Python 3.15, and
    `locale.getlocale()` is not a substitute — it reports the *current* locale,
    which is `(None, None)` until something calls `setlocale`.
    """

    def test_it_reads_the_environment(self, monkeypatch) -> None:
        for name in i18n.SYSTEM_LOCALE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LANG", "de_DE.UTF-8")
        assert i18n.system_locale() == "de_DE.UTF-8"
        monkeypatch.delenv(i18n.LOCALE_ENV_VAR, raising=False)
        assert i18n.resolve_locale() == "de"

    def test_the_c_locale_means_no_preference(self, monkeypatch) -> None:
        """`LANG=C` asks for no localisation at all, not for a language."""
        for name in i18n.SYSTEM_LOCALE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LANG", "C")
        assert i18n.system_locale() is None
        monkeypatch.delenv(i18n.LOCALE_ENV_VAR, raising=False)
        assert i18n.resolve_locale() == "en"

    def test_the_most_specific_variable_wins(self, monkeypatch) -> None:
        for name in i18n.SYSTEM_LOCALE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LANG", "de_DE.UTF-8")
        monkeypatch.setenv("LC_ALL", "fr_FR.UTF-8")
        assert i18n.system_locale() == "fr_FR.UTF-8"

    def test_a_preference_list_takes_its_first_entry(self, monkeypatch) -> None:
        for name in i18n.SYSTEM_LOCALE_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
        monkeypatch.setenv("LANGUAGE", "fr:de:en")
        assert i18n.system_locale() == "fr"

    def test_no_deprecated_locale_call_remains(self) -> None:
        from pathlib import Path

        source = (Path(i18n.__file__)).read_text(encoding="utf8")
        assert "getdefaultlocale" not in source.replace(
            "locale.getdefaultlocale()`, which is deprecated", ""
        )
