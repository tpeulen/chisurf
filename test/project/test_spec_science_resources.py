"""Exact attachment bytes survive scientific restore and transport loops."""

import base64
import json
from pathlib import Path

import pytest

from chisurf.core.project.archive import ProjectArchive
from chisurf.core.project.session import capture_session, restore_session
from chisurf.core.project.storage import load_file, save_file
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    _payload_with_fit,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from test.project.test_real_mmfdb_http import standalone_server as real_http_server

standalone_server = real_http_server


@pytest.fixture
def measured_export(authenticated_browser, sample_project_payload, tmp_path):
    """Produce a fresh authenticated export from checked-in measured science."""
    from chisurf.core.project.pto import publish_project_bytes

    client = authenticated_browser["client"]
    saved = client.save_project(
        "Measured resource continuity", project_payload=_payload_with_fit(sample_project_payload)
    )
    assert saved["ok"] is True
    exported = client.export_csp(saved["version_id"])
    assert exported["ok"] is True
    path = publish_project_bytes(
        tmp_path / "measured.cs.pto",
        base64.b64decode(exported["archive_bytes"], validate=True),
    )
    # Only this fixture's copied source is removed, never checked-in measurements.
    resources = measured_resources(ProjectArchive.open(path))
    for filename, data in resources.items():
        source = Path(filename)
        assert source.parent.resolve() == tmp_path.resolve()
        assert source.read_bytes() == data
        source.unlink()
    return path


def measured_resources(archive):
    """Read the real export's aliases and object content, independently."""
    export = json.loads(archive.read_text("mmfdb_export.json"))
    objects = {
        obj["object_uuid"]: base64.b64decode(obj["data_base64"], validate=True)
        for obj in export["dependencies"]["objects"]
    }
    return {
        art["file_path"]: objects[art["object_uuid"]]
        for art in export["dependencies"]["artifacts"]
        if art["artifact_kind"] == "raw_measurement"
    }


def test_real_export_resources_survive_restore_recapture_save(tmp_path, measured_export):
    """Recapture retains the actual reviewed export bytes without source I/O."""
    original = ProjectArchive.open(measured_export)
    resources = measured_resources(original)
    assert sum(map(len, resources.values())) == 35186
    project = load_file(measured_export)
    restored = restore_session(project)
    recaptured = capture_session(restored.datasets, restored.fits)
    archive = ProjectArchive()
    recaptured.save_to_archive(archive)
    assert archive.read_bytes("mmfdb_export.json") == original.read_bytes("mmfdb_export.json")
    path = save_file(recaptured, tmp_path / "roundtrip.cs.pto")
    assert measured_resources(ProjectArchive.open(path)) == resources


def test_owned_bytes_survive_authenticated_database_export_import(
    standalone_server, tmp_path, measured_export
):
    """Real HTTP saves and restores exact science and aliases after sources vanish."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.storage import load_database, save_database
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    url, token, _database = standalone_server
    base = MMFDBClient(mode="remote", base_url=url, allow_insecure_http=True, inprocess=False)
    base.token = token
    client = ProjectBrowserClient(mmfdb_client=base)
    settings = {"client": {"mode": "remote", "base_url": url, "allow_insecure_http": True}}
    project = load_file(measured_export)
    original = dict(project.resources.sources)
    # Add a non-data resource whose original file is actually deleted.
    source = tmp_path / "structure.pdb"
    source.write_bytes(Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes())
    source_bytes = source.read_bytes()
    project.resources = ResourceContext(
        project.resources.entries, {**original, str(source): source_bytes}
    )
    source.unlink()
    expected = {**original, str(source): source_bytes}
    saved = save_database(project, mmfdb_settings=settings, client=client)
    loaded, _meta = load_database(saved["version_id"], mmfdb_settings=settings, client=client)
    assert loaded.to_dict() == project.to_dict()
    assert dict(loaded.resources.sources) == expected
    restored = restore_session(loaded)
    recaptured = capture_session(restored.datasets, restored.fits, resources=restored.resources)
    second = save_database(
        recaptured,
        project_id=saved["project_id"],
        parent_version_id=saved["version_id"],
        mmfdb_settings=settings,
        client=client,
    )
    exported = client.export_csp(second["version_id"])
    path = tmp_path / "authenticated.cs.pto"
    path.write_bytes(base64.b64decode(exported["archive_bytes"], validate=True))
    assert dict(load_file(path).resources.sources) == expected
    imported = client.import_csp(file_path=str(path), resolve_collisions=True)
    assert imported["ok"] is True
    final, _meta = load_database(imported["version_id"], mmfdb_settings=settings, client=client)
    assert final.to_dict() == recaptured.to_dict()
    assert dict(final.resources.sources) == expected


def test_empty_project_resources_are_owned_and_transactional(tmp_path):
    """No curve is required to retain exact named IRF/PDB attachment bytes."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.transition import replace_project
    from chisurf.server.session import SessionState

    sources = {
        "IRF.dat": Path("test/data/tcspc/ibh_sample/IRF_8-0 ps_4096 ch.dat").read_bytes(),
        "148l.pdb": Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes(),
    }
    context = ResourceContext(sources=sources)
    project = capture_session([], [], resources=context)
    owner = SessionState()
    replace_project(load_file(save_file(project, tmp_path / "empty.cs.pto")), owner=owner)
    assert dict(owner.project_resources.sources) == sources
    recaptured = capture_session(owner.datasets, owner.fits, resources=owner.project_resources)
    assert (
        dict(load_file(save_file(recaptured, tmp_path / "second.cs.pto")).resources.sources)
        == sources
    )


