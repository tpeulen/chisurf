# Measuring: surface area, bonds, hydrogens.
load solvated_fragment.pdb
bg_color white
hide everything
show sticks, polymer
h_add polymer
get_area polymer
get_bonds polymer
count_atoms polymer
orient
zoom
