# A trajectory, and why intra_fit matters.
#
# Load the coarse-grained transition, then fit every state onto the first: without
# it the movie shows the model tumbling and the conformational change is buried
# under rigid-body drift.
#
# Two files, because that is what a trajectory *is*. A DCD stores coordinates and
# nothing else -- no atom names, no residues, no chains -- so the topology comes
# from the PDB loaded first and `load_traj` lays the frames onto it. Loading the
# DCD on its own would work and would look wrong: a point cloud with no atom
# identity, where `cartoon` splines through all 5235 atoms instead of the CA
# trace and no selection resolves.
load topol.pdb
load_traj hgbp1_transition.dcd
bg_color white
hide everything
show cartoon, polymer
count_states
intra_rms all, 1
intra_fit all, 1
intra_rms all, 1
frame 1
orient
zoom
mplay
