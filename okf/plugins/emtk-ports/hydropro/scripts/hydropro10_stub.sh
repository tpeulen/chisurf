#!/bin/sh
# Test stand-in for the HYDROPRO executable (not installed here; it is a separate download).
# Reads the input file name from stdin like HYDROPRO, prints a banner, and writes the
# <FILENAME>-res.txt report that run_hydro parses -- with a FIXED stub value, 1.000E-06 cm2/s,
# which is not a computed diffusion coefficient.
read input
generic=$(sed -n '2p' "$input" | awk '{print $1}')
echo "HYDROPRO stub: read $input ($generic)"
printf 'Translational diffusion coefficient:   1.000E-06 cm2/s\n' > "${generic}-res.txt"
