# Banshee Brush

A desktop recolour editor and live OpenGL preview for **Avatar: Frontiers of Pandora** banshee (Ikran) skins. Load the game's vanity pattern files, repaint the ten colour slots for the head and body, preview the result on the actual model in real time, and export skins the game will accept.

> **Banshee Brush ships no game files.** It reads your own extracted Avatar: Frontiers of Pandora assets and only ever *references* their paths — it never copies or redistributes them. Not affiliated with or endorsed by Ubisoft or Massive Entertainment. For personal modding use.

---

## Features

- **Live recolour preview.** The viewport recolours the model as you edit. The shader is a faithful transcription of the game's `px_wildlife_skin_banshee` colour path, so what you see closely matches in-game.
- **Head and body palettes** of ten colours each, with anatomically-labelled slots (see below), hex entry, and a colour picker.
- **Pattern controls** — Level 1/2 and Invert 1/2 — matching the `.mpatterncontrol` constants, applied live.
- **3D viewer** with orbit/pan/zoom, normal-mapped detail, transparent wing membranes, and a reference floor grid.
- **Reads the real game formats:** `.mmb` / `.cast` models, Snowdrop "STF" `.dds` textures (plus standard DDS), and the three vanity config formats.
- **Identity-preserving export.** Exports either overwrite your loaded files in place or write a fresh `blue/gameplay/vanity/juice/` tree, always keeping the original names, UIDs, and filenames intact (only colours, control values, and coat paths change).

---

## Installation

### Windows (recommended)

