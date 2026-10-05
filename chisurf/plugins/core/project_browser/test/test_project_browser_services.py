from __future__ import annotations

import base64
import json
from pathlib import Path

import numpy as np
import pytest

from test.project.test_real_mmfdb_http import standalone_server as standalone_server


@pytest.fixture
def project_db(tmp_path, monkeypatch):
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session

    from chisurf.plugins.core.project_browser.backend import services

    db_path = tmp_path / "project_browser.db"
    object_root = tmp_path / "objects"
    with MFDatabase(db_path) as db:
        db.add_user("user_default", "Default User")
        db.add_user("admin_user", "Admin User", is_admin=1)
        session = create_session(db.conn, "admin_user", client_name="pytest")
        db.conn.commit()

    monkeypatch.setattr(services, "resolve_database_path", lambda: db_path)
    monkeypatch.setattr(
        "mmfdb.store.database_resolver.resolve_database_path",
        lambda: db_path,
    )
    monkeypatch.setattr(
        "mmfdb.store.database_resolver.object_store_root",
        lambda: object_root,
    )
    return {"path": db_path, "auth": {"token": session["token"]}, "tmp_path": tmp_path}


@pytest.fixture
def sample_project_payload(tmp_path):
    """Capture measured TCSPC arrays and the real reader, retaining its source file."""
    import shutil

    from chisurf.core.experiments.tcspc import TCSPCReader
    from chisurf.core.project import capture_session

    source = Path(__file__).resolve().parents[5] / "test/data/tcspc/ibh_sample/Decay_577D.txt"
    data_path = tmp_path / source.name
    shutil.copyfile(source, data_path)
    reader = TCSPCReader(
        dt=0.048, rep_rate=80.0, skiprows=9, use_header=False, rebin=(1, 1), record_provenance=False
    )
    curve = reader.get_data(filename=str(data_path))[0]
    curve.unique_identifier = "ds_sample"
    curve.name = "Sample Curve"
    raw = np.loadtxt(source, skiprows=9)
    np.testing.assert_array_equal(curve.y, raw[:, 1])
    np.testing.assert_allclose(curve.x, raw[:, 0] * reader.dt)
    return capture_session([curve], [], name="Sample Project").to_dict()


@pytest.fixture
def authenticated_browser(standalone_server, tmp_path, monkeypatch):
    """Configure the exact authenticated standalone deployment used by Save."""
    from mmfdb.security.credentials import credential_account, session_token_registry

    import chisurf
    from chisurf.core.settings import cs_settings
    from chisurf.plugins.core.mmfdb_admin.gui.client import (
        MMFDBClient,
        client_config,
        credential_endpoint,
    )
    from chisurf.plugins.core.project_browser.gui.client import ProjectBrowserClient

    monkeypatch.setattr(chisurf, "imported_datasets", [])
    monkeypatch.setattr(chisurf, "fits", [])
    monkeypatch.setattr(chisurf, "cs", None, raising=False)
    monkeypatch.setattr(chisurf, "current_fit_idx", -1, raising=False)
    url, token, path = standalone_server
    settings = {
        "client": {
            "mode": "remote",
            "base_url": url,
            "allow_insecure_http": True,
            "username": "real-http-user",
        }
    }
    monkeypatch.setitem(cs_settings, "mmfdb", settings)
    endpoint = credential_endpoint(client_config(settings))
    monkeypatch.setitem(
        session_token_registry(), credential_account(*endpoint, "real-http-user"), token
    )
    base_client = MMFDBClient(
        mode="remote", base_url=url, allow_insecure_http=True, inprocess=False
    )
    base_client.token = token
    return {
        "url": url,
        "token": token,
        "path": path,
        "tmp_path": tmp_path,
        "client": ProjectBrowserClient(mmfdb_client=base_client),
        "settings": settings,
    }


