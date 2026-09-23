"""A vector constant of ndX (``gamma[HF]``, ``gamma[LF]``) in the Global View.

Each element is published as a fitting parameter of its own, named
``name[population]``, so a fit parameter can be linked to one population's
value; pushing writes it back under the same name, which ndX's equations read
as that population's element.
"""
from types import SimpleNamespace

from chisurf.plugins.ndxplorer.parameters import NdxConstants


def test_every_element_is_a_parameter_of_its_own():
    window = SimpleNamespace(constants={"gamma": 0.7, "gamma[HF]": 0.61, "gamma[LF]": 0.83,
                                        "Bg": 1.2})
    group = NdxConstants()
    created = group.pull(window)
    assert created == ["gamma", "gamma[HF]", "gamma[LF]", "Bg"]
    assert {p.name for p in group.parameters_all} >= {"gamma[HF]", "gamma[LF]"}
    group.parameter("gamma[LF]").value = 0.9
    applied = group.push(window, recompute=False)
    assert applied["gamma[LF]"] == 0.9 and window.constants["gamma[LF]"] == 0.9
