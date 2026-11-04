"""python -m cmc_light [--sim | --port PORT | --tcp HOST]  (no option: USB instrument, else simulator)"""

import argparse

try:
    from .gui import AUTO, SIMULATOR, run
except (ImportError, ValueError):
    from cmc_light.gui import AUTO, SIMULATOR, run


def main():
    ap = argparse.ArgumentParser(prog="cmc-light", description="ALEX laser source control panel")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--sim", action="store_true", help="connect to the built-in simulator")
    g.add_argument("--port", help="serial port, e.g. /dev/cu.wchusbserial10")
    g.add_argument("--tcp", metavar="HOST", help="SCPI over WiFi (port 5025)")
    ap.add_argument("--debug", action="store_true", help="echo every SCPI command/reply to stdout")
    args = ap.parse_args()
    # no option: the first cmc-light found on USB, or the simulator when none is plugged in
    target = SIMULATOR if args.sim else args.port or ("tcp://" + args.tcp if args.tcp else AUTO)
    raise SystemExit(run(autoconnect=target, debug=args.debug))


if __name__ == "__main__":
    main()
