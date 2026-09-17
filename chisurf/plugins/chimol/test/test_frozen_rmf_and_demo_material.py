"""The demos' material on a host with nothing but chimol: frozen RMF, shipped data, radii.

Everything here came out of making the eleven demos run in a page (see
``test_browser_demos.py``), but none of it is browser-specific -- a
toolkit-free desktop without ChiSurf, the RMF library or the swarm simulator
hits the same walls. So the pieces are pinned here, in-process:

* a **frozen RMF** (``io/rmf_snapshot.py``) reads back exactly what the RMF
  reader produced, and the structure loader takes it through the same
  ``_parse_rmf`` path -- with the RMF library present or blocked;
* the demo catalogue resolves the biofilm's ``load biofilm_growth.rmf`` to
  the shipped frozen copy when the simulator cannot run;
* the shipped ``plugins/demos/data`` carries every file a demo names;
* chimol's own PDB/mmCIF readers fill van der Waals radii by element -- left
  at zero, ``get_area polymer`` reported ``0.000 A^2`` on every host without
  the core reader.
"""
from __future__ import annotations

import pathlib
import sys

import numpy as np
import pytest

from chimol.plugins.demos.catalog import DEMO_DIR, DEMOS, read_demo, resolve_structure

DATA = pathlib.Path(DEMO_DIR)


# --------------------------------------------------------------------------- #
# The frozen RMF
# --------------------------------------------------------------------------- #
def _biofilm_snapshot() -> pathlib.Path:
    path = DATA / "biofilm_growth.rmf.npz"
    assert path.is_file(), "the frozen biofilm is part of the demo material"
    return path


def test_the_snapshot_round_trips_the_readers_dict(tmp_path):
    """Write from the live reader, read back: arrays equal, hierarchy equal."""
    RMF = pytest.importorskip("RMF", reason="needs the RMF library to read the source")
    from chimol.io.rmf import load_rmf_full
    from chimol.io.rmf_snapshot import read_rmf_snapshot, write_rmf_snapshot

    source = pathlib.Path.home() / ".chisurf" / "chimol_demos" / "biofilm_growth.rmf"
    if not source.is_file():
        pytest.skip("no generated biofilm RMF on this machine")
    data = load_rmf_full(source)
    out = write_rmf_snapshot(data, tmp_path / "biofilm_growth.rmf")
    assert out.name == "biofilm_growth.rmf.npz", "an .rmf freezes to its sidecar name"
    back = read_rmf_snapshot(out)
    assert set(back) == set(data)
    for key, value in data.items():
        if isinstance(value, np.ndarray):
            expected = value.astype(str) if value.dtype == object else value
            assert np.array_equal(back[key], expected), key
        elif key == "hierarchy":
            assert repr(back[key]) == repr(value)
        else:
            assert back[key] == value, key


def test_the_loader_reads_a_frozen_rmf_as_an_rmf():
    from chimol.io.structure import load_structure_payload

    structure, payload = load_structure_payload(_biofilm_snapshot())
    assert structure is None
    assert payload.reader == "rmf"
    assert payload.frames is not None and payload.frames.shape[0] == 60
    assert payload.hierarchy is not None and payload.hierarchy.children
    # The growth is in the per-frame radii: hidden (0) early, all present late.
    frame_radii = np.asarray(payload.extras["frame_radii"])
    assert (frame_radii[0] == 0).sum() > (frame_radii[-1] == 0).sum()


def test_the_loader_takes_the_sidecar_when_rmf_is_missing(tmp_path, monkeypatch):
    """`load x.rmf` on a host without RMF reads `x.rmf.npz` beside it."""
    import chimol.io.rmf as rmf_module
    from chimol.io.structure import load_structure_payload

    fake = tmp_path / "biofilm_growth.rmf"
    fake.write_bytes(b"not an rmf")
    (tmp_path / "biofilm_growth.rmf.npz").write_bytes(_biofilm_snapshot().read_bytes())
    monkeypatch.setattr(rmf_module, "RMF", None)
    _structure, payload = load_structure_payload(fake)
    assert payload.reader == "rmf" and payload.frames.shape[0] == 60


# --------------------------------------------------------------------------- #
# The demo material
# --------------------------------------------------------------------------- #
def test_the_biofilm_resolves_to_the_frozen_copy_without_the_simulator(monkeypatch):
    from chimol.plugins.demos import material as demo_data

    def unavailable(name):
        raise demo_data.DemoDataUnavailable("no simulator here")

    monkeypatch.setattr("chimol.plugins.demos.material.generated_demo_path", unavailable)
    resolved = pathlib.Path(resolve_structure("biofilm_growth.rmf"))
    assert resolved.name == "biofilm_growth.rmf.npz" and resolved.is_file()


