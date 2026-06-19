"""User-supplied game-asset management for Banshee Brush.

The tool ships no AFoP files; the user points it at their own extracted files and we remember
each path in <AppConfigLocation>/config.json (never copying them), validating on load.
classify / scan_folder decide which file fills which slot.
"""
from __future__ import annotations
import json
import os

from PyQt6.QtCore import QStandardPaths

IMG_EXT = (".dds", ".png", ".tga", ".jpg", ".jpeg")

# slot, human label, expected-filename hint, tier
SLOTS = [
    ("model",            "Model mesh",            "wildlife_banshee_*.mmb (or wl_banshee_*.cast)", "required"),
    ("body_color",       "Body \u2014 base colour",    "wildlife_banshee_*_body_d.dds",  "required"),
    ("body_pattern",     "Body \u2014 pattern coat",   "wildlife_banshee_*_body_pc.dds", "required"),
    ("head_color",       "Head \u2014 base colour",    "wildlife_banshee_*_head_d.dds",  "required"),
    ("head_pattern",     "Head \u2014 pattern coat",   "wildlife_banshee_*_head_pc.dds", "required"),
    ("body_material",    "Body \u2014 material",       "wildlife_banshee_*_body_m.dds",  "recommended"),
    ("head_material",    "Head \u2014 material",       "wildlife_banshee_*_head_m.dds",  "recommended"),
    ("wing_color",       "Wing \u2014 albedo",         "insect_wing_d.dds (shared)",  "optional"),
    ("eye_color",        "Eye \u2014 albedo",          "wildlife_eye_grayscale.dds (shared)", "optional"),
    ("body_normal",      "Body \u2014 normal",         "wildlife_banshee_*_body_n.dds",  "optional"),
    ("head_normal",      "Head \u2014 normal",         "wildlife_banshee_*_head_n.dds",  "optional"),
    ("body_dn_mask",     "Body \u2014 detail mask",    "wildlife_banshee_*_body_dn_mask.dds", "optional"),
    ("head_dn_mask",     "Head \u2014 detail mask",    "wildlife_banshee_*_head_dn_mask.dds", "optional"),
    ("detail1",          "Detail normal 1",          "skin_detail_1_nr.dds (shared)", "optional"),
    ("detail2",          "Detail normal 2",          "skin_detail_2_nr.dds (shared)", "optional"),
    ("detail3",          "Detail normal 3",          "skin_detail_4_nr.dds (shared)", "optional"),
]
SLOT_HINT = {s: h for s, _l, h, _t in SLOTS}
REQUIRED = [s for s, _l, _h, tier in SLOTS if tier == "required"]

# The tool is banshee-specific; creature-named files must match this so an export
# dump full of other wildlife (thanator, crawler, bully, ...) can't be picked up.
CREATURE = "banshee"
# When several banshee variants exist (wl_banshee_01, corpse_banshee_01, ...),
# prefer the standard one.
DEFAULT_VARIANT = "wildlife_banshee_01"

# Canonical in-game locations (paths are relative to the extracted-bundle root,
# i.e. below the extractor-specific prefix). Shown under each row so users know
# where to look in their own extraction.
_BANSHEE_DIR = "characterart/wildlife/banshee/wildlife_banshee_01"
_SHARED_DIR = "characterart/sharedtexture"
GAME_PATH = {
    "model":            "characterart/wildlife/banshee/wl_banshee_01/wl_banshee_01.mmb",
    "body_color":       _BANSHEE_DIR + "/wildlife_banshee_01_body_d.dds",
    "body_pattern":     _BANSHEE_DIR + "/wildlife_banshee_01_body_pc.dds",
    "body_material":    _BANSHEE_DIR + "/wildlife_banshee_01_body_m.dds",
    "head_color":       _BANSHEE_DIR + "/wildlife_banshee_01_head_d.dds",
    "head_pattern":     _BANSHEE_DIR + "/wildlife_banshee_01_head_pc.dds",
    "head_material":    _BANSHEE_DIR + "/wildlife_banshee_01_head_m.dds",
    "body_normal":      _BANSHEE_DIR + "/wildlife_banshee_01_body_n.dds",
    "head_normal":      _BANSHEE_DIR + "/wildlife_banshee_01_head_n.dds",
    "body_dn_mask":     _BANSHEE_DIR + "/wildlife_banshee_01_body_dn_mask.dds",
    "head_dn_mask":     _BANSHEE_DIR + "/wildlife_banshee_01_head_dn_mask.dds",
    "wing_color":       _SHARED_DIR + "/insect_wing_d.dds",
    "eye_color":        _SHARED_DIR + "/wildlife_eye_grayscale.dds",
    "detail1":          _SHARED_DIR + "/skin_detail_1_nr.dds",
    "detail2":          _SHARED_DIR + "/skin_detail_2_nr.dds",
    "detail3":          _SHARED_DIR + "/skin_detail_4_nr.dds",
}


def slot_filter(slot):
    """Qt file-dialog filter for a given slot."""
    if slot == "model":
        return "Model (*.mmb *.cast)"
    return "Texture (*.dds *.png *.tga *.jpg *.jpeg)"


# ----------------------------------------------------------------- paths/config
def config_dir():
    d = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    os.makedirs(d, exist_ok=True)
    return d


def config_path():
    return os.path.join(config_dir(), "config.json")


