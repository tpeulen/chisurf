"""Parse model for stopped-flow traces."""
from __future__ import annotations

from chisurf.core.models.parse import parse as parse_module


class ParseStoppedFlowModel(parse_module.ParseModel):
    """A stopped-flow trace described by a user-supplied equation.

    The hand-written widget pointed at ``settings/stopped_flow.models.json``, a
    file that is not in the tree, and passed it as a ``str`` where a
    ``pathlib.Path`` was expected -- so this model raised ``AttributeError`` on
    construction and could never be opened at all. ``models.yaml`` beside this
    module is the catalogue it never had; it holds the standard relaxation forms
    and is extended by editing the file.
    """

    name = "Parse stopped-flow"
    catalogue_file = "models.yaml"
    view_spec_file = "parse.view.json"
