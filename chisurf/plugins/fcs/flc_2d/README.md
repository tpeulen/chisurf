# 2D-FLCS

2D fluorescence lifetime correlation spectroscopy resolves lifetime species from
TTTR photon streams and estimates exchange dynamics from lifetime-filtered
species correlations.

The method is due to Ishii & Tahara (J. Phys. Chem. B 117(39), 11414–11422 and
11423–11432, 2013; doi:10.1021/jp406861u, doi:10.1021/jp406864e); the original
MATLAB implementation this plugin ports (`TK_Create2DFDC_04.m` and the fit
family, by T. Kondo, Schlau-Cohen lab, MIT) was written for the single-molecule
application in Kondo et al. (Proc. Natl. Acad. Sci. USA 116(23), 11247–11252,
2019; doi:10.1073/pnas.1821207116). The photon-pair kernels now live in tttrlib
(`fdc_scan_log` et al.), verified against the original `.m` tick for tick.

The plugin is now split into the migrated plugin layout:

- `api.py` - Qt-free analysis API for notebooks, tests, CLI, and services.
- `core.py` and `fit/` - numerical 2D-FDC, ILT, MEM, kinetics, and simulator code.
- `backend/services.py` - JSON-RPC handlers under the `flc2d.*` namespace.
- `gui/client.py` - typed client used by the GUI instead of direct backend calls.
- `gui/tool.py` - stateful docked widget shell with persistent dock layout.
- `cli/` - command-line entrypoint declared in `manifest.json`.

## GUI

Open the tool from FCS Tools. The top toolbar uses short labels:

- `Open` loads TTTR photon streams.
- `IRF` loads an instrument-response TTTR file.
- `Sim` creates a synthetic two-state exchange stream.
- `Run` performs the active analysis.
- `?` opens modal help with workflow, RPC, and CLI reference.

The central area is a ChiSurf `DockArea`. Right-click the dock area or dock tabs
to hide/show docks. Dock arrangement and window geometry are persisted through
`QSettings`.

Longer field descriptions are kept as tooltips/descriptions in
`gui/flc_2d.view.json`; visible labels are intentionally short.

## RPC

The manifest registers `chisurf.plugins.fcs.flc_2d.backend.services:register_services`.
Available methods:

- `flc2d.load_tttr`
- `flc2d.correlate`
- `flc2d.fit`
- `flc2d.lifetime_spectrum`
- `flc2d.lifetime_lcurve`
- `flc2d.contract.describe`

All RPC payloads are plain JSON-compatible dictionaries/lists. NumPy arrays are
converted at the service boundary.

## CLI

The manifest exposes:

```bash
flc-2d --help
flc-2d metadata measurement.ptu
flc-2d lifetime measurement.ptu --method nnls --components 40
```

The CLI uses the same Qt-free API as the backend.

## API Example

```python
from chisurf.plugins.fcs.flc_2d import api

data = api.load_tttr("measurement.ptu")

spec = api.lifetime_spectrum(
    data.micro_times,
    data.n_microtime_channels,
    data.micro_time_resolution_ns,
)
print(spec.peak_lifetimes(2))

fdc = api.two_d_fdc(
    data.macro_times,
    data.micro_times,
    dT=1000,
    ddT=2000,
    tMin=1,
    tMax=data.n_microtime_channels,
)
result = api.two_d_spectrum(
    fdc["mat_lin"],
    (fdc["mat_lin_t"] + 1) * data.micro_time_resolution_ns,
)
```

## Validation

The `test/` package validates the numerical core on synthetic and reference
data where available. Slow reference-data checks are marked with
`@pytest.mark.slow`.
