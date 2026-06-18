"""Headless reader for Snowdrop .mmb skeletal-mesh assets.

Ported (read path, LOD0) from the AFoP Mesh Tool Blender addon (AlexPo, JasperZebra, J-Lyt,
SaintBaron) so it runs without Blender and returns the same SubMesh objects as cast_loader.
Supports versions 15/16/17; reads positions, uv0 and indices, recomputing normals from faces.
"""

from __future__ import annotations
import io
import struct
import numpy as np

from cast_loader import SubMesh  # identical SubMesh structure

FLIP_X = True  # match the cast/viewer orientation (engine X is mirrored)


class _R:
    """Cursor reader over a bytes buffer."""

    def __init__(self, buf):
        self.f = io.BytesIO(buf)

    def seek(self, o, w=0):
        self.f.seek(o, w)

    def tell(self):
        return self.f.tell()

    def read(self, n):
        return self.f.read(n)

    def u8(self):
        return self.f.read(1)[0]

    def i8(self):
        return struct.unpack("<b", self.f.read(1))[0]

    def u16(self):
        return struct.unpack("<H", self.f.read(2))[0]

    def i16(self):
        return struct.unpack("<h", self.f.read(2))[0]

    def u32(self):
        return struct.unpack("<I", self.f.read(4))[0]

    def f32(self):
        return struct.unpack("<f", self.f.read(4))[0]

    def name(self):
        n = self.u16()
        return self.f.read(n).decode("latin1").rstrip("\x00")

    def int16_norm(self):
        i = self.u16()
        v = (i ^ 0x8000) - 0x8000
        return v / 32767.0

    def int8_norm(self):
        i = self.u8()
        v = (i ^ 0x80) - 0x80
        return v / 127.0


class Mesh:
    def __init__(self):
        self.name = ""
        self.lods = []
        self.vertex_stride = 0
        self.normals_stride = 0
        self.uv_count = 0
        self.color_count = 0
        self.normal_type = 0
        self.position_type = 0
        self.color_in_normals = True


class LOD:
    pass


def _parse(buf):
    r = _R(buf)
    magic = r.read(3)
    if magic != b"MMB":
        raise ValueError("not an MMB file")
    version = r.u8()
    size = r.u32()
    if version >= 15:
        r.seek(4, 1)
    if version not in (15, 16, 17):
        raise ValueError(
            f"unsupported .mmb version {version} (this loader does 15/16/17)"
        )

    bone_count = r.u32()
    for _ in range(bone_count):  # skip skeleton: name + 4x4 matrix + parent
        r.name()
        r.seek(64, 1)
        r.u16()

    mesh_count = r.u32()
    meshes = []
    for _ in range(mesh_count):
        meshes.append(_parse_mesh(r, version, size))
    return version, size, meshes


def _parse_mesh(r, version, asset_size):
    m = Mesh()
    m.name = r.name()
    r.seek(48, 1)  # bind matrix-ish
    r.seek(1, 1)
    x_count = r.u8()
    r.seek(1 + 4 * x_count, 1)
    u_count = r.u16()
    for _ in range(u_count):  # per-influence 4x4 matrix + bone index
        r.seek(64, 1)
        r.u16()

    if u_count > 0:  # v15/16/17
        r.seek(2, 1)  # root_bone_index
        lod_info_type = r.u8()
    else:
        lod_info_type = r.u8()

    lod_count = r.u8()
    r.seek(4, 1)
    for li in range(lod_count):
        lod = LOD()
        lod.index = li
        lod.vertex_count = r.u32()
        lod.index_count = r.u32()
        lod.size_a = r.u32()
        lod.vertex_data_offset_a = r.u32()
        lod.vertex_data_offset_b = r.u32()
        lod.face_block_offset = r.u32()
        lod.data_offset = r.u32()
        lod.data_size = r.u32()
        lod.screen_size = r.f32()
        if lod_info_type == 2:
            r.seek(28, 1)
        m.lods.append(lod)

    # tail: uv hashes, color hashes, strides (v16/v17 path)
    m.uv_count = r.u8()
    r.seek(4 * m.uv_count, 1)
    if version in (16, 17):
        m.color_count = r.u8()
        r.seek(4 * m.color_count, 1)
        r.seek(4, 1)
        count_c = r.u8()
        r.seek(4 * count_c, 1)
    else:  # v15
        r.seek(4, 1)
        m.color_count = r.u8()
        r.seek(4 * m.color_count, 1)

    m.vertex_stride = r.u16()
    m.normals_stride = r.u16()

    nb_with_color = m.normals_stride - 4 * m.color_count - 4 * m.uv_count
    m.color_in_normals = nb_with_color >= 8
    normals_base = m.normals_stride - 4 * m.uv_count - 4 * m.color_count
    m.normal_type = 1 if normals_base >= 28 else 0
    if m.vertex_stride in (32, 40):
        m.position_type = 0
    elif m.vertex_stride in (28, 36):
        m.position_type = 1
    elif normals_base >= 28:
        m.position_type = 1
    else:
        m.position_type = 0

    r.seek(20 if version == 17 else 16, 1)
    return m


