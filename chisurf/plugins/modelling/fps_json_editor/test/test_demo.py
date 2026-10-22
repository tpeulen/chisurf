"""The FPS JSON editor's example: a labelling plan from the shipped examples."""

import json

import pytest

from chisurf.plugins.modelling.fps_json_editor.demo import demo_folder, load_document, make_demo


def test_make_demo_stages_a_real_fps_json():
    """The sample document is the FRET-modelling plugin's tutorial plan."""
    path = make_demo()
    payload = json.loads(path.read_text())
    assert "Positions" in payload or "Mean FRET Efficiencies" in payload
    assert demo_folder() / "sample.fps.json" == path


def test_load_document_round_trips():
    """The headless half loads, edits and saves the sample document."""
    model = load_document()
    payload = model.fps_json_payload
    assert payload, "the sample document parsed to an empty payload"
    model.add_score_set("demo_score_set")
    out = demo_folder() / "sample_edited.fps.json"
    model.save_file(str(out))
    reloaded = json.loads(out.read_text())
    assert "demo_score_set" in json.dumps(reloaded)


def test_load_into_opens_the_structure_in_chimol():
    """The editor is a ChiMOL window; the affordance opens the bundled structure there."""
    pytest.importorskip("chimol")
    from chisurf.plugins.modelling.fps_json_editor.gui.app import make_app

    app = make_app()
    assert app.load_example() is True
    assert make_demo().is_file()