def assert_scientific_roundtrip(payload):
    """Restore real science and recapture every array, UID, model and UI field."""
    from chisurf.core.project import Project, capture_session, restore_session

    project = Project.from_dict(payload)
    restored = restore_session(project)
    captured = capture_session(
        restored.datasets,
        restored.fits,
        ui_state=restored.ui_state,
        experiments=restored.experiments,
        name=project.name,
    ).to_dict()
    for section in ("datasets", "fits", "ui", "experiments", "parameters", "dependency_edges"):
        assert captured[section] == payload[section]
    return restored


def test_save_list_restore_and_export_sample_project(project_db, sample_project_payload):
    from chisurf.plugins.core.project_browser.backend.services import (
        export_csp_handler,
        list_projects_handler,
        restore_project_handler,
        save_project_handler,
    )

    auth = project_db["auth"]
    saved = save_project_handler(
        auth=auth,
        project_name="Sample Project",
        project_payload=sample_project_payload,
        visibility="private",
        notes="sample payload",
    )

    assert saved["ok"] is True
    assert saved["artifact_count"] == 1

    listed = list_projects_handler(auth=auth)
    assert listed["ok"] is True
    assert len(listed["projects"]) == 1
    project = listed["projects"][0]
    assert project["project_name"] == "Sample Project"
    assert project["latest_version_id"] == saved["version_id"]
    assert project["versions"][0]["dataset_count"] == 1

    restored = restore_project_handler(auth=auth, version_id=saved["version_id"])
    assert restored["ok"] is True
    restored_payload = restored["project_payload"]
    assert "ds_sample" in restored_payload["datasets"]
    assert restored_payload["datasets"]["ds_sample"]["name"] == "Sample Curve"

    exported = export_csp_handler(auth=auth, version_id=saved["version_id"])
    assert exported["ok"] is True
    archive_bytes = base64.b64decode(exported["archive_bytes"])
    assert archive_bytes
    from chisurf.core.project.archive import ProjectArchive

    assert restored["version_id"] == saved["version_id"]
    assert restored["project_id"] == saved["project_id"]
    assert_scientific_roundtrip(restored_payload)
    archive_path = project_db["tmp_path"] / "exported.cs.pto"
    archive_path.write_bytes(archive_bytes)
    archive = ProjectArchive.open(archive_path)
    source = Path(sample_project_payload["datasets"]["ds_sample"]["filename"])
    dependencies = json.loads(archive.read_text("mmfdb_export.json"))["dependencies"]
    source_artifacts = [
        artifact
        for artifact in dependencies["artifacts"]
        if artifact["artifact_kind"] == "raw_measurement"
    ]
    assert len(source_artifacts) == 1
    objects = {obj["object_uuid"]: obj for obj in dependencies["objects"]}
    source_object = objects[source_artifacts[0]["object_uuid"]]
    assert base64.b64decode(source_object["data_base64"], validate=True) == source.read_bytes()
    assert source_object["filename"] == str(source)


def test_project_browser_services_register_with_dispatcher(project_db):
    from chisurf.core.plugin.client import InProcessClient
    from chisurf.plugins.core.project_browser.backend.services import register_services
    from chisurf.server.dispatcher import ServiceDispatcher
    from chisurf.server.session import SessionState

    dispatcher = ServiceDispatcher(SessionState())
    register_services(dispatcher)
    client = InProcessClient(dispatcher)

    result = client.call("project_browser.list", {"auth": project_db["auth"]})

    assert result["ok"] is True
    assert result["projects"] == []
    assert "project_browser.create_branch" in dispatcher.list_methods()
    assert "project_browser.parameters" in dispatcher.list_methods()


def _payload_with_fit(sample_project_payload):
    """Capture a real lifetime model with bounded and fixed parameters."""
    from chisurf.core.fitting.fit import Fit
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project import Project, capture_session, restore_session

    curve = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    fit = Fit(data=curve, model_class=ParseModel)
    fit.unique_identifier = "fit_sample"
    fit.name = "Sample Fit"
    fit.model.func = "amp*x+tau"
    amplitude, lifetime = fit.model.parameters_all[:2]
    amplitude.value, amplitude.bounds, amplitude.bounds_on = 2.0, (0.0, 10.0), True
    lifetime.value, lifetime.fixed = 4.0, True
    fit.model.update()
    return capture_session([curve], [fit], name="Sample Project").to_dict()


