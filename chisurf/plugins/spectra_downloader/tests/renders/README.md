# Spectra native renders

The screenshots here are real EMTK controls rendered through `NativeHost` and the Metal GPU using the offscreen
rendercanvas backend. Reproduce them with:

```
python -m chisurf.plugins.spectra_downloader.tests.capture_native
```

Both 1000×700 and 640×700 captures contain five staging components, properties and synthetic spectral arrays. The
narrow browser has a separate scrolled screenshot showing the entire spectral curve. Scratch databases are temporary
and never imported into a user's MMFDB by this script.
