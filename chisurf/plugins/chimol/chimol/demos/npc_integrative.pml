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
delete all
fetch PDBDEV_00000012
spectrum count, rainbow
zoom all
