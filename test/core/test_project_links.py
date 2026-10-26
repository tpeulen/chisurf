"""The file-link adapter: ptolib's link semantics, with or without ptolib links in tttrlib.

``chisurf.core.project.links`` uses ptolib's links (``sha256_file``, ``find_link_candidates``) where
the installed tttrlib exposes them and its own Python fallbacks otherwise; both must behave the
same. The ptolib path is driven with a small fake ``PtoFile`` that follows ptolib's documented
semantics (``include/ptolib/ptolib.h``: ``find_link_candidates`` walks by name, recorded size first,
hashes nothing); the fallback runs the real code. Embedding and unembedding go through a real
project save.
"""

from __future__ import annotations

import hashlib
import os
import types
from pathlib import Path

import pytest

from chisurf.core.data import LinkedDataset
from chisurf.core.project import links
from chisurf.core.project.project import Project
from chisurf.core.project.session import capture_session, restore_session


def _file(path: Path, content: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@pytest.fixture
def no_ptolib(monkeypatch):
    monkeypatch.setattr(links, "ptolib_links", lambda: False)


def test_the_fallback_records_size_and_hash_and_resolves_by_relative_path(tmp_path, no_ptolib):
    data = _file(tmp_path / "study" / "data" / "m.bin", b"photons" * 100)
    link = links.relativize(links.add_link(str(data)), tmp_path / "study")
    assert link["size"] == data.stat().st_size and link["sha256"] == _sha(data.read_bytes())
    assert link["relative"] == os.path.join("data", "m.bin")
    moved = tmp_path / "moved"
    (tmp_path / "study").rename(moved)
    resolution = links.resolve(link, moved)
    assert resolution.ok and resolution.found == (moved / "data" / "m.bin").resolve()


def test_relink_accepts_the_moved_original_and_refuses_another_file(tmp_path, no_ptolib):
    original = _file(tmp_path / "a" / "m.bin", b"x" * 64)
    link = links.add_link(str(original))
    moved = tmp_path / "b" / "renamed.bin"
    moved.parent.mkdir()
    original.rename(moved)
    relinked = links.relink(link, moved)
    assert relinked["container"] == str(moved.resolve()) and relinked["sha256"] == link["sha256"]
    other = _file(tmp_path / "c" / "m.bin", b"y" * 64)  # same size, other content
    with pytest.raises(links.LinkError, match="content"):
        links.relink(link, other)
    forced = links.relink(link, other, force=True)  # "Use anyway" records the new file
    assert forced["sha256"] == _sha(b"y" * 64)


def test_the_fallback_finds_candidates_by_name_with_the_recorded_size_first(tmp_path, no_ptolib):
    original = _file(tmp_path / "data" / "m.bin", b"z" * 10)
    link = links.add_link(str(original))
    original.unlink()
    _file(tmp_path / "search" / "a" / "m.bin", b"z" * 11)
    right = _file(tmp_path / "search" / "b" / "m.bin", b"z" * 10)
    _file(tmp_path / "search" / "c" / "other.bin", b"z" * 10)
    found = links.find_candidates(link, tmp_path / "search")
    assert [c.path for c in found][0] == right and found[0].size_matches
    assert len(found) == 2 and not found[1].size_matches


class _FakeObject:
    def __init__(self, uid, name):
        self.uid, self.name, self.size = uid, name, 0


class _FakePtoFile:
    """ptolib's link API as documented, over one link object named after its target."""

    calls: list[str] = []

    def __init__(self):
        self._objects = []

    def open(self, path):
        self._objects = [_FakeObject(1, "m.bin")]
        return True

    def objects(self):
        return list(self._objects)

    def is_link(self, uid):
        return uid == 1

    def add_link(self, *args, **kwargs):  # capability marker
        return 1

    def find_link_candidates(self, uid, root):
        _FakePtoFile.calls.append(f"find_link_candidates({uid})")
        out = []
        for directory, _dirs, files in os.walk(root):
            if "m.bin" in files:
                path = Path(directory) / "m.bin"
                out.append(
                    types.SimpleNamespace(
                        path=str(path),
                        size=path.stat().st_size,
                        size_matches=path.stat().st_size == 10,
                    )
                )
        return sorted(out, key=lambda c: not c.size_matches)

    def close(self):
        pass


@pytest.fixture
def fake_ptolib(monkeypatch):
    calls = []

    def sha256_file(path):
        calls.append(f"sha256_file({Path(path).name})")
        return _sha(Path(path).read_bytes())

    module = types.SimpleNamespace(PtoFile=_FakePtoFile, sha256_file=sha256_file)
    monkeypatch.setattr(links, "_tttrlib", lambda: module)
    _FakePtoFile.calls = calls
    return calls


def test_with_ptolib_links_the_hash_and_the_search_are_ptolibs(tmp_path, fake_ptolib):
    assert links.ptolib_links()
    original = _file(tmp_path / "data" / "m.bin", b"z" * 10)
    link = links.add_link(str(original))
    assert "sha256_file(m.bin)" in fake_ptolib and link["sha256"] == _sha(b"z" * 10)
    link["object"] = "m.bin"
    project = _file(tmp_path / "p.cs.pto", b"container")
    original.unlink()
    right = _file(tmp_path / "search" / "m.bin", b"z" * 10)
    found = links.find_candidates(link, tmp_path / "search", project_path=project)
    assert "find_link_candidates(1)" in fake_ptolib
    assert found[0].path == right and found[0].size_matches


def test_the_project_container_carries_ptolib_link_records(tmp_path):
    import tttrlib

    data = _file(tmp_path / "data" / "image.tif", b"I" * 300)
    project_path = tmp_path / "p.cs.pto"
    capture_session([LinkedDataset(str(data), data_kind="image")], []).save(project_path)
    handle = tttrlib.PtoFile()
    assert handle.open(str(project_path))
    try:
        (obj,) = [o for o in handle.objects() if o.name == "image.tif"]
        tags = {t.name: t for t in handle.tags_for(obj.uid)}
    finally:
        handle.close()
    assert obj.size == 0  # linked: no bytes in the project
    assert tags["pto.link.path"].text == os.path.join("data", "image.tif")
    assert tags["pto.link.size"].u == 300
    assert tags["pto.link.sha256"].text == _sha(b"I" * 300)


def test_embed_then_unembed_restores_the_file_byte_for_byte(tmp_path):
    content = os.urandom(4096)
    data = _file(tmp_path / "data" / "image.tif", content)
    project_path = tmp_path / "p.cs.pto"
    dataset = LinkedDataset(str(data), data_kind="image")
    dataset.link = links.embed(dataset.link)
    capture_session([dataset], []).save(project_path)
    data.unlink()
    record = next(iter(Project.load(project_path).datasets.values()))
    assert record["link"]["embedded"] and record["link"]["object"] == "image.tif"
    (restored,) = restore_session(Project.load(project_path)).datasets
    assert restored.link_status == "ok" and restored.address.startswith(str(project_path))
    link = links.unembed(record["link"], project_path)
    assert data.read_bytes() == content and not links.is_embedded(link)
    assert links.resolve(link, tmp_path).ok


def test_embedding_refuses_a_file_that_changed_since_it_was_linked(tmp_path):
    data = _file(tmp_path / "m.bin", b"a" * 50)
    link = links.add_link(str(data))
    data.write_bytes(b"b" * 50)
    with pytest.raises(links.LinkError, match="Cannot embed"):
        links.embed(link)


def test_report_lists_each_linked_dataset_with_its_state(tmp_path):
    ok = _file(tmp_path / "ok.bin", b"1")
    gone = _file(tmp_path / "gone.bin", b"2")
    datasets = [
        LinkedDataset(str(ok), data_kind="image", name="ok"),
        LinkedDataset(str(gone), data_kind="image", name="gone"),
    ]
    datasets[0].link = links.embed(datasets[0].link)
    gone.unlink()
    rows = {r.name: r for r in links.report(datasets, tmp_path)}
    assert rows["ok"].embedded and rows["ok"].ok
    assert rows["gone"].status == "missing" and not rows["gone"].embedded


def test_an_embedded_spc_carries_its_set_and_unembeds_both(tmp_path):
    import tttrlib

    spc = _file(tmp_path / "data" / "m000.spc", os.urandom(2048))
    setup = _file(tmp_path / "data" / "m000.set", b"SETUP" * 20)
    dataset = LinkedDataset(str(spc), data_kind="raw")
    assert [c["name"] for c in dataset.link["companions"]] == ["m000.set"]
    dataset.link = links.embed(dataset.link)
    project_path = tmp_path / "p.cs.pto"
    capture_session([dataset], []).save(project_path)
    handle = tttrlib.PtoFile()
    assert handle.open(str(project_path))
    try:
        objects = {o.name: o for o in handle.objects()}
        sidecar = {t.name: t for t in handle.tags_for(objects["m000.set"].uid)}
    finally:
        handle.close()
    assert sidecar["pto.sidecar_of"].u == objects["m000.spc"].uid
    spc_bytes, set_bytes = spc.read_bytes(), setup.read_bytes()
    spc.unlink()
    setup.unlink()
    record = next(iter(Project.load(project_path).datasets.values()))
    links.unembed(record["link"], project_path)
    assert spc.read_bytes() == spc_bytes and setup.read_bytes() == set_bytes
