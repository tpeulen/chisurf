(plugin-img_tracking)=
# Particle Tracking

Single-particle tracking: detect diffraction-limited particles in every frame, link them into trajectories by exact assignment with gap closing, and fit the diffusion coefficient and anomalous exponent from the mean squared displacement.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_tracking` |
| Menu path | Microscopy → Imaging → **Particle Tracking** |
| Categories | Microscopy, Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `img_tracking` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Movie

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Image stack | `filename` | path |  |  | TIFF-like image stack or photon-stream file. Tracking runs on one channel at a time, because combining channels first would blur the very spots it has to localise. |
| Channel | `channel` | int |  | 0 … 63 | Which channel to track in. |
| Max frames | `max_frames` | int |  | 0 … 1000000 | Track at most this many frames; 0 uses all of them. Lower it for a first look at a long acquisition. |

### Simulate instead

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Simulate | `use_simulation` | bool |  |  | Track a simulated movie instead of the loaded file. |
| True D [px²/frame] | `sim_diffusion` | float |  | 1e-06 … 10000.0 | Diffusion coefficient of the simulated particles, in pixels squared per frame. |
| Particles | `sim_n_particles` | int |  | 1 … 2000 | How many particles. Crowding is what breaks tracking: when particles come within the linking distance of one another the assignment is genuinely ambiguous and identities get swapped. |
| Frames | `sim_n_frames` | int |  | 2 … 5000 | Number of simulated frames. |
| Field [px] | `sim_size` | int |  | 32 … 2048 | Width and height of the simulated frame. Memory grows as frames × size²; a very large request is refused rather than allowed to exhaust the machine. |
| Spot amplitude | `sim_amplitude` | float |  | 1.0 … 100000.0 | Peak counts of a particle above background. |
| Background | `sim_background` | float |  | 0.0 … 100000.0 | Background level; shot noise is applied on top. |
| Seed | `sim_seed` | int |  | 0 … 1000000 | Random seed, so a simulation can be reproduced. |

### 1. Detect

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Detector | `method` | choice |  | choices: `method_options` | Wavelet is the multiscale-product detector: it suppresses the background and rejects single hot pixels without any intensity threshold, and holds up at low signal. Quantile thresholds the raw frame and is cheaper, but needs bright, well-separated spots on a flat background. |
| Threshold [σ] | `threshold` | float |  | 0.5 … 50.0 | Detection threshold in robust standard deviations of the wavelet response. Check the detections per frame in the report against what you expect before lowering it — noise admitted here becomes short spurious tracks that bias everything downstream. |
| Min area [px] | `min_area` | int |  | 1 … 1000 | Smallest connected bright region that can be a particle. A diffraction-limited spot is always wider than one pixel; a dead or hot camera pixel is exactly one. |
| Min separation [px] | `min_separation` | float |  | 0.0 … 200.0 | Two particles closer than this in the same frame are collapsed to the brighter one. Spots nearer than the point-spread function cannot be told apart anyway, and admitting both invents a particle for the linker to mis-assign. |

### 2. Link

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Max step [px] | `max_distance` | float |  | 0.1 … 1000.0 | Largest displacement that may be called the same particle between consecutive frames. This is the whole safety margin — set it from the physics (a Brownian particle moves about sqrt(4·D·dt) per frame), never from what makes the tracks look longest. |
| Max gap [frames] | `max_frame_gap` | int |  | 0 … 100 | How many missing frames a track may bridge; 0 disables gap closing. Every closed gap asserts that nothing else could have been there, so keep it small and check what changing it does to the answer. |

### 3. Transport

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Pixel size [µm] | `pixel_size` | float |  | 1e-05 … 1000.0 | Physical pixel size. Leave at 1 to report D in pixels squared per frame. |
| Frame interval [s] | `frame_interval` | float |  | 1e-06 … 10000.0 | Time between frames. Leave at 1 to report D per frame. |
| Min track length | `min_track_length` | int |  | 3 … 10000 | Shortest track admitted to the fit. Short tracks are not merely noisy but biased: a particle is likelier to be found twice in a row if it happened to stay put, so the shortest tracks over-represent the slowest motion. |
| Fit anomalous exponent | `fit_alpha` | bool |  |  | Fit α as well as D instead of holding it at 1. Do this only when the question actually is whether the motion is anomalous: α and D are nearly degenerate, and fitting both roughly quadruples the spread of D. |
| Bootstrap resamples | `n_bootstrap` | int |  | 0 … 5000 | Resamples of the track set behind the error bars. The fit covariance cannot be used here — MSD lags share displacements and are strongly correlated, so its error bar covers the truth about one run in five. |
| Tracks drawn | `max_drawn_tracks` | int |  | 1 … 2000 | Upper limit of trajectories drawn in the plot, longest first. The fit always uses all of them. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `img_tracking.jobs.track` | yes | Detect, link and fit transport for an image stack. |
| `img_tracking.jobs.simulate` | yes | Track a simulated movie of Brownian particles with a known D. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_tracking/`
- Manifest: `chisurf/plugins/microscopy/img_tracking/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_tracking/gui/tracking.view.json`
