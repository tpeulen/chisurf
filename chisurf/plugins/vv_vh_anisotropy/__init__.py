"""VV/VH anisotropy calculator, a native emtk app."""

from pathlib import Path

from chisurf.core.plugin.manifest import load_manifest

icon = "🎏"
name = "Spectroscopy:Fluorescence decay:VV/VH Anisotropy Decay"
menu_hidden = True
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
deprecated = bool(_manifest.deprecated) if _manifest is not None else True
deprecation_message = (_manifest.deprecation_message if _manifest is not None else "") or (
    "VV/VH Anisotropy Decay is deprecated/obsolete. "
    "Use the VV/VH G-Factor plugin and reader-integrated anisotropy workflow instead."
)

