"""The name a per-pixel map carries in the measurement's file is a label, not a class.

A tool without a ``WINDOW_KIND`` fell back to ``type(self).__name__``, so the
intensity map of a CLSM measurement was stored under ``IntensityViewModel`` --
a Python class name, and a GUI one. It is what a reader (ndX, the container
listing, anyone opening the file in five years) sees, and renaming the class
would have renamed the artifact in every file written before it.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _model(cls_name: str, window_kind=None):
    """Return a view-model instance whose class name is *cls_name*."""
    from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

    made = type(cls_name, (ImagingMapViewModel,), {"WINDOW_KIND": window_kind})
    return made.__new__(made)


@pytest.mark.parametrize(
    ("class_name", "expected"),
    [
        ("IntensityViewModel", "intensity"),
        ("ImgPixelIntensityViewModel", "img_pixel_intensity"),
        ("DriftTool", "drift"),
        ("Flow", "flow"),
    ],
)
def test_the_class_name_becomes_a_label(class_name, expected):
    from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

    assert ImagingMapViewModel.artifact_name(_model(class_name)) == expected


def test_a_declared_window_kind_wins():
    """A tool that says what it computes keeps saying it."""
    from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

    model = _model("NBViewModel", window_kind="nb")
    assert ImagingMapViewModel.artifact_name(model) == "nb"


def test_a_name_never_comes_back_empty():
    """A container object with no name is unaddressable; a fallback beats that."""
    from chisurf.plugins.microscopy.imaging_common.base import ImagingMapViewModel

    assert ImagingMapViewModel.artifact_name(_model("ViewModel")) == "pixel_map"
