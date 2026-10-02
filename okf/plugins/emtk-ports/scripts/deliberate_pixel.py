"""Write deliberate.json for an imaging pixel plugin: the `lost` entries of compare.json that are the pyqtgraph ImageView's own chrome.
Usage: deliberate_pixel.py <plugin_id> [extra.json]; entries it cannot explain are printed (explain them by hand in extra.json)."""
import json, pathlib, sys
E = pathlib.Path("okf/plugins/emtk-ports") / sys.argv[1]
lost = json.load(open(E / "compare.json"))["lost"]
IMG = {"roi": "pyqtgraph ImageView ROI button (line-profile ROI of the viewer); the emtk image has none.",
       "menu": "pyqtgraph ImageView Menu button (ROI / normalisation options).",
       "operation": "pyqtgraph ImageView normalisation (subtract/divide/blur of a frame range): a display tool, not part of the analysis.",
       "subtract": "normalisation option of the Qt ImageView", "divide": "normalisation option of the Qt ImageView", "blur": "normalisation option of the Qt ImageView",
       "mean": "normalisation option of the Qt ImageView", "off": "normalisation 'off' option of the Qt ImageView", "timerange": "time-range widget of the Qt ImageView normalisation",
       "frame": "frame label of the Qt ImageView normalisation", "t": "axis label (frame index) of the Qt ImageView; the emtk movie has Play, Loop, Stop and a frame slider",
       "x": "axis letters of the Qt viewer; emtk draws 'x [px]' and 'y [px]'", "y": "axis letters of the Qt viewer; emtk draws 'x [px]' and 'y [px]'",
       "viridis": "colormap menu of the Qt ImageView; the shared emtk ImageCanvas offers magma, inferno, viridis and gray", "cividis": "colormap menu entry of the Qt ImageView, not offered by the shared ImageCanvas",
       "plasma": "colormap menu entry of the Qt ImageView, not offered by the shared ImageCanvas", "turbo": "colormap menu entry of the Qt ImageView, not offered by the shared ImageCanvas",
       "inferno": "in emtk's colormap list (shown when opened)", "gray": "in emtk's colormap list (shown when opened)", "magma": "in emtk's colormap list (shown when opened)"}
extra = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else {}
out, rest = (json.load(open(E / "deliberate.json")) if (E / "deliberate.json").exists() else {}), []
for k in lost:
    if k in out: continue
    if k in extra: out[k] = extra[k]
    elif k in IMG: out[k] = IMG[k]
    elif k.lstrip("-").replace(".", "").isdigit() and len(k) <= 3: out[k] = "axis tick / spin digit of the Qt viewer"
    else: rest.append(k)
json.dump(out, open(E / "deliberate.json", "w"), indent=1, ensure_ascii=False)
print("unexplained:", rest)
