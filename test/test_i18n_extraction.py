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


def test_catalogue_whitespace_is_preserved_without_translation_transfer(tmp_path):
    """An idempotent merge must still encode authored trailing spaces cleanly."""
    from build_tools.i18n.extract_strings import preserve_finished_translations

    source = '<TS><context><name>chisurf</name><message><source>Alpha \nBeta</source><translation type="unfinished"/></message></context></TS>'
    path = tmp_path / "catalogue.ts"
    path.write_text(source)
    preserve_finished_translations(source, path)
    assert "Alpha&#32;\nBeta" in path.read_text()
    import xml.etree.ElementTree as ET

    assert ET.parse(path).findtext(".//source") == "Alpha \nBeta"


def _catalogue_paths():
    """Every shipped ``.ts`` catalogue: chisurf's own plus the emtk, chimol and ndX ones."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1]
    dirs = [
        root / "chisurf" / "gui" / "i18n",
        root / "modules" / "ndxplorer" / "ndxplorer" / "locale",
    ]
    try:
        import emtk.i18n as emtk_i18n

        dirs.append(emtk_i18n.catalogue_directory())
    except Exception:  # emtk not installed: its catalogues are not under test here
        pass
    try:
        import chimol

        dirs.append(pathlib.Path(chimol.__file__).resolve().parent / "locales")
    except Exception:
        dirs.append(pathlib.Path.home() / "dev" / "chimol" / "chimol" / "locales")
    paths = sorted(p for d in dirs if d.is_dir() for p in d.glob("*.ts"))
    return paths


def _format_fields(text):
    import re

    return sorted(re.findall(r"\{[^{}]*\}|%\d+|%[sdr]", text))


def test_finished_translations_keep_whitespace_and_placeholders():
    """A finished translation keeps its source's edge whitespace and placeholder set.

    A translator fed an indented listing once returned every row indented by three spaces, so
    German/French labels were drawn shifted. The edge whitespace is part of the message (strings
    are concatenated and padded around), and a lost ``{name}`` / ``%1`` breaks formatting.
    """
    import xml.etree.ElementTree as ET

    paths = _catalogue_paths()
    assert any(p.name == "chisurf_de.ts" for p in paths)
    problems = []
    for path in paths:
        for message in ET.parse(path).getroot().iter("message"):
            source = message.findtext("source") or ""
            node = message.find("translation")
            if node is None or node.get("type") in ("unfinished", "obsolete", "vanished"):
                continue
            text = node.text or ""
            if not text.strip():
                continue
            lead = source[: len(source) - len(source.lstrip())]
            trail = source[len(source.rstrip()) :]
            if (
                text[: len(text) - len(text.lstrip())] != lead
                or text[len(text.rstrip()) :] != trail
                or _format_fields(source) != _format_fields(text)
            ):
                problems.append(f"{path.name}: {source[:60]!r} -> {text[:60]!r}")
    assert not problems, f"{len(problems)} translations drift from their source:\n" + "\n".join(
        problems[:20]
    )
