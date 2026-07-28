"""The browser opens TTTR files through the one staging seam, never directly.

``tttrlib.TTTR(path, None)`` hands a null ``const char *`` to C++ and **segfaults**
— it does not raise, so the ``except Exception`` around the call cannot catch it.
``reading_routine`` is ``None`` whenever no detector setup pins a container type,
which is the state the browser is in the moment a folder is dropped, so browsing a
folder of TTTR files before choosing a setup took the whole application down.
:func:`chisurf.core.fio.staging.open_tttr` resolves that to auto-detection (and is
the seam that makes a read LUT-aware), so these tests pin the call site to it.
"""

import ast
import pathlib

import pytest

IMAGE_MODULE = pathlib.Path(__file__).resolve().parents[1] / "core" / "image.py"


def _tttr_constructions(source: str) -> list[int]:
    """Return the lines constructing ``tttrlib.TTTR(...)`` directly."""
    tree = ast.parse(source)
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "TTTR"
            and isinstance(func.value, ast.Name)
            and func.value.id == "tttrlib"
        ):
            lines.append(node.lineno)
    return lines


def test_image_module_opens_through_the_staging_seam():
    """No direct ``tttrlib.TTTR(...)``; a ``None`` routine must not reach C++."""
    assert _tttr_constructions(IMAGE_MODULE.read_text(encoding="utf-8")) == []


def test_render_mosaic_array_survives_an_unreadable_file(tmp_path):
    """An unreadable file with no reading routine returns ``None``, not a crash."""
    pytest.importorskip("tttrlib")
    from chisurf.plugins.tttr.tttr_image_browser.core.image import render_mosaic_array

    unreadable = tmp_path / "empty.ptu"
    unreadable.write_bytes(b"")
    channels = {
        "Image": [
            {"window_range": (None, None), "detector_chs": [], "micro_time_range": (None, None)}
        ]
    }
    assert render_mosaic_array(unreadable, channels, None) is None
