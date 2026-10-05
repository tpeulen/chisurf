"""Authenticated content transport never delegates client filesystem paths."""

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from chisurf.core.project.archive import ProjectArchive
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    _payload_with_fit,
    assert_scientific_roundtrip,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    standalone_server as standalone_server,
)


def test_authenticated_portable_bytes_and_server_path_rejection(
    authenticated_browser, sample_project_payload, tmp_path
):
    """Read exact typed PTO and measurement attachments over the actual HTTP endpoint."""
    client = authenticated_browser["client"]
    payload = _payload_with_fit(sample_project_payload)
    import shutil

    from chisurf.core.data import DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project import capture_session

    curve = assert_scientific_roundtrip(payload).datasets[0]
    prompt = Path(__file__).resolve().parents[2] / "test/data/tcspc/ibh_sample/Prompt.txt"
    alias = tmp_path / "prompt-alias.txt"
    shutil.copyfile(prompt, alias)
    curve.meta_data["reader_resource"] = [{"filename": str(prompt)}, {"filename": str(alias)}]
    group = FitGroup(DataCurveGroup([curve]), model_class=ParseModel)
    group.grouped_fits[0].model.func = "amp*x+tau"
    shared = FittingParameter(name="shared-tau", value=4.1)
    group._model.append_global_parameter(shared)
    group.grouped_fits[0].model.parameters_all[1].link = shared
    group.grouped_fits[0].mask = np.ones(len(curve.y))
    group.grouped_fits[0].mask[:12] = 0
    group.grouped_fits[0].model.update()
    payload = capture_session([curve], [group], name="Measured transport").to_dict()
    saved = client.save_project("Measured transport", project_payload=payload)
    source = tmp_path / "Decay_577D.txt"
    measured = source.read_bytes()
    for method, params in (
        (
            "project_browser.export_csp",
            {
                "version_id": saved["version_id"],
                "target_path": str(tmp_path / "server-write.cs.pto"),
            },
        ),
        ("project_browser.import_preview", {"file_path": str(source)}),
        ("project_browser.import_csp", {"file_path": "../server.sqlite"}),
    ):
        with pytest.raises(Exception, match="[Pp]ath|[Cc]ontent|[Ff]ilesystem"):
            client._call(method, params)
    assert not (tmp_path / "server-write.cs.pto").exists()
    exported = client.export_csp(saved["version_id"])
    assert exported["version_id"] == saved["version_id"]
    archive = ProjectArchive.open_bytes(base64.b64decode(exported["archive_bytes"], validate=True))
    assert json.loads(archive.read_text("project.json")) == payload
    dependencies = json.loads(archive.read_text("mmfdb_export.json"))["dependencies"]
    objects = {obj["object_uuid"]: obj for obj in dependencies["objects"]}
    raw = next(
        art for art in dependencies["artifacts"] if art["artifact_kind"] == "raw_measurement"
    )
    assert base64.b64decode(objects[raw["object_uuid"]]["data_base64"], validate=True) == measured
    source.unlink()
    alias.unlink()
    preview = client.import_preview(archive_base64=exported["archive_bytes"])
    assert preview["has_collisions"]
    imported = client.import_csp(archive_base64=exported["archive_bytes"], resolve_collisions=True)
    restored = client.restore_project(imported["version_id"])
    assert restored["project_payload"] == payload
    assert_scientific_roundtrip(restored["project_payload"])
    from mmfdb.repository import MFDatabase

    with MFDatabase(authenticated_browser["path"]) as db:
        artifacts = db.get_operation_artifacts(imported["version_id"])
        raw_artifacts = {
            art["file_path"]: art for art in artifacts if art["artifact_kind"] == "raw_measurement"
        }
        assert set(raw_artifacts) == {str(source), str(prompt), str(alias)}
        assert db.get_object(raw_artifacts[str(source)]["object_uuid"]) == measured
        assert db.get_object(raw_artifacts[str(prompt)]["object_uuid"]) == prompt.read_bytes()
        assert db.get_object(raw_artifacts[str(alias)]["object_uuid"]) == prompt.read_bytes()
        links = db.conn.execute(
            "SELECT * FROM mmfdb_edge WHERE operation_id = ? "
            "AND relationship_type = 'parameter_depends_on'",
            (imported["version_id"],),
        ).fetchall()
        assert len(links) == 1
    assert client.list_artifacts(imported["version_id"])
    assert len(client.list_parameters(imported["version_id"])) == 3


def test_server_save_does_not_open_snapshot_resource_paths(
    authenticated_browser, sample_project_payload
):
    """An existing absolute source label alone grants no server filesystem access."""
    client = authenticated_browser["client"]
    saved = client._call(
        "project_browser.save",
        {
            "project_name": "No supplied resource bytes",
            "project_payload": sample_project_payload,
        },
    )
    assert saved["ok"]
    assert all(
        art["artifact_kind"] != "raw_measurement"
        for art in client.list_artifacts(saved["version_id"])
    )
    assert client.restore_project(saved["version_id"])["project_payload"] == sample_project_payload