def test_resource_transport_is_exact_bytes_and_rejects_opaque_state():
    """A/C wrappers can transport bounded named content without live objects."""
    import pytest

    from chisurf.core.project.project import ResourceContext

    original = ResourceContext(
        entries={"reader/calibration.bin": bytes(range(256))}, sources={"named IRF": b"\x00\xff\n"}
    )
    restored = ResourceContext.from_transport_dict(
        json.loads(json.dumps(original.to_transport_dict()))
    )
    assert dict(restored.entries) == dict(original.entries)
    assert dict(restored.sources) == dict(original.sources)
    with pytest.raises(ValueError):
        ResourceContext.from_transport_dict({"entries": {}, "sources": {}, "controller": {}})
    with pytest.raises(ValueError):
        ResourceContext.from_transport_dict({"entries": {"../unsafe": "AA=="}, "sources": {}})
    with pytest.raises(ValueError):
        ResourceContext.from_transport_dict({"entries": {}, "sources": {"label": "not base64!"}})


def test_remote_owner_transaction_preserves_empty_project_resources():
    """The real dispatcher receives resource bytes separately from canonical science."""
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.transition import replace_project
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.services.projects import register_project_snapshot_services
    from chisurf.server.session import SessionState

    context = ResourceContext(
        sources={"148l.pdb": Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes()}
    )
    project = capture_session([], [], resources=context)
    owner = SessionState()
    dispatcher = ServiceDispatcher(owner)
    register_project_snapshot_services(dispatcher, owner)
    client = InProcessClient(dispatcher)
    assert replace_project(project, client=client)["ok"]
    assert dict(owner.project_resources.sources) == dict(context.sources)
    response = client.call("project.capture")
    assert response["ok"]
    assert ResourceContext.from_transport_dict(response["resources"]).sources == context.sources


def test_named_archive_entries_survive_actual_database_file_loop(standalone_server, tmp_path):
    """Native named attachments retain bytes and entry/source distinction in MMFDB."""
    from chisurf.core.project.project import ResourceContext
    from chisurf.core.project.storage import load_database, save_database
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    url, token, _database = standalone_server
    base = MMFDBClient(mode="remote", base_url=url, allow_insecure_http=True, inprocess=False)
    base.token = token
    client = ProjectBrowserClient(mmfdb_client=base)
    settings = {"client": {"mode": "remote", "base_url": url, "allow_insecure_http": True}}
    entries = {
        "reader/calibration.bin": bytes(range(256)),
        "structure/148l.pdb": Path("test/data/atomic_coordinates/pdb_files/148l.pdb").read_bytes(),
    }
    sources = {"IRF.dat": Path("test/data/tcspc/ibh_sample/IRF_8-0 ps_4096 ch.dat").read_bytes()}
    project = capture_session([], [], resources=ResourceContext(entries=entries, sources=sources))
    for _ in range(2):
        saved = save_database(project, mmfdb_settings=settings, client=client)
        project, _meta = load_database(saved["version_id"], mmfdb_settings=settings, client=client)
        assert dict(project.resources.entries) == entries
        assert dict(project.resources.sources) == sources
        project = load_file(save_file(project, tmp_path / "attachments.cs.pto"))
        assert dict(project.resources.entries) == {
            **entries,
            "resources.json": json.dumps(
                {k: base64.b64encode(v).decode("ascii") for k, v in sources.items()}, sort_keys=True
            ).encode(),
        }
        restored = restore_session(project)
        project = capture_session([], [], resources=restored.resources)
        entries = dict(project.resources.entries)


def test_database_entry_codec_rejects_invalid_expansion_and_trailing_bytes():
    """Untrusted compressed metadata cannot overrun its declared byte boundary."""
    import pytest

    from chisurf.core.project.project import ResourceContext

    context = ResourceContext(entries={"calibration.bin": bytes(range(256))})
    bundle = context.database_bundle()
    content = base64.b64decode(bundle["urn:chisurf:project:resource-context"], validate=True)
    assert ResourceContext._decode_database_descriptor(content)["entries"] == dict(context.entries)
    envelope = json.loads(content)
    for size in (0, 128 * 1024 * 1024, True):
        with pytest.raises(ValueError):
            ResourceContext._decode_database_descriptor(
                json.dumps({**envelope, "decoded_size": size}).encode()
            )
    compressed = base64.b64decode(envelope["data"], validate=True) + b"unexpected suffix"
    with pytest.raises(ValueError):
        ResourceContext._decode_database_descriptor(
            json.dumps({**envelope, "data": base64.b64encode(compressed).decode("ascii")}).encode()
        )
