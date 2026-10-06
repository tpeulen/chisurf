from chisurf.plugins.tttr.trace_browser.api.contract import METHOD_LIST_FILES, contract_descriptor
from chisurf.plugins.tttr.trace_browser.api.io import list_files
from chisurf.plugins.tttr.trace_browser.core.metadata import load_meta, save_meta


def test_contract_describes_rpc_methods(tmp_path):
    contract = contract_descriptor()
    assert METHOD_LIST_FILES in contract["methods"]


def test_metadata_roundtrip(tmp_path):
    save_meta(tmp_path, {"a.ptu": {"rating": 2, "annotation": "good"}})
    assert load_meta(tmp_path)["a.ptu"]["rating"] == 2


def test_list_files(tmp_path):
    trace = tmp_path / "demo.ptu"
    trace.write_bytes(b"trace")
    rows = list_files(str(tmp_path))
    assert rows[0]["name"] == "demo.ptu"


def test_the_ndxplorer_integration_is_actually_wired():
    """The one-click button opens ChiSurf's ndX window on the analysis folder.

    The browser used to reach into ndX's Qt window through guarded imports;
    when ndX reorganised, they went stale and the button did nothing. It now
    goes through the plugin's single construction, pinned here.
    """
    import inspect

    import pytest

    pytest.importorskip("ndxplorer")
    from chisurf.plugins.ndxplorer.window import build_ndxplorer_window

    # The Qt workspace moved from the package ``__init__`` (now a lazy, Qt-free shim)
    # to ``widget.py``; the wiring is pinned where the code is.
    from chisurf.plugins.tttr.trace_browser import widget as trace_browser

    assert "path" in inspect.signature(build_ndxplorer_window).parameters
    source = inspect.getsource(trace_browser)
    assert "build_ndxplorer_window(analysis_dir)" in source
    assert "NDXplorer(" not in source
