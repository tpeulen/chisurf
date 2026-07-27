# The nuclear pore complex: an integrative model from PDB-IHM.
#
# There are no atoms in this entry at all. An integrative structure carries its
# coordinates as BEADS, each standing for a range of residues and each with its
# own radius -- so a reader that knows only about atoms reports "no coordinates"
# for a file that is full of them.
#
# This is one spoke of the yeast NPC: about 29,000 beads. The whole eight-spoke
# pore is PDBDEV_00000012, which loads but is slow enough to be unpleasant --
# see okf/references/known-issues.md.
delete all
fetch PDBDEV_00000010, pdb-ihm
spectrum count, rainbow
zoom all
