"""Record the HMM lattice parity fixture, and check it against hmmlearn.

``chisurf.core.math.hmm`` compiles its forward/backward/Viterbi recursions with
numba. That is being retired: tttrlib PRD-035 replaces the kernels with a
compiled generic log-domain lattice, after which the numba versions are deleted.
A port needs a reference that outlives them, so this writes one to
``test/data/numba_parity/hmm_lattice.npz`` — inputs and expected outputs for ten
cases, recorded from the numba kernels **while they still exist**.

A fixture recorded from our own code only proves the port matches *us*, which is
worth much less than it looks: building the first version of this file is what
uncovered a live bug (an impossible sequence turned the shared ``xi`` accumulator
into ``nan``), and a port checked against that fixture would have been required
to reproduce it. So the second half of this script cross-checks every case
against **hmmlearn**, the implementation ChiSurf's replaced, which is
independent and widely used.

hmmlearn is *not* a ChiSurf dependency and must not become one — it is not in
the manifests and nothing shipped imports it. This is a developer tool, run by
hand; the committed artifact is the ``.npz``. That is deliberate: an
``importorskip`` in the test suite would turn into a skip on any machine without
hmmlearn, and a skip reads like a pass.

Run with hmmlearn importable::

    python -m build_tools.dev_utils.hmm_lattice_fixture            # check only
    python -m build_tools.dev_utils.hmm_lattice_fixture --write    # re-record

Two hmmlearn API traps, both of which produce confident nonsense rather than an
error, and both of which cost a run here:

* ``_hmmc.forward_log`` / ``backward_log`` / ``viterbi`` take ``startprob`` and
  ``transmat`` as **plain probabilities**; only the frame probabilities are in
  log space. Passing logs gives ``log`` of a negative number, so every
  log-likelihood comes back ``nan``.
* ``_hmmc.viterbi`` returns ``(logprob, states)``, not ``(states, logprob)``.
"""

from __future__ import annotations

import argparse
import pathlib

import numpy as np

from chisurf.core.math import hmm as H

FIXTURE = (
    pathlib.Path(__file__).resolve().parents[2]
    / "test" / "data" / "numba_parity" / "hmm_lattice.npz"
)

#: Cross-check tolerances. forward/backward are asserted **exact** because they
#: measured exact: ChiSurf and hmmlearn evaluate the same recursion in the same
#: order. Posteriors and xi differ only by accumulation order -- ChiSurf fuses
#: the backward sweep with the posterior and transition-count accumulation,
#: where hmmlearn makes three passes.
_EXACT = 0.0
_TOL_POSTERIORS = 1e-12
_TOL_XI = 1e-10


def _case_inputs():
    """Yield ``(name, log_startprob, log_transmat, log_frameprob)`` per case."""

    def rand(n_samples, n_components, seed):
        rng = np.random.default_rng(seed)
        transmat = rng.dirichlet(np.ones(n_components) * 8, size=n_components)
        return (
            np.log(np.full(n_components, 1.0 / n_components)),
            np.log(transmat),
            np.log(rng.uniform(1e-6, 1.0, (n_samples, n_components))),
        )

    for n_samples, n_components, seed in ((5, 2, 1), (37, 3, 2), (200, 4, 3), (1000, 6, 4)):
        yield (f"random_T{n_samples}_K{n_components}", *rand(n_samples, n_components, seed))

    # No transition exists, so xi_sum must stay all zero.
    yield ("single_sample", *rand(1, 3, 5))

    # No state explains this frame: the whole sequence is impossible.
    lsp, ltm, lfp = rand(40, 3, 6)
    lfp = lfp.copy()
    lfp[17, :] = -np.inf
    yield ("all_inf_frame", lsp, ltm, lfp)

    # A structurally dead state: a whole -inf column.
    lsp, ltm, lfp = rand(40, 3, 7)
    lfp = lfp.copy()
    lfp[:, 2] = -np.inf
    yield ("dead_state_column", lsp, ltm, lfp)

    # log(0) in the transition matrix.
    lsp, ltm, lfp = rand(40, 3, 8)
    ltm = ltm.copy()
    ltm[0, 2] = -np.inf
    ltm[1, 0] = -np.inf
    yield ("forbidden_transitions", lsp, ltm, lfp)

    # A state unreachable at t = 0.
    lsp, ltm, lfp = rand(40, 3, 9)
    lsp = lsp.copy()
    lsp[1] = -np.inf
    yield ("zero_startprob", lsp, ltm, lfp)

    # All of them at once -- the combination is what breaks ports.
    lsp, ltm, lfp = rand(60, 4, 10)
    lsp, ltm, lfp = lsp.copy(), ltm.copy(), lfp.copy()
    lsp[3] = -np.inf
    ltm[2, 1] = -np.inf
    lfp[11, :] = -np.inf
    lfp[:, 3] = -np.inf
    yield ("combined_degeneracies", lsp, ltm, lfp)


