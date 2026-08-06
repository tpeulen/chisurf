# A biofilm growing on a surface -- a simulation, not a structure.
#
# There is no file to fetch for this one. The agent-swarm simulator that ships
# beside ChiSurf grows the colony the first time this demo runs, and ChiMOL
# opens what it wrote; the second run reads the cached result.
#
# What an RMF carries here is more than motion. Every cell is one bead whose
# radius and colour are written PER FRAME, so three things happen at once as it
# plays:
#
#   * cells appear -- a bead with no radius is one that has not divided off yet,
#     and it grows to full size over two frames after it does;
#   * the film thickens -- a cell walled in by its neighbours cannot divide, so
#     growth happens only where the colony touches open space;
#   * cells change colour without moving -- green at the surface, amber, red and
#     violet deeper in. A cell never moves once it is born, so its colour can
#     only change because the colony grew *over* it. That is the whole point:
#     what you are watching is cells being buried.
#
# Spheres, not cartoon: these are cells, not residues, and each carries its own
# radius.
#
# The camera is framed on the LAST frame before playing. Framing the first one
# instead -- which is what `orient; zoom; mplay` does if you write it in that
# order -- fits the view to ten cells, and the colony then grows straight out of
# the picture.
#
# `movie_recenter` off is what keeps the substratum still. On -- which is the
# default, and what you want for a molecule wandering across a box -- the camera
# follows the centroid of the frame being shown, and the centroid of a growing
# film rises with it: the floor would slide downward while the surface stayed
# put, so the film would appear to sink rather than to grow.
delete all
load biofilm_growth.rmf
bg_color white
set movie_recenter, off
as spheres
count_states
frame 60
turn x, -75
zoom all, 2, 1
frame 1
mplay
