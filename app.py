"""Banshee Brush - AFoP banshee skin recolour editor with an OpenGL viewport.

Autoloads models/textures/patterns from an "Assets" folder beside app.py; everything can
also be loaded from inside the tool. HEAD and BODY panels hold 10 colours each and the
viewport recolours live.
"""

from __future__ import annotations
import sys
import os
import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QSurfaceFormat
from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QHBoxLayout,
    QVBoxLayout,
    QGroupBox,
    QFileDialog,
    QColorDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QDialog,
    QScrollArea,
    QFrame,
    QCheckBox,
    QDoubleSpinBox,
    QGridLayout,
)

import assets
from patterns import ColorPattern, PatternControl, BansheePatternData
from recolor_core import palette_from_pattern, recolor

# Best-effort anatomical labels for each palette slot, per panel. Derived from the
# shader coat structure (slots 1-5 = Coat 1 "pattern" gradient, 6-10 = Coat 2 "base"
# gradient) cross-referenced with the in-game per-slot test captures. The mid-gradient
# stops (4,5,7,8) are transitions that rarely show in isolation. Tweak freely.
SLOT_LABELS = {
    "body": [
        "Body Accent",
        "Forewing edges",
        "Wing-root streaks",
        "Tail Secondary",
        "Tail Primary",
        "Speckle flecks",
        "Body veins",
        "Fine capillaries",
        "Body Secondary",
        "Body base",
    ],
    "head": [
        "Upper neck / nape",
        "Brow / neck ridge",
        "Lip line / gums",
        "Snout-tip accents",
        "Chin tip",
        "Lower jaw / throat",
        "Jaw / cheek veins",
        "Muzzle / cheek",
        "Head base",
        "Main head / neck",
    ],
}

QSS = """
* { font-family:'Segoe UI','Inter','DejaVu Sans',sans-serif; font-size:12px; color:#dfe6ee; }
QMainWindow, QWidget { background:#15181d; }
QLabel { background:transparent; }
QMenuBar { background:#1b1f26; color:#cfd8e3; padding:2px; }
QMenuBar::item { padding:4px 10px; background:transparent; }
QMenuBar::item:selected { background:#262c35; border-radius:5px; }
QMenu { background:#1b1f26; border:none; padding:4px; }
QMenu::item { padding:5px 22px; border-radius:5px; }
QMenu::item:selected { background:#1f6f6a; }
QGroupBox { background:#181e2a; border:none; border-radius:11px;
            margin-top:18px; padding:10px 4px 4px 4px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; subcontrol-position:top center;
            padding:4px 22px; margin-top:2px; color:#141a3a; background:#8b93f0;
            border-radius:9px; font-size:13px; font-weight:700; letter-spacing:1px;
            font-family:'Noto Sans','Cantarell','DejaVu Sans',sans-serif; }
QLineEdit { background:#0f1216; border:none; border-radius:6px;
            padding:3px 6px; selection-background-color:#1f6f6a; }
QLineEdit:focus { background:#12171e; }
QLineEdit:disabled { background:#171a1f; color:#566072; }
QPushButton { background:#252b34; border:none; border-radius:7px;
            padding:5px 11px; color:#e6edf5; }
QPushButton:hover { background:#2d343f; }
QPushButton:pressed { background:#1f6f6a; }
QPushButton:disabled { background:#191d23; color:#566072; }
QPushButton#arrow { font-size:18px; font-weight:700; padding:0;
            color:#cfe7e4; background:#222831; }
QPushButton#arrow:hover { background:#1f6f6a; color:#ffffff; }
QPushButton#accent { background:#5ed9ff; border:none; color:#06243a; font-weight:700;
            padding:8px 5px; border-radius:8px; font-size:11px; letter-spacing:0px;
            font-family:'Noto Sans','Cantarell','DejaVu Sans',sans-serif; }
QPushButton#accent:hover { background:#7ee4ff; }
QPushButton#accent:disabled { background:#222b33; color:#566072; }
QCheckBox { color:#cdd6e2; spacing:7px; background:transparent; }
QCheckBox:disabled { color:#566072; }
QCheckBox::indicator { width:16px; height:16px; border-radius:4px;
            border:none; background:#0f1216; }
QCheckBox::indicator:checked { background:#5ed9ff; }
QCheckBox::indicator:disabled { background:#191d23; }
QPushButton#swatch { border:2px solid #3a424d; border-radius:5px; padding:0; }
QPushButton#swatch:hover { border:2px solid #16b3a7; }
QLabel#subtitle { color:#5f6b7a; font-size:11px; padding-left:2px; background:transparent; }
QLabel#sectiontitle { color:#7f8b9a; font-size:10px; font-weight:600;
            letter-spacing:1px; padding:0 0 1px 2px; background:transparent; }
QToolTip { background:#11151b; color:#d7e0ea; border:none;
            padding:4px 7px; border-radius:5px; }
QLabel#legend { color:#8895a5; font-size:11px; letter-spacing:1px;
            background:#1b1f26; border:none; border-radius:9px; padding:5px; }
QLabel#gamepath { color:#6b7488; font-size:10px; padding:0 0 0 2px; background:transparent; }
QComboBox { background:#252b34; border:none; border-radius:7px;
            padding:4px 10px; color:#e6edf5; }
QComboBox:hover { background:#2d343f; }
QComboBox::drop-down { border:none; width:20px; }
QComboBox QAbstractItemView { background:#1b1f26; border:none;
            selection-background-color:#1f6f6a; outline:none; }
QStatusBar { background:#1b1f26; color:#8895a5; }
QSplitter::handle { background:#262c35; }
QSplitter::handle:hover { background:#16b3a7; }
QScrollArea { background:transparent; }
QScrollBar:vertical { background:transparent; width:12px; margin:2px 2px 2px 0; }
QScrollBar::handle:vertical { background:#46546b; min-height:36px; border-radius:6px; }
QScrollBar::handle:vertical:hover { background:#5ed9ff; }
QScrollBar::handle:vertical:pressed { background:#7ee4ff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background:transparent; }
QScrollBar:horizontal { background:transparent; height:12px; margin:0 2px 2px 2px; }
QScrollBar::handle:horizontal { background:#46546b; min-width:36px; border-radius:6px; }
QScrollBar::handle:horizontal:hover { background:#5ed9ff; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background:transparent; }
"""

try:
    from PIL import Image
except Exception:
    Image = None


def load_rgba(path):
    """RGBA uint8 loader. .dds -> AFoP STF reader, everything else -> Pillow."""
    if os.path.splitext(path)[1].lower() == ".dds":
        import stf_dds

        return stf_dds.load_dds(path)
    if Image is None:
        raise RuntimeError("Pillow is required to load textures")
    return np.asarray(Image.open(path).convert("RGBA"))