def test_import_rejects_actual_typed_container_with_traversal_entry(
    authenticated_browser, sample_project_payload, tmp_path
):
    """A real PTO container cannot smuggle an extraction path through content transport."""
    import tttrlib

    archive = ProjectArchive()
    archive.write_text("project.json", json.dumps(sample_project_payload))
    path = archive.save(tmp_path / "unsafe.cs.pto")
    handle = tttrlib.PtoFile()
    assert handle.open(str(path), True)
    assert handle.add("chisurf.project-entry", "raw", "aa/escaped", b"unsafe resource")
    assert handle.commit()
    handle.close()
    path.write_bytes(path.read_bytes().replace(b"aa/escaped", b"../escaped"))
    client = authenticated_browser["client"]
    with pytest.raises(
        Exception, match="Unsafe project entry path|Invalid PTO|invalid|unsafe|walks out|Could not"
    ):
        client.import_preview(file_path=str(path))
    assert not (tmp_path / "escaped").exists()


def test_actual_auth_and_private_version_detail_boundaries(
    authenticated_browser, sample_project_payload
):
    """All standalone routes authenticate and private details remain owner-bound."""
    from mmfdb.admin.backend.password_services import hash_password
    from mmfdb.repository import MFDatabase

    from test.project.test_real_mmfdb_http import _rpc

    client = authenticated_browser["client"]
    saved = client.save_project("Private measured project", project_payload=sample_project_payload)
    with MFDatabase(authenticated_browser["path"]) as db:
        db.add_user(
            "transport-other", "Other reader", password_hash=hash_password("reader-password")
        )
        db.conn.commit()
    session = _rpc(
        authenticated_browser["url"],
        "mmfdb.security.auth.login",
        {
            "user_id": "transport-other",
            "password": "reader-password",
            "provider": "local",
        },
    )
    methods = {
        "export_csp": {"version_id": saved["version_id"]},
        "import_preview": {},
        "import_csp": {},
        "delete_version": {"version_id": saved["version_id"]},
        "create_branch": {
            "project_id": saved["project_id"],
            "from_version_id": saved["version_id"],
            "branch_name": "forbidden",
        },
        "list_branches": {"project_id": saved["project_id"]},
        "version_graph": {"project_id": saved["project_id"]},
        "artifacts": {"version_id": saved["version_id"]},
        "parameters": {"version_id": saved["version_id"]},
    }
    from chisurf.plugins.core.mmfdb_admin.gui.client import MMFDBClient
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    base = MMFDBClient(
        mode="remote",
        base_url=authenticated_browser["url"],
        allow_insecure_http=True,
        inprocess=False,
    )
    base.token = "invalid-auth-token"
    invalid = ProjectBrowserClient(mmfdb_client=base)
    for method, params in methods.items():
        with pytest.raises(Exception, match="[Aa]uth|[Ss]ession|[Tt]oken"):
            invalid._call("project_browser." + method, params)
    base.token = session["token"]
    other = ProjectBrowserClient(mmfdb_client=base)
    for method in ("export_csp", "delete_version", "create_branch", "artifacts", "parameters"):
        with pytest.raises(Exception, match="[Pp]ermission|[Dd]enied|[Aa]ccess"):
            other._call("project_browser." + method, methods[method])
    assert other.list_branches(saved["project_id"]) == []
    assert other.version_graph(saved["project_id"])["nodes"] == []
    exported = client.export_csp(saved["version_id"])
    content = client._archive_content(exported["archive_bytes"])
    with pytest.raises(Exception, match="[Pp]ermission|[Dd]enied|[Aa]ccess"):
        other._call("project_browser.import_preview", content)
    assert client.restore_project(saved["version_id"])["project_payload"] == sample_project_payload


def test_new_remote_version_retains_attached_resources_without_client_source(
    authenticated_browser, sample_project_payload
):
    """A readback/resave inherits authorized stored resources after local files vanish."""
    client = authenticated_browser["client"]
    source = Path(sample_project_payload["datasets"]["ds_sample"]["filename"])
    measured = source.read_bytes()
    first = client.save_project("Portable resave", project_payload=sample_project_payload)
    source.unlink()
    second = client.save_project(
        "Portable resave",
        project_payload=sample_project_payload,
        project_id=first["project_id"],
        parent_version_id=first["version_id"],
    )
    assert second["version_number"] == 2
    from mmfdb.repository import MFDatabase

    with MFDatabase(authenticated_browser["path"]) as db:
        raw = [
            art
            for art in db.get_operation_artifacts(second["version_id"])
            if art["artifact_kind"] == "raw_measurement"
        ]
        assert len(raw) == 1
        assert db.get_object(raw[0]["object_uuid"]) == measured
    assert client.restore_project(second["version_id"])["project_payload"] == sample_project_payload
