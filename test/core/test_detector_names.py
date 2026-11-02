"""Detector names ``emission|excitation``; the historic green / red / yellow read as aliases."""

from chisurf.core.fluorescence import detector_names as dn


def test_the_default_names_cover_three_colour_fret_in_wavelength_order():
    assert dn.DEFAULT_NAMES == (
        "B|B", "G|B", "Y|B", "R|B", "G|G", "Y|G", "R|G", "Y|Y", "R|Y", "R|R",
    )
    assert dn.TWO_COLOUR == ("G|G", "R|G", "R|R")


def test_historic_names_are_aliases():
    assert [dn.canonical(n) for n in ("green", "Red", "YELLOW", "blue")] == ["G|G", "R|G", "R|R", "B|B"]
    assert dn.canonical("g|r") == "G|R" and dn.canonical("my APD") == "my APD"
    assert dn.find(["green", "red"], "R|G") == "red"
    assert dn.find(["G|G", "R|G"], "red") == "R|G"
    assert dn.canonical_detectors({"green": 1, "G|G": 2, "red": 3}) == {"G|G": 1, "R|G": 3}
    assert (dn.emission("R|G"), dn.excitation("R|G")) == ("R", "G")
    assert dn.emission("red") == "R" and dn.emission("my APD") is None


def test_columns_translate_both_ways_for_the_legacy_export():
    pairs = {
        "Number of Photons (G|G)": "Number of Photons (green)",
        "G|G Count Rate (KHz)": "Green Count Rate (KHz)",
        "R|G Count Rate (KHz)": "Red Count Rate (KHz)",
        "Tau (R|R)": "Tau (yellow)",
        "S prompt R|G (kHz) | 0-2048": "S prompt red (kHz) | 0-2048",
        "Duration (ms)": "Duration (ms)",
    }
    for new, old in pairs.items():
        assert dn.legacy_column(new) == old
        assert dn.column(old) == new


def test_labels_and_file_names():
    assert dn.label("G|G") == "G|G" and dn.label("green") == "Green"
    assert dn.slug("R|G") == "R-G"


def test_a_setup_is_read_under_the_names_and_the_store_converted_once(tmp_path):
    import json

    from chisurf.core.setup_channel_definition import ChannelDefinition, with_detector_names

    data, changed = with_detector_names(
        {"detectors": {"green": {"chs": [0, 2]}, "red": {"chs": [1, 3]}, "yellow": {"chs": [1, 3]}},
         "optical_config": {"detectors": [{"name": "green"}]}}
    )
    assert changed and list(data["detectors"]) == ["G|G", "R|G", "R|R"]
    assert data["optical_config"]["detectors"][0]["name"] == "G|G"
    assert with_detector_names(data)[1] is False

    path = tmp_path / "setups.json"
    path.write_text(json.dumps({"setups": {
        "lab": {"detectors": {"green": {"chs": [0]}, "red": {"chs": [1]}}},
        "theirs": {"detectors": {"green": {"chs": [0]}}, "_owner": "someone else"},
    }}))
    definition = ChannelDefinition(file_path=str(path))
    definition.refresh_setups()
    assert list(definition.setups["lab"]["detectors"]) == ["G|G", "R|G"]
    stored = json.loads(path.read_text())["setups"]
    assert list(stored["lab"]["detectors"]) == ["G|G", "R|G"]  # converted in the store, once
    assert list(stored["theirs"]["detectors"]) == ["green"]  # another user's setup is not rewritten
    definition.select_setup("theirs")
    assert list(definition.data["detectors"]) == ["G|G"]  # but read under the names


def test_the_editor_adds_a_detector_by_its_default_name():
    from chisurf.emtk.channel_definition import ChannelDefinitionWidget

    page = ChannelDefinitionWidget(settings={"detectors": {"green": {"chs": [0]}}})
    assert "G|G" not in page.unused_detector_names() and page.unused_detector_names()[0] == "B|B"
    page.add_detector("R|G")
    assert list(page.model.data["detectors"]) == ["G|G", "R|G"]


def test_roles_by_name_alias_or_word():
    assert [dn.role(n) for n in ("G|G", "R|G", "R|R", "green", "red", "yellow", "my donor", "ch3")] == [
        "donor", "acceptor", "acceptor_direct", "donor", "acceptor", "acceptor_direct", "donor", None,
    ]
    assert dn.detector_of_role(["red", "green"], "donor") == "green"
    assert dn.column_detector("Number of Photons (R|G)") == "R|G"
    assert dn.column_detector("Green Count Rate (KHz)") == "G|G"
    assert dn.column_detector("Duration (ms)") is None
