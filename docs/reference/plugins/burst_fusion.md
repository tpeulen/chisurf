(plugin-burst_fusion)=
# Burst Fusion

Fuse bursts the same molecule produced, using the recurrence same-molecule probability, into a new burst folder.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `burst_fusion` |
| Menu path | Spectroscopy → Single-Molecule → **Burst Fusion** |
| Categories | Spectroscopy, Single-Molecule |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `burst_fusion` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Fusion

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Burst folder | `folder` | directory |  |  | The burst-analysis folder to fuse — the output of burst selection. Nothing in it is modified; the fused bursts go to a new folder beside it. |
| Fuse if P(same) ≥ | `threshold` | float |  | 0.0 … 1.0 (step 0.05) | Two consecutive bursts are fused while the probability that they are the same molecule is at least this. 1 fuses nothing; low values eventually merge different molecules. |
| Never bridge gaps > | `max_gap_ms` | float |  | 0.0 … 10000.0 (step 1.0) | Ceiling on the gap fusion may bridge, whatever the probability says (0 removes it). A fused burst is one interval on disk, so bridging a gap puts its background photons inside the burst. |
| Max fragments per burst | `max_group` | int |  | 0 … 1000 (step 1) | Largest number of original bursts one fused burst may contain (0 = no limit). Caps runaway chains in dense data. |

### P(same molecule) estimate

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Shortest lag | `tau_min_ms` | float |  | 0.001 … 1000.0 (step 0.05) | Shortest inter-burst lag the correlation is evaluated at. |
| Longest lag | `tau_max_ms` | float |  | 1.0 … 100000.0 (step 100.0) | Longest lag evaluated. A threshold the curve never falls below inside this range leaves the window unresolved. |
| Lag bins | `n_bins` | int |  | 5 … 500 (step 5) | Logarithmic lag bins between the shortest and longest lag. |
| Min pairs per bin | `min_pairs` | int |  | 0 … 1000 (step 1) | Burst pairs a lag bin needs before it may end the fusion window. Stops a hole in sparse statistics reading as a confident 'different molecule'. |
| Pool measurements | `pool_measurements` | bool |  |  | Estimate one curve from every measurement of the folder (lags always stay inside a measurement). A single short file rarely has enough burst pairs on its own. |
| Record grouping in the source folder | `write_source_companion` | bool |  |  | Write an fg4 companion beside the original bursts giving each one its fused-burst number, so the grouping can be inspected or gated on there. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `burst_fusion.jobs.analyze` | yes | Estimate the same-molecule probability of a burst folder and report what a threshold would fuse. |
| `burst_fusion.jobs.fuse` | yes | Write the fused bursts as a new burst-analysis folder. |
| `burst_fusion.workflow.prepare` | no | Resolve the burst folder and detector definition from a burst workflow context. |

## Source

- Plugin package: `chisurf/plugins/burst/burst_fusion/`
- Manifest: `chisurf/plugins/burst/burst_fusion/manifest.json`
- UI spec: `chisurf/plugins/burst/burst_fusion/gui/fusion.view.json`
