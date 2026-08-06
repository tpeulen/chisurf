(plugin-hmm)=
# Hidden Markov model

Gaussian hidden Markov model for binned time traces: fits states and transitions by Baum-Welch, decodes the state path, and reports emissions, dwell times, transition rates and an AIC/BIC state-count scan. The shared HMM seam of ChiSurf — the same analysis is reachable from the GUI, the CLI and over RPC, and other plugins call its Qt-free core instead of fitting their own.

## Identity

| Field | Value |
| --- | --- |
| Plugin id | `hmm` |
| Menu path | Analysis → Kinetics → **Hidden Markov model** |
| Categories | Analysis, Kinetics |
| Version | 0.1.0 |
| Surfaces | cli, gui, services |
| State namespace | `hmm` |

## Parameters

Editable parameters exposed by the plugin's declarative (AutoForm) interface, grouped by panel.

### Model

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Traces | `sel_files` | path_list |  |  | Binned trace files: rows are time bins, columns are detection channels. Several files are fitted jointly as separate sequences. |
| States | `n_states` | int |  | 1 … 32 | Number of hidden states. Use the state scan below rather than guessing — the likelihood always improves with more states, the information criteria do not. |
| Covariance | `covariance_type` | choice |  | choices: full, diag, spherical, tied | Shape of the emission covariance: full = an unrestricted matrix per state; diag = one variance per channel; spherical = one variance per state; tied = one matrix shared by all states. Fewer parameters are more stable on short traces. |
| Bin width (s) | `time_step` | float |  | 0.0 … 1000.0 | Duration of one time bin. Dwell times and transition rates are reported in these units; leave at 1 to report them in bins. |

### Fitting

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| Max EM maps | `n_iter` | int |  | 1 … 100000 | Upper bound on Baum-Welch maps. With acceleration, one SQUAREM cycle spends three. |
| Tolerance | `tol` | float |  | 0.0 … 1000.0 | Stop once the log-likelihood gain per iteration falls below this. |
| Accelerate (SQUAREM) | `accelerate` | bool |  |  | Extrapolate the EM fixed-point iteration (Varadhan & Roland scheme S3). Same optimum, far fewer maps when the states overlap. |
| Decoder | `decode` | choice |  | choices: viterbi, map | viterbi = the single most probable state path (self-consistent, what dwell times need); map = the most probable state in each bin taken independently. |
| Seed | `random_state` | int |  | 0 … 1000000 | Seed of the k-means initialisation. A fixed seed makes the fit reproducible. |

### State scan

| Parameter | Attribute | Type | Default | Range / options | Meaning |
| --- | --- | --- | --- | --- | --- |
| From | `min_states` | int |  | 1 … 32 | Smallest state count to score. |
| To | `max_states` | int |  | 1 … 32 | Largest state count to score. |

## JSON-RPC methods

| Method | Long-running | Summary |
| --- | --- | --- |
| `hmm.fit` | no | Fit a Gaussian hidden Markov model to binned trace(s) and return states, dwell times and transitions. |
| `hmm.scan` | no | Fit a range of state counts and score each by AIC and BIC. |

## Theory and workflow

- **Theory** — [Hidden Markov models of binned traces](/concepts/hidden_markov_models.md)
- **Workflow** — [Hidden Markov models of binned traces](/guides/54_hidden_markov_models.md)

## Source

- Plugin package: `chisurf/plugins/core/hmm/`
- Manifest: {src}`chisurf/plugins/core/hmm/manifest.json`
- UI spec: {src}`chisurf/plugins/core/hmm/gui/hmm.view.json`
