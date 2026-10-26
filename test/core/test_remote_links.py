"""Links to MMFDB objects (``mmfdb://...``): registration, prefetch, sign-in, picker, locate, web cache.

No network: a fake MMFDB transport serves the object; :mod:`mmfdb.links`' cache lives in a temporary
folder. The ptolib/tttrlib side (a ``proj.cs.pto`` read through the registered resolver) needs a
tttrlib with the link registry and runs on the remote test box.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

mmfdb_links = pytest.importorskip("mmfdb.links")

from chisurf.core.project import links, remote_links  # noqa: E402

DATA = b"photons " * 512
SHA = hashlib.sha256(DATA).hexdigest()
UUID = "0f1e2d3c-0000-4000-8000-000000000001"


class FakeTransport:
    """An MMFDB server with one object (the photon file's bytes), driven synchronously."""

    base_url = "https://mmfdb.test"

    def __init__(self, data: bytes = DATA) -> None:
        self.data = data
        self.downloads = 0

    async def rpc(self, method, params):
        sha = hashlib.sha256(self.data).hexdigest()
        if method == mmfdb_links.RPC_ARTIFACT:
            return {"artifact": {"object_uuid": UUID}}
        if method == mmfdb_links.RPC_OBJECT_INFO:
            return {"object": {"content_sha256": sha}}
        if method == mmfdb_links.RPC_OBJECT_LIST:
            found = params.get("content_sha256") == sha
            return {
                "objects": [
                    {"object_uuid": UUID, "content_sha256": sha, "original_filename": "m000.spc"}
                ]
                if found
                else []
            }
        raise AssertionError(method)

    async def download(self, object_uuid):
        self.downloads += 1
        return self.data


@pytest.fixture(autouse=True)
def cache(tmp_path, monkeypatch):
    root = tmp_path / "link-cache"
    mmfdb_links.set_cache_root(root)
    monkeypatch.setattr(remote_links, "_STATE", {})
    yield root
    mmfdb_links.set_cache_root(None)


def _link():
    return remote_links.link_for("mmfdb://artifact/42", size=len(DATA), sha256=SHA, name="m000.spc")


def test_startup_registers_the_resolver_and_skips_quietly_without_mmfdb(monkeypatch):
    called = []
    monkeypatch.setattr(mmfdb_links, "register", lambda *m: called.append(m) or ["tttrlib"])
    assert remote_links.register_resolvers() == ["tttrlib"]
    assert called == [()]
    monkeypatch.setitem(sys.modules, "mmfdb.links", None)  # import fails
    assert remote_links.register_resolvers() == []


def test_a_remote_link_records_uri_size_and_hash_never_a_path_or_credentials():
    link = links.add_link("mmfdb://artifact/42", size=len(DATA), sha256=SHA)
    assert link["uri"] == "mmfdb://artifact/42" and link["container"] == ""
    assert (link["size"], link["sha256"]) == (len(DATA), SHA)
    assert "token" not in json.dumps(link)
    with pytest.raises(links.LinkError):
        links.add_link("mmfdb://artifact/42")  # no size/hash: cannot be linked
    assert links.relativize(link, "/somewhere") == link


def test_not_fetched_is_fetching_then_prefetch_resolves_from_the_cache():
    link = _link()
    assert links.resolve(link).status == remote_links.FETCHING
    server = FakeTransport()
    outcome = remote_links.prefetch([link], transport=server)
    assert outcome == {"mmfdb://artifact/42": ("ok", "")}
    resolution = links.resolve(link)
    assert resolution.ok and Path(resolution.address).read_bytes() == DATA
    assert links.verify(link).ok
    remote_links.prefetch([link], transport=server)  # cached: not downloaded again
    assert server.downloads == 1


def test_no_session_is_sign_in_needed_not_missing(monkeypatch):
    def no_session(server=""):
        raise mmfdb_links.LinkError("no MMFDB session for https://mmfdb.test (log in first)")

    monkeypatch.setattr(mmfdb_links, "default_transport", no_session)
    monkeypatch.setattr(remote_links, "server_of", lambda uri: "https://mmfdb.test")
    outcome = remote_links.prefetch([_link()])
    status, reason = outcome["mmfdb://artifact/42"]
    assert status == remote_links.SIGN_IN and "https://mmfdb.test" in reason
    resolution = links.resolve(_link())
    assert resolution.status == remote_links.SIGN_IN and not resolution.ok


def test_the_project_keeps_the_uri_and_reads_through_the_cache():
    from chisurf.core.data import PhotonStreamDataset
    from chisurf.core.project.session import _linked_record, _restore_linked

    link = _link()
    dataset = PhotonStreamDataset("mmfdb://artifact/42", link=link, name="m000.spc")
    record = _linked_record(dataset)
    assert record["address"] == "mmfdb://artifact/42"
    restored = _restore_linked(record, None)
    assert restored.address == "mmfdb://artifact/42"
    assert restored.link_status == remote_links.FETCHING
    with pytest.raises(FileNotFoundError):
        _ = restored.read_address
    remote_links.prefetch([link], transport=FakeTransport())
    assert restored.recheck() == "ok"
    assert Path(restored.read_address).read_bytes() == DATA
    assert _linked_record(restored)["address"] == "mmfdb://artifact/42"  # never the cache path


def test_picking_an_mmfdb_artifact_adds_a_linked_dataset():
    from chisurf.emtk.fit_docks import DataDocks

    added, fetched = [], []
    docks = SimpleNamespace(
        status="",
        session=SimpleNamespace(
            api=SimpleNamespace(load_dataset=lambda dataset: added.append(dataset) or {"ok": True})
        ),
        _start=lambda label, call, after=None: (after(call()), True)[1],
        prefetch_links=lambda datasets=None: fetched.append(datasets) or True,
    )
    selection = SimpleNamespace(
        artifact_id="42",
        label="m000.spc",
        metadata={"checksum": SHA, "size_bytes": len(DATA), "original_filename": "m000.spc"},
    )
    assert DataDocks.link_selection(docks, selection)
    (dataset,) = added
    assert dataset.data_kind == "photons" and dataset.address == "mmfdb://artifact/42"
    assert dataset.link["sha256"] == SHA and fetched
    curve = SimpleNamespace(
        artifact_id="7", label="decay.dat", metadata={"checksum": SHA, "size_bytes": 1}
    )
    assert not DataDocks.link_selection(docks, curve)  # a curve goes through the Read data panel
    no_hash = SimpleNamespace(artifact_id="8", label="x.ptu", metadata={})
    assert not DataDocks.link_selection(docks, no_hash) and "checksum" in docks.status


def test_locate_finds_an_mmfdb_copy_by_checksum_and_reads_from_it(tmp_path, monkeypatch):
    from chisurf.core.project.link_repair import LinkRepairModel

    gone = tmp_path / "m000.spc"
    gone.write_bytes(DATA)
    link = links.add_link(gone)
    gone.unlink()
    dataset = SimpleNamespace(
        unique_identifier="d1",
        name="m000.spc",
        link=link,
        address=str(gone),
        link_status="missing",
        link_problem="gone",
    )
    source = SimpleNamespace(
        linked_datasets=lambda: [dataset], project_path=lambda: None, changed=lambda: None
    )
    model = LinkRepairModel(source)
    model.refresh()
    model.select_dataset(model.dataset_rows()[0])
    server = FakeTransport()
    rows = model.search_mmfdb(transport=server)
    assert rows and rows[0]["mmfdb"] and rows[0]["path"] == f"mmfdb://object/{UUID}"
    monkeypatch.setattr(mmfdb_links, "default_transport", lambda server_="": server)
    assert model.use_candidate()
    assert dataset.link["uri"] == f"mmfdb://object/{UUID}"
    assert dataset.link["container"] == str(gone)  # the file is used first if it comes back
    assert links.resolve(dataset.link).ok


def test_the_web_page_mounts_a_persistent_link_cache():
    from chisurf import web

    calls = []
    fs = SimpleNamespace(
        filesystems=SimpleNamespace(IDBFS="IDBFS"),
        mkdirTree=lambda path: calls.append(("mkdir", path)),
        mount=lambda kind, opts, path: calls.append(("mount", kind, path)),
        syncfs=lambda populate, cb: calls.append(("sync", populate)),
    )
    roots = []
    fake_links = SimpleNamespace(set_cache_root=roots.append)
    assert web.mount_link_cache("/cache", fs=fs, links=fake_links)
    assert ("mount", "IDBFS", "/cache") in calls and ("sync", True) in calls
    assert roots == ["/cache"]
    assert web.persist_link_cache(fs=fs) and calls[-1] == ("sync", False)
    assert not web.mount_link_cache("/cache")  # not on a page: nothing to mount
    assert "links.py" in web.MMFDB_KEEP
