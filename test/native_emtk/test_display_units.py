"""Times kept in seconds are shown in µs / ms / s, and written back in seconds."""

import pytest

from chisurf.emtk.display_units import ScaledParameters, scaled_sections, time_unit


@pytest.mark.parametrize(
    "seconds, unit",
    [(0.0005, "ms"), (0.001, "ms"), (0.05, "ms"), (2.0, "s"), (0.2, "s"), (5e-6, "µs"), (0.0, "ms"), (None, "ms")],
)
def test_the_unit_puts_the_value_between_0_1_and_100(seconds, unit):
    assert time_unit(seconds)[0] == unit


def test_a_seconds_parameter_is_shown_and_written_in_its_unit():
    schema = {"properties": {"T": {"unit": "s", "default": 0.0005, "minimum": 1e-9, "maximum": 1.0},
                             "L": {"default": 20}}}
    sections = [
        {"attr": "T", "label": "Window duration (T)", "kind": "float", "minimum": 1e-9, "maximum": 1.0,
         "style": "scientific", "description": "The window. Unit: s."},
        {"attr": "L", "label": "Min photons (L)", "kind": "int"},
    ]
    shown, factors = scaled_sections(sections, schema)
    assert factors == {"T": 1e3}
    assert shown[0]["suffix"] == " ms" and shown[0]["maximum"] == 1000.0 and "style" not in shown[0]
    assert shown[0]["description"].endswith("Unit: ms.") and shown[1] is sections[1]

    class Params:
        T = 0.0005
        L = 20

    params = Params()
    view = ScaledParameters(params, factors)
    assert view.T == pytest.approx(0.5) and view.L == 20
    view.T = 2.0
    assert params.T == pytest.approx(0.002)


def test_a_title_with_its_unit_loses_it_for_the_suffix():
    schema = {"properties": {"dt": {"unit": "s", "default": 1e-4}}}
    shown, _ = scaled_sections([{"attr": "dt", "label": "Bin width (s)", "kind": "float"}], schema)
    assert shown[0]["label"] == "Bin width" and shown[0]["suffix"] == " ms"


def test_a_count_rate_reads_in_kcps():
    from chisurf.emtk.display_units import rate_unit

    assert rate_unit(0.0) == ("kcps", 1e-3) and rate_unit(4000.0)[0] == "kcps" and rate_unit(2e6)[0] == "Mcps"
    schema = {"properties": {"background_cps": {"unit": "cps", "default": 0.0, "maximum": 1e9}}}
    shown, factors = scaled_sections(
        [{"attr": "background_cps", "label": "Background rate (cps)", "kind": "float",
          "description": "Background count rate. Unit: cps."}], schema)
    assert shown[0]["label"] == "Background rate" and shown[0]["suffix"] == " kcps"
    assert factors == {"background_cps": 1e-3} and shown[0]["description"].endswith("Unit: kcps.")
