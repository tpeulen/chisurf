(plugin-psf_calculator)=
# PSF Calculator

Compute and view a 3-D point-spread function: scalar, Airy or vectorial Richards-Wolf, with the input polarization at the objective pupil.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `psf_calculator` |
| Menu path | Microscopy → **PSF Calculator** |
| Categories | Microscopy, Optics |
| Version | 1.0.0 |
| Surfaces | gui |
| State namespace | `psf_calculator` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Objective

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| NA | `na` | float |  | 0.05 … 1.7 (step 0.05) | Numerical aperture. Above about 1.0 the scalar models stop being trustworthy and the vectorial one should be used. |
| n (immersion) | `n_immersion` | float |  | 1.0 … 2.0 (step 0.01) | Refractive index of the immersion medium: 1.518 oil, 1.33 water, 1.0 air. The NA cannot exceed it. |
| λ (nm) | `wavelength_nm` | float |  | 300.0 … 1200.0 (step 10.0) | Emission or excitation wavelength in nanometres. |

### Model

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Optical model | `model` | choice |  | choices: vectorial, airy, gaussian | Vectorial accounts for the longitudinal field and the input polarization; Airy is the exact scalar focal-plane result and is repeated unchanged along z, so it shows no defocus; Gaussian adds a paraxial axial envelope but has no wings. |

### Polarization

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Polarization | `polarization` | choice |  | choices: circular, x, y, linear, left, unpolarized, radial, azimuthal | State of the light entering the pupil. Linear elongates the focus along its own axis; radial focuses tighter; azimuthal is a doughnut with a zero on axis. |
| Angle (°) | `angle_deg` | float |  | 0.0 … 180.0 (step 5.0) | Orientation of the linear state, measured from the x axis. Used only when Polarization is 'Linear at angle'. |

### Sampling

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Lateral size (px) | `nxy` | int |  | 16 … 192 (step 8) | Pixels per lateral side of the volume. |
| Planes | `nz` | int |  | 3 … 81 (step 2) | Number of axial planes, centred on focus. |
| Pixel (nm) | `pixel_size_nm` | float |  | 1.0 … 200.0 (step 5.0) | Lateral sampling in nanometres. |
| z step (nm) | `z_step_nm` | float |  | 5.0 … 1000.0 (step 25.0) | Axial spacing between planes. |
| Quality | `quality` | choice |  | choices: preview, full | Preview uses a coarser aperture quadrature. The vectorial model is expensive, so live editing stays on preview and the full calculation is worth waiting for only once the parameters are settled. |

### Display

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Threshold | `threshold` | float |  | 0.0 … 0.9 (step 0.01) | Hide voxels below this fraction of the peak. A diffraction-limited focus is mostly empty space and renders as fog without it. |
| Gamma | `gamma` | float |  | 0.1 … 3.0 (step 0.1) | Shapes the opacity ramp. Below 1 lifts the faint wings into view. |
| Colormap | `colormap` | choice |  | choices: magma, inferno, viridis, gray | Colormap of the rendered volume. |
| Polarization vectors | `show_polarization` | bool |  |  | Draw the pupil polarization state as strokes on a ring above the focus. Vectorial model only, since the scalar models ignore polarization. |

## Source

- Plugin package: `chisurf/plugins/calculator/psf_calculator/`
- Manifest: {src}`chisurf/plugins/calculator/psf_calculator/manifest.json`
- UI spec: {src}`chisurf/plugins/calculator/psf_calculator/psf_calculator.view.json`