def _swatch_css(rrggbb):
    return (
        f"QPushButton#swatch{{background:#{rrggbb};border:2px solid #3a424d;"
        f"border-radius:5px;}} QPushButton#swatch:hover{{border:2px solid #16b3a7;}}"
    )


class ColorRow(QWidget):
    def __init__(self, index, on_change, label=""):
        super().__init__()
        self.index = index
        self.on_change = on_change
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(8)
        self.swatch = QPushButton()
        self.swatch.setObjectName("swatch")
        self.swatch.setFixedSize(30, 22)
        self.swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self.swatch.setToolTip("Click to pick this colour")
        self.swatch.setStyleSheet(_swatch_css("000000"))
        self.swatch.clicked.connect(self._pick)
        text = f"{index + 1}. {label}" if label else f"Color {index + 1}"
        self.name = QLabel(text)
        self.name.setFixedWidth(138)
        self.name.setToolTip(
            "Coat 1 - pattern gradient stop"
            if index < 5
            else "Coat 2 - base gradient stop"
        )
        self.field = QLineEdit()
        self.field.setMaxLength(6)
        self.field.setFixedWidth(70)
        self.field.editingFinished.connect(self._typed)
        self.field.textChanged.connect(self._mark_validity)
        for w in (self.swatch, self.name, self.field):
            lay.addWidget(w)
        lay.addStretch(1)

    def is_valid(self):
        t = self.field.text().strip().lstrip("#")
        if len(t) != 6:
            return False
        try:
            int(t, 16)
        except ValueError:
            return False
        return True

    def _mark_validity(self, *_):
        self.field.setStyleSheet(
            "" if self.is_valid() else "border:1px solid #ff6b6b; background:#2a1c1f;"
        )

    def set_hex(self, rrggbb, notify=False):
        rrggbb = rrggbb.upper()
        self.field.setText(rrggbb)
        self.swatch.setStyleSheet(_swatch_css(rrggbb))
        if notify:
            self.on_change(self.index, rrggbb)

    def _typed(self):
        t = self.field.text().strip().lstrip("#")
        if len(t) == 6:
            try:
                int(t, 16)
                self.set_hex(t, notify=True)
            except ValueError:
                pass

    def _pick(self):
        cur = self.field.text().strip().lstrip("#") or "000000"
        c = QColorDialog.getColor(QColor("#" + cur), self, "Pick colour")
        if c.isValid():
            self.set_hex(f"{c.red():02X}{c.green():02X}{c.blue():02X}", notify=True)


