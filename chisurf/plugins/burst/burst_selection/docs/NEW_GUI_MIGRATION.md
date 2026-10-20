# Burst Selection — Maintained GUI direction

The native Burst Analysis hub uses `gui.native.create_app`; the public tool and
wizard retain the implemented modern Qt tool. The previous fallback and its
runtime switch are retired. Use archived before control inventories for
migration review instead of attempting to restore a removed implementation.

New surfaces are emtk/AutoForm. Keep analysis in the existing API/backend and
preserve scientific settings and output contracts. Changes to framework,
writer or RPC architecture belong in the maintained knowledge record and need
their own measured acceptance. The original phased migration plan is retained
in the history archive.

Current workflow: [Photon burst identification](../../../../../docs/guides/13_burst_identification.md).
Maintained knowledge: [Burst tools](../../../../../okf/plugins/burst.md).
