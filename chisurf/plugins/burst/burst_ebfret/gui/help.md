# ebFRET — hidden Markov analysis of binned smFRET traces

This window is a port of the **ebFRET** GUI (van de Meent, Bronson, Wiggins &
Gonzalez): the same panels, menus, dialogs and analysis. It learns the states
of a set of donor/acceptor time series — how many there are, their FRET
levels, their noise and their dwell times — with a hidden Markov model whose
**prior is shared by every trace** and learned from all of them (empirical
Bayes). New here? Press **Guide**; it loads a simulated four-state dataset and
walks you through one analysis.

## The window

**Time Series** (top) shows the current series: the signal
`E = acceptor / (donor + acceptor)` above, donor (green) and acceptor (red)
below. Once analysed, the **Viterbi path** — the most likely state per frame —
is drawn over both, coloured by state. The dashed stretches are frames outside
the crop range.

**Select Series** picks the series (edit box or slider). **Crop** sets the
frames that enter the analysis (*Min*, *Max*); **Exclude** leaves the series
out entirely. Both reset that series' result.

**Ensemble** (middle) describes all included series for the model selected in
**Select States**:

- *Histograms* — the observed signal, split by Viterbi state;
- *Centers* — the distribution of state means `μ`;
- *Noise* — the distribution of state noise `σ`;
- *Dwell Time* — the distribution of state dwell times `τ` (log axis).

Dashed curves are the **prior**, solid curves the average **posterior** of the
series. *View → Normalize by Occupancy* scales each state's curve by how much
it is occupied; *View* also hides the Viterbi paths, the prior or the
posterior.

## Running an analysis

1. **File → Load** — pick the file type in the dialog's filter list: a saved
   session (`.mat`), raw donor/acceptor `.dat` (stacked `[series donor
   acceptor]` or unstacked columns, first row of each series a label),
   SF-Tracer `.tsv`, or an SMD (`.mat`, `.json`, `.json.gz`). Loading while
   data is loaded asks whether to *Keep* it (the new files become a new group)
   or *Replace* it.
2. **Analysis → Remove Photo-bleaching** crops every series where it bleaches
   (*Manual* thresholds on donor, acceptor, their sum or FRET, with padding; or
   *Auto* detection). **Analysis → Clip Outliers** clips the signal to a range
   and excludes series with too many outliers. Both are non-destructive and
   offer to re-guess the priors afterwards.
3. **Analysis → Set Priors** sets the priors by hand: expected state centers
   (spread evenly from *Min* to *Max Center*), noise and dwell time, and how
   strongly the prior holds each (*Prior Strength*, in observations). A low
   *Center* strength leaves superfluous states empty.
4. **States → Min, Max** — the numbers of states to analyse.
5. **Analysis** — *States* **All** analyses every number from *Min* to *Max*,
   **Current** only the one in *Select States*. *Restarts* is the number of
   re-initialisations per series per iteration (0: continue from the last
   result; 1: plus an uninformative start; more: random starts drawn from the
   prior). *Precision* is the convergence threshold — `1e-3` for exploring,
   `1e-6` for results you publish. **Run** starts, **Stop** stops, **Reset**
   discards the result and re-guesses the prior.

The run happens on the backend; the window keeps redrawing while it works and
jumps to the series and state count being analysed.

## Choosing the number of states

Compare the **lower bound** of the analyses (File → Export → Analysis Summary,
*Lower_Bound*). It penalises superfluous states, so the model with the largest
bound is preferred — when two differ by less than the precision, run longer.

## Saving and exporting

- **File → Save** — the whole session (data, crops, exclusions, priors,
  posteriors, Viterbi paths) as a `.mat` ebFRET itself reads.
- **File → Export → Analysis Summary** — a `.csv` per number of states and per
  group: series statistics, lower bound, state occupancy and observation
  statistics, and the prior's centers, precisions, dwell times and transition
  matrix.
- **Export → Traces** — a `.dat`/`.mat` table of the chosen channels (donor,
  acceptor, FRET, Viterbi state, Viterbi mean) per included series.
- **Export → Single-molecule Dataset (SMD)** — the chosen model and traces as
  `.mat`, `.json` or `.json.gz`.

## Further reading

- Theory: [ebFRET — variational-Bayes HMM of binned traces](docs/concepts/ebfret.md)
- Workflow: [Hidden Markov analysis of binned FRET traces](docs/guides/20_ebfret_binned_hmm.md)
- van de Meent et al., *Biophys. J.* 2014 (ebFRET):
  [10.1016/j.bpj.2013.12.055](https://doi.org/10.1016/j.bpj.2013.12.055)
- Bronson et al., *Biophys. J.* 2009 (vbFRET):
  [10.1016/j.bpj.2009.09.031](https://doi.org/10.1016/j.bpj.2009.09.031)
