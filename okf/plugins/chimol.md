---
type: Plugin Concept
title: Molecular viewer — standalone engine and host continuation
description: Current molecular-viewer ownership, host entrypoints and verification front, folded from historical root handovers.
resource: modules/chimol/chimol/
tags: [plugins, structure, viewer, webgpu, portability]
timestamp: '2026-10-07T00:00:00Z'
---

# Where to pick this up

1. Audit the current host surfaces, not the old embedded package path. The
   [ChiSurf manifest](../../chisurf/plugins/chimol/manifest.json) selects
   `chimol.hosts.qt:MolViewPluginWindow` or `chisurf.plugins.chimol.app:make_app`;
   the standalone source is under `modules/chimol/chimol/`. Compare the native,
   Qt and browser paths with the same loaded 148L scene, selection, labels,
   groups and trajectory state before declaring host parity.
2. Serve a browser repro through `python -m chimol.hosts.web.serve`, whose
   [bundle](../../modules/chimol/chimol/hosts/web/serve.py) delegates hosting and
   input forwarding to emtk. Verify molecular pixels and real input handling,
   not merely HTTP 200 or a nonempty canvas. The old session's remote-browser
   connection failure does not establish a current tool limitation; use a
   browser reachable from the actual serving machine.
3. Use the [surface continuation](../subsystems/molecular-surface.md) for mesh
   versus splat quality and mixed-depth validation. Re-measure the selected
   compute route before optimizing neighbour counting: the current
   [router](../../modules/chimol/chimol/render/compute.py) has a general 20,000
   work-item floor and a separate 512-item shading floor, so the historical
   1,363-atom CPU/GPU comparison is not a blanket GPU-performance claim.

# Ownership and preserved design decisions

The standalone viewer owns scene/camera/commands and shared WGSL rendering;
ChiSurf supplies plugin discovery and a host. Native, Qt and browser adapters
must not create separate renderers or command sets. The current browser bundle
excludes desktop hosts. Historical measurements, one-engine rationale and
rejected alternatives remain in [the browser record](chimol-web.md), with the
[relocation boundary](chimol-relocation.md) and
[viewport toolkit work](chimol-emtk.md) as related records.

`HANDOVER_CHIMOL.md` is the provenance of this fold. Its original embedded
`chisurf.plugins.chimol.chimol.*`, `renderer/`, `app/` and `web/` paths now map to
standalone `chimol/core/viewer/`, `chimol/render/`, `chimol/hosts/qt/` and
`chimol/hosts/web/`. The old proposal to delete `app/sequence_dock.py` is not a
live work item: that file is absent from the current Qt host. Historical HOSTS
counts and completed phase claims are not current acceptance evidence.

Retain these diagnostic distinctions: logical/CSS and device coordinates meet
at the painter scale; hit testing needs a freshly rendered layout after a
resize; font advance is not glyph-ink extent; a toolkit-blocking import finder
must implement `find_spec`; and a Qt application reference must stay alive
while widgets do. Add the package's parent to PYTHONPATH, not the `chimol/`
package directory, whose `cmd` module can shadow the standard library.

The rejected second JavaScript renderer, linear font-metric scaling and sRGB
canvas reconfiguration remain rejected for the reasons in the browser record.
The old GPU-binding-stub explanation is historical; confirm current adapters
before treating it as a dependency constraint.
