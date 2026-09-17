"""The dye preset table and the dye-spec grammar behind `add_dye`.

The preset table is a shorthand for fps.json position fields, and the grammar
is what the `add_dye` command and the labelling wizard both parse. This suite
exists because the whole feature once shipped dead: ``to_position_params``
used a ``dict_factory`` that returned a *list*, so every caller that filled a
position with ``params.update(...)`` crashed on the first dye -- while the
surrounding suites stayed green, because nothing here was under test.
"""

from __future__ import annotations

import pytest
from chimol.plugins.labelling.dyes import (
    dye_parameters,
    list_dyes,
    parse_dye_spec,
    preset_names,
)


def test_the_shipped_table_loads():
    names = preset_names()
    assert "Cy5" in names and "Alexa488" in names
    assert all(d.simulation_type in ("AV1", "AV3") for d in list_dyes())


def test_a_preset_parses_to_position_fields():
    """The regression: a preset must come back as a **dict**, not a pair list."""
    params = parse_dye_spec("Cy5")
    assert isinstance(params, dict)
    assert params["simulation_type"] in ("AV1", "AV3")
    assert params["linker_length"] > 0.0
    assert params["radius1"] > 0.0


def test_the_fields_are_what_an_av_backend_reads():
    params = dye_parameters("Cy5")
    for field in (
        "linker_length",
        "linker_width",
        "radius1",
        "radius2",
        "radius3",
        "simulation_type",
    ):
        assert field in params, f"{field} missing from the preset"


def test_positional_av1_numbers_fill_in_order():
    params = parse_dye_spec("AV1 20 0.5 3.5")
    assert params == {
        "simulation_type": "AV1",
        "linker_length": 20.0,
        "linker_width": 0.5,
        "radius1": 3.5,
    }


def test_keywords_override_positional_numbers():
    params = parse_dye_spec("AV1 20 0.5 3.5 linker_length=25")
    assert params["linker_length"] == 25.0
    assert params["radius1"] == 3.5


@pytest.mark.parametrize(
    "spec",
    ["", "AV1 20 0.5 3.5 9.9", "AV1 not-a-number", "AV1", "AV9 1 2 3"],
)
def test_broken_specs_are_refused_with_the_reason(spec):
    with pytest.raises(ValueError):
        parse_dye_spec(spec)


def test_an_unknown_preset_name_is_not_silently_a_spec():
    """A typo'd preset must refuse rather than become a keyword soup."""
    with pytest.raises(ValueError):
        parse_dye_spec("Cy42")