class PatternPanel(QGroupBox):
    def __init__(self, title, key, on_palette_change, on_load_texture=None):
        super().__init__(title)
        self.key = key
        self.on_palette_change = on_palette_change
        self.on_load_texture = on_load_texture
        self.cp = None
        self.ctrl = None  # PatternControl: loaded, edited, or None (neutral)
        self.control_path = None  # path of a loaded .mpatterncontrol (None if none)
        self.path = None
        self.setMaximumWidth(300)
        root = QVBoxLayout(self)
        root.setSpacing(5)
        root.setContentsMargins(10, 8, 10, 8)

        # load row: button + pattern path
        bar = QHBoxLayout()
        bar.setSpacing(6)
        load = QPushButton("Load")
        load.setFixedWidth(86)
        load.setToolTip("Load a .mcolorpattern file into this panel")
        load.clicked.connect(self.load_dialog)
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText(".mcolorpattern path")
        self.pattern_edit.setToolTip(
            "Path to this panel's colour pattern - type a path and press Enter to load"
        )
        self.pattern_edit.returnPressed.connect(self._load_entered)
        bar.addWidget(load)
        bar.addWidget(self.pattern_edit, 1)
        root.addLayout(bar)

        root.addSpacing(10)
        root.addWidget(self._section_title("Textures"))
        self.tex_edits = {}
        for role, name, suf in (
            ("color", "Base", "_d"),
            ("material", "Mat", "_m"),
            ("pattern", "Coat", "_pc"),
        ):
            row = QHBoxLayout()
            row.setSpacing(6)
            btn = QPushButton(f"{name} ({suf})")
            btn.setFixedWidth(86)
            btn.setToolTip(f"Load this mesh's {name} texture  ({suf})")
            btn.clicked.connect(lambda _=False, r=role: self._browse_texture(r))
            edit = QLineEdit()
            edit.setPlaceholderText(f"{suf} texture path")
            edit.setToolTip(
                f"Path to the {name} texture ({suf}) - "
                "type a path and press Enter to load"
            )
            edit.returnPressed.connect(lambda r=role: self._texture_entered(r))
            self.tex_edits[role] = edit
            row.addWidget(btn)
            row.addWidget(edit, 1)
            root.addLayout(row)

        root.addSpacing(10)
        root.addWidget(self._section_title("Pattern Control"))
        # load a .mpatterncontrol to fill the fields; the four fields are editable and
        # update the preview live.
        cbar = QHBoxLayout()
        cbar.setSpacing(6)
        cload = QPushButton("Load")
        cload.setFixedWidth(86)
        cload.setToolTip(
            "Load this panel's .mpatterncontrol; its values fill the fields below"
        )
        cload.clicked.connect(self.load_control_dialog)
        self.control_edit = QLineEdit()
        self.control_edit.setPlaceholderText(".mpatterncontrol path")
        self.control_edit.setToolTip(
            "Path to a loaded pattern control - type a path and press Enter to load"
        )
        self.control_edit.returnPressed.connect(self._load_control_entered)
        cbar.addWidget(cload)
        cbar.addWidget(self.control_edit, 1)
        root.addLayout(cbar)

        self._ctrl_guard = False
        self._ctrl_name = ""
        self._ctrl_uid = ""
        self.ctrl_spins = {}
        root.addSpacing(8)
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(16)
        grid.setContentsMargins(0, 4, 0, 4)
        specs = [
            ("level1", "Level 1", 0.0, 8.0, 0.1),
            ("level2", "Level 2", 0.0, 8.0, 0.1),
            ("invert1", "Invert 1", -1.0, 1.0, 0.1),
            ("invert2", "Invert 2", -1.0, 1.0, 0.1),
        ]
        for i, (attr, lbl, lo, hi, step) in enumerate(specs):
            sb = QDoubleSpinBox()
            sb.setRange(lo, hi)
            sb.setSingleStep(step)
            sb.setDecimals(2)
            sb.setFixedHeight(28)
            sb.setMinimumWidth(54)
            sb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sb.setToolTip(f"{lbl} - edits update the preview live")
            sb.valueChanged.connect(self._control_edited)
            self.ctrl_spins[attr] = sb
            lab = QLabel(lbl)
            lab.setFixedHeight(28)  # match the spin box so vertical centring lines up
            lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            r, c = i // 2, (i % 2) * 2
            grid.addWidget(lab, r, c)
            grid.addWidget(sb, r, c + 1)
        # labels hug a fixed-width column; the two spin columns share the rest equally
        grid.setColumnMinimumWidth(0, 46)
        grid.setColumnMinimumWidth(2, 46)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        root.addLayout(grid)
        self._populate_control_fields(None)  # neutral defaults

        root.addSpacing(10)
        root.addWidget(self._section_title("Colours"))
        labels = SLOT_LABELS.get(key, [""] * 10)
        self.rows = [ColorRow(i, self._row_changed, labels[i]) for i in range(10)]
        for r in self.rows:
            root.addWidget(r)

        root.addSpacing(10)
        self.overwrite = QCheckBox("Overwrite loaded file")
        self.overwrite.setToolTip(
            "Save over this panel's loaded .mcolorpattern instead "
            "of picking a new file (needs a pattern loaded)"
        )
        root.addWidget(self.overwrite)
        exprow = QHBoxLayout()
        exprow.setSpacing(6)
        ep = QPushButton("Export Pattern")
        ep.setObjectName("accent")
        ep.setToolTip("Save this panel's colours as a .mcolorpattern file")
        ep.clicked.connect(self._export_pattern)
        et = QPushButton("Export as Texture")
        et.setObjectName("accent")
        et.setToolTip(
            "Bake the painted colours onto this mesh's texture and save a PNG"
        )
        et.clicked.connect(self._export_texture)
        exprow.addWidget(ep)
        exprow.addWidget(et)
        root.addLayout(exprow)
        root.addStretch(1)

        # export buttons are disabled unless every colour is a valid hex code
        self.export_btns = (ep, et)
        self._export_tips = {ep: ep.toolTip(), et: et.toolTip()}
        self.on_validity_change = None  # set by MainWindow (for Export All)
        for r in self.rows:
            r.field.textChanged.connect(self._refresh_export_enabled)
        self._refresh_export_enabled()

    def all_valid(self):
        return all(r.is_valid() for r in self.rows)

    def _refresh_export_enabled(self, *_):
        ok = self.all_valid()
        for b in self.export_btns:
            b.setEnabled(ok)
            b.setToolTip(
                self._export_tips[b]
                if ok
                else "Every colour must be a valid 6-digit hex code"
            )
        if self.on_validity_change:
            self.on_validity_change()

    @staticmethod
    def _section_title(text):
        lbl = QLabel(text)
        lbl.setObjectName("sectiontitle")
        return lbl

    def _browse_texture(self, role):
        if self.on_load_texture is None:
            return
        p = self.on_load_texture(self.key, role, None)
        if p:
            self.tex_edits[role].setText(p)

    def _texture_entered(self, role):
        if self.on_load_texture is None:
            return
        p = self.tex_edits[role].text().strip()
        if p:
            self.on_load_texture(self.key, role, p)

    def set_texture_path(self, role, path):
        e = self.tex_edits.get(role)
        if e is not None:
            e.setText(path)

    def set_pattern(self, cp, path=None):
        self.cp = cp
        self.path = path
        if path:
            self.pattern_edit.setText(path)
        for i in range(10):
            self.rows[i].set_hex(cp.rgb_hex(i))
        self._emit()

    def _row_changed(self, index, rrggbb):
        if self.cp is None:
            self.cp = ColorPattern(name=f"{self.key} pattern", uid="0" * 32)
        self.cp.set_rgb(index, rrggbb)
        self._emit()

    def _emit(self):
        if self.cp is None:
            return
        pal = palette_from_pattern(self.cp)
        # ctrl carries the resolved/edited level/invert constants; None -> viewer neutral
        params = self.ctrl.params() if self.ctrl is not None else None
        self.on_palette_change(self.key, pal, params)

    # ---- pattern control (load / live edit) ----
    def _populate_control_fields(self, ctrl):
        """Fill the four spin boxes from a PatternControl (neutral if None) without emitting; stash its name/uid for re-export."""
        self._ctrl_guard = True
        vals = (
            ctrl.params()
            if ctrl is not None
            else dict(level1=1.0, level2=1.0, invert1=1.0, invert2=0.0)
        )
        for attr, sb in self.ctrl_spins.items():
            sb.setValue(float(vals[attr]))
        self._ctrl_name = ctrl.name if ctrl is not None else ""
        self._ctrl_uid = ctrl.uid if ctrl is not None else ""
        self._ctrl_guard = False

    def _control_from_fields(self):
        return PatternControl(
            name=self._ctrl_name,
            uid=self._ctrl_uid,
            level1=self.ctrl_spins["level1"].value(),
            level2=self.ctrl_spins["level2"].value(),
            invert1=self.ctrl_spins["invert1"].value(),
            invert2=self.ctrl_spins["invert2"].value(),
        )

    def _control_edited(self, *_):
        if self._ctrl_guard:
            return
        self.ctrl = self._control_from_fields()
        self._emit()

    def current_control(self):
        """The control as currently shown in the fields (always a PatternControl)."""
        return self._control_from_fields()

    def set_control(self, ctrl, path=None):
        """Apply a PatternControl to the fields, keep self.ctrl in sync, and emit. None resets to neutral."""
        self.ctrl = ctrl
        self.control_path = path if (ctrl is not None and path) else None
        self._populate_control_fields(ctrl)
        self.control_edit.setText(path or "")
        self._emit()
        if self.on_validity_change:  # control-loaded state gates an export option
            self.on_validity_change()

    def load_control_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load .mpatterncontrol", "", "Pattern control (*.mpatterncontrol)"
        )
        if path:
            self._load_control(path)

    def _load_control_entered(self):
        p = self.control_edit.text().strip()
        if p:
            self._load_control(p)

    def _load_control(self, path):
        try:
            self.set_control(PatternControl.load(path), path)
        except Exception as e:
            QMessageBox.warning(self, "Pattern control load failed", str(e))

    def load_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load .mcolorpattern", "", "Color pattern (*.mcolorpattern)"
        )
        if path:
            self.set_pattern(ColorPattern.load(path), path)

    def _load_entered(self):
        path = self.pattern_edit.text().strip()
        if not path or not os.path.isfile(path):
            return
        try:
            self.set_pattern(ColorPattern.load(path), path)
        except Exception:
            pass

    def _export_pattern(self):
        if self.cp is None:
            QMessageBox.warning(
                self, "No pattern", "Load or edit some colours before exporting."
            )
            return
        if self.overwrite.isChecked() and self.path:
            out = self.path
        else:
            default = (
                self.path or f"{self.cp.name or self.key + '_pattern'}.mcolorpattern"
            )
            out, _ = QFileDialog.getSaveFileName(
                self,
                f"Export {self.key} pattern",
                default,
                "Color pattern (*.mcolorpattern)",
            )
            if not out:
                return
            if not out.lower().endswith(".mcolorpattern"):
                out += ".mcolorpattern"
        try:
            self.cp.save(out)
            self.path = out
            self.pattern_edit.setText(out)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))

    def _export_texture(self):
        if Image is None:
            QMessageBox.warning(self, "Missing dependency", "Pillow is required.")
            return
        if self.cp is None:
            QMessageBox.warning(
                self, "No pattern", "Load or edit some colours before baking a texture."
            )
            return
        paths = {
            r: self.tex_edits[r].text().strip()
            for r in ("color", "material", "pattern")
        }
        need = [
            ("Base (_d)", "color"),
            ("Material (_m)", "material"),
            ("Pattern Coat (_pc)", "pattern"),
        ]
        missing = [
            name for name, r in need if not (paths[r] and os.path.isfile(paths[r]))
        ]
        if missing:
            QMessageBox.warning(
                self,
                "Missing textures",
                "These textures must be loaded to bake the result:\n- "
                + "\n- ".join(missing),
            )
            return
        try:
            col = load_rgba(paths["color"])
            h, w = col.shape[:2]

            def load_to(p):
                arr = load_rgba(p)
                if arr.shape[0] != h or arr.shape[1] != w:
                    arr = np.asarray(
                        Image.fromarray(arr, "RGBA").resize((w, h), Image.BILINEAR)
                    )
                return arr.astype(np.float32) / 255.0

            colf = col.astype(np.float32) / 255.0
            matf = load_to(paths["material"])
            patf = load_to(paths["pattern"])
            pal = palette_from_pattern(self.cp)
            if self.ctrl is not None:
                out = recolor(
                    colf,
                    matf,
                    patf,
                    pal,
                    invert1=self.ctrl.invert1,
                    invert2=self.ctrl.invert2,
                    level1=self.ctrl.level1,
                    level2=self.ctrl.level2,
                )
            else:
                out = recolor(colf, matf, patf, pal)
            img8 = (np.clip(out, 0.0, 1.0) * 255.0 + 0.5).astype(np.uint8)
        except Exception as e:
            QMessageBox.warning(self, "Bake failed", str(e))
            return
        base = os.path.splitext(os.path.basename(paths["color"]))[0]
        default = os.path.join(
            os.path.dirname(paths["color"]), base + "_recoloured.png"
        )
        out_path, _ = QFileDialog.getSaveFileName(
            self, f"Export {self.key} texture", default, "PNG image (*.png)"
        )
        if not out_path:
            return
        if not out_path.lower().endswith(".png"):
            out_path += ".png"
        try:
            Image.fromarray(img8, "RGB").save(out_path)
            QMessageBox.information(
                self, "Exported", f"Saved recoloured texture:\n{out_path}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))


class SlotRow(QWidget):
    """One expected-asset row: status mark, label, Select button, resolved path, in-game hint."""

    def __init__(self, slot, label, hint, tier, on_pick):
        super().__init__()
        self.slot, self.hint, self.tier = slot, hint, tier
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 6)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(8)
        self.mark = QLabel("\u2013")
        self.mark.setFixedWidth(16)
        name = QLabel(label + ("" if tier == "required" else f"  ({tier})"))
        self.pick = QPushButton("Select file\u2026")
        self.pick.setFixedHeight(26)
        self.pick.clicked.connect(lambda: on_pick(self.slot))
        top.addWidget(self.mark)
        top.addWidget(name, 1)
        top.addWidget(self.pick)
        v.addLayout(top)
        self.path_lbl = QLabel()
        self.path_lbl.setObjectName("legend")
        self.path_lbl.setWordWrap(True)
        self.path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        v.addWidget(self.path_lbl)
        game = assets.GAME_PATH.get(slot)
        if game:
            gl = QLabel("in game:  \u2026/" + game)
            gl.setObjectName("gamepath")
            gl.setWordWrap(True)
            gl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(gl)

    def update_state(self, path):
        if path and os.path.isfile(path):
            self.mark.setText("\u2713")
            self.mark.setStyleSheet("color:#5ed9ff")
            self.path_lbl.setText(path)
            self.path_lbl.setStyleSheet("color:#5ed9ff")
        elif path:  # set but missing on disk
            self.mark.setText("\u2717")
            self.mark.setStyleSheet("color:#ff6b6b")
            self.path_lbl.setText(path + "   (file not found)")
            self.path_lbl.setStyleSheet("color:#ff6b6b")
        else:
            self.mark.setText("\u2717" if self.tier == "required" else "\u2013")
            self.mark.setStyleSheet(
                "color:#ff6b6b" if self.tier == "required" else "color:#8a93a6"
            )
            self.path_lbl.setText("not selected")
            self.path_lbl.setStyleSheet("color:#6b7488")


