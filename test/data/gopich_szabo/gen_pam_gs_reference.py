"""Re-run the reference Gopich-Szabo likelihood on the frozen inputs of ``pam_gs_reference.npz``.

Reference: PAM (Schrimpf et al. 2018), https://gitlab.com/PAM-PIE/PAM at commit
``7319d15d``, the unmodified ``functions/BurstBrowser/GS_likelihood/GP_logL.m``
(``logL = GP_logL(t, c, K, E)``: macrotimes, colours 1 = donor / 2 = acceptor,
rate matrix, diagonal efficiency matrix), evaluated under Octave.

The npz holds, per case, the photon ``times``, ``colors`` (0-based), the
``generator`` K and the state ``efficiencies``; this script feeds them to
``GP_logL`` and writes the result to ``<case>_octave_logl`` at ``%.17e``.
With ``--check`` it only compares against the stored values.

The checkout is not kept on disk. To regenerate::

    junk/clone.sh            # re-clones PAM into junk/PAM
    python test/data/gopich_szabo/gen_pam_gs_reference.py --pam junk/PAM
"""

from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
FIXTURE = HERE / "pam_gs_reference.npz"
CASES = ("2state", "2state_fast", "3state_chain", "3state_cycle")

DRIVER = r"""
names = {%s};
fid = fopen('octave.txt', 'w');
for i = 1:numel(names)
    n = names{i};
    t = load([n '_t.txt']);
    c = load([n '_c.txt']);
    K = load([n '_K.txt']);
    E = diag(load([n '_E.txt']));
    logL = GP_logL(t, c, K, E);
    fprintf(fid, '%%s %%.17e\n', n, logL);
end
fclose(fid);
"""


def main() -> None:
    """Run ``GP_logL`` on every stored case and write or check the results."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pam",
        type=pathlib.Path,
        default=pathlib.Path("junk/PAM"),
        help="PAM checkout (default: junk/PAM)",
    )
    parser.add_argument(
        "--check", action="store_true", help="compare against the stored values instead of writing"
    )
    args = parser.parse_args()
    gs_dir = (args.pam / "functions" / "BurstBrowser" / "GS_likelihood").resolve()
    if not (gs_dir / "GP_logL.m").exists():
        raise SystemExit(f"GP_logL.m not found under {gs_dir}; re-clone with junk/clone.sh")
    if shutil.which("octave") is None:
        raise SystemExit("octave not on PATH")

    data = dict(np.load(FIXTURE))
    with tempfile.TemporaryDirectory(prefix="pam_gs_") as tmp:
        work = pathlib.Path(tmp)
        for case in CASES:
            fmt = "%.17e"
            np.savetxt(work / f"{case}_t.txt", data[f"{case}_times"], fmt=fmt)
            np.savetxt(work / f"{case}_c.txt", data[f"{case}_colors"] + 1, fmt="%d")
            np.savetxt(work / f"{case}_K.txt", data[f"{case}_generator"], fmt=fmt)
            np.savetxt(work / f"{case}_E.txt", data[f"{case}_efficiencies"], fmt=fmt)
        names = ",".join(f"'{c}'" for c in CASES)
        (work / "driver.m").write_text(f"addpath('{gs_dir}');\n" + DRIVER % names)
        subprocess.run(
            ["octave", "--no-gui", "--quiet", "driver.m"],
            cwd=str(work),
            check=True,
            capture_output=True,
            text=True,
        )
        results = dict(line.split() for line in (work / "octave.txt").read_text().splitlines())

    for case in CASES:
        value = float(results[case])
        key = f"{case}_octave_logl"
        if args.check:
            stored = float(data[key])
            print(f"{case}: reference {value:.17e} stored {stored:.17e} diff {value - stored:.3e}")
        data[key] = np.array(value)
    if not args.check:
        np.savez(FIXTURE, **data)
        print(f"wrote {FIXTURE}")


if __name__ == "__main__":
    main()
