# CLSM Generator: a scan whose answer is known

**Tool:** *Imaging -> CLSM Generator* (`clsm_generator`). It simulates the photon stream of a confocal lifetime scan from maps
you provide: a brightness image and one **fluorescence lifetime map per detector**. Because you chose the lifetimes, the
result is a test for the analysis tools ([pixel MLE](24_scan_images.md), [CLSM-Draw](24_scan_images.md), the
[Spot Finder](84_spot_finder.md)): they must give back what you put in.

```{figure} figures/98_clsm_generator.png
:width: 100%

Two detectors (lifetimes 2 and 3 ns with gradients) and a brightness image of two blobs: the reconstructed intensity of the
simulated photons (129,201), in the Maps window.
```

## 1. Inputs
**Intensity image** loads the relative brightness (TIFF, NPY or NPZ). **Add lifetime maps** adds the lifetime map (in ns) of
each detector in detector order; **Database lifetime maps** picks registered datasets; **Remove selected** and **Clear maps**
edit the list (dropping files on the window does the same: the first drop is the intensity image, later ones lifetime maps).
All maps must have the same shape.

## 2. Simulation
The folded **Simulation** panel sets the physical pixel size, the dwell time, the number of micro-time channels and their width,
the peak brightness (photons of the brightest pixel), the Gaussian IRF (centre, sigma) and the number of lifetime and intensity
quantization levels. **Generate** runs the simulation in the background (**Cancel generation** discards its result); the
status line reports the photon count.

## 3. Look and save
The **Map** choice in the Maps window browses the input brightness, each detector's lifetime and the reconstructed intensity;
the colormap, gamma and levels are the image canvas's. **Save photon stream** writes the photons as `.pto` (with the embedded
intensity), `.npz`, `.ptu`, `.spc` or `.ht3` (the **Output format** choice) and the reconstructed intensity as a TIFF; **Save /
Load settings** keep the inputs and parameters as JSON. **Guide** walks through the whole sequence, **Help** is the reference.
