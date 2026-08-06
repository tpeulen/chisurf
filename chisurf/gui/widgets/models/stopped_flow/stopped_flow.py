"""Deprecated module: both stopped-flow editors are described by JSON.

`ParseStoppedFlowModel` carries ``parse.view.json`` and `ReactionModel` carries
``reaction.view.json``; AutoForm renders both.

Neither hand-written predecessor could ever be opened. ``ParseStoppedFlowWidget``
passed a ``str`` where a ``pathlib.Path`` was expected and pointed at a catalogue
file that is not in the tree, so constructing it raised ``AttributeError``.
``ReactionWidget`` was *abstract* — it never implemented ``update_model`` — so
selecting it in the model menu raised ``TypeError``. Functional compatibility with
what ``reaction.ui`` offered was therefore the bar for the port, not file
compatibility.

The names stay importable because user copies of ``experiment_configs.yaml``
*replace* the bundled model list and pickled projects pin class paths, so a path
that no longer resolves drops the entry from the model menu without saying so.
"""
from __future__ import annotations

from chisurf.core.models.stopped_flow.parse import ParseStoppedFlowModel
from chisurf.core.models.stopped_flow.reaction import ReactionModel

#: Deprecated aliases of the pure compute models.
ParseStoppedFlowWidget = ParseStoppedFlowModel
ReactionWidget = ReactionModel
