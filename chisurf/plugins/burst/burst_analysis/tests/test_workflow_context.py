"""The workflow hand-off is plain data (no Qt): JSON-ready payload, and a storage mode mmfdb accepts."""

from __future__ import annotations

from pathlib import Path


def test_workflow_context_payload_is_json_ready(tmp_path: Path) -> None:
    """Workflow context serializes paths and MMFDB artifact handoff data."""
    from chisurf.plugins.burst.burst_analysis.workflow_context import BurstWorkflowContext

    context = BurstWorkflowContext(
        raw_files=[tmp_path / "a.spc"],
        burst_folder=tmp_path / "burstwise",
        bur_files=[tmp_path / "burstwise" / "bi4_bur" / "a.bur"],
        mmfdb_artifacts={"sidecar_artifacts": {"output_folder": "artifact-1"}},
        raw_mmfdb_artifacts={"imports": {"a.spc": {"object_result": {"ok": True}}}},
    )
    payload = context.to_payload()
    assert payload["raw_files"] == [str(tmp_path / "a.spc")]
    assert payload["burst_folder"] == str(tmp_path / "burstwise")
    assert payload["bur_files"] == [str(tmp_path / "burstwise" / "bi4_bur" / "a.bur")]
    assert payload["mmfdb_artifacts"]["sidecar_artifacts"]["output_folder"] == "artifact-1"
    assert payload["raw_mmfdb_artifacts"]["imports"]["a.spc"]["object_result"]["ok"] is True


def test_registered_storage_mode_is_a_term_mmfdb_accepts() -> None:
    """Importing a file must not be rejected by the raw-data vocabulary.

    ``raw_data.register`` validates ``storage_mode`` against the dictionary-generated vocabulary; the selector
    once sent ``"file"``, which is not a term, so no raw data was ever registered.
    """
    import ast
    import inspect
    import textwrap

    from mmfdb.models import STORAGE_MODES

    from chisurf.plugins.burst.burst_analysis.gui.data_selection_app import import_raw_file

    src = inspect.getsource(import_raw_file)
    modes = [
        node.value
        for node in ast.walk(ast.parse(textwrap.dedent(src)))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    sent = [m for m in modes if m in STORAGE_MODES or m == "file"]
    assert sent, "no storage_mode literal found — did the payload change?"
    for mode in sent:
        assert mode in STORAGE_MODES, f"{mode!r} is not one of {STORAGE_MODES}"
