# FRET calculator

HeteroFRET links donor–acceptor distance (Å), donor-only lifetime (ns), Förster radius (Å), efficiency and transfer rate (1/ns). Edit distance to compute the other quantities; edit lifetime, efficiency or rate to solve for distance. A positive distribution width averages efficiencies over Gaussian or noncentral chi distances. Inverse fields represent a single effective distance, so they are not an exact inverse of a broad distribution.

HomoFRET links anisotropy migration time and rotational correlation time to energy-migration rate and distance. Edit the distance to solve backwards for migration time. The migration rate is a calculated output.

The distance and induced rate/time distributions update with every edit. The selected distribution is solid; the comparison is dashed. Hover controls for units and meaning. Drag plot axes to zoom and pan.

## Editing the parameter sliders

Every parameter is a slider: drag the track and the value follows the pointer, updating the linked quantities as you go. Wide positive ranges (lifetimes, Förster radius, rates) are logarithmic — one decade per centimetre instead of the whole range under your thumb. To type an exact value, **Ctrl+Click** (⌘-Click on macOS) the track: a field opens over it; Enter or a click anywhere else commits, Escape puts the old value back.
