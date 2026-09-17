"""Record the reference Number & Brightness (N&B) outputs into ``pam_nb_reference.npz``.

Reference: PAM (Schrimpf et al. 2018), https://gitlab.com/PAM-PIE/PAM at commit
``7319d15d``, ``functions/MIA/Analysis/Do_NB.m`` — the ``Do_NB`` callback of the
MIA image-analysis window. Its computation (dead-time correction, PCH, per-pixel
``nanmean``/``nanstd``, the averaging / disk / Gaussian moment filter, the γ = 1/√8
number and brightness, the optional 3×3 median filter, cross N&B, and the
starting histogram thresholds) is **extracted from the file at generation time**
and only its GUI handle reads are rewritten into plain variables (see
``SUBSTITUTIONS``); the arithmetic is PAM's own text. Also recorded: the box
average of the "Moving average" stack correction in
``functions/MIA/Mia_Correct.m`` (``imfilter(Data, ones(Box)/prod(Box), 'replicate')``)
for an odd and an even lateral box.

Run under Octave with the ``image`` package (``fspecial``/``imfilter``/``medfilt2``;
``pkg install -forge image``). Octave core lacks ``nanmean``/``nanstd``/``mean2``, so
the driver defines them with MATLAB's semantics, and Octave's ``imfilter`` refuses
the complex ``sqrt(covariance)`` cross N&B filters, so that one call filters the
real and imaginary parts separately (what MATLAB's linear filter does).
Deliberate deviation: the stacks are passed as double, where MIA stores corrected
data as single — the comparison is of the arithmetic, not of single-precision
rounding.

The checkout is not kept on disk. To regenerate::

    junk/clone.sh                 # re-clones PAM into junk/PAM
    python test/data/nb/gen_pam_nb_reference.py --pam junk/PAM
"""

from __future__ import annotations

import argparse
import pathlib
import re
import shutil
import subprocess
import tempfile

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "pam_nb_reference.npz"
DO_NB = pathlib.Path("functions") / "MIA" / "Analysis" / "Do_NB.m"

#: GUI handle reads in Do_NB.m -> driver variables.
SUBSTITUTIONS = [
    (r"h\.Mia_Image\.Calculations\.NB_Type\.Value", "NB_Type"),
    (r"h\.Mia_Image\.Settings\.Channel_PIE\((\w+)\)\.Value", r"\1"),
    (r"str2double\(h\.Mia_Image\.Calculations\.NB_Detector_Deadtime\.String\)", "Deadtime"),
    (r"str2double\(h\.Mia_Image\.Settings\.Image_Pixel\.String\)", "PixelTime"),
    (r"str2double\(h\.Mia_Image\.Calculations\.NB_Average_Radius\.String\)", "Radius"),
    (r"h\.Mia_Image\.Calculations\.NB_Average\.Value", "NB_Average"),
    (r"h\.Mia_Image\.Calculations\.NB_Median\.Value", "NB_Median"),
    (r"str2double\(h\.Mia_NB\.Image\.Pixel\.String\)", "PixelTime"),
    (r"h\.Mia_NB\.Image\.Hist\((\d),(\d)\)\.String=num2str\((.*)\);", r"Hist(\1,\2)=\3;"),
    (r"h\.Mia_NB\.Image\.Hist\((\d),(\d)\)\.String='(\d+)';", r"Hist(\1,\2)=\3;"),
    # Octave's imfilter rejects complex images, MATLAB's filters them linearly;
    # cross N&B filters sqrt(covariance), which is complex where it is negative.
    (r"\bimfilter\(", "imfilter_linear("),
]

