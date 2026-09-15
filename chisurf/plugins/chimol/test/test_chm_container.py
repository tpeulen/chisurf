"""`.chm.pto` — the container a gigastructure is navigated from.

The claim under test is that one file can be *opened* without reading the
geometry in it, and then read a chunk at a time, straight into a GPU buffer.
Three things have to hold for that, and each is checked here against something
other than the code that produced it:

* **The envelope is a valid PTO document.** ``render/pto.py`` writes its own
  EBML, so a test written against its own reader would pass a consistent
  misreading of RFC 8794. The walk below decodes the file's variable-width
  integers from scratch and insists every element exactly fills its parent —
  and where ``CHIMOL_PTO_EBML_CHECK`` names tttrlib's ``pto_ebml_check``
  binary, **libebml** (the reference implementation) walks it too.
* **The payload is the bytes the GPU consumes.** Every chunk payload starts on
  an 8-byte boundary and is exactly ``count * 16`` octets, so residency is a
  slice of a mapping rather than a decode. What comes back out decodes to the
  atoms that went in, within one quantisation step.
* **Opening costs the index, not the structure.** The two directory objects are
  reachable through the seek table, so the open cost does not grow with the
  number of chunks — which is the whole point at 61k of them.

The design record is ``chimol/okf/architecture/chm-container.md``.
"""
from __future__ import annotations

import json
import os
import subprocess

import numpy as np
import pytest
from chimol.render import pto
from chimol.render.chm import (
    CHM_SUFFIX,
    CHUNK_ROW,
    ChmIndex,
    ChunkResidency,
    build_chm,
    container_path,
    decode_rows,
)
from chimol.render.cluster import _morton_keys

ATOMS = 20_000
CHUNK = 4_096
#: Far from the origin on purpose: the anchors are float64 and the deltas are
#: 16-bit, so a container this far out is the precision claim.
WORLD_OFFSET = np.array([1.2e5, -3.4e5, 7.7e4])


@pytest.fixture(scope="module")
def sample():
    rng = np.random.default_rng(7)
    xyz = rng.normal(0.0, 40.0, (ATOMS, 3)) + WORLD_OFFSET
    radii = rng.uniform(1.0, 2.0, ATOMS)
    rgba = np.column_stack([rng.random((ATOMS, 3)), np.ones(ATOMS)])
    occlusion = rng.random(ATOMS)
    identity = np.zeros(ATOMS, dtype=[("name", "S4"), ("resid", "<i4")])
    identity["name"] = b"CA"
    identity["resid"] = np.arange(ATOMS)
    order = np.argsort(_morton_keys(xyz), kind="stable")
    return {
        "xyz": xyz, "radii": radii, "rgba": rgba, "occlusion": occlusion,
        "identity": identity, "order": order,
    }


@pytest.fixture(scope="module")
def container(sample, tmp_path_factory):
    path = build_chm(
        sample["xyz"], sample["radii"], sample["rgba"], sample["occlusion"],
        tmp_path_factory.mktemp("chm") / "probe",
        levels=3, chunk_atoms=CHUNK, identity=sample["identity"], source="test",
    )
    return path


