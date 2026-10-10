"""Tests for the integrated lifetime analysis tool (the native hub)."""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin.manifest import load_manifest


def test_lifetime_panel_order() -> None:
    """The hub lists the requested tools in order."""
    from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import PANELS

    assert [panel[1] for panel in PANELS] == [
        "1. IRF Estimation",
        "2. MaxEnt MEM",
        "3. Lazy Lifetime Analysis",
        "4. Histogram-Microtime",
        "5. VV/VH G-Factor",
        "6. VV/VH Anisotropy",
        "Synthetic Decay",
    ]


def test_lazy_lifetime_panel_marked_experimental() -> None:
    """The hub reads the experimental flag from the LLTF manifest, not from its own table."""
    from chisurf.plugins.fluorescence_decay.lifetime_analysis.gui.app import make_app

    lltf = load_manifest(Path(__file__).resolve().parents[2] / "lltf" / "manifest.json")
    assert lltf is not None and lltf.experimental
    app = make_app()
    try:
        assert app.experimental_message("lltf") == lltf.experimental_message
        assert "experimental" in app.experimental_message("lltf").lower()
        assert not app.experimental_message("maxent_decay")
    finally:
        app.close()


def test_lifetime_analysis_menu_metadata() -> None:
    """Only the grouped lifetime tool remains visible in plugin menus."""
    root = Path(__file__).resolve().parents[1]
    visible = load_manifest(root / "manifest.json")
    assert visible is not None
    # The Spectroscopy tab groups by method; decay analysis is the Decay group.
    assert visible.display_name == "Spectroscopy:Decay:Decay Analysis"
    assert visible.experimental is True
    assert "experimental" in visible.experimental_message.lower()
    assert visible.menu_hidden is False

    hidden_manifests = [
        root.parent / "irf_estimator" / "manifest.json",
        root.parent / "maxent_decay" / "manifest.json",
        root.parent / "lltf" / "manifest.json",
        root.parents[1] / "tttr" / "microtime_histogram" / "manifest.json",
        root.parents[1] / "vv_vh_g_factor" / "manifest.json",
    ]
    for manifest_path in hidden_manifests:
        manifest = load_manifest(manifest_path)
        assert manifest is not None, manifest_path
        assert manifest.menu_hidden is True, manifest_path
