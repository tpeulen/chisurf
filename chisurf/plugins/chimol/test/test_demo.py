"""The ChiMOL host's example: the bundled T4 lysozyme, staged as a structure file."""

import pytest

from chisurf.plugins.chimol.demo import demo_folder, make_demo


def test_make_demo_stages_a_structure():
    """A real PDB (bundled or minimal synthetic) sits in the demo folder."""
    path = make_demo()
    text = path.read_text()
    assert path.stat().st_size > 0
    assert "ATOM" in text or "HETATM" in text


def test_load_example_loads_the_bundled_structure():
    """The host's own Load example runs the chimol catalogue's 148l."""
    chimol = pytest.importorskip("chimol")
    from chisurf.plugins.chimol.app import make_app

    app = make_app()
    loaded = app.load_example()
    assert loaded is True
    path = make_demo()
    assert path.is_file()