def load_config():
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}
    if not isinstance(cfg, dict):
        cfg = {}
    cfg.setdefault("paths", {})
    cfg.setdefault("models", [])
    return cfg


def save_config(cfg):
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------- matching
def classify(fname):
    """Return the asset slot a filename fills, or None. Creature slots require 'banshee'; wing/eye also accept their shared textures."""
    stem, ext = os.path.splitext(fname.lower())
    if ext in (".mmb", ".cast"):
        return "model" if CREATURE in stem else None
    if ext in IMG_EXT:
        if CREATURE in stem:
            # accept the plural "heads" shared-texture naming as well as "head"
            for key, toks in (("body", ("body",)), ("head", ("heads", "head"))):
                for t in toks:
                    if stem.endswith(t + "_d"):
                        return key + "_color"
                    if stem.endswith(t + "_m"):
                        return key + "_material"
                    if stem.endswith(t + "_dn_mask"):
                        return key + "_dn_mask"
                    if stem.endswith(t + "_n"):
                        return key + "_normal"
                    if t in stem and ("pattern" in stem or "coat" in stem
                                      or stem.endswith(t + "_pc")):
                        return key + "_pattern"
            if stem.endswith("wing_d"):
                return "wing_color"
            if stem.endswith("eye_d") or stem.endswith("eyes_d"):
                return "eye_color"
        # shared (not creature-named) textures the banshee uses
        if stem.endswith("insect_wing_d") or stem.endswith("insect_wing"):
            return "wing_color"
        if stem.endswith("wildlife_eye_grayscale"):
            return "eye_color"
        if stem.endswith("skin_detail_1_nr"):
            return "detail1"
        if stem.endswith("skin_detail_2_nr"):
            return "detail2"
        if stem.endswith("skin_detail_4_nr"):
            return "detail3"
    return None


def _rank(slot, path):
    """Sort key for candidate files (lower preferred): default variant first, .dds over .png / .mmb over .cast, corpse/lod/ragdoll last."""
    stem = os.path.splitext(os.path.basename(path).lower())[0]
    if DEFAULT_VARIANT in stem:
        var = 0
    elif CREATURE + "_01" in stem or "_" + CREATURE + "_01" in stem or "banshee_01" in stem:
        var = 1
    elif CREATURE in stem:
        var = 2
    else:
        var = 3                                  # shared (insect_wing, wildlife_eye_grayscale)
    if any(b in stem for b in ("corpse", "lastlod", "_lod", "crashed", "ragdoll", "death")):
        var += 5
    pl = path.lower()
    if slot == "model":
        typ = 0 if pl.endswith(".mmb") else 1
    elif pl.endswith(".dds"):
        typ = 0
    elif pl.endswith(".png"):
        typ = 1
    else:
        typ = 2
    return (var, typ, stem)


def scan_folder(folder):
    """Recursively scan `folder`; return (slots, models) - best path per slot plus every banshee model found."""
    slots, models = {}, []
    if folder and os.path.isdir(folder):
        for dp, _d, fs in os.walk(folder):
            for f in sorted(fs):
                slot = classify(f)
                if slot is None:
                    continue
                p = os.path.join(dp, f)
                if slot == "model":
                    models.append(p)
                cur = slots.get(slot)
                if cur is None or _rank(slot, p) < _rank(slot, cur):
                    slots[slot] = p
    return slots, models


# ----------------------------------------------------------------- validation
def missing_required(pathmap):
    """Required slots that are absent or point at a file that no longer exists."""
    return [s for s in REQUIRED
            if not (pathmap.get(s) and os.path.isfile(pathmap[s]))]


def invalid_paths(pathmap):
    """Tracked slots whose stored path no longer exists (unknown/legacy slots are ignored)."""
    known = {s for s, _l, _h, _t in SLOTS}
    return [s for s, p in pathmap.items() if s in known and p and not os.path.isfile(p)]


def afop_blue_root(path):
    """If `path` is inside an AFOP 'blue/...' tree, return the directory containing 'blue' (so 'blue/...' engine paths resolve under it), else None."""
    parts = os.path.abspath(path).replace("\\", "/").split("/")
    idx = None
    for i, seg in enumerate(parts[:-1]):     # skip the filename itself
        if seg.lower() == "blue":
            idx = i                          # take the last 'blue' if nested
    if idx is None:
        return None
    root = "/".join(parts[:idx])
    return root or "/"


def find_related(manifest_path, engine_path):
    """Resolve a file referenced by a .mbansheepatterndata, searching in strict order and never
    outside these scopes: the manifest's folder, its sub-folders, then (if it sits in a
    'blue/...' tree) the engine path under the blue root. Returns an absolute path or None."""
    base = os.path.dirname(os.path.abspath(manifest_path))
    rel = engine_path.replace("\\", "/").lstrip("/")
    name = os.path.basename(rel)
    lname = name.lower()
    # 1) the manifest's own folder
    cand = os.path.join(base, name)
    if os.path.isfile(cand):
        return cand
    # 2) sub-folders of the manifest's own folder
    for dp, _sub, files in os.walk(base):
        if dp == base:
            continue                         # own folder already checked in (1)
        for f in files:
            if f.lower() == lname:
                return os.path.join(dp, f)
    # 3) relative to the AFOP 'blue' root, using the engine path verbatim
    root = afop_blue_root(manifest_path)
    if root is not None:
        cand = os.path.join(root, *rel.split("/"))
        if os.path.isfile(cand):
            return cand
    return None