class SetupDialog(QDialog):
    """Asset setup: add an export folder to search recursively, or pick each file by hand. Paths are referenced, not copied; used as a startup gate (require=True) or re-opened later."""

    def __init__(self, require=True, parent=None):
        super().__init__(parent)
        self.require = require
        self.cfg = assets.load_config()
        self.paths = dict(self.cfg.get("paths", {}))
        self.models = list(self.cfg.get("models", []))
        self.setWindowTitle("Banshee Brush  -  Game Assets")
        self.setMinimumSize(560, 520)
        self.resize(700, 860)
        self.setAcceptDrops(True)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        intro = QLabel(
            "Banshee Brush ships no game files. Point it at your own extracted "
            "Avatar: Frontiers of Pandora assets. Nothing is copied \u2014 the tool just "
            "remembers where your files are."
        )
        intro.setWordWrap(True)
        v.addWidget(intro)

        # ---- Section A: export folder
        secA = QLabel("Add Export Folder")
        secA.setObjectName("subtitle")
        v.addWidget(secA)
        folder_btn = QPushButton("Add Export Folder\u2026")
        folder_btn.clicked.connect(self._add_export_folder)
        fr = QHBoxLayout()
        fr.addWidget(folder_btn)
        fr.addStretch(1)
        v.addLayout(fr)
        capA = QLabel(
            "Recursively searches your extracted mod / export folder and fills "
            "in every banshee file it can find (prefers .dds, falls back to .png)."
        )
        capA.setWordWrap(True)
        v.addWidget(capA)

        # ---- OR divider
        orrow = QHBoxLayout()
        for _ in range(2):
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setStyleSheet("color:#39435a")
            orrow.addWidget(line, 1)
        orlbl = QLabel("  OR  ")
        orlbl.setObjectName("legend")
        orrow.insertWidget(1, orlbl)
        v.addLayout(orrow)

        # ---- Section B: per-file selection
        secB = QLabel("Add files individually")
        secB.setObjectName("subtitle")
        v.addWidget(secB)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 8, 0)
        iv.setSpacing(2)
        self.rows = {}
        for slot, label, hint, tier in assets.SLOTS:
            row = SlotRow(slot, label, hint, tier, self._pick_one)
            self.rows[slot] = row
            iv.addWidget(row)
        iv.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)

        # ---- footer
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.quit_btn = QPushButton("Quit" if require else "Cancel")
        self.quit_btn.clicked.connect(self.reject)
        self.ok_btn = QPushButton("Continue" if require else "Save")
        self.ok_btn.setObjectName("accent")
        self.ok_btn.clicked.connect(self.accept)
        foot.addWidget(self.quit_btn)
        foot.addWidget(self.ok_btn)
        v.addLayout(foot)
        self._refresh()

    # ---- behaviour
    def _refresh(self):
        for slot, row in self.rows.items():
            row.update_state(self.paths.get(slot))
        missing = assets.missing_required(self.paths)
        self.ok_btn.setEnabled(not (self.require and missing))
        self.ok_btn.setToolTip("Add the required assets to continue" if missing else "")

    def accept(self):
        # selections are only written to disk when Continue/Save is pressed
        self.cfg["paths"] = {k: v for k, v in self.paths.items() if v}
        self.cfg["models"] = self.models
        assets.save_config(self.cfg)
        super().accept()

    def _set(self, slot, path):
        self.paths[slot] = path
        self._refresh()

    def _pick_one(self, slot):
        start = next(
            (
                os.path.dirname(p)
                for p in self.paths.values()
                if p and os.path.isdir(os.path.dirname(p))
            ),
            "",
        )
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select " + assets.SLOT_HINT.get(slot, "file"),
            start,
            assets.slot_filter(slot),
        )
        if path:
            self._set(slot, path)

    def _add_export_folder(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose your extracted mod / export folder"
        )
        if not d:
            return
        slots, models = assets.scan_folder(d)
        for slot, p in slots.items():  # folder fills what it finds
            self.paths[slot] = p
        if models:
            self.models = models
        self._refresh()
        if not slots:
            QMessageBox.information(
                self,
                "Nothing found",
                "No recognised banshee assets were found in that folder.",
            )

    def _drop_paths(self, paths):
        for p in paths:
            if os.path.isdir(p):
                slots, models = assets.scan_folder(p)
                self.paths.update(slots)
                if models:
                    self.models = models
            elif os.path.isfile(p):
                slot = assets.classify(os.path.basename(p))
                if slot:
                    self.paths[slot] = p
                    if slot == "model" and p not in self.models:
                        self.models.append(p)
        self._refresh()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self._drop_paths(paths)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Banshee Brush  -  AFoP Skin Recolour")
        self.resize(1180, 760)
        self.setAcceptDrops(True)
        from viewer import BansheeViewer
        from app_icon import app_icon

        self.setWindowIcon(app_icon())
        self.viewer = BansheeViewer()

        self.head = PatternPanel(
            "Head", "head", self._palette_changed, self.open_texture
        )
        self.body = PatternPanel(
            "Body", "body", self._palette_changed, self.open_texture
        )
        self._coat_engine = {"body": "", "head": ""}  # engine paths of set-loaded coats
        self._pset_path = None  # path of a loaded .mbansheepatterndata (None if none)
        self._pset_data = None  # the loaded BansheePatternData (for in-place overwrite)

        controls = QWidget()
        controls.setMaximumWidth(640)
        col = QVBoxLayout(controls)
        col.setContentsMargins(8, 8, 8, 8)
        col.setSpacing(8)

        # ---- pattern-set loader, above the Head/Body panels ----
        pdbox = QGroupBox("Load Banshee Pattern Data")
        pdl = QVBoxLayout(pdbox)
        pdl.setContentsMargins(10, 6, 10, 8)
        pdl.setSpacing(5)
        pdrow = QHBoxLayout()
        pdrow.setSpacing(6)
        pdbtn = QPushButton("Browse...")
        pdbtn.setFixedWidth(86)
        pdbtn.setToolTip(
            "Load a .mbansheepatterndata - applies its body/head colours, "
            "controls and pattern coats at once"
        )
        pdbtn.clicked.connect(self._load_pattern_set)
        self.pset_edit = QLineEdit()
        self.pset_edit.setPlaceholderText(".mbansheepatterndata path (optional)")
        self.pset_edit.setToolTip(
            "Path to a .mbansheepatterndata - type a path and press Enter"
        )
        self.pset_edit.returnPressed.connect(self._load_pattern_set_entered)
        pdrow.addWidget(pdbtn)
        pdrow.addWidget(self.pset_edit, 1)
        pdl.addLayout(pdrow)
        hint = QLabel(
            "Optional: load an existing .mbansheepatterndata here to auto-fill every "
            "field below. The colour patterns, controls and coat .dds it references are "
            "found automatically alongside it (same folder or a sub-folder, blue/\u2026 "
            "layout). Otherwise, fill each section in by hand."
        )
        hint.setObjectName("legend")
        hint.setWordWrap(True)
        pdl.addWidget(hint)
        col.addWidget(pdbox)

        panels = QHBoxLayout()
        panels.setSpacing(8)
        panels.addWidget(self.head)
        arrows = QVBoxLayout()
        arrows.setSpacing(8)
        arrows.addStretch(1)
        to_body = QPushButton("\u2192")
        to_body.setObjectName("arrow")
        to_body.setFixedSize(38, 38)
        to_body.setToolTip("Copy Head colours into Body")
        to_body.clicked.connect(lambda: self._copy_from_other("body"))
        to_head = QPushButton("\u2190")
        to_head.setObjectName("arrow")
        to_head.setFixedSize(38, 38)
        to_head.setToolTip("Copy Body colours into Head")
        to_head.clicked.connect(lambda: self._copy_from_other("head"))
        arrows.addWidget(to_body)
        arrows.addWidget(to_head)
        arrows.addStretch(1)
        panels.addLayout(arrows)
        panels.addWidget(self.body)
        col.addLayout(panels, 1)
        expbox = QGroupBox("Export")
        ebl = QVBoxLayout(expbox)
        ebl.setContentsMargins(10, 8, 10, 8)
        ebl.setSpacing(7)
        namerow = QHBoxLayout()
        namerow.setSpacing(6)
        nlbl = QLabel("Pattern name")
        nlbl.setObjectName("subtitle")
        self.pattern_name = QLineEdit()
        self.pattern_name.setPlaceholderText("export folder name")
        self.pattern_name.setToolTip(
            "Names the export folder - a blue/gameplay/vanity/juice "
            "tree is created inside it and the files (with their "
            "original names) are written there. Greyed out when "
            "overwriting in place."
        )
        namerow.addWidget(nlbl)
        namerow.addWidget(self.pattern_name, 1)
        ebl.addLayout(namerow)

        self._ov_guard = False
        self.ov_master = QCheckBox("Overwrite existing pattern files")
        self.ov_master.setToolTip(
            "Save over the loaded files in place (colour patterns, "
            "controls and Banshee Pattern Data). Ticks and locks the "
            "per-panel overwrites and both export options below, and "
            "disables the folder name. Needs both colour patterns loaded."
        )
        self.ov_master.toggled.connect(self._on_master_overwrite)
        ebl.addWidget(self.ov_master)

        self.exp_ctrl_cb = QCheckBox("Export Pattern Control (.mpatterncontrol) files")
        self.exp_ctrl_cb.setToolTip(
            "Also write the Body and Head pattern controls with the "
            "current Level/Invert values (names, uids and file names "
            "preserved). Needs a control loaded in both panels."
        )
        ebl.addWidget(self.exp_ctrl_cb)

        self.exp_pd_cb = QCheckBox("Export Banshee Pattern Data (.mbansheepatterndata)")
        self.exp_pd_cb.setToolTip(
            "Also write the loaded Banshee Pattern Data, preserving its "
            "name/uids/references and updating only the coat paths. "
            "Needs one loaded."
        )
        ebl.addWidget(self.exp_pd_cb)

        export = QPushButton("Export All Patterns")
        export.setObjectName("accent")
        export.setFixedHeight(32)
        export.setToolTip("Save both colour patterns (plus any ticked extras above)")
        export.clicked.connect(self.export_all)
        ebl.addWidget(export)
        col.addWidget(expbox)

        self.export_all_btn = export
        self._export_all_tip = export.toolTip()
        self.body.overwrite.toggled.connect(self._on_child_overwrite)
        self.head.overwrite.toggled.connect(self._on_child_overwrite)
        self.body.on_validity_change = self._refresh_export_all
        self.head.on_validity_change = self._refresh_export_all
        self._refresh_export_all()

        # right pane: model path bar + legend (top) | viewer | animation picker (bottom)
        right = QWidget()
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(8, 8, 8, 8)
        rcol.setSpacing(8)
        modelrow = QHBoxLayout()
        modelrow.setSpacing(8)
        mlbl = QLabel("Model")
        mlbl.setObjectName("subtitle")
        self.model_path_edit = QLineEdit()
        self.model_path_edit.setFixedHeight(30)
        self.model_path_edit.setPlaceholderText("path to a .mmb / .cast model")
        self.model_path_edit.setToolTip(
            "Path to the displayed model - type a path and press Enter to load"
        )
        self.model_path_edit.returnPressed.connect(self._model_path_entered)
        browse = QPushButton("Browse...")
        browse.setFixedHeight(30)
        browse.setToolTip("Browse for a model file (.mmb / .cast)")
        browse.clicked.connect(self._browse_model)
        manage = QPushButton("Assets...")
        manage.setFixedHeight(30)
        manage.setToolTip("Import / review your extracted game assets")
        manage.clicked.connect(self._manage_assets)
        modelrow.addWidget(mlbl)
        modelrow.addWidget(self.model_path_edit, 1)
        modelrow.addWidget(browse)
        modelrow.addWidget(manage)
        rcol.addLayout(modelrow)
        legend = QLabel("Orbit   LMB        Pan   MMB        Zoom   Wheel")
        legend.setObjectName("legend")
        legend.setAlignment(Qt.AlignmentFlag.AlignCenter)
        legend.setFixedHeight(30)
        rcol.addWidget(legend)
        rcol.addWidget(self.viewer, 1)

        split = QSplitter()
        split.addWidget(controls)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([600, 560])
        self.setCentralWidget(split)

        self._autoload()

    # ---------------- load from the configured (referenced) asset paths ----------------
    def _autoload(self):
        cfg = assets.load_config()
        slots = dict(cfg.get("paths", {}))
        found, failed = [], []
        stale = assets.invalid_paths(slots)
        tex_slots = {
            "body_color": ("body", "color"),
            "body_material": ("body", "material"),
            "body_pattern": ("body", "pattern"),
            "head_color": ("head", "color"),
            "head_material": ("head", "material"),
            "head_pattern": ("head", "pattern"),
            "body_normal": ("body", "normal"),
            "head_normal": ("head", "normal"),
            "body_dn_mask": ("body", "dn_mask"),
            "head_dn_mask": ("head", "dn_mask"),
            "detail1": ("shared", "detail1"),
            "detail2": ("shared", "detail2"),
            "detail3": ("shared", "detail3"),
            "wing_color": ("wing", "color"),
            "eye_color": ("eye", "color"),
        }
        panels = {"body": self.body, "head": self.head}

        # 1) reflect every configured path in the UI first, independent of whether
        #    the file loads/decodes (so the boxes always mirror the config).
        model_path = slots.get("model")
        if model_path:
            self.model_path_edit.setText(model_path)
        for slot, (key, role) in tex_slots.items():
            p = slots.get(slot)
            panel = panels.get(key)
            if p and panel is not None and role in ("color", "material", "pattern"):
                panel.set_texture_path(role, p)

        # 2) load the model into the viewer
        if model_path and os.path.isfile(model_path):
            try:
                self.viewer.load_model(model_path)
                found.append(os.path.basename(model_path))
            except Exception as e:
                failed.append(f"model ({e})")

        # 3) load textures into the viewer
        for slot, (key, role) in tex_slots.items():
            p = slots.get(slot)
            if not p or not os.path.isfile(p):
                continue
            try:
                self.viewer.set_texture(key, role, load_rgba(p))
                found.append(f"{key}/{role}")
            except Exception:
                failed.append(f"{key}/{role}")

        if stale:
            labels = ", ".join(assets.SLOT_HINT.get(s, s) for s in stale)
            self.statusBar().showMessage(
                f"Some files have moved or been deleted ({labels}). Open Assets... to relink.",
                0,
            )
        elif failed:
            self.statusBar().showMessage(
                "Could not read: "
                + ", ".join(failed)
                + "   (for .dds, check that texture2ddecoder is installed)",
                0,
            )
        elif found:
            self.statusBar().showMessage("Loaded: " + ", ".join(found), 9000)
        else:
            self.statusBar().showMessage(
                "No assets loaded. Use the Assets... button to add your extracted files."
            )

    def _assets_dir(self):
        cfg = assets.load_config()
        for p in cfg.get("paths", {}).values():
            if p and os.path.isdir(os.path.dirname(p)):
                return os.path.dirname(p)
        return ""

    # ---------------- asset setup (button + drag-and-drop) ----------------
    def _manage_assets(self):
        SetupDialog(require=False, parent=self).exec()
        self._autoload()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if not paths:
            return
        cfg = assets.load_config()
        pm = dict(cfg.get("paths", {}))
        models = list(cfg.get("models", []))
        n = 0
        for p in paths:
            if os.path.isdir(p):
                s, m = assets.scan_folder(p)
                pm.update(s)
                n += len(s)
                if m:
                    models = m
            elif os.path.isfile(p):
                slot = assets.classify(os.path.basename(p))
                if slot:
                    pm[slot] = p
                    n += 1
                    if slot == "model" and p not in models:
                        models.append(p)
        cfg["paths"] = pm
        cfg["models"] = models
        assets.save_config(cfg)
        self._autoload()
        self.statusBar().showMessage(
            f"Linked {n} file(s)." if n else "No matching assets found.", 6000
        )

    # ---------------- model selection ----------------
    def _browse_model(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open model",
            self._assets_dir(),
            "Model (*.mmb *.cast);;MMB (*.mmb);;Cast (*.cast)",
        )
        if path:
            self._activate_model(path)

    def _model_path_entered(self):
        path = self.model_path_edit.text().strip()
        if not path:
            return
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Not found", f"No file at:\n{path}")
            return
        self._activate_model(path)

    def _activate_model(self, path):
        try:
            self.viewer.load_model(path)
        except Exception as e:
            QMessageBox.warning(self, "Model load failed", str(e))
            return
        self.model_path_edit.setText(path)
        self.statusBar().showMessage(f"Loaded {os.path.basename(path)}", 4000)

    def open_texture(self, key, role, path=None):
        if Image is None:
            QMessageBox.warning(
                self, "Missing dependency", "Pillow is required to load textures."
            )
            return None
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"{key} {role} texture",
                self._assets_dir(),
                "Images (*.png *.tga *.dds *.jpg)",
            )
            if not path:
                return None
        if not os.path.isfile(path):
            QMessageBox.warning(self, "Not found", f"No file at:\n{path}")
            return None
        try:
            self.viewer.set_texture(key, role, load_rgba(path))
            self.statusBar().showMessage(
                f"Loaded {key} {role}: {os.path.basename(path)}", 5000
            )
            return path
        except Exception as e:
            QMessageBox.warning(self, "Texture load failed", str(e))
            return None

    def _load_pattern_set_entered(self):
        p = self.pset_edit.text().strip()
        if p:
            self._load_pattern_set(path=p)

    def _load_pattern_set(self, checked=False, path=None):
        """Load a .mbansheepatterndata and apply its colour patterns, controls and coats, resolving each member via assets.find_related."""
        if not path:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open pattern set",
                self._assets_dir(),
                "Banshee pattern data (*.mbansheepatterndata)",
            )
        if not path:
            return
        try:
            data = BansheePatternData.load(path)
        except Exception as e:
            QMessageBox.warning(self, "Pattern set load failed", str(e))
            return
        self.pset_edit.setText(path)
        self._pset_path, self._pset_data = path, data
        members = data.member_paths()
        panels = {"body": self.body, "head": self.head}
        # The colour patterns + controls are what a successful find needs; the pattern
        # coats (_pc) usually live under blue/baked and may be absent - they're optional.
        applied, missing_req, missing_coat = [], [], []

        def resolve(part, role, bucket):
            ep = members.get((part, role))
            if not ep:
                return None, None
            real = assets.find_related(path, ep)
            if real is None:
                bucket.append(os.path.basename(ep))
            return ep, real

        # 1) colours
        for part in ("body", "head"):
            _ep, real = resolve(part, "color", missing_req)
            if real:
                try:
                    panels[part].set_pattern(ColorPattern.load(real), real)
                    applied.append(f"{part} colours")
                except Exception:
                    missing_req.append(os.path.basename(real))
        # 2) controls (fill the Pattern Control fields)
        for part in ("body", "head"):
            _ep, real = resolve(part, "control", missing_req)
            if real:
                try:
                    panels[part].set_control(PatternControl.load(real), real)
                    applied.append(f"{part} control")
                except Exception:
                    missing_req.append(os.path.basename(real))
        # 3) pattern coats (the _pc this set uses) - optional, never fails the find
        for part in ("body", "head"):
            ep, real = resolve(part, "coat", missing_coat)
            if real:
                try:
                    self.viewer.set_texture(part, "pattern", load_rgba(real))
                    panels[part].set_texture_path("pattern", real)
                    self._coat_engine[part] = ep  # remember the engine path
                    applied.append(f"{part} coat")
                except Exception:
                    missing_coat.append(os.path.basename(real))

        msg = f"Pattern set '{data.name}': " + (
            ", ".join(applied) if applied else "nothing applied"
        )
        if missing_coat and not missing_req:
            msg += (
                "  -  pattern coats not found (load the _pc textures by hand if needed)"
            )
        self.statusBar().showMessage(msg, 0 if missing_req else 8000)
        self._refresh_export_all()  # manifest now loaded -> pattern-data export enabled
        if missing_req:
            QMessageBox.warning(
                self,
                "Pattern set",
                "Unable to find related files. You will need to manually populate the "
                "data below or choose an .mbansheepatterndata in the correct location.",
            )

    def _palette_changed(self, key, palette, params):
        self.viewer.set_palette(key, palette, params)

    def _copy_from_other(self, key):
        src = self.body if key == "head" else self.head
        dst = self.head if key == "head" else self.body
        if src.cp is None:
            self.statusBar().showMessage(
                "Nothing to copy - the other panel has no pattern.", 4000
            )
            return
        for i in range(10):
            dst.rows[i].set_hex(src.cp.rgb_hex(i), notify=True)
        other = "Body" if key == "head" else "Head"
        self.statusBar().showMessage(
            f"Copied {other} colours into {key.title()}.", 4000
        )

    def _refresh_export_all(self):
        body_loaded, head_loaded = bool(self.body.path), bool(self.head.path)
        ok = self.body.all_valid() and self.head.all_valid()
        ctrl_ready = (
            ok and bool(self.body.control_path) and bool(self.head.control_path)
        )
        pd_ready = ok and bool(self._pset_path)

        self._ov_guard = True
        # master is available once both colour patterns are loaded
        self.ov_master.setEnabled(body_loaded and head_loaded)
        if not self.ov_master.isEnabled() and self.ov_master.isChecked():
            self.ov_master.setChecked(False)
        master_on = self.ov_master.isChecked()
        # per-panel overwrite: master forces them ticked + greyed; otherwise per loaded
        for ov, loaded in (
            (self.body.overwrite, body_loaded),
            (self.head.overwrite, head_loaded),
        ):
            if master_on:
                ov.setChecked(True)
                ov.setEnabled(False)
            else:
                ov.setEnabled(loaded)
                if not loaded and ov.isChecked():
                    ov.setChecked(False)
        # the two extra-export tickboxes: master forces both ticked + greyed
        if master_on:
            for cb in (self.exp_ctrl_cb, self.exp_pd_cb):
                cb.setChecked(True)
                cb.setEnabled(False)
        else:
            self.exp_ctrl_cb.setEnabled(ctrl_ready)
            if not ctrl_ready and self.exp_ctrl_cb.isChecked():
                self.exp_ctrl_cb.setChecked(False)
            self.exp_pd_cb.setEnabled(pd_ready)
            if not pd_ready and self.exp_pd_cb.isChecked():
                self.exp_pd_cb.setChecked(False)
        self._ov_guard = False

        # a pattern name (output folder) is only used for a new-directory export
        self.pattern_name.setEnabled(not master_on)
        self.export_all_btn.setEnabled(ok)
        self.export_all_btn.setToolTip(
            self._export_all_tip
            if ok
            else "Every Head and Body colour must be a valid 6-digit hex code"
        )

    def _on_child_overwrite(self, *_):
        if self._ov_guard:
            return
        self._refresh_export_all()

    def _on_master_overwrite(self, checked):
        if self._ov_guard:
            return
        self._ov_guard = True
        if checked:
            for ov in (self.body.overwrite, self.head.overwrite):
                ov.setChecked(True)
        self._ov_guard = False
        self._refresh_export_all()

    def export_all(self):
        panels = [(self.body, "body"), (self.head, "head")]
        todo = [(p, key) for (p, key) in panels if p.cp is not None]
        want_ctrl = self.exp_ctrl_cb.isChecked()
        want_pd = self.exp_pd_cb.isChecked()
        if not todo and not want_ctrl and not want_pd:
            self.statusBar().showMessage("Nothing to export.", 4000)
            return
        ow = self.ov_master.isChecked() and self.ov_master.isEnabled()
        # Overwrite writes back over the loaded files; otherwise everything is written into a
        # new <name>/blue/gameplay/vanity/juice/ tree. Either way the names, uids and file
        # names are preserved exactly - only colours, control values and the coat paths differ.
        col_over, col_new = [], []
        for p, key in todo:
            (col_over if (p.overwrite.isChecked() and p.path) else col_new).append(
                (p, key)
            )
        ctrl_over = ow
        pd_over = ow
        need_dest = (
            bool(col_new) or (want_ctrl and not ctrl_over) or (want_pd and not pd_over)
        )
        juice = None
        if need_dest:
            name = self.pattern_name.text().strip()
            if not name:
                QMessageBox.warning(
                    self,
                    "Pattern name needed",
                    "Enter a pattern name for the export folder.",
                )
                return
            parent = QFileDialog.getExistingDirectory(
                self, "Choose a folder to export into"
            )
            if not parent:
                return
            juice = os.path.join(parent, name, "blue", "gameplay", "vanity", "juice")
            try:
                os.makedirs(juice, exist_ok=True)
            except OSError as e:
                QMessageBox.warning(
                    self, "Export failed", f"Could not create folder:\n\n{e}"
                )
                return
        written, notes = [], []
        try:
            for p, key in col_over:
                p.cp.save(p.path)
                written.append(os.path.basename(p.path))
            for p, key in col_new:
                base = (
                    os.path.basename(p.path) if p.path else f"{key}_color.mcolorpattern"
                )
                out = os.path.join(juice, base)
                p.cp.save(out)
                written.append(os.path.basename(out))
            if want_ctrl:
                written += self._write_pattern_controls(juice, ctrl_over)
            if want_pd:
                fn, note = self._write_pattern_data(juice, pd_over)
                if fn:
                    written.append(fn)
                if note:
                    notes.append(note)
        except Exception as e:
            QMessageBox.warning(
                self, "Export failed", f"The export did not complete:\n\n{e}"
            )
            self.statusBar().showMessage("Export failed.", 6000)
            return
        if not written:
            QMessageBox.information(self, "Export", "Nothing was exported.")
            self.statusBar().showMessage("Nothing exported.", 4000)
            return
        body = "Export successful.\n\nWrote:\n  " + "\n  ".join(written)
        if juice:
            body += f"\n\nInto: {juice}"
        if want_pd:
            body += (
                "\n\nCheck that myBodyPatternCoat and myHeadPatternCoat in the "
                ".mbansheepatterndata match the location of your pattern-coat textures "
                "in your blue directory."
            )
        if notes:
            body += "\n\n" + "; ".join(notes)
        QMessageBox.information(self, "Export successful", body)
        self.statusBar().showMessage("Exported: " + ", ".join(written), 8000)

    def _coat_engine_path(self, part, panel):
        """Engine path ('blue/...') for a panel's pattern coat: derive from the loaded _pc path if it sits in a 'blue/' tree, else the loaded set's path, else None."""
        p = panel.tex_edits["pattern"].text().strip().replace("\\", "/")
        low = p.lower()
        i = low.rfind("/blue/")
        if i != -1:
            return p[i + 1 :]
        if low.startswith("blue/"):
            return p
        return self._coat_engine.get(part) or None

    def _write_pattern_controls(self, juice, overwrite):
        """Write Body and Head pattern controls, preserving name/uid/filename (only Level/Invert change). Overwrite writes over the loaded file, else into `juice`."""
        written = []
        for panel, part in ((self.body, "body"), (self.head, "head")):
            if not panel.control_path:
                continue
            ctrl = panel.current_control()  # loaded name/uid + current field values
            out = (
                panel.control_path
                if overwrite
                else os.path.join(juice, os.path.basename(panel.control_path))
            )
            ctrl.save(out)
            written.append(os.path.basename(out))
        return written

    def _write_pattern_data(self, juice, overwrite):
        """Write the loaded .mbansheepatterndata, preserving name/uid/sub-uids/references; only the coat paths are refreshed. Overwrite saves over the loaded file, else into `juice`."""
        if self._pset_data is None or not self._pset_path:
            return None, "pattern data skipped (load a .mbansheepatterndata first)"
        for key, part, panel in (
            ("myBodyPatternCoat", "body", self.body),
            ("myHeadPatternCoat", "head", self.head),
        ):
            ep = self._coat_engine_path(part, panel)
            if ep:
                self._pset_data.coats[key] = ep
        out = (
            self._pset_path
            if overwrite
            else os.path.join(juice, os.path.basename(self._pset_path))
        )
        self._pset_data.save(out)
        return os.path.basename(out), None


def main():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
    fmt.setDepthBufferSize(24)
    QSurfaceFormat.setDefaultFormat(fmt)

    app = QApplication(sys.argv)
    app.setApplicationName("BansheeBrush")
    app.setStyleSheet(QSS)
    from app_icon import app_icon

    app.setWindowIcon(app_icon())

    cfg = assets.load_config()
    if assets.missing_required(cfg.get("paths", {})):  # first run / incomplete -> gate
        if SetupDialog(require=True).exec() != QDialog.DialogCode.Accepted:
            sys.exit(0)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
