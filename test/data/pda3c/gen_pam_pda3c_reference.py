"""Regenerate ``pam_eval_prob_3c_bg_lib_reference.npz`` from the reference C kernel.

Reference: PAM (Schrimpf et al. 2018), https://gitlab.com/PAM-PIE/PAM at commit
``7319d15d``, the three-colour PDA MEX kernel
``functions/tcPDA/C Files/src/eval_prob_3c_bg_lib.c`` together with the sources
its build notes list (``randist/binomial.c``, ``randist/multinomial.c``,
``randist/specfunc/gamma.c``, ``sys/numcores.c``, ``sys/memalloc.c``).

The kernel is compiled with Octave's ``mkoctfile --mex`` and driven by the
Octave script ``DRIVER`` below, which builds the log multinomial/binomial
coefficient libraries exactly as the reference's GUI does. Inputs and the
resulting ``P`` (bursts x points) are frozen into the npz, which
``test/models/test_pda3c_octave_ab.py`` compares ChiSurf against.

The checkout is not kept on disk. To regenerate::

    junk/clone.sh            # re-clones PAM into junk/PAM
    python test/data/pda3c/gen_pam_pda3c_reference.py --pam junk/PAM

Needs ``octave`` and ``mkoctfile`` on PATH plus scipy.
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "pam_eval_prob_3c_bg_lib_reference.npz"
KERNEL_DIR = pathlib.Path("functions") / "tcPDA" / "C Files" / "src"
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


def make_inputs() -> dict[str, np.ndarray]:
    """The A/B input set: 12 bursts x 5 parameter points, generous NBG bounds.

    The bounds (12 background photons per channel) are wide enough that the
    reference's hard ``min(F, NBG)`` truncation is not what gets compared.
    """
    rng = np.random.default_rng(4242)
    n_bursts, n_points = 12, 5
    inputs = {
        name: rng.integers(0, 10, n_bursts).astype(float)
        for name in ("fbb", "fbg", "fbr", "fgg", "fgr")
    }
    p_blue = rng.dirichlet(np.ones(3), size=n_points)
    inputs["p_bb"] = p_blue[:, 0]
    inputs["p_bg"] = p_blue[:, 1]
    inputs["p_gr"] = rng.uniform(0.15, 0.85, size=n_points)
    inputs["bg_blue"] = np.array([0.7, 0.5, 0.6])
    inputs["bg_green"] = np.array([0.4, 0.8])
    inputs["nbg"] = np.full(5, 12.0)
    return inputs


def main() -> None:
    """Compile the kernel, run it on :func:`make_inputs`, write the npz."""
    from scipy.io import loadmat, savemat

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pam",
        type=pathlib.Path,
        default=pathlib.Path("junk/PAM"),
        help="PAM checkout (default: junk/PAM)",
    )
    args = parser.parse_args()
    src = args.pam / KERNEL_DIR
    if not src.is_dir():
        raise SystemExit(f"reference sources not found at {src}; re-clone with junk/clone.sh")
    for tool in ("octave", "mkoctfile"):
        if shutil.which(tool) is None:
            raise SystemExit(f"{tool} not on PATH")

    inputs = make_inputs()
    with tempfile.TemporaryDirectory(prefix="pda3c_mex_") as tmp:
        build = pathlib.Path(tmp)
        subprocess.run(
            [
                "mkoctfile",
                "--mex",
                "-O",
                "-I.",
                "-o",
                str(build / "eval_prob_3c_bg_lib.mex"),
                *SOURCES,
            ],
            cwd=str(src),
            check=True,
            capture_output=True,
            text=True,
        )
        (build / "ab_kernel.m").write_text(DRIVER)
        column = {"bg_blue", "bg_green", "nbg"}
        savemat(
            str(build / "ab_input.mat"),
            {k: (v.reshape(1, -1) if k in column else v.reshape(-1, 1)) for k, v in inputs.items()},
        )
        subprocess.run(
            ["octave", "--no-gui", "--quiet", "ab_kernel.m"],
            cwd=str(build),
            check=True,
            capture_output=True,
            text=True,
        )
        reference = loadmat(str(build / "ab_output.mat"))["P"]

    np.savez_compressed(OUT, P=reference, **inputs)
    print(f"wrote {OUT} (P {reference.shape})")


if __name__ == "__main__":
    main()
