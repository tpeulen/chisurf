"""{{ cookiecutter.plugin_display_name }}

{{ cookiecutter.plugin_description }}

Author: {{ cookiecutter.author_name }} <{{ cookiecutter.author_email }}>
Year: {{ cookiecutter.year }}
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

# Load manifest as source of truth
_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
if _manifest is not None:
    name = _manifest.display_name
    cli_entrypoint = _manifest.entrypoints.cli or ""
else:
    name = "{{ cookiecutter.plugin_category }}:{{ cookiecutter.plugin_display_name }}"
    cli_entrypoint = ""

__all__ = ["name", "cli_entrypoint"]