def _run_chisurf(log_startprob, log_transmat, log_frameprob):
    """Return ChiSurf's lattice outputs for one case, as a dict."""
    n_samples, n_components = log_frameprob.shape
    fwd = np.empty((n_samples, n_components))
    log_prob = H._forward_log(log_startprob, log_transmat, log_frameprob, fwd)
    bwd = np.empty((n_samples, n_components))
    H._backward_log(log_transmat, log_frameprob, bwd)
    posteriors = np.empty((n_samples, n_components))
    xi_sum = np.zeros((n_components, n_components))
    H._backward_posteriors_xi(log_transmat, log_frameprob, fwd, log_prob, posteriors, xi_sum)
    states = np.empty(n_samples, dtype=np.int64)
    viterbi_logprob = H._viterbi(log_startprob, log_transmat, log_frameprob, states)
    return {
        "fwd": fwd, "bwd": bwd, "log_prob": np.float64(log_prob),
        "posteriors": posteriors, "xi_sum": xi_sum, "states": states,
        "viterbi_logprob": np.float64(viterbi_logprob),
    }


def _run_hmmlearn(log_startprob, log_transmat, log_frameprob):
    """Return hmmlearn's lattice outputs for one case, in ChiSurf's conventions."""
    from hmmlearn import _hmmc

    n_samples, n_components = log_frameprob.shape
    # Plain probabilities, not logs -- see the module docstring. exp(-inf) = 0
    # round-trips the degenerate cases exactly.
    startprob, transmat = np.exp(log_startprob), np.exp(log_transmat)
    log_prob, fwd = _hmmc.forward_log(startprob, transmat, log_frameprob)
    bwd = _hmmc.backward_log(startprob, transmat, log_frameprob)

    log_gamma = fwd + bwd
    with np.errstate(under="ignore", invalid="ignore"):
        shifted = np.exp(log_gamma - log_gamma.max(axis=1, keepdims=True))
        total = shifted.sum(axis=1, keepdims=True)
        posteriors = np.where(total > 0, shifted / total, 1.0 / n_components)
    posteriors = np.where(np.isfinite(posteriors), posteriors, 1.0 / n_components)

    if n_samples > 1 and np.isfinite(log_prob):
        with np.errstate(under="ignore"):
            xi_sum = np.exp(_hmmc.compute_log_xi_sum(fwd, transmat, bwd, log_frameprob))
        xi_sum = np.where(np.isfinite(xi_sum), xi_sum, 0.0)
    else:
        xi_sum = np.zeros((n_components, n_components))

    viterbi_logprob, states = _hmmc.viterbi(startprob, transmat, log_frameprob)
    return {
        "fwd": fwd, "bwd": bwd, "log_prob": np.float64(log_prob),
        "posteriors": posteriors, "xi_sum": xi_sum, "states": states,
        "viterbi_logprob": np.float64(viterbi_logprob),
    }