def test_every_file_a_demo_names_ships_with_the_demos():
    """Own material, no checkout to walk to -- what a page (or a bare install) has.

    Or is published: the bulk data (chimol/data/registry.json) and the PetWorld
    models are fetched on first use from a recorded URL, not committed.
    """
    from chimol.plugins.demos.fetch import url_for

    named = set()
    for key, _t, _d in DEMOS:
        for line in read_demo(key).splitlines():
            verb, _, rest = line.strip().partition(" ")
            if verb in ("load", "load_traj") and rest and "," not in rest:
                named.add(rest.strip())
    missing = [
        name for name in sorted(named)
        if not (DATA / name).is_file() and not (DATA / f"{name}.npz").is_file()
        and url_for(name) is None
    ]
    assert not missing, f"neither shipped in plugins/demos/data nor published: {missing}"


def test_the_shipped_trajectory_fits_its_topology():
    from chimol.io.dcd import dcd_info

    header = dcd_info(DATA / "hgbp1_transition.dcd")
    n_atoms = sum(
        1 for line in (DATA / "topol.pdb").read_text().splitlines()
        if line.startswith(("ATOM", "HETATM"))
    )
    assert header.n_atoms == n_atoms
    assert header.n_frames >= 20, "enough frames to be a movie"


# --------------------------------------------------------------------------- #
# Radii from chimol's own readers
# --------------------------------------------------------------------------- #
def test_the_pdb_reader_fills_radii_by_element():
    from chimol.io.structure import _parse_pdb_backbone

    payload = _parse_pdb_backbone(str(DATA / "solvated_fragment.pdb"))
    radii = np.asarray(payload.atoms["radius"], dtype=float)
    assert np.all(radii > 0), "every atom has a van der Waals radius"
    elements = np.char.strip(payload.atoms["element"].astype(str))
    assert abs(float(radii[elements == "C"][0]) - 1.7) < 0.1
    assert abs(float(radii[elements == "ZN"][0]) - 1.39) < 0.05


def test_get_area_of_a_selection_is_not_zero_on_a_bare_host():
    """The measure demo's `get_area polymer` -- 0.000 A^2 before the radii were filled.

    Through the toolkit-free probe: that host reads with chimol's own parser,
    which is the configuration that had no radii.
    """
    from toolkit_free import probe

    m = probe(f'''
    app = open_app(size=(400, 300))
    messages = []
    app.cmd.set_message_callback(messages.append)
    app.cmd.set_error_callback(lambda e: messages.append("ERROR " + e))
    app.cmd.do("load {DATA / "solvated_fragment.pdb"}")
    app.cmd.do("get_area polymer")
    line = next((m for m in messages if m.startswith("get_area")), "none")
    emit("area_line", line)
    ''')
    line = m["area_line"]
    assert line.startswith("get_area:"), line
    assert float(line.split()[1]) > 100.0, line


# --------------------------------------------------------------------------- #
# `load` opens a map on every host
# --------------------------------------------------------------------------- #
def test_load_routes_a_map_to_load_map_on_a_bare_host(tmp_path):
    """`load x.mrc` used to feed the MRC bytes to the PDB parser here.

    The Qt window special-cased map suffixes in its own reader; the
    toolkit-free window and the page did not, so a dropped or mounted map
    reported "no coordinates". The command routes it now, for every host.
    """
    from test_volume import write_mrc
    from toolkit_free import probe

    grid = np.zeros((8, 8, 8), dtype=np.float32)
    grid[2:6, 2:6, 2:6] = 1.0
    path = tmp_path / "blob.mrc"
    write_mrc(path, grid, step=(1.5, 1.5, 1.5))

    m = probe(f'''
    app = open_app(size=(400, 300))
    messages = []
    app.cmd.set_message_callback(messages.append)
    app.cmd.set_error_callback(lambda e: messages.append("ERROR " + e))
    app.cmd.do("load {path}")
    emit("lines", " | ".join(messages))
    names = [str(e.get("name")) for e in app.viewer.list_objects()]
    emit("objects", ",".join(names))
    ''')
    assert "ERROR" not in m["lines"], m["lines"]
    assert "load_map" in m["lines"], m["lines"]
    assert "blob" in m["objects"], m["objects"]
