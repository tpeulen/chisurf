"""The dye presets file ships with the package: the FPS editors' Dye Preset lists read it."""

import json
from pathlib import Path

import chisurf.core.settings as settings


def test_dye_definition_json_is_shipped_and_loaded():
    path = Path(settings.package_directory) / "dye_definition.json"
    assert path.is_file(), "chisurf/core/settings/dye_definition.json is missing"
    data = json.loads(path.read_text())
    assert {"D3-Alexa488", "D1-Alexa488"} <= set(data)
    for preset in data.values():
        assert {"diffusion_coefficient", "av_length", "av_radius1", "av_linker_width"} <= set(
            preset
        )

    import chisurf.core.structure.av as av

    assert "D3-Alexa488" in av.dye_definition and "a" not in av.dye_definition


def test_the_alexa488_presets_are_the_av_defaults():
    """The presets are FPS's Alexa488 row, which IMP.bff declares as the AV defaults.

    A json file cannot read the declaration, so this holds the two together. The
    presets carried a 0.5 A linker width until 2026-10-11 (owner: "all use same
    defaults"); FPS's Alexa488 linker is 4.5 A wide.
    """
    from chisurf.core.structure.av import av_defaults

    defaults = av_defaults()
    data = json.loads((Path(settings.package_directory) / "dye_definition.json").read_text())
    for name in ("D3-Alexa488", "D1-Alexa488"):
        assert data[name]["av_length"] == defaults["linker_length"], name
        assert data[name]["av_linker_width"] == defaults["linker_width"], name
        assert data[name]["av_radius1"] == defaults["radius1"], name


def test_the_dye_group_starts_at_the_av_defaults():
    """The dye-diffusion ``Dye`` group read W 0.5, R 1.5 and a 0.5 A grid of its own."""
    from types import SimpleNamespace

    from chisurf.core.structure.av import av_defaults
    from chisurf.core.structure.av.parameters import Dye

    defaults = av_defaults()
    dye = Dye(SimpleNamespace(structure=None))
    assert dye.av_length == defaults["linker_length"]
    assert dye.av_width == defaults["linker_width"]
    assert dye.av_radius == defaults["radius1"]
    assert dye.simulation_grid_resolution == defaults["simulation_grid_resolution"]
    preset = Dye(SimpleNamespace(structure=None), dye_name="D1-Alexa488")
    assert preset.av_parameter == {
        "linker_length": defaults["linker_length"],
        "linker_width": defaults["linker_width"],
        "radius1": defaults["radius1"],
    }


def test_a_preset_sets_the_fps_cards_numbers():
    """The FPS card's Dye Preset read fps.json keys from a file that spells them ``av_*``."""
    from chisurf.plugins.modelling.structure_tools.cards.fps_model import dye_presets

    preset = dye_presets()["D1-Alexa488"]
    assert {"linker_length", "linker_width", "radius1"} <= set(preset)
