"""``python -m chisurf.core.cli`` -- the ``csc`` command without its installed entry point.

The docs environment runs ChiSurf from the source tree and has no ``csc`` script, so the
docs tasks call the CLI this way.
"""

from chisurf.core.cli import cli

cli()
