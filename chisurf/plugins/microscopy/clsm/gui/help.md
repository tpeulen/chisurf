# CLSM Pixel Select

Load photon data (or an imaging HDF5 with its source reference), choose acquisition markers and channels, then build a CLSM image. Add an intensity, mean microtime or intensity-weighted microtime representation. Sum, average or browse single frames.

Paint with the left mouse button to select or erase pixels. Middle drag pans; scrolling zooms. Live update computes a histogram of selected photons. Time is calibrated from the source microtime resolution. Capture masks as named regions, draw rectangles/ellipses/polygons, and combine enabled/inverted regions.

Compute a decay before exporting it to CSV or adding it to ChiSurf experimental data. Image TIFF and region JSON/mask exports preserve physical values and pixel geometry.
