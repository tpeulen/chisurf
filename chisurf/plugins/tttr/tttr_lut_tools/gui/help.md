# TTTR LUT Tools

Compute **TAC-linearization LUTs** for TTTR data and add them to your detector setup. The
window has two tabs, chosen with the radio buttons at the top. They are not equal partners.

# Compute LUT (the main tool)

Real TCSPC / TAC hardware has *differential non-linearity*: the micro-time bins are not exactly
equal in width, so a **uniform-illumination** (flat-light) histogram, which *should* be flat,
is not. The Felekyan et al. (Rev. Sci. Instrum. 2005) construction turns that histogram into a
cumulative table that remaps every photon's raw micro-time onto an equal-width axis. The
non-linearity is **per routing channel**, so one LUT is computed per channel.

1. Load the flat-light TTTR file(s): **Files**, **Folder**, **Database**, or drop them on the window.
2. The upper plot is the raw TAC histogram of the **Preview channel**. Drag the orange region
   (its edges, or the small square in its middle) to the flat plateau. The red line is the
   offset (**Noffset**), the green line the low-count threshold. **Auto-detect region** finds
   a plateau by itself; it can fail on a histogram that is not flat, and says so in the status line.
3. The lower plot is the **corrected preview**: the same photons after linearization. It should
   be flat. It uses at most **Preview photons** photons.
4. **Add all channels to setup** computes a LUT for every routing channel (each channel's own
   plateau, except the shown one, which keeps your region) and assigns them all.

**Save LUT file...** and **Export corrected...** are optional: they write the LUT of the shown
channel, or the corrected micro-times of its photons, to a file.

# settings.tttr.json (optional)

Only needed to share a correction between setups, or to import a LUT you already have as a
file. Load preview files, **Load LUT**, select a LUT and assign it to the active channel
(**Selected**) or to all channels (**All**), set a photon-level **Shift**, then **Save JSON**.
The channel table's *Show* column chooses which channels the plot draws.

# How the LUT reaches a detector setup

Opened from the detector setup, **Apply to detector setup** hands the assigned LUTs and shifts
to the setup. From then on every reader that selects that setup (with *Apply TAC linearization*
ticked) linearizes photons at read time, so previews here and production reads match.

# Further reading

* [Microtime LUT guide](docs/guides/37_tttr_microtime_lut.md)
