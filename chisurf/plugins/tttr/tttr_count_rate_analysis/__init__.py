"""Count Rate Analysis plugin.

Drop TTTR files and compute the count rate per detector channel in each file,
then plot the count rate vs file and report the mean and standard deviation over
all files. Ported to the new-style AutoForm + JSON view (``gui/``): a Qt-free
:class:`~.gui.view_model.CountRateViewModel` drives the detector channel-
definition page, the file list, the count-rate plot and the results table laid
out from ``count_rate.view.json``.

Ribbon: Tools › Photon data › Count Rate Analysis; the ``count-rate`` CLI is the
headless path.

CLI Usage::

    csc_count_rate --help                    # Show help
    csc_count_rate list-setups SETUP_FILE    # List available detector setups
    csc_count_rate analyze FILE1 FILE2...    # Analyze TTTR files
"""

from __future__ import annotations

from pathlib import Path

from chisurf.core.plugin import load_manifest

_manifest = load_manifest(Path(__file__).with_name("manifest.json"))
name = _manifest.display_name if _manifest is not None else "Tools:Photon data:Count Rate Analysis"

# Expose the plugin CLI through chisurf.core.cli.
cli_entrypoint = "count-rate=chisurf.plugins.tttr.tttr_count_rate_analysis.cli:cli"
