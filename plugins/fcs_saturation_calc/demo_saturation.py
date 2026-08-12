#!/usr/bin/env python3
"""
Illustrative Chisurf plugin CLI tool for FCS saturation helpers.
Meant to be invoked as a chisurf command-line integrator.
"""

import sys
import numpy as np

# Ensure plugin is importable
sys.path.insert(0, "/Users/tpeulen/dev/chisurf")

from fcs_saturation_calc import compute_apparent_volume, compute_power_dependence

def main():
    import argparse
    p = argparse.ArgumentParser(description="Chisurf FCS Saturation Calculator (demo)")
    p.add_argument("-P", "--power", type=float, required=True, help="Power (mW)")
    p.add_argument("--w0", type=float, default=250.0, help="Beam waist w0 (nm)")
    p.add_argument("--z0", type=float, default=750.0, help="Axial z0 (nm)")
    p.add_argument("-D", type=float, default=100.0, help="Diffusion D (um^2/s)")
    p.add_argument("--F_T", type=float, default=0.15, help="Max triplet fraction")
    p.add_argument("--P_sat", type=float, default=5.0, help="Saturation power (mW)")
    args = p.parse_args()

    V, tD = compute_apparent_volume(
        P_mW=args.power,
        w0_nm=args.w0,
        z0_nm=args.z0,
        D_um2s=args.D,
        F_T_max=args.F_T,
        P_sat_mW=args.P_sat,
    )

    print("Chisurf FCS Saturation Calculator (demo)")
    print(f"Parameters: w0={args.w0}nm z0={args.z0}nm D={args.D} um^2/s")
    print(f"Power={args.power:.1f} mW  P_sat={args.P_sat:.1f} mW")
    print()
    print(f"Apparent Veff: {V:.2f} um^3")
    print(f"Diffusion time tD: {tD:.2f} us")
    print(f"Triplet fraction f_T: {args.F_T:.3f}")


if __name__ == "__main__":
    main()