def _extract(buf, lods):
    out = io.BytesIO()
    for lod in reversed(lods):  # engine stores LOD blocks reversed
        out.write(buf[lod.data_offset : lod.data_offset + lod.data_size])
    return out.getvalue()


def _positions(ext, m, lod):
    r = _R(ext)
    r.seek(lod.vertex_data_offset_a)
    n = lod.vertex_count
    stride = m.vertex_stride
    P = np.empty((n, 3), np.float32)
    for v in range(n):
        s = r.tell()
        if m.position_type == 0:
            x = r.int16_norm()
            y = r.int16_norm()
            z = r.int16_norm()
            w = r.i16()
            P[v] = (x * w, y * w, z * w)
        else:
            P[v] = (r.f32(), r.f32(), r.f32())
        r.seek(s + stride)
    return P


def _uvs(ext, m, lod):
    """Read UV0 and (if present) UV1 from the normals stream. UV1 is the body/head decal channel."""
    r = _R(ext)
    n = lod.vertex_count
    stride = m.normals_stride
    cc = m.color_count if m.color_in_normals else 0
    pre = (4 * cc + 4 + 4) if m.normal_type == 0 else (4 * cc + 12 + 12 + 4)
    base = lod.vertex_data_offset_b
    nuv = max(1, min(m.uv_count, 2))  # read up to 2 UV sets
    # compact (12-bit) vs int16_norm detection, tested on the first UV
    compact = True
    for v in range(n):
        r.seek(base + v * stride + pre)
        if abs(struct.unpack("<h", r.read(2))[0]) > 8191:
            compact = False
            break
    out = [np.empty((n, 2), np.float32) for _ in range(nuv)]
    for v in range(n):
        for k in range(nuv):
            r.seek(base + v * stride + pre + 4 * k)
            if compact:
                u = (r.u16() % 4096) / 4095.0
                w = (r.u16() % 4096) / 4095.0
            else:
                u = r.int16_norm()
                w = r.int16_norm()
            out[k][v] = (u, w)
    uv0 = out[0]
    uv1 = out[1] if nuv > 1 else None
    return uv0, uv1


def _faces(ext, lod):
    r = _R(ext)
    r.seek(lod.face_block_offset)
    n = lod.index_count
    use32 = False
    if n > 0:
        if (
            lod.size_a == lod.face_block_offset // 4
            and lod.size_a != lod.face_block_offset // 2
        ):
            use32 = True
        else:
            peek = ext[lod.face_block_offset : lod.face_block_offset + 16]
            if len(peek) >= 16:
                hi = [struct.unpack("<H", peek[i : i + 2])[0] for i in range(2, 16, 4)]
                use32 = all(v == 0 for v in hi)
    if use32:
        idx = np.frombuffer(ext, np.uint32, count=n, offset=lod.face_block_offset)
    else:
        idx = np.frombuffer(
            ext, np.uint16, count=n, offset=lod.face_block_offset
        ).astype(np.uint32)
    return idx.copy()


def _normals_from_faces(P, idx):
    nrm = np.zeros(P.shape, np.float32)
    tri = idx.reshape(-1, 3)
    a, b, c = P[tri[:, 0]], P[tri[:, 1]], P[tri[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(nrm, tri[:, k], fn)
    ln = np.linalg.norm(nrm, axis=1, keepdims=True)
    return np.divide(nrm, ln, out=np.zeros_like(nrm), where=ln > 1e-12)


def load_model(path):
    buf = open(path, "rb").read()
    version, size, meshes = _parse(buf)
    out = []
    for m in meshes:
        if not m.lods:
            continue
        lod = m.lods[0]  # LOD0 = highest detail
        if lod.vertex_count == 0 or lod.index_count == 0:
            continue
        ext = _extract(buf, m.lods)
        P = _positions(ext, m, lod)
        UV, UV1 = _uvs(ext, m, lod)
        idx = _faces(ext, lod)
        if FLIP_X:
            P[:, 0] = -P[:, 0]
            idx = idx.reshape(-1, 3)[:, ::-1].reshape(-1)  # keep winding after mirror
        N = _normals_from_faces(P, idx)
        out.append(SubMesh(m.name, P, N, UV, idx.astype(np.uint32), None, uv1=UV1))
    if not out:
        raise ValueError("no LOD0 geometry found in MMB")
    return out, {}
