# Intensity trace

A TTTR file binned into counts per time window, one trace per detector (from the detector setup) or per routing
channel, with each trace's count histogram beside it, and their sum.

## Steps

1. **Load TTTR** (or drop a file; **Example** loads a simulated molecule switching between two FRET states).
   **Setup** chooses which routing channels and micro-time ranges make each detector; *Routing channels* bins every
   routing channel on its own. **Detector Selection** ticks the traces to bin.
2. **Time Window**: the bin width. Short bins resolve fast switching but carry few photons (shot noise); long bins
   average short visits away. **Histogram Settings** (bins, min/max counts) shape the histograms only.
3. **HMM** tab: **Compute HMM** fits a hidden Markov model with **HMM Components** states to the binned counts (the
   states are numbered dimmest first) and writes, beside the file in `<file>_HMM#<n>_<ms>ms/`:
   `bst/` the burst IDs of each state (first/last photon of every visit), `traces/` the traces with the state, the state
   and FRET trajectories, `hist/` the count and FRET histograms. **BIC Elbow** fits 1 to 15 states: the number where the
   curve stops falling is what the data support.
4. **Results**: **HMM Matrix** (transition probability per bin, from → to), **Dwell Times** (how long each visit lasts,
   with a single-exponential fit; a visit shorter than a few bins is not resolved and lengthens the fitted time),
   **FRET Distributions** (first detector over the sum, per state; needs two detectors).

**Save Traces** writes the traces (and the state) as CSV.

## Further reading

- [Intensity traces and file tools](docs/guides/74_intensity_traces_and_file_tools.md)
- [HMM of binned traces](docs/guides/92_hmm_binned_traces.md)
