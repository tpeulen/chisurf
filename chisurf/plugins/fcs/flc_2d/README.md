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
flc-2d reproduce fitted_params.json -o model.json
flc-2d rise-search-2d mol_*.ptu --irf irf.npz --dt 100 --ddt 10 -o scan.npz
flc-2d average-2d mol_*.ptu --irf irf.npz --dt 100 --dt 1000 --ddt 10 --center 298 -o avg.npz
flc-2d bootstrap mol_*.ptu --dt 100 --dt 1000 --dt 100000 --ddt 10 \
    --tmin 125 --tmax 3050 --replicates 200 -o fdc_bootstrap.npz
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

## Single-molecule data sets and error bars

A single-molecule measurement is one photon stream per molecule, and a photon
pair must never span two of them. `api.separate_data_2d_fdc` builds the matrices
of the original data-preparation driver per molecule — each lag, the longest lag
as the uncorrelated background (`cor_*` = lag − background), the shortest lag
`ddT/2` (`short_*`) and the zero-lag decay (`fdc_1d_*`), linear and log axes,
symmetrized — and `.total()` sums them. `api.bootstrap_2d_fdc` redraws which
molecules are summed (each at most `group_factor` times, until
`photon_factor` × the photons are reached) and returns every element's mean and
standard deviation over the replicates:

```python
molecules = [(d.macro_times, d.micro_times) for d in map(api.load_tttr, files)]
sep = api.separate_data_2d_fdc(molecules, [100, 1000, 100_000], 10, tMin=125, tMax=3050)
boot = api.bootstrap_2d_fdc(sep, 200, seed=1)
cor, err = sep.total()["cor_log"], boot.std["cor_log"]
```

## The reference's 2D-MEM workflow

The original code fits log-binned matrices with a basis **summed over each bin**
(`api.exp_curves`; a basis sampled at the bin position misfits log columns by a
median 43%, so `two_d_spectrum` refuses a log axis without `basis=`), a
maximum-entropy objective minimized along a regulator ramp, and an IRF placed by a
"rise point" that is scanned rather than known. The three drivers:

```python
mats = sep.total()                                    # from separate_data_2d_fdc
kw = dict(irf=irf, xdata_ns=irf_t, estimates=[0, 1, 1, 0.3, 1, 3, 0.3],
          t_min_ns=0.5, t_max_ns=12.2, t_step_ns=0.004, lint_bin_factor=4, logt_imax=100)
scan = api.search_irf_rise_2d(mats, center=310, n_points=20, **kw)   # chi2 per rise point
avg = api.average_2d_mem(mats, center=scan.best, n_points=5, **kw)   # A, G, maps, models
```

`flc-2d rise-search-2d` and `flc-2d average-2d` run the same from TTTR files.

## Checking a fit

`api.reproduce_2d_fdc(A, G, time_axis_ns, tau_grid=...)` rebuilds the 2D-FLC map
`A G Aᵀ` and the 2D-FDC it predicts (a `G` stack is the global multi-lag form);
`api.reproduce_1d_fdc` does the decay. With the measured matrix, the entropy prior
and the regulator they also return the original code's chi-square, entropy and
MEM estimator `Q`. `api.reproduce_fit(result, time_axis_ns)` rebuilds any of this
plugin's fit results on another axis — the check the original minimizers finish
with (fit on the linear axis, reproduce on the log one).

## Validation

The `test/` package validates the numerical core on simulated streams whose
answer is known: the data-driven checks (`@pytest.mark.slow`) simulate the
reference data set of the original MATLAB code (τ = 1 / 3 ns, rates
`[[0, 30], [10, 0]]` s⁻¹, its IRF) from a fixed seed. The reproduction and the
per-molecule/bootstrap driver are pinned against the original MATLAB run in
Octave (`test/data/flc_2d/matlab_reproduct.npz`, `matlab_bootstrap.npz`).
The code and its technical note (P. Manna, *2D-Fluorescence Lifetime Correlation
Code: Mathematical Basis, Tutorial and Technical Notes*) are at
https://github.com/PremashisManna/2D-FLC-code.
