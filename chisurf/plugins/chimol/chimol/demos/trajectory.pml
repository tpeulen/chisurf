# A trajectory, and why intra_fit matters.
#
# Load the coarse-grained transition, then fit every state onto the first: without
# it the movie shows the model tumbling and the conformational change is buried
# under rigid-body drift.
#
# `trace` rather than `cartoon`: this is a bead model whose points are ~15 A
# apart, so there is no backbone for a ribbon to follow and a cartoon comes out
# as hundreds of disconnected fragments. On an all-atom trajectory the cartoon
# does animate -- see okf/references/known-issues.md.
load hgbp1_transition.h5
bg_color white
hide everything
show trace
count_states
intra_rms all, 1
intra_fit all, 1
intra_rms all, 1
frame 1
orient
zoom
mplay
