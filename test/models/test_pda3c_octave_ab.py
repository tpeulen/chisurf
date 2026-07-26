"""Execute the incumbent's compiled PDA3c kernel and compare it to ChiSurf.

The sibling ``test_pda3c_pam_ab.py`` transcribes the incumbent's *expressions*;
this one runs its actual **C code**. The kernel is a self-contained MEX function
with a plain numeric signature, so unlike the surrounding MATLAB — which is
inline in a GUI reading a global struct — it can be compiled with Octave's
``mkoctfile`` and driven directly.

That closes the last gap a transcription leaves open: a mistake shared between
the source and its transcription would survive the other test, and would not
survive this one.

Skipped unless Octave and the reference checkout are both present, so it is a
bonus check on a developer machine rather than a dependency of the suite. The
build is cached for the session; it takes a few seconds.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import numpy as np
import pytest

pytest.importorskip("scipy.io")

#: Reference source tree; absent in a normal checkout.
PAM_SRC = pathlib.Path("junk/PAM/functions/PDA3c/C Files/src")

#: Sources the kernel needs, per the reference's own build notes.
SOURCES = [
    "eval_prob_3c_bg_lib.c",
    "randist/binomial.c",
    "randist/multinomial.c",
    "randist/specfunc/gamma.c",
    "sys/numcores.c",
    "sys/memalloc.c",
]

DRIVER = r"""
% Poisson pmf inline, so the statistics package is not required.
pois = @(k, lam) exp(-lam + k.*log(lam) - gammaln(k+1));
load('ab_input.mat');

NBGbb = double(nbg(1)); NBGbg = double(nbg(2)); NBGbr = double(nbg(3));
NBGgg = double(nbg(4)); NBGgr = double(nbg(5));

BGbb = pois((0:NBGbb)', bg_blue(1));
BGbg = pois((0:NBGbg)', bg_blue(2));
BGbr = pois((0:NBGbr)', bg_blue(3));
BGgg = pois((0:NBGgg)', bg_green(1));
BGgr = pois((0:NBGgr)', bg_green(2));

nb = numel(fbb);

% The kernel reads its log multinomial / binomial coefficients from a
% precomputed library, flat-indexed exactly as below.
lib_t = zeros(nb*(NBGbb+1)*(NBGbg+1)*(NBGbr+1), 1);
for j = 1:nb
  for a = 0:NBGbb
    for b = 0:NBGbg
      for c = 0:NBGbr
        k = [fbb(j)-a, fbg(j)-b, fbr(j)-c];
        ix = (j-1)*(NBGbb+1)*(NBGbg+1)*(NBGbr+1) + a*(NBGbg+1)*(NBGbr+1) + b*(NBGbr+1) + c + 1;
        if any(k < 0)
          lib_t(ix) = -Inf;
        else
          lib_t(ix) = gammaln(sum(k)+1) - sum(gammaln(k+1));
        end
      end
    end
  end
end

lib_b = zeros(nb*(NBGgg+1)*(NBGgr+1), 1);
for j = 1:nb
  for a = 0:NBGgg
    for b = 0:NBGgr
      k = [fgg(j)-a, fgr(j)-b];
      ix = (j-1)*(NBGgg+1)*(NBGgr+1) + a*(NBGgr+1) + b + 1;
      if any(k < 0)
        lib_b(ix) = -Inf;
      else
        lib_b(ix) = gammaln(sum(k)+1) - sum(gammaln(k+1));
      end
    end
  end
end

P = eval_prob_3c_bg_lib(fbb, fbg, fbr, fgg, fgr, ...
                        NBGbb, NBGbg, NBGbr, NBGgg, NBGgr, ...
                        BGbb, BGbg, BGbr, BGgg, BGgr, ...
                        p_bb, p_bg, p_gr, lib_b, lib_t);
save('-v7', 'ab_output.mat', 'P');
"""


@pytest.fixture(scope="session")
def compiled_kernel(tmp_path_factory):
    """Compile the reference MEX kernel once per session, or skip."""
    if shutil.which("octave") is None or shutil.which("mkoctfile") is None:
        pytest.skip("octave / mkoctfile not available")
    if not PAM_SRC.is_dir():
        pytest.skip(f"reference sources not present at {PAM_SRC}")

    build = tmp_path_factory.mktemp("pda3c_mex")
    result = subprocess.run(
        ["mkoctfile", "--mex", "-O", "-I.", "-o", str(build / "eval_prob_3c_bg_lib.mex"),
         *SOURCES],
        cwd=str(PAM_SRC), capture_output=True, text=True,
    )
    if result.returncode != 0 or not (build / "eval_prob_3c_bg_lib.mex").exists():
        pytest.skip(f"mkoctfile failed:\n{result.stderr[-2000:]}")
    (build / "ab_kernel.m").write_text(DRIVER)
    return build


def test_chisurf_matches_the_compiled_reference_kernel(compiled_kernel):
    """ChiSurf's factorised likelihood equals the reference's nested-sum C code.

    The two compute the same quantity by different algorithms — the reference
    sums over every channel's background count, ChiSurf collapses that into two
    matrix products — so agreement to machine precision is a real check on the
    factorisation rather than a restatement of it.
    """
    from scipy.io import loadmat, savemat

    from chisurf.core.fluorescence.pda3c import burst_log_likelihood

    rng = np.random.default_rng(4242)
    n_bursts, n_points = 12, 5

    counts = {name: rng.integers(0, 10, n_bursts).astype(float)
              for name in ("fbb", "fbg", "fbr", "fgg", "fgr")}
    p_blue = rng.dirichlet(np.ones(3), size=n_points)
    p_gr = rng.uniform(0.15, 0.85, size=n_points)
    bg_blue = np.array([0.7, 0.5, 0.6])
    bg_green = np.array([0.4, 0.8])
    # Generous bounds, so the reference's hard min(F, NBG) truncation is not
    # what is being compared and both sides evaluate the complete sum.
    nbg = np.full(5, 12.0)

    savemat(
        str(compiled_kernel / "ab_input.mat"),
        {
            **{k: v.reshape(-1, 1) for k, v in counts.items()},
            "p_bb": p_blue[:, 0].reshape(-1, 1),
            "p_bg": p_blue[:, 1].reshape(-1, 1),
            "p_gr": p_gr.reshape(-1, 1),
            "bg_blue": bg_blue.reshape(1, -1),
            "bg_green": bg_green.reshape(1, -1),
            "nbg": nbg.reshape(1, -1),
        },
    )

    run = subprocess.run(
        ["octave", "--no-gui", "--quiet", "ab_kernel.m"],
        cwd=str(compiled_kernel), capture_output=True, text=True,
    )
    assert run.returncode == 0, run.stderr[-2000:]

    reference = loadmat(str(compiled_kernel / "ab_output.mat"))["P"]  # (bursts, points)

    counts_blue = np.stack([counts["fbb"], counts["fbg"], counts["fbr"]], axis=1)
    counts_green = np.stack([counts["fgg"], counts["fgr"]], axis=1)
    p_green = np.stack([1.0 - p_gr, p_gr], axis=1)

    ours = np.exp(
        burst_log_likelihood(counts_blue, p_blue, bg_blue)
        + burst_log_likelihood(counts_green, p_green, bg_green)
    ).T

    assert ours.shape == reference.shape
    relative = np.abs(ours - reference) / np.maximum(np.abs(reference), 1e-300)
    assert relative.max() < 1e-10, f"max relative difference {relative.max():.3e}"
