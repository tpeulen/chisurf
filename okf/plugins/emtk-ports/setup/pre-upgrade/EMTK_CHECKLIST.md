# Unified settings native port plan

- Preserve all 15 discoverable original settings destinations; resolve native entrypoints lazily from each manifest.
- Keep the old Qt workspace accessible through lazy package exports.
- Provide working native configuration-file editing routes for panels whose dedicated factories are still pending, and identify those limitations explicitly.
- Validate structured settings before atomic writes, preserve string/list types, support load/reload/save/save-as and dirty state.
- Retain child state across navigation and forward native input; all controls require tooltips and help/guide.
- Test every route under Qt blockers, settings persistence/invalid input and fresh native rendering; compare genuine Qt reference.

## Verification and remaining parity

- 15 original destinations render through native manifests or working configuration-file routes with strict Qt blockers. Child state, Help/Guide and file chooser render tested.
- Typed hierarchical settings, full-path search, source editing, reload/validate/save/save-as, atomic validation protection, string/list type preservation and active settings refresh tested.
- Native factory routes currently exist for AI Settings, Plugins, Channel Definition and Plugin Check.
- Pending rich panels: Boarding, Acquisition, Styles, Plots, Models, User Editor, Updates, Packages, FCS Definitions and TTTR LUT Tools. Generic file editing does not implement their specialized operations. These require independent native factory ports; the hub will adopt manifest factories lazily.
- Native screenshot `/private/tmp/chisurf-native-imaging/setup-900.png`; actual Qt reference `okf/plugins/emtk-references/core__setup.png`. Visual verdict91 covers navigation/editor only.
