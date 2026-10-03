# CLSM Generator

Load a relative **intensity image** and one **lifetime map in ns for each detector**.
TIFF, NPY and NPZ maps are supported. All maps must have matching 2-D shapes;
stack input follows the existing simulator's collapse rule. Detector order is the
order shown in the lifetime list. Remove or clear maps to change the routing order.

Expand **Simulation** to edit physical pixel size, dwell time, TAC channel count
and width, Gaussian IRF centre and width, peak brightness, and intensity/lifetime
quantization levels. The excitation period is channel count × channel width.
These are the same settings and simulation engine as the original Qt tool.

**Generate** runs off the UI thread. Browse input brightness, detector lifetimes
and the reconstructed intensity with the Map selector. Colormap, levels and gamma
affect the preview only. Zoom and pan the image; reset axes to fit the full raster.

**Cancel generation** discards the running result and retains any previous result.
The native simulator cannot be interrupted mid-call, so the worker finishes safely
before another generation can start. Cancellation does not save anything.

**Save photon stream** offers PTO, NPZ, PTU, SPC and HT3. PTO keeps the generated
measurement and embedded intensity in one container. NPZ contains macro-times,
micro-times, routing channels and event types. Other formats use tttrlib's writers.
An intensity TIFF is also written alongside the photon output. Check the status
after saving; unsupported TTTR writers report their error there.

**Save settings** stores paths, detector order, numerical settings and display
preferences in JSON. **Load settings** restores the map inputs from those paths;
it does not serialize photon results. Drag files onto an empty tool to load its
intensity; subsequent drops add detector lifetime maps.
