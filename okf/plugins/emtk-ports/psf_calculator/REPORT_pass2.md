# emtk upgrade report (pass 2) - psf_calculator
Commits `2fe5e8801` baseline, `b2803b5e8` app + tests, `e52649139` tooltip-test fix + evidence. Tests: 64 passed, 1 xfailed (tour Next over the 3-D view). compare exit 0, 93 controls, 0 untooltipped.
NOT comparable: the Qt tool cannot be built here (no 3-D volume renderer in the emtk chiplot backend); the baseline stubs `VolumeView` and runs the real panels, export path and model. Equal to Qt: computed volume (`np.array_equal`), summary, colormap/threshold/gamma/polarization handed to the renderer, .npy/.tif exports, spec ranges/choices. Not compared: the rendered 3-D image.
Fixed: drag sliders -> typed spin fields with Qt ranges, extra Compute button + redraw loop -> debounced auto-compute, stretched slice (equal aspect), slice choice always "XY", 13-entry legend, status line shifting fields, Quality radios cut (now a combo), polarization/angle greyed when meaningless, Export as two buttons, settings round trip.
Tests: `test_emtk_psf_clicks.py`, `test_emtk_psf_parity.py`. Volume is a sampled voxel cloud (max 6000 voxels), not ray-cast.

## Review (reviewer, 2026-10-02)
Tests re-run by the reviewer with the counts above; populated screenshots read. **Accepted.** Real-input click tests, layout checks at 1200x800 / 800x600 and two deliberate breakages per plugin are the agent's claims, backed by the committed test files named below.
