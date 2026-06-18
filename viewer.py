"""moderngl viewport embedded in a PyQt6 QOpenGLWidget.

Starts empty; model and textures load at runtime via load_model(path) and
set_texture(key, role, np_rgba). Body/Head meshes use the recolour shader, others render flat.
Colours update live via set_palette(); orbit = LMB drag, zoom = wheel.
"""

from __future__ import annotations
import numpy as np
import moderngl
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

import gl_shaders as gs
import cast_loader as cl

RECOLOUR_MESHES = {"Banshee_Body": "body", "Banshee_Head": "head"}


# Which texture atlas every non-recolour mesh samples. Per the engine graph object,
# wings use the shared insect-wing texture (DragonflyWing shader) and eyes use the eye
# textures (Eye shader) - NOT the body/head skin atlas. Head_part is inner-mouth head
# skin; the weakpoint is a body skin patch.
ATLAS_OF = {
    "Banshee_Head_part": "head",
    "Banshee_weakpoint": "body",
    "Banshee_SmallEyes": "eye",
    "Banshee_Eyes": "eye",
    "Banshee_Wing": "wing",  # MMB merges the two wings into one mesh
    "Banshee_Wing1": "wing",  # cast/fbx split them
    "Banshee_Wing2": "wing",
}


class BansheeViewer(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        fmt = self.format()
        fmt.setSamples(4)  # 4x MSAA - antialias thin membrane edges / transparency
        self.setFormat(fmt)
        self.ctx = None
        self.prog = None
        self.grid_prog = None
        self.grid_vao = None
        self.grid_vbo = None
        self.floor_y = 0.0
        self.synth = None  # shared synthetic pattern texture
        self.gl_objs = []  # (vao,vbo,ibo,name,key)
        self.tex = {
            "body": {},
            "head": {},
            "wing": {},
            "eye": {},
        }  # key -> role -> Texture
        self.palettes = {"body": [(0, 0, 0)] * 10, "head": [(0, 0, 0)] * 10}
        # neutral defaults: invert2=0 keeps the pre-load surface on Coat 1 (no splotch);
        # the real per-skin constants are resolved from the colour pattern on load.
        self.params = {
            k: dict(invert1=1.0, invert2=0.0, level1=1.0, level2=1.0)
            for k in ("body", "head")
        }
        self.center = np.zeros(3, np.float32)
        self.radius = 1.0
        self.az, self.el, self.dist = 35.0, 12.0, 3.0
        self.pan = np.zeros(3, np.float32)
        self.flip_v = False
        # normal-mapping controls (tweak if detail reads inverted / too strong).
        # normal_strength = base _n shape; detail_weight = tiled micro-grain overlay.
        # Both were 1.0 (raw game values); dialled down because the combined base +
        # 3 detail layers read too strong. Raise toward 1.0 for more relief.
        self.detail_tiling = (8.0, 8.0, 8.0)  # UV tiling per skin_detail normal
        self.normal_strength = 0.5  # base-normal (_n) strength
        self.detail_weight = 0.35  # overall detail-normal strength
        self.normal_yflip = -1.0  # DirectX-style green; flip to +1 if inverted
        self._last = QPoint()
        self._w, self._h = 1, 1
        self._pending_model = None
        self._pending_tex = []

    # ---------------- public API ----------------
    def load_model(self, path):
        if self.ctx is None:
            self._pending_model = path
            return
        self.makeCurrent()
        self._build_meshes(path)
        self.doneCurrent()
        self.update()

    def set_texture(self, key, role, arr):
        arr = np.ascontiguousarray(arr)
        if self.ctx is None:
            self._pending_tex.append((key, role, arr))
            return
        self.makeCurrent()
        slot = self.tex.setdefault(key, {})
        if role in slot:
            slot[role].release()
        slot[role] = self._tex_from_np(arr)
        self.doneCurrent()
        self.update()

    def set_palette(self, key, palette, params=None):
        self.palettes[key] = [tuple(c) for c in palette]
        if params:
            self.params[key].update(params)
        self.update()

    def has_model(self):
        return bool(self.gl_objs)

    # ---------------- GL lifecycle ----------------
    def initializeGL(self):
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.DEPTH_TEST | moderngl.CULL_FACE)
        self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA)
        self.prog = self.ctx.program(
            vertex_shader=gs.VERTEX_SHADER, fragment_shader=gs.FRAGMENT_SHADER
        )
        self.synth = self._tex_from_np(gs.synthetic_pattern(512), mip=False)
        self.grid_prog = self.ctx.program(
            vertex_shader=gs.GRID_VERTEX_SHADER, fragment_shader=gs.GRID_FRAGMENT_SHADER
        )
        if self._pending_model:
            self._build_meshes(self._pending_model)
            self._pending_model = None
        for key, role, arr in self._pending_tex:
            slot = self.tex.setdefault(key, {})
            if role in slot:
                slot[role].release()
            slot[role] = self._tex_from_np(arr)
        self._pending_tex.clear()

    def _tex_from_np(self, arr, mip=True):
        h, w = arr.shape[:2]
        comp = arr.shape[2]
        t = self.ctx.texture((w, h), comp, arr.tobytes())
        t.repeat_x = t.repeat_y = True
        if mip:
            t.build_mipmaps()
            t.filter = (moderngl.LINEAR_MIPMAP_LINEAR, moderngl.LINEAR)
            t.anisotropy = 16.0  # reduce grazing-angle aliasing (membrane sparkle)
        else:
            t.filter = (moderngl.LINEAR, moderngl.LINEAR)
        return t

    def _build_meshes(self, path):
        for vao, vbo, ibo, *_ in self.gl_objs:
            vao.release()
            vbo.release()
            ibo.release()
        self.gl_objs.clear()
        meshes, _ = cl.load_model(path)
        self.center, self.radius = cl.model_bounds(meshes)
        self.floor_y = float(min(m.positions[:, 1].min() for m in meshes))
        self.dist = self.radius * 2.4
        self.pan = np.zeros(3, np.float32)
        self._build_grid()
        for m in meshes:
            inter = np.concatenate([m.positions, m.normals, m.uv0], 1).astype("f4")
            vbo = self.ctx.buffer(inter.tobytes())
            ibo = self.ctx.buffer(m.indices.astype("i4").tobytes())
            vao = self.ctx.vertex_array(
                self.prog,
                [(vbo, "3f 3f 2f", "in_pos", "in_nrm", "in_uv")],
                index_buffer=ibo,
            )
            key = RECOLOUR_MESHES.get(m.name)
            atlas = key or ATLAS_OF.get(m.name)  # which texture set to sample
            self.gl_objs.append((vao, vbo, ibo, m.name, key, atlas))

    def _build_grid(self):
        if self.grid_vao is not None:
            self.grid_vao.release()
            self.grid_vbo.release()
            self.grid_vao = self.grid_vbo = None
        data = gs.grid_lines(self.center, self.radius, self.floor_y)
        self.grid_vbo = self.ctx.buffer(data.tobytes())
        self.grid_vao = self.ctx.vertex_array(
            self.grid_prog, [(self.grid_vbo, "3f 3f", "in_pos", "in_col")]
        )

    def resizeGL(self, w, h):
        self._w, self._h = max(w, 1), max(h, 1)

    def paintGL(self):
        if self.ctx is None:
            return
        self.ctx.detect_framebuffer().use()
        self.ctx.clear(0.10, 0.11, 0.14, 1.0)
        if not self.gl_objs:
            return
        aspect = self._w / self._h
        M, _ = gs.mvp(
            self.center, self.az, self.el, self.dist, aspect, self.radius, self.pan
        )
        if self.grid_vao is not None:
            self.grid_prog["uMVP"].write(np.ascontiguousarray(M.T))
            self.grid_vao.render(moderngl.LINES)
        self.prog["uMVP"].write(np.ascontiguousarray(M.T))
        self.prog["uNormalMat"].write(np.eye(3, dtype="f4").tobytes())
        self.prog["uLightDir"].value = (-0.4, -0.7, -0.55)
        self.prog["uFlipV"].value = 1.0 if self.flip_v else 0.0
        self.prog["uColor"].value = 0
        self.prog["uMaterial"].value = 1
        self.prog["uPatternCoat"].value = 2
        self.prog["uNormalTex"].value = 4
        self.prog["uDetail1"].value = 5
        self.prog["uDetail2"].value = 6
        self.prog["uDetail3"].value = 7
        self.prog["uDetailMask"].value = 8

        # opaque meshes first, then transparent ones (body membrane + wing) blended & two-sided
        transp = []
        for obj in self.gl_objs:
            if (
                obj[5] == "wing" or obj[4] == "body"
            ):  # wing mesh, or body (membrane in _d alpha)
                transp.append(obj)
                continue
            self._draw_mesh(obj, transparent=False)
        if transp:
            self.ctx.enable(moderngl.BLEND)
            self.ctx.disable(moderngl.CULL_FACE)  # membrane visible from both sides
            for obj in transp:
                self._draw_mesh(obj, transparent=True)
            self.ctx.enable(moderngl.CULL_FACE)
            self.ctx.disable(moderngl.BLEND)

    def _draw_mesh(self, obj, transparent):
        vao, vbo, ibo, name, key, atlas = obj
        ts = self.tex.get(key, {})
        bts = self.tex.get("body", {})
        col = ts.get("color") or bts.get("color")  # head falls back to body
        mat = ts.get("material") or bts.get("material")
        pat = ts.get("pattern") or bts.get("pattern") or self.synth
        self.prog["uUseTexAlpha"].value = 1 if transparent else 0
        if key is not None and col is not None and mat is not None:
            col.use(0)
            mat.use(1)
            pat.use(2)
            self.prog["uRecolor"].value = 1
            self.prog["uTextured"].value = 0
            self.prog["uDesat"].value = (0.0, 0.0)
            self.prog["uColors"].write(np.array(self.palettes[key], "f4").tobytes())
            p = self.params[key]
            self.prog["uInvert1"].value = float(p["invert1"])
            self.prog["uInvert2"].value = float(p["invert2"])
            self.prog["uLevel1"].value = float(p["level1"])
            self.prog["uLevel2"].value = float(p["level2"])
            # normal maps: base (_n) + three shared tiling detail normals masked by _dn_mask
            nrm = ts.get("normal") or bts.get("normal")
            if nrm is not None:
                sh = self.tex.get("shared", {})
                d1 = sh.get("detail1")
                d2 = sh.get("detail2")
                d3 = sh.get("detail3")
                dmk = ts.get("dn_mask") or bts.get("dn_mask")
                nrm.use(4)
                (d1 or nrm).use(5)
                (d2 or nrm).use(6)
                (d3 or nrm).use(7)
                (dmk or nrm).use(8)
                self.prog["uUseNormalMap"].value = 1
                self.prog["uNormalStrength"].value = self.normal_strength
                self.prog["uDetailTiling"].value = self.detail_tiling
                have_detail = d1 is not None and dmk is not None
                self.prog["uDetailWeight"].value = (
                    self.detail_weight if have_detail else 0.0
                )
                self.prog["uNormalYFlip"].value = self.normal_yflip
            else:
                self.prog["uUseNormalMap"].value = 0
        else:
            self.prog["uUseNormalMap"].value = 0
            # non-recolour mesh: sample its atlas albedo if we have it, else flat grey
            acol = self.tex.get(atlas, {}).get("color") if atlas else None
            if acol is not None:
                acol.use(0)
                self.prog["uRecolor"].value = 0
                self.prog["uTextured"].value = 1
            else:
                self.prog["uRecolor"].value = 0
                self.prog["uTextured"].value = 0
                self.prog["uFlat"].value = (0.45, 0.44, 0.42)
        vao.render()

    # ---------------- interaction ----------------
    def mousePressEvent(self, e):
        self._last = e.position().toPoint()

    def mouseMoveEvent(self, e):
        p = e.position().toPoint()
        dx, dy = p.x() - self._last.x(), p.y() - self._last.y()
        self._last = p
        if e.buttons() & Qt.MouseButton.LeftButton:
            self.az -= dx * 0.4
            self.el = max(-89.0, min(89.0, self.el + dy * 0.4))
            self.update()
        elif e.buttons() & Qt.MouseButton.MiddleButton:
            s, u = gs.camera_basis(self.center + self.pan, self.az, self.el, self.dist)
            scale = self.dist / max(self._h, 1)
            self.pan = self.pan + (-dx * s + dy * u) * scale
            self.update()

    def wheelEvent(self, e):
        f = 0.9 if e.angleDelta().y() > 0 else 1.1
        self.dist = max(self.radius * 0.2, min(self.radius * 8, self.dist * f))
        self.update()
