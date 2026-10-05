"""An imported version is numbered after its project's newest one when the project exists.

The archive keeps its project id (a version moved between databases joins its project),
and it also kept its own version number: importing v1 into a database that held v1 of
the same project gave the project two "v1" rows. This drives the browser client against
a real authenticated MMFDB server; the allocator contract itself, including the import
into a database without the project, is pinned in mmfdb's ``tests/test_project_services.py``.
"""

from __future__ import annotations


def test_import_into_an_existing_project_gets_the_next_number(authenticated_browser):
    from chisurf.macros.core_fit import get_project_payload

    client = authenticated_browser["client"]
    saved = client.save_project(
        project_name="decay study",
        project_payload=get_project_payload("decay study").to_dict(),
        notes="first",
        visibility="private",
        fit_count=0,
        dataset_count=0,
    )
    archive = authenticated_browser["tmp_path"] / "decay.cs.pto"
    assert client.export_csp(version_id=saved["version_id"], target_path=str(archive)).get("ok")
    result = client.import_csp(file_path=str(archive), resolve_collisions=True)
    assert result["project_id"] == saved["project_id"] and result["version_number"] == 2
    numbers = sorted(
        v["version_number"]
        for v in client.list_projects(show_public=True, search=None)[0]["versions"]
    )
    assert numbers == [1, 2]
