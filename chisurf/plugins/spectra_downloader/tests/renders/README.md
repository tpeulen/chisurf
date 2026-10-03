# Spectra native verification

The `qt/spectra_downloader.png` reference is a genuine Qt QWidget capture from historical source revision `d26edb928123ad482a29e841e9d48ed6fbc4e155`, generated before replacing the factory. Its capture metadata identifies the source and rejects embedded EMTK children.

The native screenshots are real EMTK controls rendered through `NativeHost` and the Metal GPU using the offscreen rendercanvas backend. Reproduce them with:

```
python -m chisurf.plugins.spectra_downloader.tests.capture_native
```

Both 1000×700 and 640×700 captures contain five staging components, properties and real synthetic spectral arrays. The narrow browser has a separate scrolled screenshot showing the entire spectral curve. Scratch databases are temporary and never imported into a user's MMFDB by this script.

The earlier overview-based 91 acceptance was rejected because it did not establish matched Browse parity. `visual-verdict-browse-rejected.json` records that correction. The final verdict is **90**, comparing `qt/spectra-browse-populated.png` against `native-normal-browse.png` using the same five rows and selected Alexa Fluor 488 curve. The corrected native table separates checkbox selection from IDs and uses explicit column widths; all fixture data values render without truncation at both sizes. This is a functional and visual comparison, not a pixel-equivalence claim.

Reproduce the matched genuine Qt Browse reference with:

```
python -m chisurf.plugins.spectra_downloader.tests.capture_qt_browse
```

That plugin-local wrapper adds fixture population and Browse selection to the shared helper's in-memory historical capture workflow. It does not edit the shared helper or use the current native implementation as a Qt reference.

Verification: 49 plugin tests pass, one existing test is skipped; native registry construction and drawing block all Qt bindings, `qtpy`, `sip`, and `pyqtgraph`. Tests cover exact provenance tokens, category/name filters, spectra decoding, multiselection, import IDs, subprocess commands/output/concurrency, administrator authorization, cached server sessions, local replacement backup, approval flags, six locales, real native clicks and credentials excluded from exported state. Ruff and syntax compilation pass.

Network scrapers and a live ZMQ server were not exercised; scraper parsing remains covered by the existing offline tests. The current help document and guided-tour prose remain English. Legacy explicitly imported Qt browser/dialog modules remain for compatibility, while default/manifest factories and standalone launch are native.