def test_artifact_and_parameter_browsing_for_project_version(
    project_db,
    sample_project_payload,
):
    from chisurf.plugins.core.project_browser.backend.services import (
        list_project_artifacts_handler,
        list_project_parameters_handler,
        save_project_handler,
    )

    auth = project_db["auth"]
    payload = _payload_with_fit(sample_project_payload)
    saved = save_project_handler(
        auth=auth,
        project_name="Sample Project",
        project_payload=payload,
        visibility="private",
        notes="artifact and parameter coverage",
    )
    assert saved["ok"] is True, saved
    assert saved["artifact_count"] >= 2
    assert saved["parameter_count"] == len(payload["fits"][0]["members"][0]["model"]["parameters"])

    artifacts = list_project_artifacts_handler(auth=auth, version_id=saved["version_id"])
    assert artifacts["ok"] is True
    artifact_kinds = {artifact["artifact_kind"] for artifact in artifacts["artifacts"]}
    assert {"processed_data", "fit_result"}.issubset(artifact_kinds)

    parameters = list_project_parameters_handler(auth=auth, version_id=saved["version_id"])
    assert parameters["ok"] is True
    by_name = {parameter["name"]: parameter for parameter in parameters["parameters"]}
    assert by_name["amp"]["value"] == 2.0
    assert by_name["amp"]["bounds_on"] == 1
    assert by_name["tau"]["parameter_type"] == "fixed"


