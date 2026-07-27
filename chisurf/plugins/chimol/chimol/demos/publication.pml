# The figure look: flat shading with silhouettes on white.
# PyMOL has no equivalent outside its ray tracer.
load 148l.pdb
bg_color white
hide everything
show cartoon, polymer
spectrum count, rainbow, polymer
lighting flat
orient
zoom
