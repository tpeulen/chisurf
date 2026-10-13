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
    """The one-click button opens ChiSurf's ndX on the analysis folder.

    The browser used to reach into ndX's Qt window through guarded imports;
    when ndX reorganised, they went stale and the button did nothing. It now
    hands the folder to ndX's declared receiver (manifest ``accepts``
    ``open_path``), which opens it the way File > Open does -- pinned here.
    """
    import inspect

    from chisurf.core.plugin import handoff
    from chisurf.emtk.plugins import manifests
    from chisurf.plugins.ndxplorer.gui import app as ndx_app
    from chisurf.plugins.tttr.trace_browser.gui.handoffs import ROUTES

    plugin, kind, adapt = ROUTES["open_ndxplorer"]
    assert (plugin, kind) == ("ndxplorer", "open_path")
    assert adapt({"folder": "/d/m_TW_10ms", "file": "/d/m.spc"})["path"] == "/d/m_TW_10ms"
    spec = handoff.accepted("ndxplorer", "open_path", manifests()["ndxplorer"])
    assert spec.receive == "chisurf.plugins.ndxplorer.gui.app:receive_path"
    assert "app.open_path(str(path))" in inspect.getsource(ndx_app.receive_path)
