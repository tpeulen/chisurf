# Spectra Downloader

Builds a local **staging** database of optical-component spectra —
fluorophores, filters, dichroics, detectors, light sources — from public
sources, lets you inspect what came in, and pushes it into the MMFDB, where
the Förster-radius calculator and the light-path simulator read it.

It computes nothing itself. R₀ from a donor–acceptor pair is computed by the
**calc R0** button of the TCSPC FRET models, from the spectra in the MMFDB.

## Panels

| panel | what it does |
|---|---|
| **Overview** | counts in the staging DB, by category and by source |
| **Browse** | filter by name, source, category; one component's properties, raw metadata and spectra; **Push selected** / **Push all** |
| **Download** | run one scraper into the staging DB and follow its log |
| **Add to MMFDB** | choose a local MMFDB file or a server, authenticate, push the staging set |

## Sources, and what their data may be used for

| source | carries | terms |
|---|---|---|
| FPbase | fluorescent proteins, some dyes, detectors | data free of copyright; attribute the original authors |
| Chroma | filters, dichroics, dye excitation/emission | no data licence published; vendor data |
| Thorlabs | filters, one APD (via the `thor2` R package) | no licence declared |
| PhotochemCAD | 331 compounds with ε and quantum yield | © Lindsey, Taniguchi, Du; no licence declared |
| ATTO-TEC | ATTO dyes, recovered from the Internet Archive | vendor data |

Only FPbase states an open data policy. Treat the rest as reference data for
your own analysis: the staging DB is git-ignored and must not be redistributed.

## Before trusting an R₀ from it

- Spectra are **peak-normalised**. R₀ needs the acceptor's ε_max and the
  donor's quantum yield as well; the calculator fills them from the database
  when the component carries them (ATTO, PhotochemCAD, FPbase) and leaves the
  previous value otherwise (Chroma).
- The calculator offers only acceptors with an **absorption** spectrum. Chroma
  dyes (Alexa Fluor, Cy3, Cy5, …) carry excitation spectra only, so they are
  not offered as acceptors.
- Everything scraped is `unverified` until approved in the MMFDB admin.

## Further reading

- [Spectra, overlap integrals and R₀](docs/guides/83_spectra_and_r0.md)
- [Förster resonance energy transfer](docs/concepts/fret.md)
- [Energy transfer (fundamentals)](docs/fundamentals/energy_transfer.md)
