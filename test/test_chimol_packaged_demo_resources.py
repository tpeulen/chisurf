"""The viewer's runtime demos use its packaged resources, without test fixtures."""
from pathlib import Path

import pytest


@pytest.fixture
def demo_host(monkeypatch):
    """Keep catalog state and host settings hooks isolated for the resource checks."""
    import chimol.core.settings.dirs as dirs
    import chimol.core.settings.logging as logging
    import chimol.plugins.demos.catalog as catalog

    import chisurf.plugins.chimol as host

    monkeypatch.setattr(catalog, "_INJECTED_DIRS", [])
    calls = []
    monkeypatch.setattr(dirs, "set_settings_dir", lambda directory: calls.append("settings"))
    monkeypatch.setattr(logging, "configure_logging", lambda: calls.append("logging"))
    return host, catalog, calls


@pytest.mark.parametrize("name", ["148l.pdb", "topol.pdb", "hgbp1_transition.dcd"])
def test_demos_resolve_packaged_material_without_checkout_test_data(demo_host, name):
    """The original structure and trajectory demos remain available after packaging."""
    host, catalog, calls = demo_host
    host._place_chimol_settings_beside_chisurf_s()
    assert calls == ["settings", "logging"]
    assert all(not {"test", "tests"}.intersection(path.parts) for path in catalog.data_dirs())
    material = Path(catalog.resolve_structure(name))
    assert material.parent == catalog.DEMO_DIR
    assert material.is_file() and material.stat().st_size > 0


def test_host_does_not_replace_an_explicit_user_sample_directory(demo_host, tmp_path):
    """Removing a checkout injection preserves the catalog's intentional user override."""
    host, catalog, calls = demo_host
    catalog.set_data_dirs(tmp_path)
    user_structure = tmp_path / "148l.pdb"
    user_structure.write_text("USER STRUCTURE")
    host._place_chimol_settings_beside_chisurf_s()
    assert calls == ["settings", "logging"]
    assert Path(catalog.resolve_structure("148l.pdb")) == user_structure