SHIMS = {
    "nanmean.m": "function m = nanmean(x, dim)\n  m = mean(x, dim, 'omitnan');\nend\n",
    "nanstd.m": (
        "function s = nanstd(x, opt, dim)\n"
        "  ok = ~isnan(x); n = sum(ok, dim);\n"
        "  x0 = x; x0(~ok) = 0; mu = sum(x0, dim) ./ n;\n"
        "  d = x - mu; d(~ok) = 0;\n"
        "  s = sqrt(sum(abs(d).^2, dim) ./ (n - 1 + opt));\n"
        "end\n"
    ),
    "mean2.m": "function m = mean2(x)\n  m = mean(x(:));\nend\n",
    "imfilter_linear.m": (
        "function y = imfilter_linear(x, f, varargin)\n"
        "  if iscomplex(x)\n"
        "    y = imfilter(real(x), f, varargin{:}) + 1i * imfilter(imag(x), f, varargin{:});\n"
        "  else\n"
        "    y = imfilter(x, f, varargin{:});\n"
        "  end\n"
        "end\n"
    ),
}

#: (name, NB_Type, NB_Average, Radius, NB_Median, Deadtime [ns], PixelTime [us])
CASES = [
    ("top_plain", 1, 1, 3, 0, 0.0, 10.0),
    ("top_average_deadtime", 1, 2, 3, 0, 100.0, 10.0),
    ("bottom_disk_median_deadtime", 2, 3, 4, 1, 50.0, 20.0),
    ("cross_gaussian", 3, 4, 3, 0, 0.0, 10.0),
    ("cross_plain", 3, 1, 3, 0, 0.0, 10.0),
    ("top_radius_one", 1, 3, 1, 0, 0.0, 10.0),
]

#: Lateral box sizes of the recorded Mia_Correct moving averages (odd and even).
MOVING_AVERAGE_BOXES = [3, 4]


def extract_computation(source: str) -> str:
    """Return Do_NB's computation block with the GUI reads rewritten."""
    start = source.index("%% Determines, for which channels to calculate")
    stop = source.index("%%% Updates N&B plots")
    body = source[start:stop]
    for pattern, repl in SUBSTITUTIONS:
        body = re.sub(pattern, repl, body)
    leftover = re.findall(r"\bh\.[A-Za-z_.()0-9,]+", body)
    if leftover:
        raise SystemExit(f"unsubstituted GUI reads in Do_NB.m: {sorted(set(leftover))}")
    return body


