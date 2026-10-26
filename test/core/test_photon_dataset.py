"""Photon streams in the workspace and the project: linked, never copied, checked when opened.

A real Becker & Hickl SPC-132 recording (``test/data/tttr/BH/132``) is imported, saved in a project,
and the project is opened again with the measurement present, moved with it, missing, and changed —
each outcome asserted. The fit guard still keeps photon streams out of every fit.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from chisurf.core.data import LinkedDataset, PhotonStreamDataset
from chisurf.core.data_kinds import kind_of
from chisurf.core.fio.classify import classify, container_entries
from chisurf.core.project import links
from chisurf.core.project.project import Project
from chisurf.core.project.session import capture_session, restore_session

REPO = Path(__file__).resolve().parents[2]
SPC = REPO / "test" / "data" / "tttr" / "BH" / "132" / "BH_SPC132.spc"

pytestmark = pytest.mark.skipif(not SPC.is_file(), reason="the SPC-132 test recording is absent")


@pytest.fixture
def measurement(tmp_path) -> Path:
    """The recording copied into a project folder's data/ subfolder."""
    data = tmp_path / "study" / "data"
    data.mkdir(parents=True)
    target = data / "m000.spc"
    shutil.copy(SPC, target)
    for companion in SPC.parent.glob(SPC.stem + ".set"):
        shutil.copy(companion, data / "m000.set")
    return target


def _restored(project_path: Path) -> PhotonStreamDataset:
    (dataset,) = restore_session(Project.load(project_path)).datasets
    return dataset


def test_an_imported_photon_file_is_a_photons_dataset_with_its_checksum(measurement):
    dataset = PhotonStreamDataset.from_address(str(measurement))
    assert kind_of(dataset) == "photons"
    assert dataset.link["sha256"] == hashlib.sha256(measurement.read_bytes()).hexdigest()
    assert dataset.link["size"] == measurement.stat().st_size
    assert dataset.n_photons > 0 and dataset.duration_s > 0 and dataset.channels
    assert dataset.filename == str(measurement) and dataset.header_json
    assert dataset.photons().get_n_valid_events() == dataset.n_photons


def test_the_dataset_row_says_photons_and_shows_the_address(measurement):
    from chisurf.server.services.datasets import _dataset_dto

    dto = _dataset_dto(PhotonStreamDataset.from_address(str(measurement)), 0)
    assert dto["kind"] == "photons"
    assert dto["filename"] == str(measurement)
    assert dto["link_status"] == "ok"


def test_a_project_links_the_file_and_finds_it_again(measurement):
    project_path = measurement.parent.parent / "study.cs.pto"
    dataset = PhotonStreamDataset.from_address(str(measurement))
    capture_session([dataset], [], name="study").save(project_path)
    record = next(iter(Project.load(project_path).datasets.values()))
    assert record["kind"] == "linked" and record["data_kind"] == "photons"
    assert record["link"]["relative"] == "data/m000.spc"
    assert project_path.stat().st_size < measurement.stat().st_size  # linked, not copied
    restored = _restored(project_path)
    assert restored.link_status == "ok" and restored.n_photons == dataset.n_photons
    assert Path(restored.address).resolve() == measurement.resolve()


def test_a_project_moved_with_its_data_still_resolves(measurement, tmp_path):
    project_path = measurement.parent.parent / "study.cs.pto"
    capture_session([PhotonStreamDataset.from_address(str(measurement))], []).save(project_path)
    moved = tmp_path / "elsewhere"
    shutil.move(str(measurement.parent.parent), moved)
    restored = _restored(moved / "study.cs.pto")
    assert restored.link_status == "ok"
    assert Path(restored.address).resolve() == (moved / "data" / "m000.spc").resolve()


def test_a_missing_file_restores_the_dataset_marked_unresolved(measurement):
    project_path = measurement.parent.parent / "study.cs.pto"
    capture_session([PhotonStreamDataset.from_address(str(measurement))], []).save(project_path)
    measurement.unlink()
    restored = _restored(project_path)
    assert restored.link_status == "missing" and "not found" in restored.link_problem
    with pytest.raises(FileNotFoundError):
        restored.photons()


