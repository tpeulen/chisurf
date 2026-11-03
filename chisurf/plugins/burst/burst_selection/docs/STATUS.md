# Burst Selection — Current entry points

The production Burst Analysis hub constructs the native emtk/AutoForm selection
app with `gui.native.create_app`; there is no other GUI.

`tests/test_emtk_native_model.py` runs the model on two real SPC files and
recounts every burst row (photons per detector, duration) from the raw
photons; `tests/test_demo.py` checks the search finds the demo's planted
bursts. Read the actual public exports and manifest for callable
contracts. The June implementation checkpoints are preserved in the history
archive rather than presented as current status.

Current workflow: [Photon burst identification](../../../../../docs/guides/13_burst_identification.md).
Maintained knowledge: [Burst tools](../../../../../okf/plugins/burst.md).
