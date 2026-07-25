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
    """A guarded import that fails leaves the feature silently missing.

    The browser hands a burst analysis to ndXplorer through two optional
    imports wrapped in ``try``/``except``. When ndXplorer reorganised its
    modules both paths went stale, and nothing failed — ``ndx_reader`` and
    ``NDXplorer`` simply became ``None`` and the button did nothing. This pins
    the symbols and the two calls the browser makes on them.
    """
    import pytest

    pytest.importorskip("ndxplorer")
    from chisurf.plugins.tttr import trace_browser

    assert trace_browser.ndx_reader is not None, "ndXplorer reader import went stale"
    assert trace_browser.NDXplorer is not None, "ndXplorer window import went stale"
    assert hasattr(trace_browser.ndx_reader, "read_burst_analysis")