def test_authenticated_canonical_indexes_retain_arrays_links_and_version_identity(
    authenticated_browser, sample_project_payload
):
    """Read real measured data, global links and immutable indexes after HTTP saves."""
    from mmfdb.repository import MFDatabase

    from chisurf.core.data import DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project import Project, capture_session, restore_session

    first = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    second = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    second.unique_identifier = "ds_index_second"
    resource_path = Path(__file__).resolve().parents[5] / "test/data/tcspc/ibh_sample/Prompt.txt"
    assert resource_path.is_file()
    import shutil

    resource_alias = authenticated_browser["tmp_path"] / "reader-prompt-copy.txt"
    shutil.copyfile(resource_path, resource_alias)
    first.meta_data["reader_resource"] = [
        {"filename": str(resource_path)},
        {"filename": str(resource_alias)},
    ]
    group = FitGroup(DataCurveGroup([first, second]), model_class=ParseModel)
    shared = FittingParameter(name="tau-global", value=4.1)
    group._model.append_global_parameter(shared)
    for member in group.grouped_fits:
        member.model.func = "amp*x+tau"
        member.model.parameters_all[1].link = shared
        member.mask = np.ones(len(first.y), dtype=np.float64)
        member.mask[:12] = 0
        member.model.update()
    client = authenticated_browser["client"]
    payload = capture_session([first, second], [group], name="Indexed project").to_dict()
    saved = client.save_project("Indexed project", project_payload=payload)
    assert saved["ok"] and saved["parameter_count"] == 5, saved
    assert client.restore_project(saved["version_id"])["project_payload"] == payload

    def read_indexes(version_id):
        """Read attached bytes and actual SQL rows from the deployment database."""
        with MFDatabase(authenticated_browser["path"]) as db:
            artifacts = db.conn.execute(
                "SELECT a.* FROM mmfdb_artifact a JOIN mmfdb_edge e "
                "ON e.target_node_id = a.artifact_id "
                "WHERE e.source_node_id = ? AND e.relationship_type = 'project_contains'",
                (version_id,),
            ).fetchall()
            datasets = {
                json.loads(row["metadata_json"])["ds_id"]: json.loads(
                    db.get_object(row["object_uuid"])
                )
                for row in artifacts
                if row["artifact_kind"] == "processed_data"
            }
            fits = [
                json.loads(row["data_json"])
                for row in artifacts
                if row["artifact_kind"] == "fit_result"
            ]
            parameters = [
                dict(row)
                for row in db.conn.execute(
                    "SELECT * FROM mmfdb_parameter WHERE operation_id = ? "
                    "OR operation_id LIKE ? ORDER BY parameter_uuid",
                    (version_id, f"fit_{version_id}:%"),
                )
            ]
            links = [
                dict(row)
                for row in db.conn.execute(
                    "SELECT * FROM mmfdb_edge WHERE operation_id = ? "
                    "AND relationship_type = 'parameter_depends_on' ORDER BY source_node_id",
                    (version_id,),
                )
            ]
            sources = db.conn.execute(
                "SELECT a.* FROM mmfdb_artifact a JOIN mmfdb_operation_artifact l "
                "ON l.artifact_id = a.artifact_id WHERE l.operation_id = ? "
                "AND a.artifact_kind = 'raw_measurement' ORDER BY a.artifact_id",
                (version_id,),
            ).fetchall()
            assert sources
            assert {source["file_path"] for source in sources} == {
                first.filename,
                str(resource_path),
                str(resource_alias),
            }
            for source in sources:
                assert (
                    db.get_object(source["object_uuid"]) == Path(source["file_path"]).read_bytes()
                )
        return datasets, fits, parameters, links, [dict(source) for source in sources]

    datasets, fits, parameters, links, sources = before = read_indexes(saved["version_id"])
    assert len(sources) == 3
    assert datasets == payload["datasets"]
    assert len(fits) == 2
    assert all(item["fit"] == payload["fits"][0] for item in fits)
    assert {item["member_uid"] for item in fits} == {
        member["uid"] for member in payload["fits"][0]["members"]
    }
    assert len(parameters) == 5 and len(links) == 2
    by_uid = {json.loads(row["metadata_json"])["fit_parameter_uid"]: row for row in parameters}
    models = [member["model"] for member in payload["fits"][0]["members"]]
    models.append(payload["fits"][0]["aggregate_model"])
    for model in models:
        for parameter in model["parameters"]:
            row = by_uid[parameter["uid"]]
            assert row["value"] == parameter["value"]
            assert json.loads(row["metadata_json"])["parameter"] == parameter
    for edge in links:
        metadata = json.loads(edge["metadata_json"])
        assert edge["source_node_id"] == by_uid[metadata["parameter_uid"]]["parameter_uuid"]
        assert (
            edge["target_node_id"]
            == by_uid[metadata["link_target"]["parameter_uid"]]["parameter_uuid"]
        )
    shared.value = 6.2
    newer = capture_session([first, second], [group], name="Indexed project").to_dict()
    next_version = client.save_project(
        "Indexed project",
        project_payload=newer,
        project_id=saved["project_id"],
        parent_version_id=saved["version_id"],
    )
    assert next_version["ok"] and next_version["parameter_count"] == 5
    assert read_indexes(saved["version_id"]) == before
    assert client.restore_project(saved["version_id"])["project_payload"] == payload
    assert client.restore_project(next_version["version_id"])["project_payload"] == newer


