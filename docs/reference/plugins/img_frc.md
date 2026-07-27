(plugin-img_frc)=
# FRC Resolution

Measure the resolution an image actually achieved by Fourier ring correlation — of a TIFF stack or a photon stream — and read it against the 1/7, ½-bit or 2σ criterion.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `img_frc` |
| Menu path | Imaging → **FRC Resolution** |
| Categories | Imaging |
| Version | 1.0.0 |
| Surfaces | cli, gui, services |
| State namespace | `img_frc` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Settings

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Image | `filename` | data_source |  |  | The acquisition to measure: a TIFF stack, or a photon-stream file (PTU/HT3/…) reconstructed into a confocal-scan image. A single-frame image cannot be split into halves by frame — use a channel split or a second file. |
| Split into halves by | `split` | choice |  | choices: even_odd, halves, channels, two_files | How the one measurement is cut into two statistically independent halves. This is the choice the whole method rests on: correlating an image with itself, or with a filtered copy of itself, measures the filter and not the resolution. Even/odd is the default and is insensitive to slow drift because both halves span the whole acquisition; first/second half is for detectors whose consecutive frames are not independent; two channels correlates two detectors that saw the same object; two files correlates two repeated acquisitions. |
| Channel | `channel` | choice |  | choices: `channel_names` | Channel to measure. Pick the brightest, most structured one — a flat channel has no fine detail to correlate and reports the field of view as its resolution. |
| Second channel | `channel_2` | choice |  | choices: `channel_names` | Only for a two-channel split: the detector the first is correlated against. Both must have seen the same structure; two spectrally distinct labels on different structures correlate nowhere. |
| Second file | `second_filename` | data_source |  |  | Only for a two-file split: a second acquisition of the same field of view. It must be independent of the first — the same file twice returns a correlation of 1 at every frequency and no resolution at all. |
| Pixel size [nm] | `pixel_size_nm` | float |  | 0.0 … 100000.0 | Physical pixel size, which converts the answer from pixels into nanometres. Zero leaves it in pixels — still a resolution, just not one to quote in a figure. It scales the result linearly, so an uncertain pixel size is an uncertain resolution. |
| Criterion | `criterion` | choice |  | choices: fixed_1/7, half_bit, two_sigma | The threshold the correlation has to fall through. Fixed 1/7 (Nieuwenhuizen 2013) is the usual choice for fluorescence images and the only one independent of how the rings were binned. ½-bit (van Heel & Schatz 2005) is the frequency at which the accumulated information suffices to interpret the structure. 2σ is twice the correlation expected from pure noise. They disagree by tens of per cent on the same data, so the criterion belongs beside any number you quote. |

### Estimator

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| TIFF axis order | `axis_order` | choice |  | choices: auto, frames, channels | How to read the leading axis of a 3-D TIFF. 'Auto' takes a short axis (up to four planes) as channels and a longer one as frames, which is right for an RGB image and wrong for a four-frame time series — and a frame split then finds a single frame. Set it explicitly when the file is short and the guess went the wrong way. Photon streams are unaffected: their frames and detector channels are declared in the file. |
| Ring width [cyc/px] | `bin_width` | float |  | 0.0 … 0.5 | Width of the Fourier rings. Zero means one Fourier pixel of the longer axis, the finest binning the sampling supports. Wider rings average more pixels and give a smoother curve at the cost of frequency resolution. |
| Smoothing [rings] | `smooth` | int |  | 1 … 51 | Rings averaged before the threshold crossing is read. The raw curve is noisy ring to ring, and an unsmoothed crossing can land early on a single dip. One disables it. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `img_frc.resolution.compute` | yes | Measure image resolution by Fourier ring correlation. |
| `img_frc.criteria.list` | no | List the threshold criteria and the available splits. |
| `img_frc.contract.describe` | no | Return the RPC contract descriptor. |

## Source

- Plugin package: `chisurf/plugins/microscopy/img_frc/`
- Manifest: `chisurf/plugins/microscopy/img_frc/manifest.json`
- UI spec: `chisurf/plugins/microscopy/img_frc/gui/frc.view.json`
