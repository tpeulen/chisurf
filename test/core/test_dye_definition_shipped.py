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