def test_branch_dag_and_version_graph_roots_and_leaves(
    project_db,
    sample_project_payload,
):
    from chisurf.plugins.core.project_browser.backend.services import (
        create_branch_handler,
        get_version_graph_handler,
        list_branches_handler,
        save_project_handler,
    )

    auth = project_db["auth"]
    root = save_project_handler(
        auth=auth,
        project_name="Branch Project",
        project_payload=sample_project_payload,
        visibility="private",
        notes="root",
    )
    assert root["ok"] is True

    main_child = save_project_handler(
        auth=auth,
        project_name="Branch Project",
        project_payload=sample_project_payload,
        project_id=root["project_id"],
        parent_version_id=root["version_id"],
        visibility="private",
        notes="main child",
    )
    assert main_child["ok"] is True

    branch = create_branch_handler(
        auth=auth,
        project_id=root["project_id"],
        from_version_id=root["version_id"],
        branch_name="analysis fork",
    )
    assert branch["ok"] is True
    fork_child = save_project_handler(
        auth=auth,
        project_name="Branch Project",
        project_payload=sample_project_payload,
        project_id=root["project_id"],
        parent_version_id=root["version_id"],
        branch_uuid=branch["branch_uuid"],
        visibility="private",
        notes="fork child",
    )
    assert fork_child["ok"] is True

    branches = list_branches_handler(auth=auth, project_id=root["project_id"])
    assert branches["ok"] is True
    branch_counts = {item["name"]: item["version_count"] for item in branches["branches"]}
    assert branch_counts[f"project_{root['project_id']}"] == 2
    assert branch_counts["analysis fork"] == 1

    graph = get_version_graph_handler(auth=auth, project_id=root["project_id"])
    assert graph["ok"] is True
    assert set(graph["graph"]["roots"]) == {root["version_id"]}
    assert set(graph["graph"]["leaves"]) == {
        main_child["version_id"],
        fork_child["version_id"],
    }
    assert {(edge["source"], edge["target"]) for edge in graph["graph"]["edges"]} == {
        (main_child["version_id"], root["version_id"]),
        (fork_child["version_id"], root["version_id"]),
    }


def test_import_collision_preview_requires_and_applies_remap(
    project_db,
    sample_project_payload,
):
    from chisurf.plugins.core.project_browser.backend.services import (
        export_csp_handler,
        import_csp_handler,
        import_preview_handler,
        list_projects_handler,
        save_project_handler,
    )

    auth = project_db["auth"]
    saved = save_project_handler(
        auth=auth,
        project_name="Collision Project",
        project_payload=_payload_with_fit(sample_project_payload),
        visibility="private",
        notes="collision source",
    )
    assert saved["ok"] is True
    exported = export_csp_handler(auth=auth, version_id=saved["version_id"])
    assert exported["ok"] is True

    preview = import_preview_handler(auth=auth, archive_base64=exported["archive_bytes"])
    assert preview["ok"] is True
    assert preview["has_collisions"] is True
    assert saved["version_id"] in preview["collisions"]["operations"]

    rejected = import_csp_handler(auth=auth, archive_base64=exported["archive_bytes"])
    assert rejected["ok"] is False
    accepted = import_csp_handler(
        auth=auth,
        archive_base64=exported["archive_bytes"],
        resolve_collisions=True,
    )
    assert accepted["ok"] is True
    assert accepted["id_remap"]["operations"][saved["version_id"]] == accepted["version_id"]

    listed = list_projects_handler(auth=auth)
    assert listed["ok"] is True
    projects = [
        project for project in listed["projects"] if project["project_id"] == saved["project_id"]
    ]
    assert projects[0]["version_count"] == 2


def test_import_and_restore_a_regular_chisurf_pto_project(
    project_db, sample_project_payload, tmp_path
):
    from chisurf.core.project import ProjectArchive
    from chisurf.core.project.archive import PROJECT_JSON
    from chisurf.plugins.core.project_browser.backend.services import (
        import_csp_handler,
        import_preview_handler,
        restore_project_handler,
    )

    archive = ProjectArchive()
    archive.write_text(PROJECT_JSON, json.dumps(sample_project_payload, sort_keys=True))
    project_path = archive.save(tmp_path / "standalone.cs.pto")

    preview = import_preview_handler(auth=project_db["auth"], file_path=str(project_path))
    assert preview["ok"] is True
    assert preview["archive_kind"] == "chisurf_project"
    assert preview["has_collisions"] is False

    imported = import_csp_handler(auth=project_db["auth"], file_path=str(project_path))
    assert imported["ok"] is True
    assert imported["archive_kind"] == "chisurf_project"

    restored = restore_project_handler(auth=project_db["auth"], version_id=imported["version_id"])
    assert restored["ok"] is True
    restored_payload = restored["project_payload"]
    assert restored_payload["meta"]["name"] == sample_project_payload["meta"]["name"]
    assert set(restored_payload["datasets"]) == set(sample_project_payload["datasets"])
    assert restored_payload["fits"] == sample_project_payload["fits"]
    assert_scientific_roundtrip(restored_payload)


