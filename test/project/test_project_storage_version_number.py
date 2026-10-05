"""Exact-version storage metadata through the authenticated standalone service."""

from __future__ import annotations

import json

from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    _payload_with_fit,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    authenticated_browser as authenticated_browser,
)
from chisurf.plugins.core.project_browser.test.test_project_browser_services import (
    sample_project_payload as sample_project_payload,
)
from test.project.test_real_mmfdb_http import standalone_server as standalone_server


def test_save_database_returns_checked_exact_version_number(
    authenticated_browser,
    sample_project_payload,
):
    """Return the allocated HTTP version number with its exact scientific readback."""
    from mmfdb.repository import MFDatabase

    from chisurf.core.project import Project
    from chisurf.core.project.storage import save_database

    deployment = authenticated_browser
    project = Project.from_dict(_payload_with_fit(sample_project_payload))
    project_id = parent_version_id = None
    for expected_number in (1, 2, 3):
        result = save_database(
            project,
            project_id=project_id,
            parent_version_id=parent_version_id,
            mmfdb_settings=deployment["settings"],
            client=deployment["client"],
        )
        assert result["version_number"] == expected_number
        restored = deployment["client"].restore_project(result["version_id"])
        assert restored["ok"] is True
        assert restored["project_id"] == result["project_id"]
        assert restored["version_id"] == result["version_id"]
        assert restored["version_number"] == result["version_number"]
        assert restored["parent_version_id"] == parent_version_id
        assert restored["project_payload"] == project.to_dict()
        with MFDatabase(deployment["path"]) as db:
            row = db.conn.execute(
                "SELECT metadata_json FROM mmfdb_operation WHERE operation_id = ?",
                (result["version_id"],),
            ).fetchone()
        metadata = json.loads(row[0])
        assert metadata["version_number"] == result["version_number"]
        assert metadata["fit_structure"] == project.to_dict()
        project_id, parent_version_id = result["project_id"], result["version_id"]
