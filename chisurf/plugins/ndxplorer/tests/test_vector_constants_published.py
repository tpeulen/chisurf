"""A vector constant of ndX (``gamma[HF]``, ``gamma[LF]``) in the Global View.

Each element is a parameter of the window's constants group, named
``name[population]``, so its ChiSurf mirror is a fitting parameter of its own
and a fit parameter can be linked to one population's value; an edit of the
mirror is what ndX's equations read as that population's element.
"""

import pytest

pytest.importorskip("ndxplorer", reason="ndxplorer not on the path")

from ndxplorer.core import chisurf_binding  # noqa: E402
from ndxplorer.core.constants_group import (  # noqa: E402
    ConstantsMapping,
    build_constants_group,
    set_vector,
)


def test_every_element_is_a_parameter_of_its_own():
    group = build_constants_group({"gamma": 0.7, "Bg": 1.2})
    set_vector(group, "gamma", [0.61, 0.83], ["HF", "LF"])
    try:
        assert chisurf_binding.publish(group, "ndxplorer", "ndX constants")
        names = {p.name for p in chisurf_binding.chisurf_group(group).parameters_all}
        assert names >= {"gamma", "gamma[HF]", "gamma[LF]", "Bg"}
        chisurf_binding.mirrored(group.parameters_all_dict["gamma[LF]"]).value = 0.9
        assert ConstantsMapping(group)["gamma[LF]"] == pytest.approx(0.9)
    finally:
        chisurf_binding.withdraw("ndxplorer")
