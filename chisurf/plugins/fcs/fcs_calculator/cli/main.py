"""Command-line entry point for the FCS confocal calculator."""

from __future__ import annotations

import argparse
import json

from ..core.algorithms import compute_confocal, get_dye, reference_dyes, scale_D_from_25C
from ..core.algorithms import mPa_s_to_Pa_s, water_viscosity_Pa_s


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="FCS confocal diffusion/volume calculator.")
    p.add_argument(
        "--list-dyes", action="store_true",
        help="List the MMFDB reference species with a diffusion coefficient and exit",
    )
    p.add_argument(
        "--dye", default=None,
        help="Take D from an MMFDB reference species (scaled to --temp-C and the viscosity)",
    )
    p.add_argument("--tau-us", type=float, default=70.0)
    p.add_argument("--S", type=float, default=5.0)
    p.add_argument("--temp-C", type=float, default=20.0)
    p.add_argument("--eta-mPa-s", type=float, default=0.89)
    p.add_argument("--water-eta", action="store_true", help="Use water viscosity model")
    p.add_argument("--constraint", choices=["D", "rh", "V"], default="D")
    p.add_argument("--D-um2-s", type=float, default=400.0)
    p.add_argument("--rh-nm", type=float, default=0.5)
    p.add_argument("--veff-fL", type=float, default=0.4)
    p.add_argument("--conc-nM", type=float, default=1.0)
    args = p.parse_args(argv)

    if args.list_dyes:
        print(json.dumps(list(reference_dyes().values()), indent=2, ensure_ascii=False))
        return 0

    D_um2_s = args.D_um2_s
    if args.dye:
        entry = get_dye(args.dye)
        if entry is None:
            p.error(f"unknown species {args.dye!r} (see --list-dyes)")
        T_K = args.temp_C + 273.15
        eta = water_viscosity_Pa_s(T_K) if args.water_eta else mPa_s_to_Pa_s(args.eta_mPa_s)
        D_um2_s = scale_D_from_25C(float(entry["d25_um2_s"]), T_K, eta)

    result = compute_confocal(
        tau_us=args.tau_us, S=args.S, temp_C=args.temp_C, eta_mPa_s=args.eta_mPa_s,
        use_water_eta=args.water_eta, constraint=args.constraint,
        D_um2_s=D_um2_s, rh_nm=args.rh_nm, veff_fL=args.veff_fL,
        conc_nM=args.conc_nM, num_mols=0.0, invN=0.0, last_edited="conc",
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