def make_stacks(seed: int = 20260917) -> tuple[np.ndarray, np.ndarray]:
    """Two correlated channels, ``(frames, ny, nx)``, of fluctuating molecule numbers.

    Per pixel and frame a molecule number ``n ~ Poisson(N(x,y))`` emits
    ``Poisson(ε₁ n + b₁)`` counts into channel 1 and ``Poisson(ε₂ f n + b₂)`` into
    channel 2 (a fraction ``f`` carries the second label), so the channels share
    number fluctuations and cross N&B is non-zero.
    """
    rng = np.random.default_rng(seed)
    frames, ny, nx = 30, 10, 12
    yy, xx = np.mgrid[0:ny, 0:nx]
    number = 2.0 + 3.0 * xx / (nx - 1)
    eps1 = 1.0 + 1.5 * (yy >= ny // 2)
    n = rng.poisson(number, size=(frames, ny, nx))
    ch1 = rng.poisson(eps1 * n + 0.5)
    ch2 = rng.poisson(0.8 * rng.binomial(n, 0.6) + 0.3)
    return ch1.astype(np.int16), ch2.astype(np.int16)


def driver(body: str) -> str:
    """Octave function wrapping the extracted computation."""
    return (
        "function out = pam_do_nb(Data1, Data2, NB_Type, NB_Average, Radius, NB_Median, Deadtime, PixelTime)\n"
        "global MIAData\n"
        "MIAData = struct();\n"
        "MIAData.Data = {[], Data1; [], Data2};\n"
        "MIAData.NB = [];\n"
        "Hist = zeros(3, 3);\n" + body + "out = MIAData.NB;\nout.Hist = Hist;\nend\n"
    )


def main() -> None:
    """Run every case of :data:`CASES` through the extracted Do_NB and write the npz."""
    from scipy.io import loadmat, savemat

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pam", type=pathlib.Path, default=pathlib.Path("junk/PAM"))
    args = parser.parse_args()
    src = args.pam / DO_NB
    if not src.exists():
        raise SystemExit(f"{src} not found; re-clone with junk/clone.sh")
    if shutil.which("octave") is None:
        raise SystemExit("octave not on PATH")

    body = extract_computation(src.read_text(encoding="utf-8", errors="replace"))
    ch1, ch2 = make_stacks()
    record: dict[str, np.ndarray] = {"ch1": ch1, "ch2": ch2}
    names = ["Int", "Std", "Num", "Eps", "PCH"]

    with tempfile.TemporaryDirectory(prefix="pam_nb_") as tmp:
        work = pathlib.Path(tmp)
        (work / "pam_do_nb.m").write_text(driver(body))
        for fname, text in SHIMS.items():
            (work / fname).write_text(text)
        # MATLAB images are (y, x, frames)
        savemat(
            str(work / "stacks.mat"),
            {
                "Data1": np.moveaxis(ch1.astype(float), 0, -1),
                "Data2": np.moveaxis(ch2.astype(float), 0, -1),
            },
        )
        lines = ["pkg load image;", "load('stacks.mat');"]
        for name, nb_type, avg, radius, median, dead, pixel in CASES:
            lines.append(
                f"NB = pam_do_nb(Data1, Data2, {nb_type}, {avg}, {radius}, {median}, {dead!r}, {pixel!r});"
            )
            lines.append("s = struct(); s.Hist = NB.Hist;")
            for field in names:
                lines.append(
                    f"for k = 1:numel(NB.{field}); if ~isempty(NB.{field}{{k}}); "
                    f's.(["{field}" num2str(k)]) = NB.{field}{{k}}; end; end;'
                )
            lines.append(f"save('-v7', '{name}.mat', '-struct', 's');")
        # The box average Mia_Correct.m subtracts ("Moving average" correction):
        # Filter=ones(Box)/prod(Box); imfilter(Data, Filter, 'replicate'), Box=[px px frames].
        # Octave's imfilter is 2-D only, so the lateral box is recorded frame by frame
        # (frames = 1); MATLAB centres the frame axis by the same floor((n+1)/2) rule.
        for px in MOVING_AVERAGE_BOXES:
            lines.append(
                f"ma = zeros(size(Data1)); for k = 1:size(Data1, 3); "
                f"ma(:,:,k) = imfilter(Data1(:,:,k), ones([{px} {px}])/({px}*{px}), 'replicate'); end; "
                f"save('-v7', 'ma_{px}.mat', 'ma');"
            )
        (work / "run_cases.m").write_text("\n".join(lines) + "\n")
        run = subprocess.run(
            ["octave", "--no-gui", "--quiet", "run_cases.m"],
            cwd=str(work),
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            raise SystemExit(run.stderr[-3000:])
        for name, nb_type, avg, radius, median, dead, pixel in CASES:
            record[f"{name}__settings"] = np.array(
                [nb_type, avg, radius, median, dead, pixel], dtype=float
            )
            data = loadmat(str(work / f"{name}.mat"))
            for key, value in data.items():
                if key.startswith("__"):
                    continue
                arr = np.asarray(value)
                if np.iscomplexobj(arr) and not np.any(arr.imag):
                    arr = arr.real
                record[f"{name}__{key}"] = np.squeeze(arr) if key.startswith("PCH") else arr

        for px in MOVING_AVERAGE_BOXES:
            ma = loadmat(str(work / f"ma_{px}.mat"))["ma"]
            record[f"moving_average__{px}"] = np.moveaxis(ma, -1, 0)

    version = subprocess.run(
        ["octave", "--version"], capture_output=True, text=True
    ).stdout.splitlines()[0]
    record["octave_version"] = np.array(version)
    np.savez_compressed(OUT, **record)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(record)} arrays)")


if __name__ == "__main__":
    main()