Prebuilt Windows builds are on the **[Releases](https://github.com/SaintBaron/AFOP_BansheeBrush/releases)** tab — no Python or dependencies required.

1. Open the [Releases](https://github.com/SaintBaron/AFOP_BansheeBrush/releases) tab and download the latest release's ZIP.
2. Extract it anywhere (your Desktop, a tools folder, etc.).
3. Run **`BansheeBrush.exe`** from the extracted folder.

The build is unsigned, so Windows SmartScreen or your antivirus may warn on first launch — choose **More info → Run anyway** (or allow it) to start.

### Linux (from source)

Run it directly with Python.

- Python 3.10 or newer
- [PyQt6](https://pypi.org/project/PyQt6/), [moderngl](https://pypi.org/project/moderngl/), [numpy](https://pypi.org/project/numpy/), [Pillow](https://pypi.org/project/Pillow/) (≥ 10.4, for BCn texture decoding)
- [texture2ddecoder](https://pypi.org/project/texture2ddecoder/) — *optional* fallback BCn decoder, used if Pillow can't handle a surface

```bash
pip install pyqt6 moderngl numpy pillow texture2ddecoder
python app.py
```

(Windows users can also run from source this way if they'd rather not use the prebuilt `.exe`.)

### Both platforms

A working **OpenGL 3.3** GPU and driver is required for the 3D viewport (any modern GPU). On first run you'll be asked to point the tool at your extracted game files (see below); after that it autoloads them on every launch.

---

## First-run: pointing it at your assets

Banshee Brush remembers the path to each file you select in a small config (`config.json` under your OS application-config folder, e.g. `~/.config/BansheeBrush/` on Linux). Your files are never moved or copied.

Two ways to set up:

1. **Add an export folder** — point it at the folder where you extracted the banshee assets and it searches recursively for everything it recognises (preferring `.dds` over `.png`).
2. **Pick each file by hand.**

The files it looks for (canonically under `…/blue/baked/characterart/wildlife/banshee/…`):

| | File | Needed |
|---|---|---|
| Model | `…banshee…*.mmb` or `…*.cast` | required |
| Body / Head base colour | `…_body_d.dds` / `…_head_d.dds` | required |
| Body / Head pattern coat | `…_body_pc.dds` / `…_head_pc.dds` | required |
| Body / Head material | `…_body_m.dds` / `…_head_m.dds` | improves preview |
| Body / Head normal | `…_body_n.dds` / `…_head_n.dds` | optional |
| Detail masks, shared wing / eye textures | various | optional |

If a saved path goes stale (file moved or deleted), the tool flags it and lets you relink from the **Assets…** dialog.

---

## Using it

- Pick a model in the **Model** bar (or via **Browse…**); orbit with **LMB**, pan with **MMB**, zoom with the **wheel**.
- In the **Head** and **Body** panels, click a swatch or type a hex code to recolour a slot. Use **→ / ←** to copy a whole side to the other.
- Load an existing skin with **Load Banshee Pattern Data** (`.mbansheepatterndata`) to auto-fill every field from a real skin, or load colour patterns / controls individually.

### Colour slots

Each side has ten slots. They are gradient stops, not solid regions — slots 1–5 drive the pattern (Coat 1) layer and 6–10 the base (Coat 2) layer — but each one most affects the area named below (mapped by setting a single slot to pure red and noting where it lands):

| # | Body | Head |
|---|---|---|
| 1 | Body Accent | Upper neck / nape |
| 2 | Forewing edges | Brow / neck ridge |
| 3 | Wing-root streaks | Lip line / gums |
| 4 | Tail Secondary | Snout-tip accents |
| 5 | Tail Primary | Chin tip |
| 6 | Speckle flecks | Lower jaw / throat |
| 7 | Body veins | Jaw / cheek veins |
| 8 | Fine capillaries | Muzzle / cheek |
| 9 | Body Secondary | Head base |
| 10 | Body base | Main head / neck |

---

## Exporting

Both export modes write **functionally identical** files — they differ only in *where* the files go:

- **Overwrite existing pattern files** (ticked): saves back over the files you loaded, in place. Also locks and ticks the per-panel overwrites and both export options.
- **Otherwise:** you name an output folder and the files are written into a fresh `…/<name>/blue/gameplay/vanity/juice/` tree, ready to pack as a mod.

Either way the asset **names, UIDs, and filenames are preserved exactly** — only the colour hexes, the Level/Invert control values, and the `myBodyPatternCoat` / `myHeadPatternCoat` paths can change. This matters: the game resolves a skin by matching the manifest's references to existing asset names and UIDs, so renaming or re-minting them breaks resolution and the Ikran renders black.

You can also **Export as Texture** to bake a recoloured albedo to PNG.

### Supported formats

| | Read | Write |
|---|---|---|
| Models | `.mmb`, `.cast` | — |
| Textures | `.dds` (Snowdrop STF and standard BCn) | `.png` (texture export) |
| Vanity config | `.mcolorpattern`, `.mpatterncontrol`, `.mbansheepatterndata` | same three (byte-faithful round-trip) |

---

## Building a Windows `.exe`

Most people should just grab the prebuilt `.exe` from the [Releases](https://github.com/SaintBaron/AFOP_BansheeBrush/releases) tab — this section is only for building it yourself.

Use [PyInstaller](https://pyinstaller.org/) **on Windows** — it can't cross-compile, so building on Linux yields a Linux binary, not an `.exe`.

```bat
python -m venv build-env
build-env\Scripts\activate
pip install pyinstaller pyqt6 moderngl numpy pillow texture2ddecoder
pyinstaller --noconfirm --windowed --name BansheeBrush --hidden-import mmb_loader app.py
```

The result is `dist\BansheeBrush\BansheeBrush.exe`. Add `--onefile` for a single distributable; if the 3D view fails to start, try `--collect-all PyQt6` and/or `--collect-all moderngl`. No data files need bundling (the window icon is embedded and game assets are loaded at runtime).

---

## Project layout

| File | Role |
|---|---|
| `app.py` | Qt UI, panels, asset setup, export — entry point (`python app.py`) |
| `viewer.py` | moderngl viewport embedded in a Qt widget |
| `gl_shaders.py` | GLSL recolour/grid shaders + camera math |
| `recolor_core.py` | CPU reference of the recolour pipeline (used for PNG export) |
| `cast_loader.py` | Cast (`.cast`) parser + `SubMesh` + model-load dispatcher |
| `mmb_loader.py` | headless `.mmb` reader (LOD0 geometry) |
| `patterns.py` | read/write the three vanity config formats |
| `stf_dds.py` | Snowdrop STF / standard `.dds` BCn texture loader |
| `assets.py` | user-asset config, scanning, and path resolution |
| `app_icon.py` | embedded window icon |

---

## Credits

- Cast format and binary parser by **DTZxPorter**.
- The `.mmb` read path is ported (read-only, LOD0) from the **AFoP Mesh Tool** Blender addon — **AlexPo, JasperZebra, J-Lyt, SaintBaron**.

---

## Disclaimer

Avatar: Frontiers of Pandora is © Ubisoft / Massive Entertainment. This is an unofficial fan-made modding tool that contains no game assets and is not affiliated with or endorsed by the rights holders. Use it only with files you have lawfully extracted from your own copy of the game.
