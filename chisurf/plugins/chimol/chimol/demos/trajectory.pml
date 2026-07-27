# A trajectory, and why intra_fit matters.
#
# Load the coarse-grained transition, then fit every state onto the first: without
# it the movie shows the model tumbling and the conformational change is buried
# under rigid-body drift.
#
# The file is all-atom and its topology is read, so `cartoon` works: the
# globular GTPase domain and the long helical stalk are both drawn as a ribbon.
load hgbp1_transition.h5
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
