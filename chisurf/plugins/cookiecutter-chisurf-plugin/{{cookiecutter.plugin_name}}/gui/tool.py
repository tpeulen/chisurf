"""{{ cookiecutter.plugin_display_name }}

{{ cookiecutter.plugin_description }}

Author: {{ cookiecutter.author_name }} <{{ cookiecutter.author_email }}>
Year: {{ cookiecutter.year }}
"""

from __future__ import annotations

import sys
from pathlib import Path

from qtpy.QtWidgets import QMainWindow, QWidget, QVBoxLayout

from chisurf.core.plugin import load_manifest
from chisurf.gui.widgets.tools.help_guide import HelpGuideMixin

# Load manifest for metadata
_manifest = load_manifest(Path(__file__).parents[1] / "manifest.json")
if _manifest is not None:
    name = _manifest.display_name
else:
    name = "{{ cookiecutter.plugin_category }}:{{ cookiecutter.plugin_display_name }}"


class {{ cookiecutter.widget_class_name }}(HelpGuideMixin, QMainWindow):
    """Main widget for {{ cookiecutter.plugin_display_name }}.

    ``HelpGuideMixin`` gives this tool the ``?`` and **Guide** buttons. It reads
    ``help.md`` and ``guide.json`` from this directory, so the two are edited as
    text and never as code. Both are required of a plugin -- see
    ``test/test_plugin_help_guide_seam.py``.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("{{ cookiecutter.plugin_display_name }}")
        self.resize(800, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Connect to backend via client
        from .client import {{ cookiecutter.widget_class_name }}Client
        self._client = {{ cookiecutter.widget_class_name }}Client()

        # Add your plugin UI components here

        # The ? and Guide buttons, in a slim toolbar of their own. Fill in
        # help.md and guide.json beside this file; until you do, this adds
        # nothing rather than an empty strip.
        self.ensure_help_toolbar(title="{{ cookiecutter.plugin_display_name }} — help")
