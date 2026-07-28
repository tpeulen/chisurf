# The nuclear pore complex: an integrative model from PDB-IHM.
#
# There are no atoms in this entry at all. An integrative structure carries its
# coordinates as BEADS, each standing for a range of residues and each with its
# own radius -- so a reader that knows only about atoms reports "no coordinates"
# for a file that is full of them.
#
# This is the whole eight-spoke yeast pore: 234,184 beads, the eight-fold
# symmetry and the open central channel. It used to take seven minutes to open,
# because the viewer splined a cartoon ribbon through beads that have no
# backbone; drawn as what they are it takes about two seconds. One spoke on its
# own is PDBDEV_00000010.
# Colour by MOLECULE, not by position in the file. `spectrum count` ramps over
# 234,184 beads in file order, which says nothing about the structure; colouring
# by molecule gives all sixteen copies of a nucleoporin one colour, so the
# eight-fold symmetry appears as a repeating pattern rather than a smear. The
# names come from the entry's own hierarchy -- Nup84, Nsp1, Mlp1 and 28 others.
#
# The pale ramp is deliberate: ambient occlusion darkens beads by how enclosed
# they are, and a saturated hue has little room left to darken. Pale colours let
# the crevices read as depth.
delete all
fetch PDBDEV_00000012
spectrum molecule, lightblue_palecyan_palegreen_paleyellow_wheat_salmon_lightpink
zoom all
