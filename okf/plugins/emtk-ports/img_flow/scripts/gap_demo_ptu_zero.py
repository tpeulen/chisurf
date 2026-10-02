"""The simulated flow demo PTU reads back as an all-zero image stack with the installed tttrlib (0.27.0). Run from the repo root (a 16x16, 4-frame scan: seconds).

The same photons with the frame-marker tag written as 4 instead of 3 reconstruct (as ONE frame of 64 lines): the counts are there; the frame segmentation
with the PTU marker decoding (tag 3 -> marker 4) puts them in no pixel. img_flow's Load demo -> Map flow therefore ends in "No arrows".
"""
import numpy as np, tttrlib
from chisurf.core.fluorescence.imaging import load_image_stack
TY_INT8 = 0x10000008
n_pixel, n_frames, dwell, pixel, w_r, w_z = 16, 4, 20e-6, 0.1, 0.25, 1.0
field = n_pixel * pixel; box_xy = 0.5 * field * 1.6 + 4.0 * w_r; box_z = 4.0
sample = tttrlib.SimSystem(); sp = tttrlib.SimSpecies(); sp.D = 0.15; sp.q = [1.2e6]; sp.r0 = 0.0
sample.add_species(sp); sample.set_background([0.0]); sample.set_box(box_xy, box_z); sample.set_population(0, 300.0)
sample.set_flow_field(tttrlib.SimVectorGrid.poiseuille(2.0, 0.5 * field, 0, box_xy * 1.1, box_z * 1.1, 0.2))
integ = tttrlib.SimIntegrator(); integ.dt = dwell; integ.n_channels = 1; integ.n_ph_max = 10**12
integ.n_microtime_channels = 256; integ.microtime_resolution = 0.032; integ.laser_period = 256 * 0.032
integ.seed_diffusion = 7; integ.seed_emission = 8; integ.fast_grid_bbox = True
eng = tttrlib.SimEngine(sample, tttrlib.SimGrid.gaussian3d(w_r, w_z, 4 * w_r, min(4 * w_z, box_z), 0.05, 1.0), [], integ)
markers = tttrlib.SimMarkerConfig(); markers.emit_pixel_markers = False
scanner = tttrlib.SimScanner.uniform(n_pixel, n_pixel, dwell, pixel, pixel, -0.5 * field, -0.5 * field, markers, False)
for _ in range(n_frames):
    eng.run_scan(scanner)
for frame_tag in (3, 4):
    tttr = tttrlib.TTTR(np.asarray(eng.macro_window(), np.uint64), np.asarray(eng.micro_time(), np.uint16), np.asarray(eng.channel(), np.int8), np.asarray(eng.event_type(), np.int8))
    h = tttr.header; h.set_macro_time_resolution(dwell); h.set_micro_time_resolution(0.032e-9)
    for name, v in (("ImgHdr_LineStart", 1), ("ImgHdr_LineStop", 2), ("ImgHdr_Frame", frame_tag), ("ImgHdr_PixX", n_pixel), ("ImgHdr_PixY", n_pixel), ("ImgHdr_BiDirect", 0)):
        h.set_tag(name, int(v), TY_INT8)
    tttr.write(f"/tmp/demo_ptu_zero_{frame_tag}.ptu", "PTU")
    s = load_image_stack(f"/tmp/demo_ptu_zero_{frame_tag}.ptu")
    print(f"ImgHdr_Frame={frame_tag}: stack {s.data.shape}, photons in the image {int(s.data.sum())} of {len(tttr)}")
# expected (a working reader): ImgHdr_Frame=3 -> (3 or 4, 1, 16, 16) with ~all photons; seen: (3, 1, 16, 16) with 0
