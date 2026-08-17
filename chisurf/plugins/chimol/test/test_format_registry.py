"""File formats and fetch sources are registries a plugin adds to.

``load`` routes on the format's *kind* (structure / map / trajectory /
session / plan), a plugin structure format brings its own reader whose
payload the viewer applies, and a plugin fetch source is recognised by its
identifier pattern before the built-in catch-all. Unloading the plugin
takes both away.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pytest

from chimol.io.registry import FETCH, FORMATS, FetchSource, FormatSpec
from chimol.plugins import load_plugins


def test_the_builtin_formats_route_by_kind():
    assert FORMATS.kind_of("x.pdb") == "structure"
    assert FORMATS.kind_of("x.cif") == "structure"
    assert FORMATS.kind_of("x.rmf.npz") == "structure"
    assert FORMATS.kind_of("x.dcd") == "trajectory"
    assert FORMATS.kind_of("emd_1234.map.gz") == "map"
    assert FORMATS.kind_of("x.pse") == "session"
    assert FORMATS.kind_of("plan.fps.json") == "plan"     # the compound suffix, not bare .json
    assert FORMATS.kind_of("x.json") is None
    assert ".map.gz" in FORMATS.suffixes("map")


def test_the_builtin_fetch_sources_are_the_repositories_table():
    from chimol.commands.command import Cmd

    assert FETCH.names()[-1] == "pdb", "the PDB catch-all must stay last"
    assert set(FETCH.names()) >= set(Cmd.REPOSITORIES)


def _read_xyz(path: pathlib.Path):
    """A toy reader: ``x y z`` per line -> a bare-coordinate payload."""
    from chimol.io.structure import StructurePayload

    coords = np.loadtxt(path, ndmin=2)
    return StructurePayload(coords=coords, trace_coords=None)


class _XyzPlugin:
    name = "xyz"

    def register(self, api):
        api.add_format(FormatSpec(name="xyz", suffixes=(".xyz",), kind="structure", read=_read_xyz))
        api.add_fetch_source(FetchSource(
            name="toydb", label="Toy DB", url="https://toy.example/{id}.xyz", suffix=".xyz",
            pattern=r"^toy[-_]\d+$",
        ))


@pytest.fixture
def qapp():
    from qtpy import QtWidgets

    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_a_plugin_format_is_read_by_its_reader_and_routed_by_load(qapp, tmp_path):
    from chimol.commands.command import Cmd
    from chimol.core.viewer import MolView
    from chimol.hosts.base import ViewerHost
    from chimol.io.structure import load_structure_payload
    from chimol.render.headless import SceneSink

    cmd = Cmd(None, plugins=False)
    loaded = load_plugins(cmd, [_XyzPlugin()])
    try:
        assert FORMATS.kind_of("a.xyz") == "structure"
        f = tmp_path / "three.xyz"
        f.write_text("0 0 0\n1 0 0\n0 1 0\n")
        _structure, payload = load_structure_payload(f)
        assert payload is not None and payload.coords.shape == (3, 3)

        # through the whole load path: host, viewer, command
        viewer = MolView(renderer_factory=SceneSink)
        host = ViewerHost(viewer)
        host.cmd = cmd
        cmd.set_window(host)
        errors: list[str] = []
        cmd.set_error_callback(errors.append)
        cmd.set_message_callback(lambda _m: None)
        cmd.do(f'load "{f}"')
        assert errors == [], errors
        assert len(viewer.objects) >= 1
        assert any(e.name.startswith("three") for e in viewer.objects.values())

        # the fetch source is recognised by pattern, before the PDB catch-all
        assert cmd._repository_for("toy-12") == "toydb"
        assert cmd._repository_for("148l") == "pdb"
        assert FETCH.names()[0] == "toydb"
    finally:
        loaded.unload("xyz")
    assert FORMATS.kind_of("a.xyz") is None
    assert FETCH.get("toydb") is None
    assert cmd._repository_for("toy-12") == "pdb"
