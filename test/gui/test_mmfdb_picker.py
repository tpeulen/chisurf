"""The shared MMFDB dataset picker: a chosen dataset resolves to a local path.

The session-client behaviour (one shared client, adopting the cached login) is covered with the
emtk picker in ``test/native_emtk/test_helpers.py``.
"""

from __future__ import annotations

from chisurf.emtk import dataset_picker as picker


def test_resolve_local_path_prefers_selection_then_opens():
    class _Sel:
        local_path = "/data/already.ptu"
        artifact_id = "a1"

    # local_path present -> no service call
    assert picker.resolve_local_path(None, _Sel()) == "/data/already.ptu"

    class _SelNoPath:
        local_path = None
        artifact_id = "a1"

    class _Client:
        def call(self, method, params):
            assert method == "mmfdb.datasets.open"
            assert params == {"artifact_id": "a1"}
            return {"local_path": "/cache/from_s3.ptu"}

    assert picker.resolve_local_path(_Client(), _SelNoPath()) == "/cache/from_s3.ptu"