def _max_abs_diff(a, b):
    """Largest absolute difference, counting ``-inf == -inf`` as agreement."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    both_neg_inf = np.isneginf(a) & np.isneginf(b)
    # `-inf - -inf` is nan and numpy evaluates the subtraction before the
    # `where` selects it away, so the warning has to be suppressed rather than
    # avoided.
    with np.errstate(invalid="ignore"):
        difference = np.where(both_neg_inf, 0.0, np.abs(a - b))
    return float(np.max(difference)) if a.size else 0.0


def check() -> int:
    """Compare every case against hmmlearn. Returns a process exit code."""
    failures = []
    header = f"{'case':<24s} {'logL':>8s} {'fwd':>10s} {'bwd':>10s} {'post':>10s} {'xi':>10s} {'path':>12s}"
    print(header)
    print("-" * len(header))
    for name, lsp, ltm, lfp in _case_inputs():
        ours, ref = _run_chisurf(lsp, ltm, lfp), _run_hmmlearn(lsp, ltm, lfp)
        impossible = np.isneginf(ours["log_prob"])
        d = {k: _max_abs_diff(ours[k], ref[k]) for k in ("fwd", "bwd", "posteriors", "xi_sum")}
        log_ok = (impossible and np.isneginf(ref["log_prob"])) or \
            abs(ours["log_prob"] - ref["log_prob"]) < 1e-9
        path_diff = int((ours["states"] != ref["states"]).sum())

        # Where no path is possible at all, every candidate scores -inf and the
        # arg-max is arbitrary; both implementations say "impossible" via the
        # log-probability, which is the part that carries meaning.
        path_note = "n/a (-inf)" if impossible else f"{path_diff} differ"
        print(f"{name:<24s} {'same' if log_ok else 'DIFF':>8s} {d['fwd']:10.2e} "
              f"{d['bwd']:10.2e} {d['posteriors']:10.2e} {d['xi_sum']:10.2e} {path_note:>12s}")

        if not log_ok:
            failures.append(f"{name}: log-likelihood {ours['log_prob']} vs {ref['log_prob']}")
        if d["fwd"] > _EXACT or d["bwd"] > _EXACT:
            failures.append(f"{name}: lattice not exact (fwd {d['fwd']:.2e}, bwd {d['bwd']:.2e})")
        if d["posteriors"] > _TOL_POSTERIORS:
            failures.append(f"{name}: posteriors {d['posteriors']:.2e} > {_TOL_POSTERIORS:.0e}")
        if d["xi_sum"] > _TOL_XI:
            failures.append(f"{name}: xi_sum {d['xi_sum']:.2e} > {_TOL_XI:.0e}")
        if not impossible and path_diff:
            failures.append(f"{name}: {path_diff} Viterbi states differ on a possible path")

    print()
    if failures:
        print("DISAGREEMENTS:")
        for f in failures:
            print("  -", f)
        return 1
    print("hmmlearn agrees on every case: forward and backward lattices exact, "
          "posteriors and xi within accumulation-order noise, Viterbi identical "
          "wherever a path exists.")
    return 0


def write() -> None:
    """Re-record the fixture from the numba kernels."""
    arrays, names = {}, []
    for i, (name, lsp, ltm, lfp) in enumerate(_case_inputs()):
        out = _run_chisurf(lsp, ltm, lfp)
        arrays.update({f"log_startprob_{i}": lsp, f"log_transmat_{i}": ltm,
                       f"log_frameprob_{i}": lfp})
        arrays.update({f"{k}_{i}": v for k, v in out.items()})
        names.append(name)
        assert not np.isnan(out["posteriors"]).any(), f"{name}: nan posteriors"
        assert not np.isnan(out["xi_sum"]).any(), f"{name}: nan xi_sum"
    # Fixed-width unicode, never dtype=object: an object array forces every
    # reader to pass allow_pickle=True, which is a bad habit to push onto a test
    # suite for the sake of a label.
    np.savez_compressed(FIXTURE, n_cases=np.int64(len(names)),
                        names=np.array(names, dtype="<U32"), **arrays)
    print(f"wrote {FIXTURE} ({FIXTURE.stat().st_size} bytes, {len(names)} cases)")


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--write", action="store_true",
                        help="re-record the fixture from the numba kernels")
    args = parser.parse_args()
    if args.write:
        write()
    return check()


if __name__ == "__main__":
    raise SystemExit(main())
