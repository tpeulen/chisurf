# VV/VH Anisotropy Decay

This tool is deprecated: use the VV/VH G-Factor plugin and the reader-integrated anisotropy
workflow instead. It stays for existing data.

It computes the fluorescence anisotropy decay r(t) = (VV - g VH) / (VV + 2 g VH) from a file that
holds the parallel decay (VV) followed by the perpendicular decay (VH), and the residual
anisotropy r∞ as the mean of r(t) over a region.

## Settings
G-factor (0 to 10) corrects the different sensitivity of the two channels. Apply
backgrounds subtracts the constant BG VV and BG VH first. Flip VV↔VH swaps the
channels of a file whose polarizations are reversed. Shift VH (channels) moves VH by a
fractional number of channels (interpolated, -150 to 150); points outside the shifted range
are left out. Points where VV + 2 g VH is not positive are left out of r(t).

## The r∞ region
The two green lines of the anisotropy plot, or Region start and Region end, bound the
channels whose r(t) is averaged. The y axis of the plot is fixed to 0 to 0.45.

## Files
The Input section lists the decays of the Datasets workspace (drop a VV/VH file on the ChiSurf
window to add it): picking a row reads its .dat/.txt file, and two curves named VV and VH are
analysed as one pair. A file with no numbers is reported on the status line and the loaded data
stays. Save outputs… writes
<name>_shifted.dat (VV and the shifted VH), <name>_anisotropy.txt (channel, r(t), r(t) minus
r∞) and <name>_rinf.csv (file, r∞, region, backgrounds, g).

## Batch
Batch files… opens the batch window with a snapshot of the current settings: queue files from
its Input section (the workspace), press Run Batch, then Save CSV…. A file that cannot be
read gets a row with its error and the others are still processed.
