# Burst Selection — Current entry points

The production Burst Analysis hub constructs the native emtk/AutoForm selection
app with `gui.native.create_app`. The Qt `BurstSelectionTool` (`gui/tool.py`), its
`wizard.py` launcher and the hosted emtk shell over it are retired (see the
"Burst plugins whose Qt tool is still shipped" entry of
`okf/references/known-issues.md`); the Qt-run numbers are kept in
`tests/qt_reference.json`. The older fallback, private assets and runtime chooser are
retired.

The legacy cleanup's 26 scoped runtime checks pass. A real two-file SPC
comparison preserves all ten numeric columns, settings and 72 controls:
198 bursts (71/127), 353909 photons and 45868 selected photons. This is a
bounded retirement check; other writer, RPC and GUI acceptance has its own
maintained evidence. Read the actual public exports and manifest for callable
contracts. The June implementation checkpoints are preserved in the history
archive rather than presented as current status.

Current workflow: [Photon burst identification](../../../../../docs/guides/13_burst_identification.md).
Maintained knowledge: [Burst tools](../../../../../okf/plugins/burst.md).
Original dated plans/checklists: [retained history archive](../../../../../okf/validation/release-readiness-w1/burst-selection-retirement/package-notes-history.zip).
