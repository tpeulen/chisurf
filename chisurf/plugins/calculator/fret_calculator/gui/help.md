# FRET calculator

HeteroFRET links the donor-acceptor distance (Å), the donor-only lifetime (ns), the Förster radius (Å), the transfer efficiency and the transfer rate (1/ns). Edit the distance to compute the other quantities; edit the lifetime, the efficiency or the rate to solve for the distance. A positive distribution width averages the efficiency over Gaussian or noncentral chi distances. The inverse fields describe one effective distance, so they are not an exact inverse of a broad distribution.

HomoFRET links the anisotropy migration time and the rotational correlation time to the energy-migration rate and a donor-acceptor distance. Edit the migration time to compute the distance; edit the distance to solve backwards for the migration time. The migration rate is a calculated output and cannot be edited.

## Plots

The distance distribution and the induced rate (HeteroFRET) or anisotropy-time (HomoFRET) distribution redraw with every edit. The selected distribution is solid, the other one dashed. Drag a plot to pan it, scroll to zoom.

## Editing fields

Click a field, type the value and press Enter (or click elsewhere) to apply it. The arrows step the value; a value outside the allowed range is moved to the nearest end. When a calculation fails (for example an efficiency of exactly 0 or 1 has no finite distance) the line under the buttons says so and the fields keep their last values. Dropping a file on the window only shows a notice: the calculator has no file input.

## Further reading

- [Förster resonance energy transfer (FRET)](docs/concepts/fret.md)
