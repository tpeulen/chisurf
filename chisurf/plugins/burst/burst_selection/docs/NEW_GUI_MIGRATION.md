# Burst Selection — Maintained GUI direction

The Burst Analysis hub and the standalone tool both use `gui.native.create_app`
(emtk); there is no other GUI.

New surfaces are emtk/AutoForm. Keep analysis in the existing API/backend and
preserve scientific settings and output contracts. Changes to framework,
writer or RPC architecture belong in the maintained knowledge record and need
their own measured acceptance. The original phased migration plan is retained
in the history archive.

Current workflow: [Photon burst identification](../../../../../docs/guides/13_burst_identification.md).
Maintained knowledge: [Burst tools](../../../../../okf/plugins/burst.md).
