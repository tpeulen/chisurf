"""The demo container the inspector tour opens is a real, readable .pto."""

from chisurf.plugins.core.pto_inspector.core import PtoInspection
from chisurf.plugins.core.pto_inspector.demo import make_demo


def test_demo_container_opens_with_its_two_tables(tmp_path):
    path = make_demo(tmp_path)
    assert path.suffix == ".pto" and path.is_file()
    with PtoInspection(path) as inspection:
        names = {item.name for item in inspection.infos()}
    assert {"bursts", "lifetimes green"} <= names


def test_demo_container_exports_to_the_legacy_burst_folder(tmp_path):
    """The inspector's one export must accept the container it ships as its own demo."""
    from chisurf.plugins.core.legacy_export.core import export_burst_folder as export_legacy

    path = make_demo(tmp_path / "demo")
    written = export_legacy(path, tmp_path / "out")
    assert any(p.parent.name == "bg4" for p in written)  # the green lifetime companion