# ── the envelope ─────────────────────────────────────────────────────────
def _walk(buf, start, stop, depth, payloads):
    """Walk EBML from scratch: an ID, a Data Size, and no knowledge of PTO.

    Deliberately not ``render/pto.py``'s reader — this is the second opinion
    that a misread VINT would not survive.
    """
    at = start
    while at < stop:
        first = buf[at]
        id_len = 1
        while id_len <= 4 and not (first & (0x80 >> (id_len - 1))):
            id_len += 1
        assert id_len <= 4, f"no valid element ID at {at}"
        element_id = int.from_bytes(buf[at:at + id_len], "big")

        first = buf[at + id_len]
        size_len = 1
        while size_len <= 8 and not (first & (0x80 >> (size_len - 1))):
            size_len += 1
        assert size_len <= 8, f"no valid Data Size at {at}"
        raw = int.from_bytes(buf[at + id_len:at + id_len + size_len], "big")
        size = raw & ((1 << (7 * size_len)) - 1)
        assert size != (1 << (7 * size_len)) - 1, f"unknown size at {at}"

        data_at = at + id_len + size_len
        assert data_at + size <= stop, f"element at {at} runs past its parent"
        if element_id == pto.ID_FILE_DATA:
            payloads.append((data_at, size))
        if element_id in (pto.ID_SEGMENT, pto.ID_ATTACHMENTS,
                          pto.ID_ATTACHED_FILE, pto.ID_SEEK_HEAD):
            _walk(buf, data_at, data_at + size, depth + 1, payloads)
        at = data_at + size
    assert at == stop, f"the last element in [{start}, {stop}) ends at {at}"


def test_the_file_is_an_ebml_document_that_fills_itself_exactly(container):
    raw = container.read_bytes()
    assert raw[:4] == b"\x1a\x45\xdf\xa3", "no EBML header"
    payloads = []
    _walk(raw, 0, len(raw), 0, payloads)
    assert payloads, "no FileData at all"


def test_the_document_says_pto_and_a_1_0_reader_could_still_read_it(container):
    with pto.PtoReader(container) as reader:
        assert reader.doctype == "pto"
        assert reader.doctype_version == pto.DOCTYPE_VERSION
    raw = container.read_bytes()
    # DocTypeReadVersion is what decides whether a deployed reader refuses the
    # file; the profile may move forward, this may not.
    at = raw.index(pto.id_bytes(pto.ID_DOCTYPE_READ_VERSION))
    size, width = pto.read_size(raw, at + 2)
    assert int.from_bytes(raw[at + 2 + width:at + 2 + width + size], "big") == 1


def test_the_suffix_names_the_profile_not_a_new_format(container):
    assert container.name.endswith(CHM_SUFFIX)
    assert container_path(container) == container


def test_every_payload_starts_on_an_eight_byte_boundary(container):
    raw = container.read_bytes()
    payloads = []
    _walk(raw, 0, len(raw), 0, payloads)
    unaligned = [offset for offset, _ in payloads if offset % pto.ALIGNMENT]
    assert unaligned == [], f"{len(unaligned)} payload(s) a mapping cannot slice"


