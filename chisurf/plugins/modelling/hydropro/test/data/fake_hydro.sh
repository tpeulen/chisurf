#!/bin/sh
# Test stand-in for the HYDROPRO / HYDRO++ executable (a separate download, never run here).
# Like the real program it reads the main input file name from stdin. Line 3 of that file names the structure
# in both flavours; the stand-in replies with the RECORDED report data/recorded/<structure stem>-res.txt
# (written under the name the input announced on line 2), prints a banner, and never computes anything.
#   stem containing "fails"   -> exits 3 with a message on stderr
#   stem containing "silent"  -> prints nothing and writes no report (parser answers "not found")
#   stem containing "slow"    -> sleeps 5 s first (cancel tests)
here=$(cd "$(dirname "$0")" && pwd)
recorded="${HYDRO_RECORDED_DIR:-$here/recorded}"
read input
generic=$(sed -n '2p' "$input" | awk '{print $1}')
struct=$(sed -n '3p' "$input" | awk '{print $1}')
stem=$(basename "$struct"); stem="${stem%.*}"
echo "HYDRO fake: read $input ($generic) for $stem"
case "$stem" in
  *slow*) sleep 5 ;;
esac
case "$stem" in
  *fails*) echo "fake HYDRO: cannot open structure" >&2; exit 3 ;;
  *silent*) exit 0 ;;
esac
if [ -f "$recorded/$stem-res.txt" ]; then
  cp "$recorded/$stem-res.txt" "${generic}-res.txt"
fi
