"""Builders for the *_emtk.view.json specs of the imaging pixel tools (the JSON files are the artifact; this only saves typing the shared rows)."""
import json


def buttons(hdf5_label, run_desc, hdf5_desc, container_desc, container_name="the container beside the photon file"):
    return {"type": "button_row", "description": "Compute the maps, write them out, explore them or go on to the next step.", "buttons": [
        {"action": "run_maps", "label": "Run", "description": run_desc},
        {"action": "request_hdf5", "label": hdf5_label, "description": hdf5_desc},
        {"action": "save_container", "label": "Save container", "description": container_desc},
        {"action": "open_ndx", "label": "ndX", "description": "Explore the per-pixel table in ndX, the shared live dataset. A Back button returns to the maps."},
        {"action": "next_step", "label": "Next", "description": "Remember the file and the HDF5 and go to the next analysis step. Only available inside the Imaging Tools pipeline."}]}


def file_rows(desc="PTU/HT3 imaging file with line and frame markers (or drop one onto the window: it is loaded and run). The scanner geometry is read from its header. Press Enter to select a typed path."):
    return [{"type": "value", "attr": "filename", "label": "TTTR file", "kind": "str", "call": "commit_filename", "elide": "start",
             "placeholder": "pick a file, drop one here, or load from the database", "description": desc},
            {"type": "button_row", "description": "Pick the photon file from disk or from the database.", "buttons": [
                {"action": "open_file", "label": "Browse", "description": "Browse for a photon imaging file on disk."},
                {"action": "open_database", "label": "Database", "description": "Load a dataset registered in the database; the database resolves it to a local file wherever its object store keeps the data."}]}]


def window_choice():
    return {"type": "choice", "attr": "display_window", "label": "Detector window", "options_source": "window_names", "call": "refresh_display",
            "description": "The detector window shown in the maps. Every window is computed and written; this only chooses which one is drawn. The windows come from the Detectors tab (or the Imaging Tools setup step); without any, the channel-0 window is used."}


def info(desc="What was computed: the file, the size of the image and the detector windows."):
    return {"type": "info", "source": "summary_text", "description": desc}


def image_tab(title, desc, source, name, movie=False, empty=""):
    return {"type": "panel", "title": title, "dock": "views", "description": desc, "sections": [
        {"type": "custom", "key": "image_panel", "title": title, "description": desc,
         "options": {"name": name, "source": source, "colormap_attr": "colormap", **({"movie": True} if movie else {}), "empty": empty or f"No {name.lower()} yet. Select a photon file and press Run."}}]}


def plane_tab(title, desc, name):
    return {"type": "panel", "title": title, "dock": "views", "description": desc, "sections": [
        {"type": "custom", "key": "plane", "title": title, "description": desc, "options": {"name": name}}]}


def settings(sections, desc):
    return {"type": "panel", "title": "Settings", "dock": "settings", "n_col": 1, "description": desc, "sections": sections}


def write(path, comment, panels):
    json.dump({"_comment": comment, "sections": panels}, open(path, "w"), indent=2, ensure_ascii=False)