def test_libebml_agrees_it_is_a_pto_document(container):
    """The reference implementation, when the caller has built it.

    ``c++ -std=c++17 -I<ebml>/include tttrlib/test/tools/pto_ebml_check.cpp
    <ebml>/lib/libebml.a -o pto_ebml_check`` and point
    ``CHIMOL_PTO_EBML_CHECK`` at the result.
    """
    binary = os.environ.get("CHIMOL_PTO_EBML_CHECK")
    if not binary or not os.path.exists(binary):
        pytest.skip("CHIMOL_PTO_EBML_CHECK is not set to a built pto_ebml_check")
    done = subprocess.run([binary, str(container), "--aligned"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr


# ── the index ────────────────────────────────────────────────────────────
def test_opening_reads_the_index_and_not_the_structure(container, sample):
    index = ChmIndex.open(container)
    try:
        assert index.meta["n_atoms"] == ATOMS
        assert index.meta["chunk_atoms"] == CHUNK
        # Both directory objects are in the seek table, so open() is two seeks
        # whether the container holds six chunks or sixty thousand.
        assert set(index.reader._seeked) == {"chm.meta", "chm.index"}
        leaves = index.level(0)
        assert index.table["count"][leaves].sum() == ATOMS
        assert list(index.table["first"][leaves]) == list(range(0, ATOMS, CHUNK))
        # Leaves hold 16-byte atom rows; every level above holds 24-byte
        # Gaussians (see `CHUNK_GAUSS_ROW`), so the stride is per kind.
        from chimol.render.chm import CHUNK_GAUSS_ROW, ROW_GAUSS

        stride = np.where(index.table["kind"] == ROW_GAUSS,
                          CHUNK_GAUSS_ROW.itemsize, CHUNK_ROW.itemsize)
        assert (index.table["nbytes"] == index.table["count"] * stride).all()
        assert (index.table["offset"] % pto.ALIGNMENT == 0).all()
    finally:
        index.close()


def test_the_levels_form_one_tree_of_beads(container):
    index = ChmIndex.open(container)
    try:
        assert index.n_levels >= 2
        roots = index.table["parent"] == -1
        assert roots.sum() == 1, "a container has one root chunk"
        for level in range(index.n_levels - 1):
            for chunk in index.level(level):
                parent = int(index.table["parent"][chunk])
                assert parent >= 0
                assert int(index.table["level"][parent]) == level + 1
        # A parent's bounds contain its children's centres: it stands for them.
        for parent in index.level(1):
            kids = index.children(parent)
            assert len(kids) > 0
            lo, hi = index.table["bounds"][parent][:3], index.table["bounds"][parent][3:]
            centres = index.table["center"][kids]
            assert (centres >= lo - 1e-6).all() and (centres <= hi + 1e-6).all()
    finally:
        index.close()


def test_a_container_from_another_version_is_refused_not_misread(container, tmp_path):
    raw = bytearray(container.read_bytes())
    meta = json.dumps({"version": 999, "n_atoms": 1, "chunk_atoms": 1, "levels": 1,
                       "row_bytes": 16, "n_chunks": 1,
                       "world_bounds": [[0, 0, 0], [1, 1, 1]], "source": ""})
    with pto.PtoReader(container) as reader:
        obj = reader.find("chm.meta")
        span = (obj.offset, obj.size)
    assert len(meta) <= span[1]
    raw[span[0]:span[0] + span[1]] = meta.encode("ascii").ljust(span[1], b" ")
    forged = tmp_path / ("forged" + CHM_SUFFIX)
    forged.write_bytes(bytes(raw))
    with pytest.raises(ValueError, match="999"):
        ChmIndex.open(forged)


# ── the atoms ────────────────────────────────────────────────────────────
def _rows(residency, chunk_id):
    return np.frombuffer(residency.rows(chunk_id), dtype=CHUNK_ROW)


def test_the_atoms_come_back_within_one_quantisation_step(container, sample):
    index = ChmIndex.open(container)
    try:
        residency = ChunkResidency(index, budget_bytes=1 << 20)
        order = sample["order"]
        for chunk in index.level(0):
            row = index.table[chunk]
            got = decode_rows(_rows(residency, chunk), row)
            first, count = int(row["first"]), int(row["count"])
            want = order[first:first + count]
            step = float(row["pos_scale"])
            assert np.abs(got["xyz"] - sample["xyz"][want]).max() <= 0.6 * step
            assert np.abs(got["radii"] - sample["radii"][want]).max() <= 1e-3
            assert np.abs(got["rgba"][:, :3] - sample["rgba"][want][:, :3]).max() <= 1 / 255
            assert np.abs(got["occlusion"] - sample["occlusion"][want]).max() <= 1e-3
            assert list(got["local_id"]) == list(range(count))
    finally:
        index.close()


def test_a_chunk_is_a_slice_of_the_mapping_not_a_copy(container):
    index = ChmIndex.open(container)
    try:
        residency = ChunkResidency(index, budget_bytes=1 << 20)
        chunk = int(index.level(0)[0])
        row = index.table[chunk]
        rows = residency.rows(chunk)
        assert isinstance(rows, memoryview)
        assert len(rows) == int(row["nbytes"]) == int(row["count"]) * 16
        assert bytes(rows) == bytes(
            index.reader.view[int(row["offset"]):int(row["offset"]) + int(row["nbytes"])]
        )
    finally:
        index.close()


def test_residency_holds_the_budget_and_counts_what_it_did(container):
    index = ChmIndex.open(container)
    try:
        leaves = [int(c) for c in index.level(0)]
        one = int(index.table["nbytes"][leaves[0]])
        residency = ChunkResidency(index, budget_bytes=2 * one)
        for chunk in leaves:
            residency.rows(chunk)
        assert residency.resident_bytes <= 2 * one
        assert residency.stats["loads"] == len(leaves)
        assert residency.stats["evictions"] == len(leaves) - 2
        # The most recent chunk is still resident: asking again is a hit.
        residency.rows(leaves[-1])
        assert residency.stats["hits"] == 1
        assert residency.stats["loads"] == len(leaves)
    finally:
        index.close()


def test_identity_waits_in_a_sidecar_until_a_pick_asks(container, sample):
    index = ChmIndex.open(container)
    try:
        residency = ChunkResidency(index, budget_bytes=1 << 20)
        order = sample["order"]
        chunk = int(index.level(0)[1])
        row = index.table[chunk]
        assert int(row["sidecar"]) >= 0
        side = residency.sidecar(chunk)
        first, count = int(row["first"]), int(row["count"])
        assert list(side["resid"]) == list(sample["identity"]["resid"][order[first:first + count]])
        # A parent bead stands for its children and has no identity of its own.
        assert int(index.table["sidecar"][index.level(1)[0]]) == -1
    finally:
        index.close()


def test_chunks_follow_each_other_in_morton_order_on_disk(container):
    index = ChmIndex.open(container)
    try:
        leaves = index.level(0)
        offsets = index.table["offset"][leaves]
        assert list(offsets) == sorted(offsets), "a fly-through would seek backwards"
    finally:
        index.close()


# ── copies: a prototype, placed ──────────────────────────────────────────
def test_a_prototype_placed_many_times_never_exists_in_memory(sample, tmp_path):
    """`copies` is what makes a container bigger than the file it came from.

    A PetWorld model *is* a prototype and a list of placements, and so is the
    container: the builder walks the prototype once per placement, so 256 copies
    of a 3.45M-atom structure write 883M atoms while nothing larger than one
    chunk is ever held. What has to hold for that to be more than a trick is
    that each chunk still belongs to exactly one copy -- otherwise a chunk's
    bounds span the gap between two placements and every cull keeps it.
    """
    n = 4_000
    xyz = sample["xyz"][:n]
    lattice = np.array([[0.0, 0.0, 0.0], [400.0, 0.0, 0.0],
                        [0.0, 400.0, 0.0], [400.0, 400.0, 0.0]])
    path = build_chm(xyz, sample["radii"][:n], sample["rgba"][:n], None,
                     tmp_path / "placed", levels=4, chunk_atoms=1024, copies=lattice)
    index = ChmIndex.open(path)
    try:
        assert index.meta["n_atoms"] == n * len(lattice)
        assert index.meta["n_prototype_atoms"] == n
        assert index.meta["copies"] == len(lattice)
        leaves = index.level(0)
        assert index.table["count"][leaves].sum() == n * len(lattice)
        for chunk in leaves:
            first, count = int(index.table["first"][chunk]), int(index.table["count"][chunk])
            assert first % n + count <= n, "a chunk spans two placements"
        lo, hi = np.asarray(index.meta["world_bounds"])
        # The lattice moves x and y by 400 A, so the world must have grown by
        # that much along both -- the prototype's own span is ~300 A.
        assert (hi[:2] - lo[:2] > 400.0).all(), "the world bounds ignore the placements"
        # Every placement is somewhere in the container: each lattice point is
        # inside some leaf chunk's bounds.
        for point in lattice + xyz.mean(axis=0):
            inside = (
                (index.table["bounds"][leaves][:, :3] <= point).all(axis=1)
                & (index.table["bounds"][leaves][:, 3:] >= point).all(axis=1)
            )
            assert inside.any(), f"no chunk holds the copy at {point}"
    finally:
        index.close()
