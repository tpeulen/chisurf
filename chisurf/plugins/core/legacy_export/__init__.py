"""The legacy-export core plugin: the dedicated bridge out of the ``.pto`` world.

PRD-154's rule: the workflow tools read and write ``.pto`` containers; legacy
formats (the Seidel/Margarita burst folder, the ALEX-Suite CSVs) are reached
only through an explicit export, and this plugin is that export. The packing
itself lives in one place -- :mod:`chisurf.core.fio.fluorescence.legacy_export`
(the burst folder) and :mod:`chisurf.plugins.burst.alex_suite.api.legacy_export`
(the five CSVs); this plugin previews what a container will produce and runs
those writers.
"""