def test_restore_preserves_global_fit_and_window_state(project_db, sample_project_payload, qapp):
    from chisurf.core.data import DataCurveGroup
    from chisurf.core.fitting.fit import FitGroup
    from chisurf.core.fitting.parameter import FittingParameter
    from chisurf.core.models.parse.parse import ParseModel
    from chisurf.core.project import Project, capture_session, restore_session
    from chisurf.plugins.core.project_browser.backend.services import (
        restore_project_handler,
        save_project_handler,
    )

    first = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    second = restore_session(Project.from_dict(sample_project_payload)).datasets[0]
    second.unique_identifier = "ds_second"
    curves = DataCurveGroup([first, second], name="measured decays")
    group = FitGroup(curves, model_class=ParseModel)
    group.unique_identifier = "global-fit"
    shared = FittingParameter(name="tau-global", value=4.1)
    group._model.append_global_parameter(shared)
    for local in group.grouped_fits:
        local.model.func = "amp*x+tau"
        local.model.parameters_all[1].link = shared
        local.model.update()
    from qtpy import QtWidgets

    from chisurf.core.project.ui_state import get_ui_state

    window = QtWidgets.QMainWindow()
    window.resize(1100, 700)
    ui = {**get_ui_state(window), "current_fit_index": 0, "current_fit_uid": "global-fit"}
    window.close()
    assert ui["geometry"] and ui["dock_state"]
    payload = capture_session([curves], [group], name="Global Project", ui_state=ui).to_dict()

    saved = save_project_handler(
        auth=project_db["auth"],
        project_name="Global Project",
        project_payload=payload,
    )
    assert saved["ok"] is True

    restored = restore_project_handler(auth=project_db["auth"], version_id=saved["version_id"])
    assert restored["ok"] is True
    assert restored["project_payload"] == payload
    session = assert_scientific_roundtrip(restored["project_payload"])
    restored_group = session.fits[0]
    assert restored_group.unique_identifier == "global-fit"
    shared_restored = restored_group._model.global_parameters_all[0]
    assert shared_restored.value == 4.1
    assert all(
        local.model.parameters_all[1].link is shared_restored
        for local in restored_group.grouped_fits
    )
    assert session.ui_state["current_fit_uid"] == "global-fit"
    assert session.ui_state["geometry"] == ui["geometry"]
    assert session.ui_state["dock_state"] == ui["dock_state"]


def test_delete_version_requires_manage_permission(project_db, sample_project_payload):
    from mmfdb.repository import MFDatabase
    from mmfdb.security.auth import create_session

    from chisurf.plugins.core.project_browser.backend.services import (
        delete_version_handler,
        list_projects_handler,
        save_project_handler,
    )

    auth = project_db["auth"]
    saved = save_project_handler(
        auth=auth,
        project_name="Delete Project",
        project_payload=sample_project_payload,
        visibility="public",
        notes="delete permission coverage",
    )
    assert saved["ok"] is True

    with MFDatabase(project_db["path"]) as db:
        db.add_user("viewer_user", "Viewer User")
        viewer_session = create_session(db.conn, "viewer_user", client_name="pytest-viewer")
        db.conn.commit()

    viewer_auth = {"token": viewer_session["token"]}
    denied = delete_version_handler(auth=viewer_auth, version_id=saved["version_id"])
    assert denied["ok"] is False

    deleted = delete_version_handler(auth=auth, version_id=saved["version_id"])
    assert deleted["ok"] is True
    listed = list_projects_handler(auth=auth)
    assert listed["ok"] is True
    assert listed["projects"] == []
