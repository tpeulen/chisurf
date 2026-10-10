"""The demo container the inspector tour opens is a real, readable .pto."""

from chisurf.plugins.core.pto_inspector.core import PtoInspection
from chisurf.plugins.core.pto_inspector.demo import make_demo


def test_demo_container_opens_with_its_two_tables(tmp_path):
    path = make_demo(tmp_path)
    assert path.suffix == ".pto" and path.is_file()
    with PtoInspection(path) as inspection:
        names = {item.name for item in inspection.infos()}
    assert {"bursts", "lifetimes"} <= names
