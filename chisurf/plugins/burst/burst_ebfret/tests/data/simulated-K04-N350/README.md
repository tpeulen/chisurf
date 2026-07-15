# ebFRET reference fixture — simulated-K04-N350

Vendored from the ebFRET distribution (`datasets/simulated-K04-N350-*`,
https://github.com/ebfret/ebfret-gui), used as the recovery test fixture for the
binned-trajectory HMM port.

- `raw-stacked.dat` — whitespace-delimited ASCII, columns `[trace_id, donor,
  acceptor]`; 350 simulated two-colour smFRET traces (39,595 frames) grouped by
  `trace_id`. FRET efficiency is `acceptor / (donor + acceptor)`.
- `reference.json` — ebFRET's own converged results for this dataset (K-sweep
  state means, from the shipped `*-ebfret-session.mat`), used as the assertion
  target.

Ground truth: K = 4 states. See the plugin README for the correspondence
between this port's proximity-ratio means and ebFRET's background-subtracted
signal means.
