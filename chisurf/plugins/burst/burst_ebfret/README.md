# burst_ebfret — ebFRET, ported

A plain port of [ebFRET](https://github.com/ebfret/ebfret-gui) (van de Meent,
Bronson, Wiggins & Gonzalez, *Biophys. J.* 2014) into ChiSurf: the MATLAB GUI
and its analysis. Empirical-Bayes hidden Markov analysis of **binned donor/acceptor
smFRET time series** (TIRF-style intensity-vs-time traces) — the binned-data
complement to the photon-by-photon `burst_h2mm` plugin.

## What is ported

| MATLAB | here |
| --- | --- |
| `ebfret.ui.MainWindow` — panels, menus, controls, callbacks | `gui/app.py` (emtk window), `gui/main.view.json` (the declared controls), `gui/controls.py`, `core/session.py` (the callbacks, without the window) |
| `+ui/+dialog/*`, `questdlg`/`inputdlg`/`msgbox`/`uigetfile` | `gui/*.view.json` + `gui/dialogs.py` |
| `@MainWindow/refresh.m`, `+plot/*` | `core/plots.py`, `core/views.py` |
| `+analysis/+hmm/*`, `+analysis/+dist/*`, `photobleach_index`, `x_lim` | `core/hmm.py`, `core/dist.py` |
| `run_ebayes.m` / `run_vbayes.m` | `core/ebayes.py` (loop), `backend/services.py` (runs it in a backend thread) |
| `+io/*`, session `.mat`, exports | `io.py` |

The window runs as a ChiSurf tool (`gui/tool.py`, Qt only as the host) with a
**Load demo** action (`demo.py`: a simulated four-state dataset), a guided tour
(`gui/guide.json`) and help (`gui/help.md`). The GUI holds no data: every action
is an RPC call (`burst_ebfret.session.*`) on a backend session.

Deliberate differences from the MATLAB program are listed in the OKF concept
`okf/plugins/burst-ebfret.md`; the main ones: the dark emtk theme, a tables pair
(View → Series List / States Table) the MATLAB window does not have, SMD ids
that are MD5 hashes of the values (MATLAB's DataHash cannot be reproduced), and
a NumPy forward-backward instead of the MEX kernels.

Not ported, because the GUI never reaches it: the prior-mixture
(`+hmm/ebayes.m`, which calls functions that no longer exist upstream), the
soft/hard k-means restarts, the jitter filter, the `+batch` scripts.

## Validation

- `tests/test_octave_ab.py` — the numerical core against ebFRET run under GNU
  Octave on recorded fixtures (`tests/octave/make_fixtures.m`): e-step,
  forward-backward, m-step, KL, VBEM lower-bound traces, Viterbi paths, priors,
  h-steps and the report agree to ≲1e-11; three empirical-Bayes iterations to
  1.5e-14 in the lower bound.
- `tests/test_io.py` — the file formats against Octave and against the files
  MATLAB wrote for `simulated-K04-N350` (traces export byte-identical; SMD
  identical but for ids and the version string; the MATLAB session loads and
  re-saves unchanged).
- `tests/test_session.py`, `tests/test_services.py`, `tests/test_gui.py`,
  `tests/test_tool_qt.py` — the workflow, the RPC layer, the emtk window driven
  by clicks, and the Qt host with its tour anchors.

## Usage

GUI: **Spectroscopy → Single-Molecule → ebFRET**, then **Guide**.

Python:

```python
from chisurf.plugins.burst.burst_ebfret.core.session import Session, RAW

session = Session(seed=1)
session.load_data(["stacked.dat"], RAW)
for event in session.run_ebayes(should_stop=lambda: False):
    pass
session.export_summary("summary.csv")
```

CLI: `ebfret compute stacked.dat --min-states 2 --max-states 4`.

## Licence of the ported code

ebFRET is MIT-licensed: Copyright (c) 2013 Jan-Willem van de Meent, Sakellarios
Zairis. Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"), to
deal in the Software without restriction, including without limitation the
rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is furnished
to do so, subject to the following conditions: The above copyright notice and
this permission notice shall be included in all copies or substantial portions
of the Software. THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO
EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