def test_a_changed_file_is_reported_never_read_as_the_same(measurement):
    project_path = measurement.parent.parent / "study.cs.pto"
    capture_session([PhotonStreamDataset.from_address(str(measurement))], []).save(project_path)
    content = bytearray(measurement.read_bytes())
    content[200] ^= 0xFF
    measurement.write_bytes(bytes(content))
    restored = _restored(project_path)
    # Opening checks the size only (cheap); the hash check is on demand.
    assert restored.link_status == "ok"
    assert links.verify(restored.link, project_path.parent).status == "hash changed"
    measurement.write_bytes(bytes(content) + b"\0")
    restored = _restored(project_path)
    assert restored.link_status == "size changed" and "bytes" in restored.link_problem


def test_saving_and_restoring_never_hashes_again(measurement, monkeypatch):
    dataset = PhotonStreamDataset.from_address(str(measurement))

    def no_hashing(_path):
        raise AssertionError("a save or restore re-hashed a linked file")

    monkeypatch.setattr(links, "file_digest", no_hashing)
    project_path = measurement.parent.parent / "study.cs.pto"
    capture_session([dataset], [], name="autosave").save(project_path)
    assert _restored(project_path).link_status == "ok"


def test_embedding_says_it_is_not_available_yet():
    assert links.EMBED_AVAILABLE is False
    with pytest.raises(NotImplementedError, match="stays linked"):
        links.embed({}, "p.cs.pto")


def test_a_photon_stream_cannot_be_fitted(measurement):
    from chisurf.core.data import DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.models.description import tcspc_lifetime

    dataset = PhotonStreamDataset.from_address(str(measurement))
    with pytest.raises((TypeError, ValueError)):
        FitGroup(data=DataCurveGroup([dataset]), model_class=tcspc_lifetime)


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("p.cs.pto", "project"),
        ("m000.pto", "container"),
        ("m000.ptu", "photons"),
        ("m000.spc", "photons"),
        ("m000.set", "companion"),
        ("148l.pdb", "structure"),
        ("148l.cif.gz", "structure"),
        ("stack.tif", "image"),
        ("decay.dat", "curve"),
    ],
)
def test_a_dropped_path_is_sorted_by_what_it_holds(name, kind):
    assert classify(name) == kind


def test_a_container_contributes_its_photon_streams(measurement, tmp_path):
    from chisurf.core.fio.pto import Measurement

    with Measurement.create(measurement, out_dir=tmp_path) as m:
        container = m.path
    entries = container_entries(container)
    assert entries and all(kind == "photons" for kind, _ in entries)
    kind, address = entries[0]
    dataset = PhotonStreamDataset.from_address(address)
    assert dataset.n_photons > 0
    assert dataset.link["member"] and Path(dataset.link["container"]) == container.resolve()


def test_a_linked_image_keeps_its_kind_across_a_project(tmp_path):
    image = tmp_path / "stack.tif"
    image.write_bytes(b"II*\0" + bytes(64))
    project_path = tmp_path / "p.cs.pto"
    capture_session([LinkedDataset(str(image), data_kind="image")], []).save(project_path)
    (restored,) = restore_session(Project.load(project_path)).datasets
    assert kind_of(restored) == "image" and restored.link_status == "ok"


def test_an_spc_link_records_its_set_and_needs_it_beside(tmp_path):
    spc = tmp_path / "m000.spc"
    shutil.copy(SPC, spc)
    companion = tmp_path / "m000.set"
    companion.write_bytes(b"*SETUP\n" + bytes(32))
    link = links.add_link(str(spc))
    (recorded,) = link["companions"]
    assert recorded["name"] == "m000.set" and recorded["size"] == companion.stat().st_size
    assert links.resolve(link).ok
    companion.write_bytes(b"*SETUP\n" + bytes(33))
    assert links.resolve(link).status == "size changed"
    companion.unlink()
    resolution = links.resolve(link)
    assert resolution.status == "missing" and "m000.set" in resolution.reason
