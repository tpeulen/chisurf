# The selection language: the same grammar PyMOL uses.
load 148l.pdb
bg_color white
hide everything
show cartoon, polymer
color grey80, polymer
color red, resi 1-30
color blue, chain S
show spheres, organic
color yellow, organic
show sticks, byres (polymer within 5 of organic)
orient organic
zoom organic, 6
