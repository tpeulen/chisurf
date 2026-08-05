(plugin-img_coloc)=
# Colocalization

Two-channel colocalization (Pearson, Manders, Costes, Li ICQ) on TIFF stacks and photon-stream images, with an interactive intensity scatter gate.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_coloc` |
| Menu path | Imaging → **Colocalization** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui |
| State namespace | `img_coloc` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Setup | `setup_name` | setup_selector |  |  | Detector setup whose named windows (green, red, …) become the pickable image channels — the same vocabulary as the rest of ChiSurf. Setups are created in the Detector Def tool. Leave it empty to use the raw detector channels stored in the file; it does not apply to camera images. |
| Image | `filename` | data_source |  |  | The image to analyse: a TIFF stack (or any other readable image), or a photon-stream file (PTU/HT3/…) reconstructed into a confocal-scan image — one channel per detector window of the setup above, or per raw routing channel when no setup is picked. Browse the disk, load a dataset registered in the database, or drop a file here. |
| Channel A | `channel_a` | choice |  | choices: `channel_names` | First channel of the pair. With a detector setup this lists its named windows (green, red, …); otherwise the channels found in the file (available after the first run). |
| Channel B | `channel_b` | choice |  | choices: `channel_names` | Second channel of the pair. Manders M1 answers 'how much of A sits with B', M2 the mirror question, so the A/B order matters for those two coefficients. |
| Frame | `frame` | int |  | -1 … 100000 (step 1) | Which frame of the stack to analyse. -1 (default) sums every frame, which maximises the signal-to-noise of the coefficients; pick a single frame to follow a time series. |
| Axis order | `channel_axis_mode` | choice |  | choices: auto, first axis | Only for images whose axes are unlabelled. 'auto' treats a short leading axis (≤ 4 planes) as the channels and anything longer as frames; 'first axis' forces the leading axis to be the channels. TIFFs written with ImageJ/OME metadata are read exactly as labelled and ignore this. |

### Background / thresholds

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Auto background | `auto_background` | bool |  |  | Estimate each channel's background as a low intensity quantile of that channel and subtract it. Background offsets bias Pearson and, much more strongly, Manders' overlap coefficient, so subtracting them is not optional for comparable numbers. |
| Quantile | `background_quantile` | float |  | 0.0 … 0.5 (step 0.01) | Quantile used by the automatic background estimate. 0.05 (the lower 5 %) is the conventional choice: low enough to sit in dark/out-of-cell pixels, high enough not to be a single outlier. |
| Background A | `background_a` | float |  |  | Intensity subtracted from channel A before anything else. Filled in by the estimate; type your own value (e.g. a measured dark level) to override it. |
| Background B | `background_b` | float |  |  | Intensity subtracted from channel B before anything else. |
| Costes thresholds | `auto_threshold` | bool |  |  | Derive both thresholds from the data instead of by hand: an orthogonal regression of the channel pair is walked downwards until the pixels below it are no longer positively correlated. Everything below that point is indistinguishable from uncorrelated background. Hand-picked thresholds are the single largest source of irreproducible colocalization numbers. |
| Threshold A | `threshold_a` | float |  |  | A pixel counts as 'channel A present' above this background-subtracted intensity. Filled in by the Costes search when that is enabled. |
| Threshold B | `threshold_b` | float |  |  | A pixel counts as 'channel B present' above this background-subtracted intensity. |

### Scatter gate

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Gate active | `gate_enabled` | bool |  |  | Restrict the gated coefficients to a rectangle in the intensity-vs-intensity plane. Drag the blue rectangle on the 'Intensity scatter' tab to set it, or type the bounds below; the gated pixels are highlighted in the 'Colocalized pixels' map. |
| A min | `gate_a_min` | float |  |  | Lower channel-A intensity of the gate rectangle. |
| A max | `gate_a_max` | float |  |  | Upper channel-A intensity of the gate rectangle. |
| B min | `gate_b_min` | float |  |  | Lower channel-B intensity of the gate rectangle. |
| B max | `gate_b_max` | float |  |  | Upper channel-B intensity of the gate rectangle. |
| Gate regions | `gates` | region_list |  |  | Every gate on the intensity scatter in one list: the typed box, a painted population, an ellipse or polygon drawn on the plane. Tick to include, ~ for everything outside, and pick how they combine — a cloud AND a threshold, not one overriding the other. |

### Region of interest

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Brush (px) | `brush_size` | int |  | 1 … 64 | Edge length of the square brush used to paint the region of interest on the Channel A map. Painting restricts every coefficient — thresholds, the null model and the profiles — to that region, the way a hand-drawn cell outline should. |

### Objects (punctate signal)

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Object analysis | `object_analysis` | bool |  |  | Segment both channels into discrete particles and count how many coincide. This is the right question for puncta (vesicles, foci): on sparse spots the intensity coefficients are dominated by the empty background between them and report almost nothing. |
| Tolerance (px) | `object_distance` | float |  | 0.0 … 100.0 (step 0.5) | Centre-to-centre distance within which two objects count as coincident. Set it to the optical resolution — nothing can be localised better than the PSF, so demanding an identical centroid would only measure noise. |
| Min size (px) | `object_min_size` | int |  | 1 … 10000 | Objects smaller than this are discarded as noise. |
| Smoothing (σ px) | `object_smoothing` | float |  | 0.0 … 10.0 (step 0.5) | Gaussian smoothing applied before segmenting; use it when shot noise fragments single objects into several. |
| Split touching objects | `object_split` | bool |  |  | Separate objects that touch, with a distance-transform watershed. Helps dense puncta; over-segments irregular shapes. |

### Significance / profile

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Costes randomization test | `costes_test` | bool |  |  | Scramble one channel in PSF-sized blocks many times and compare the measured correlation against that null distribution. It answers the question the coefficients cannot: is this correlation more than what random co-occurrence of two dense stainings would give? Colocalization is conventionally called significant at p > 0.95. Costs one correlation per randomization. |
| Block (px) | `costes_block` | int |  | 1 … 64 | Edge length of the scrambled blocks. Use the PSF width in pixels: smaller blocks destroy the image's own texture and make almost anything look significant, larger ones throw away resolution. |
| Randomizations | `costes_randomizations` | int |  | 10 … 10000 | Size of the null distribution. 100–200 is enough for a p-value quoted to two decimals; more only sharpens the tail. |
| Seed | `costes_seed` | int |  | 0 … 1000000 | Seed of the random generator, so the same image and settings always give the same p-value (a reported number stays reproducible). |
| van Steensel shift (px) | `ccf_max_shift` | int |  | 0 … 200 | Largest horizontal shift of the cross-correlation profile; 0 disables it. The profile peaks at 0 for true colocalization and away from 0 when the channels are misregistered — the standard check for chromatic aberration before trusting any coefficient. |
| Profile bins | `profile_bins` | int |  | 4 … 200 | Number of intensity bins in the 'PCC vs intensity' profiles. Fewer bins average more pixels per point (smaller error bars), more bins resolve where in the brightness range the correlation changes. |
| Histogram bins | `bins` | int |  | 8 … 1024 | Bins per axis of the intensity scatter (joint histogram). More bins resolve fine structure in the cloud; fewer make sparse images look continuous. |
| Log histogram | `log_histogram` | bool |  |  | Show the intensity scatter on a logarithmic count scale, so the sparse bright tail stays visible next to the dense background cloud. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_coloc/`
- Manifest: `chisurf/plugins/microscopy/img_coloc/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_coloc/gui/coloc.view.json`
