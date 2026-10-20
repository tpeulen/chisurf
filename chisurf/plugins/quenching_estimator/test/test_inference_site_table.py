"""Site tables: the MalE prototype's arithmetic exactly, then today's IMP.bff geometry, pinned.

Two things moved under the prototype's cached tables, both deliberately (imp.bff
``okf/quest-site-kernels.md``): the accessible volume (FPS-parity changes, 97 722 -> 106 992
voxels at 1OMP/72/L 20.12) and the voxel frame of the quenching model's stamps (anchored on
the attachment point instead of the snapped grid; about 0.3 ns at APO 233). So:

* on the prototype's own volume, rebuilt in its own frame, the port must give the shipped
  table bit for bit (``test_the_prototype_volume_gives_the_shipped_table``);
* on today's geometry the numbers are re-pinned (``REPIN``; the log line of 2026-10-20 in
  ``okf/log.md`` accounts for each).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from chisurf.plugins.quenching_estimator.core.inference import site_table as st

pytestmark = pytest.mark.needs_av

DATA = Path(__file__).resolve().parent / "data"
SHIPPED = DATA / "male_site_1omp72_L20.12.npz"
VOLUME = DATA / "male_site_1omp72_L20.12_volume.npz"

#: Today's IMP.bff AV and the grid frame (imp.bff 0b178903a).
REPIN = {
    "apo72_voxels": 106992,  # prototype 97722
    "apo72_exposure_mean": 0.9643839001655579,  # prototype 0.9620543718338013
    "apo233_L21.5_voxels": 138241,
    "direct_apo233": 2.831786916428258,  # notebook 2.59 (stored), 2.523 old frame + today's AV
}


@pytest.fixture(scope="module")
def apo72_atoms():
    return st.site_atoms(st.male_structure("APO"), 72)


def test_site_atoms_cut_the_labelled_residue_to_its_backbone(apo72_atoms):
    atoms = apo72_atoms
    at_site = (atoms["chain"] == "A") & (atoms["res_id"] == 72)
    assert sorted(np.char.strip(atoms["atom_name"][at_site].astype(str))) == sorted(
        ["N", "CA", "C", "O", "CB"]
    )
    assert len(atoms) == 2858  # the prototype's 1omp_site72.pdb
    assert not np.isin(np.char.strip(atoms["element"].astype(str)), ["H", "D"]).any()


def test_the_prototype_volume_gives_the_shipped_table(apo72_atoms):
    """The port's arithmetic is the notebook's: neighbours, contacts and exposure exactly.

    The volume is the prototype's voxel set (IMP.bff fceece9ed) with the frame it used,
    ``grid_origin = attachment - ((ng - 1) // 2 - 0.5) dg`` (imp.bff
    ``test_the_prototype_site_table_is_reproduced``).
    """
    import IMP.bff as bff

    v = np.load(VOLUME)
    ng, dg = int(v["ng"]), float(v["dg"])
    attachment = np.asarray(v["attachment"], dtype=float)
    density = np.zeros(ng**3)
    density[v["voxel_indices"]] = 1.0
    origin = attachment - ((ng - 1) // 2 - 0.5) * dg
    av = bff.ProbeAccessibleVolume([], density, list(origin), dg, "prototype", list(attachment))

    table = st.table_from_volume(av, apo72_atoms, 72)
    ref = np.load(SHIPPED)
    assert np.array_equal(table.neighbours, ref["neighbours"])
    assert table.contacts.dtype == np.float16
    assert np.array_equal(table.contacts, ref["contacts"])
    assert np.abs(table.exposure - ref["exposure"]).max() <= 1e-6
    assert table.meta["n_rotamer_quenchers"] > 0


def test_todays_geometry_is_pinned_and_cached(apo72_atoms, tmp_path, monkeypatch):
    table = st.site_table(st.male_structure("APO"), 72, 20.12, cache_dir=tmp_path)
    assert table.n_voxels == REPIN["apo72_voxels"]
    assert table.neighbours.shape == (table.n_voxels, 20)
    assert table.contacts.shape == (table.n_voxels, 5, 10, 2)
    assert abs(float(table.exposure.mean()) - REPIN["apo72_exposure_mean"]) < 1e-9
    assert table.path is not None and table.path.parent == tmp_path

    # the voxel centres are the grid's and lie within the linker of the attachment atom
    centres = table.voxel_centres()
    cb = np.asarray(table.meta["attachment"])
    assert np.linalg.norm(centres - cb, axis=1).max() <= 20.12 + 1e-9

    # a second call reads the file, it does not rebuild
    def no_build(*args, **kwargs):
        raise AssertionError("rebuilt a cached table")

    monkeypatch.setattr(st, "build_site_table", no_build)
    again = st.site_table(st.male_structure("APO"), 72, 20.12, cache_dir=tmp_path)
    assert again.path == table.path
    assert np.array_equal(again.contacts, table.contacts)

    # the key follows the inputs
    s = st.settings()
    key = st.site_key(st.male_structure("APO"), 72, 20.12)
    assert key != st.site_key(st.male_structure("APO"), 72, 20.4)
    assert key != st.site_key(st.male_structure("HOLO"), 72, 20.12)
    assert key != st.site_key(st.male_structure("APO"), 72, 20.12, settings_={**s, "clash": 3.0})


def test_every_feature_sits_in_the_volume_s_own_frame(apo72_atoms):
    """No double shift: contacts, neighbours and the volume share one frame.

    The volume's voxels are ``grid_origin + ijk dg``: only there do they all lie within the
    linker of the attachment atom (the attachment frame reaches 20.27 A at L 20.12). A
    quencher or slow centre is snapped to the nearest of those voxels and stamped with
    ``|d| < floor(R / dg) dg``; a brute-force count in that frame equals the kernels' tables
    voxel for voxel, and the same count a quarter voxel off does not.
    """
    import IMP.bff as bff

    s = st.settings()
    av = st.accessible_volume(apo72_atoms, 72, 20.12)
    centres = np.asarray(av.get_voxel_centres())
    indices = np.asarray(av.get_voxel_indices())
    origin, dg = np.asarray(av.get_grid_origin(), float), float(av.grid_step)
    ng = int(av.ng)
    attachment = np.asarray(av.get_attachment_point(), float)
    old = attachment + (np.stack(np.unravel_index(indices, (ng,) * 3), 1) - (ng - 1) // 2
                        + 0.5) * dg
    assert np.linalg.norm(centres - attachment, axis=1).max() <= 20.12
    assert np.linalg.norm(old - attachment, axis=1).max() > 20.12

    def count(points, centres_q, radius, shift=0.0):
        snapped = origin + shift + np.round((centres_q - origin - shift) / dg) * dg
        d = np.linalg.norm(points[:, None, :] + shift - snapped[None], axis=2)
        return (d < int(radius / dg) * dg - 1e-9).sum(1)

    quenchers = st.quencher_ensembles(apo72_atoms, 72)
    trp = np.array([q["crystal"] for q in quenchers if q["name"] == "TRP"])
    radius = bff.amino_acid_quenching_defaults(1.0, 1.0, float(s["dye_radius"]))["TRP"].quench_radius
    stamped = st.contact_map(av, quenchers, "TRP", 0.0, "crystal")[indices]
    assert np.array_equal(count(centres, trp, radius), stamped)
    assert not np.array_equal(count(centres, trp, radius, shift=0.25 * dg), stamped)

    types = st.residue_types(s)
    counts = np.asarray(bff.residue_type_neighbour_counts(av, st.obstacles(apo72_atoms), types,
                                                          float(s["slow_radius"])))
    slow = {}
    for a in apo72_atoms:
        key = (str(a["chain"]), int(a["res_id"]), str(a["res_name"]).strip())
        name = str(a["atom_name"]).strip()
        if name == "CB" or (name == "CA" and key not in slow):
            slow[key] = np.asarray(a["coord"], float)
    lys = np.array([x for (_, _, r), x in slow.items() if r == "LYS"])
    assert np.array_equal(count(centres, lys, float(s["slow_radius"])),
                          counts[:, types.index("LYS")])


def test_direct_method_and_walk_agree_on_the_corrected_frame():
    """Notebook cell 23 at APO 233, slow 0.3, L 21.5, tau0 4.108.

    The stored notebook had direct 2.59 vs walk 2.31 +- 0.03 ns (12 %). In the grid frame the
    two agree to a few per cent; the walk depends on the platform's random numbers, so only
    the notebook's tolerance is asserted for it.
    """
    v = st.settings()["validation"]
    atoms = st.site_atoms(st.male_structure(v["state"]), v["site"])
    av = st.accessible_volume(atoms, v["site"], v["linker_length"])
    assert len(np.asarray(av.get_voxel_indices())) == REPIN["apo233_L21.5_voxels"]
    direct = st.direct_lifetime(av, atoms, v["slow_factor"], v["tau0"])
    assert abs(direct - REPIN["direct_apo233"]) < 1e-9
    walks = st.walk_lifetimes(av, atoms, v["slow_factor"], v["tau0"])
    assert len(walks) == len(v["seeds"])
    assert abs(np.mean(walks) - direct) < v["tolerance"]


def test_a_missing_kernel_is_named(monkeypatch):
    import IMP.bff as bff

    monkeypatch.delattr(bff, "probe_solvent_exposure")
    with pytest.raises(ImportError, match="probe_solvent_exposure"):
        st._bff()


def test_a_prototype_cache_file_reads_as_a_table():
    table = st.load_site_table(SHIPPED)
    assert table.n_voxels == 97722
    assert table.voxel_indices is None
    with pytest.raises(ValueError):
        table.voxel_centres()
