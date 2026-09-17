"""Getting an entry *in*: which repository an id belongs to, and which formats read.

Two ways a structure never reaches the viewer, both of which report something
that sends you looking in the wrong place:

* an identifier routed to the wrong service comes back as "that repository has
  no entry X" — a true statement about the wrong repository;
* a BinaryCIF opened as text comes back as "no coordinates" — a true statement
  about the nonsense that survived decoding.

Neither looks like a bug in the thing that is actually wrong.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from chimol.commands.builtin.loader import LoaderCommands


def _repository_for(code: str) -> str:
    """Resolve an identifier exactly as ``_repository_for`` does."""
    lowered = code.lower()
    for name, spec in LoaderCommands.REPOSITORIES.items():
        if re.match(spec["pattern"], lowered):
            return name
    return "pdb"


# --------------------------------------------------------------------------- #
# Which repository an identifier belongs to
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code",
    ["PDBDEV_00000012", "pdbdev_00000010", "PDBDEV-12", "pdbdev12", "ihm-12", "IHM_7"],
)
def test_an_integrative_identifier_goes_to_pdb_ihm(code):
    """``PDBDEV_00000012`` is the canonical form and must resolve on its own.

    It is what the entry is called on the site, in the nuclear-pore demo and in
    the viewer guide — and it matched no pattern at all, so `fetch
    PDBDEV_00000012` asked **RCSB** for a PDB entry and reported a PDB failure.
    Only the explicit `fetch PDBDEV_00000012, pdb-ihm` in the docs hid it.
    """
    assert _repository_for(code) == "pdb-ihm"


@pytest.mark.parametrize("code", ["148l", "8zzc", "1abc", "pdb_00008zzc"])
def test_an_ordinary_code_still_goes_to_rcsb(code):
    r"""A four-character code is a PDB code, including when it starts with a digit.

    PDB-IHM used to claim `^\d[0-9a-z]{3}$`, which is both unreachable (it sits
    behind "any four characters") and wrong if reached: `148l` and `8zzc` are
    ordinary PDB entries.
    """
    assert _repository_for(code) == "pdb"


@pytest.mark.parametrize("code", ["EMD-3061", "emd_1234", "EMD3061"])
def test_a_map_identifier_goes_to_emdb(code):
    assert _repository_for(code) == "emdb"


def test_the_catch_all_is_last():
    """``pdb`` matches almost anything, so every other entry must precede it.

    This is the property that made the PDB-IHM pattern dead code, and it is
    invisible in the patterns themselves — it lives in the *order* of a dict.
    """
    names = list(LoaderCommands.REPOSITORIES)
    assert names[-1] == "pdb", "the catch-all must be tried last"


def test_every_repository_is_reachable_by_some_identifier():
    """A pattern no identifier can reach is dead configuration.

    The guard is generic on purpose: it fails for the next entry added behind
    the catch-all too, not only for the one that was wrong.
    """
    samples = {
        "pdb": "148l",
        "emdb": "EMD-3061",
        "pdb-ihm": "PDBDEV_00000012",
        "alphafold": "AF-P69905-F1",
        "shareloc": "shareloc-1234567",
        "npc": "npc-cell2",
    }
    assert set(samples) == set(LoaderCommands.REPOSITORIES), (
        "a repository was added or renamed; give it a sample identifier here"
    )
    for name, code in samples.items():
        assert _repository_for(code) == name, f"{name} is unreachable via {code}"


# --------------------------------------------------------------------------- #
# BinaryCIF
# --------------------------------------------------------------------------- #
def _write_bead_system(path: pathlib.Path, *, binary: bool) -> None:
    """Write a three-bead integrative model as mmCIF or BinaryCIF."""
    import ihm
    import ihm.dumper
    import ihm.model
    import ihm.representation

    system = ihm.System(title="format probe")
    entity = ihm.Entity("ACGT" * 3, description="Mol")
    system.entities.append(entity)
    asym = ihm.AsymUnit(entity, details="A")
    system.asym_units.append(asym)

    class _Model(ihm.model.Model):
        def get_spheres(self):
            for i in range(3):
                yield ihm.model.Sphere(
                    asym_unit=asym, seq_id_range=(i + 1, i + 1),
                    x=float(i), y=float(2 * i), z=0.0, radius=5.0 + i,
                )

    representation = ihm.representation.Representation(
        [ihm.representation.FeatureSegment(
            asym, rigid=False, primitive="sphere", count=3, starting_model=None)]
    )
    system.orphan_representations.append(representation)
    model = _Model(assembly=ihm.Assembly([asym]), protocol=None,
                   representation=representation)
    system.state_groups.append(
        ihm.model.StateGroup([ihm.model.State([ihm.model.ModelGroup([model])])])
    )

    if binary:
        with open(path, "wb") as handle:
            ihm.dumper.write(handle, [system], format="BCIF")
    else:
        with open(path, "w") as handle:
            ihm.dumper.write(handle, [system])


def test_binarycif_reads_the_same_as_mmcif(tmp_path):
    """The same model in both encodings must produce the same payload.

    BinaryCIF is msgpack. It was routed to the mmCIF reader and opened in *text*
    mode with ``errors="ignore"``, which cannot work and cannot fail honestly:
    the decoder throws away every byte it cannot turn into UTF-8, so the reader
    saw a truncated nonsense document and said the file had no coordinates.
    """
    pytest.importorskip("ihm.format_bcif", reason="BinaryCIF needs ihm + msgpack")
    from chimol.io.structure import _parse_mmcif_backbone

    text_path = tmp_path / "model.cif"
    binary_path = tmp_path / "model.bcif"
    _write_bead_system(text_path, binary=False)
    _write_bead_system(binary_path, binary=True)

    # It really is binary -- otherwise this test would pass on a text file
    # renamed `.bcif` and prove nothing.
    head = binary_path.read_bytes()[:64]
    assert b"data_" not in head, "the fixture is not BinaryCIF"

    from_text = _parse_mmcif_backbone(str(text_path))
    from_binary = _parse_mmcif_backbone(str(binary_path))

    assert len(from_binary.coords) == len(from_text.coords) == 3
    assert from_binary.atom_radii.tolist() == from_text.atom_radii.tolist()
    assert from_binary.atoms["chain"].tolist() == from_text.atoms["chain"].tolist()
