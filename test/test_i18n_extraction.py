"""The catalogue extractor follows the actual form's authored text vocabulary."""

import json

from build_tools.i18n import extract_strings as extractor


def test_form_text_arrays_choice_labels_and_identifiers():
    spec = {
        "type": "choice",
        "attr": "model_id",
        "label": "Estimator",
        "options": ["hidden_value"],
        "labels": ["Visible model"],
        "descriptions": ["Why choose this model"],
        "tooltip": "Visible tooltip",
        "special_text": "Automatic",
        "hint": "Enter a number",
        "units": "ns",
    }
    found = set()
    extractor._collect_from_json(spec, found)
    assert {
        "Estimator",
        "Visible model",
        "Why choose this model",
        "Visible tooltip",
        "Automatic",
        "Enter a number",
        "ns",
    } <= found
    assert not {"model_id", "hidden_value"} & found
    found = set()
    extractor._collect_from_json({"type": "choice", "options": [["key", "Pretty label"]]}, found)
    assert "Pretty label" in found and "key" not in found
    found = set()
    extractor._collect_from_json(
        {
            "type": "custom",
            "key": "data_table",
            "options": {
                "source": "binding_method",
                "columns": [{"title": "Value", "tooltip": "Measured quantity"}],
            },
        },
        found,
    )
    assert found == {"Value", "Measured quantity"}


def test_collects_bare_views_and_named_guides_and_rejects_bad_specs(tmp_path, monkeypatch):
    monkeypatch.setattr(extractor, "CHISURF", tmp_path)
    monkeypatch.setattr(extractor, "REPO", tmp_path)
    (tmp_path / "view.json").write_text(
        json.dumps({"sections": [{"type": "info", "text": "Bare view text"}]})
    )
    (tmp_path / "setup_guide.json").write_text(
        json.dumps({"steps": [{"title": "Guide title", "text": "Guide body"}]})
    )
    found = extractor.collect_strings()
    assert {"Bare view text", "Guide title", "Guide body"} <= found
    (tmp_path / "bad.view.json").write_text("{")
    import pytest

    with pytest.raises(ValueError, match="bad.view.json"):
        extractor.collect_strings()


def test_extractor_text_keys_cover_the_installed_renderer():
    from emtk.view_form import TEXT_KEYS

    assert extractor.TEXT_KEYS >= TEXT_KEYS


def test_catalogue_audit_retains_unfinished_sources_without_installing_them(tmp_path):
    from chisurf.emtk.i18n import read_catalog

    path = tmp_path / "catalogue.ts"
    path.write_text(
        "<TS><context><name>chisurf</name>"
        "<message><source>Finished</source><translation>Traduit</translation></message>"
        '<message><source>New source</source><translation type="unfinished"/></message>'
        '<message><source>Removed</source><translation type="obsolete">Old</translation></message>'
        "</context></TS>"
    )
    assert read_catalog(path) == {"chisurf": {"Finished": "Traduit"}}
    assert read_catalog(path, include_unfinished=True) == {
        "chisurf": {"Finished": "Traduit", "New source": ""}
    }


def test_finished_translation_moves_context_only_when_unambiguous(tmp_path):
    before = (
        "<TS><context><name>OldForm</name>"
        "<message><source>Detector setup</source><translation>Détecteurs</translation></message>"
        "<message><source>Open</source><translation>Ouvrir</translation></message>"
        "</context><context><name>Other</name>"
        "<message><source>Open</source><translation>Afficher</translation></message>"
        "</context></TS>"
    )
    path = tmp_path / "after.ts"
    path.write_text(
        "<TS><context><name>chisurf</name>"
        '<message><source>Detector setup</source><translation type="unfinished">Détecteurs</translation></message>'
        '<message><source>Open</source><translation type="unfinished">Ouvrir</translation></message>'
        "</context></TS>"
    )
    extractor.preserve_finished_translations(before, path)
    from chisurf.emtk.i18n import read_catalog

    assert read_catalog(path) == {"chisurf": {"Detector setup": "Détecteurs"}}


def test_committed_authored_ui_text_has_german_and_french_catalogue_sources(tmp_path, monkeypatch):
    """Compare shipped bytes, not uncommitted plugin prototypes, with real runtime catalogues."""
    import io
    import subprocess
    import tarfile
    from pathlib import Path

    from chisurf.emtk.i18n import read_catalog

    root = Path(__file__).resolve().parents[1]
    archive = subprocess.check_output(
        ["git", "archive", "--format=tar", "HEAD", "--", "chisurf"], cwd=root
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        bundle.extractall(tmp_path, filter="data")
    monkeypatch.setattr(extractor, "REPO", tmp_path)
    monkeypatch.setattr(extractor, "CHISURF", tmp_path / "chisurf")
    required = extractor.collect_strings()
    assert len(required) > 1000
    for locale in ("de", "fr"):
        catalog = read_catalog(
            root / "chisurf" / "gui" / "i18n" / f"chisurf_{locale}.ts", include_unfinished=True
        )
        present = set().union(*(set(messages) for messages in catalog.values()))
        assert not required - present, (
            f"{locale}: missing catalogue sources {sorted(required - present)[:20]}"
        )
