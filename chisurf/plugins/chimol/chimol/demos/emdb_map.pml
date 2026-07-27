# A density map straight from EMDB, contoured.
#
# The map keeps its own voxel size and origin, so it lands where the file says
# it does rather than at the scene origin.
delete all
fetch EMD-3061
map_info
isosurface dens, EMD-3061
zoom all
