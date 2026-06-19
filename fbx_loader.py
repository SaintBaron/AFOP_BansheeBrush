"""Minimal pure-Python binary-FBX model loader -> (list[SubMesh], material_dict).

Reads geometry (vertices, polygons, per-corner normals and UVs) from a *binary*
FBX file and returns render-ready SubMesh objects matching cast_loader/mmb_loader.

Scope: static geometry only. No skinning, no animation, and node/model transforms
are not composed (control points are used in their local space). ASCII FBX files
are not supported. Good enough to preview arbitrary meshes in the viewport.
"""
import struct
import zlib

import numpy as np

_MAGIC = b"Kaydara FBX Binary  \x00"          # 21 bytes
_PROP_SCALAR = {"Y": ("<h", 2), "C": ("<?", 1), "I": ("<i", 4),
                "F": ("<f", 4), "D": ("<d", 8), "L": ("<q", 8)}
_ARRAY_FMT = {"f": "f", "d": "d", "l": "q", "i": "i", "b": "b"}


class _Elem:
    __slots__ = ("name", "props", "children")

    def __init__(self, name):
        self.name = name
        self.props = []
        self.children = []

    def child(self, name):
        for c in self.children:
            if c.name == name:
                return c
        return None

    def children_named(self, name):
        return [c for c in self.children if c.name == name]


def _read_prop(data, o):
    t = chr(data[o]); o += 1
    sc = _PROP_SCALAR.get(t)
    if sc is not None:
        (v,) = struct.unpack_from(sc[0], data, o)
        return v, o + sc[1]
    if t in _ARRAY_FMT:
        length, enc, comp = struct.unpack_from("<III", data, o)
        o += 12
        raw = data[o:o + comp]
        o += comp
        if enc == 1:
            raw = zlib.decompress(raw)
        arr = np.frombuffer(raw, dtype="<" + _ARRAY_FMT[t], count=length)
        return arr, o
    if t in ("S", "R"):
        (length,) = struct.unpack_from("<I", data, o)
        o += 4
        blob = data[o:o + length]
        o += length
        return (blob.decode("latin1") if t == "S" else blob), o
    raise ValueError("unknown FBX property type %r at offset %d" % (t, o - 1))


def _read_node(data, o, ver):
    if ver >= 7500:
        end, nprops, _plen = struct.unpack_from("<QQQ", data, o)
        o += 24
    else:
        end, nprops, _plen = struct.unpack_from("<III", data, o)
        o += 12
    namelen = data[o]
    o += 1
    name = data[o:o + namelen].decode("latin1")
    o += namelen
    if end == 0:                       # null record: end of a sibling list
        return None, o
    el = _Elem(name)
    for _ in range(nprops):
        v, o = _read_prop(data, o)
        el.props.append(v)
    while o < end:                     # nested nodes (terminated by a null record)
        child, o = _read_node(data, o, ver)
        if child is None:
            break
        el.children.append(child)
    return el, end


def _parse(data):
    if data[:len(_MAGIC)] != _MAGIC:
        raise ValueError("not a binary FBX file (ASCII FBX is not supported)")
    (ver,) = struct.unpack_from("<I", data, 23)
    o = 27
    root = _Elem("")
    n = len(data)
    while o < n:
        node, o = _read_node(data, o, ver)
        if node is None:               # top-level null record -> done
            break
        root.children.append(node)
    return root, ver


def _clean_name(s):
    if isinstance(s, bytes):
        s = s.decode("latin1", "replace")
    # binary FBX stores object names as "Name\x00\x01Class"
    return (s.split("\x00\x01")[0].split("::")[-1]) or "object"


def _layer(elem, value_name, index_name):
    """Pull (array, index_array, mapping, reference) for a LayerElement* node."""
    if elem is None:
        return None
    vnode = elem.child(value_name)
    if vnode is None or not vnode.props:
        return None
    arr = np.asarray(vnode.props[0], np.float64)
    mp = elem.child("MappingInformationType")
    rf = elem.child("ReferenceInformationType")
    inode = elem.child(index_name)
    idx = np.asarray(inode.props[0], np.int64) if (inode and inode.props) else None
    return (arr, idx,
            mp.props[0] if (mp and mp.props) else "ByPolygonVertex",
            rf.props[0] if (rf and rf.props) else "Direct")


def _resolve_layer_vec(layer, ncomp, corner_idx, cp, poly_id):
    """Vectorised per-corner gather of a LayerElement (normals/UVs)."""
    arr, idx_arr, mapping, reference = layer
    if mapping == "ByPolygonVertex":
        key = corner_idx
    elif mapping in ("ByVertice", "ByVertex", "ByControlPoint"):
        key = cp
    elif mapping == "ByPolygon":
        key = poly_id
    else:                                        # AllSame (ByEdge unsupported)
        key = np.zeros(corner_idx.shape, np.int64)
    if reference != "Direct" and idx_arr is not None:   # IndexToDirect
        key = idx_arr[key]
    arr = np.asarray(arr, np.float32)
    flat = key.astype(np.int64)[:, None] * ncomp + np.arange(ncomp)[None, :]
    return arr[flat]


def _geometry_to_submesh(geo, name, material_hash, SubMesh):
    vt = geo.child("Vertices")
    pvi = geo.child("PolygonVertexIndex")
    if vt is None or pvi is None or not vt.props or not pvi.props:
        return None
    verts = np.asarray(vt.props[0], np.float64).reshape(-1, 3)
    raw = np.asarray(pvi.props[0], np.int64)

    # polygon boundaries: the last corner of each polygon is bitwise-NOT encoded (< 0)
    ends = np.flatnonzero(raw < 0)
    if ends.size == 0:
        return None
    ncorner = int(ends[-1]) + 1
    raw = raw[:ncorner]
    cp = np.where(raw < 0, ~raw, raw)            # control-point index per corner
    corner_idx = np.arange(ncorner)
    poly_id = np.searchsorted(ends, corner_idx)  # polygon index per corner

    pos = verts[cp].astype(np.float32)

    nrm_layer = _layer(geo.child("LayerElementNormal"), "Normals", "NormalsIndex")
    uv_layer = _layer(geo.child("LayerElementUV"), "UV", "UVIndex")
    nrm = (_resolve_layer_vec(nrm_layer, 3, corner_idx, cp, poly_id)
           if nrm_layer is not None else np.zeros((ncorner, 3), np.float32))
    uv0 = (_resolve_layer_vec(uv_layer, 2, corner_idx, cp, poly_id)
           if uv_layer is not None else np.zeros((ncorner, 2), np.float32))

    # fan-triangulate every polygon (corners starts[p]..ends[p] -> size-2 triangles)
    starts = np.empty_like(ends)
    starts[0] = 0
    starts[1:] = ends[:-1] + 1
    sizes = ends - starts + 1
    ntri = np.maximum(sizes - 2, 0)
    total = int(ntri.sum())
    if total == 0:
        return None
    poly_for_tri = np.repeat(np.arange(ends.size), ntri)
    t = np.arange(total) - (np.cumsum(ntri) - ntri)[poly_for_tri] + 1
    base = starts[poly_for_tri]
    idx = np.empty((total, 3), np.uint32)
    idx[:, 0] = base
    idx[:, 1] = base + t
    idx[:, 2] = base + t + 1
    return SubMesh(name, pos, nrm.astype(np.float32), uv0.astype(np.float32),
                   idx.reshape(-1), material_hash)


def load_model(path):
    """Render-ready geometry from a binary .fbx. Returns (list[SubMesh], {})."""
    with open(path, "rb") as f:
        data = f.read()
    root, _ver = _parse(data)
    objects = root.child("Objects")
    if objects is None:
        raise ValueError("FBX has no Objects section")

    from cast_loader import SubMesh

    # readable mesh names: Geometry -> connected Model name (via Connections)
    model_name = {}
    for m in objects.children_named("Model"):
        if m.props:
            mid = int(m.props[0])
            model_name[mid] = _clean_name(m.props[1]) if len(m.props) > 1 else "model"
    geo_to_model = {}
    conns = root.child("Connections")
    if conns is not None:
        for c in conns.children_named("C"):
            if len(c.props) >= 3 and c.props[0] == "OO":
                geo_to_model.setdefault(int(c.props[1]), int(c.props[2]))

    meshes, mat_names = [], {}
    for n, geo in enumerate(objects.children_named("Geometry")):
        if len(geo.props) >= 3 and geo.props[2] != "Mesh":
            continue
        gid = int(geo.props[0]) if geo.props else None
        name = model_name.get(geo_to_model.get(gid))
        if not name and len(geo.props) > 1:
            name = _clean_name(geo.props[1])
        if not name:
            name = "fbx_mesh_%d" % n
        sm = _geometry_to_submesh(geo, name, None, SubMesh)
        if sm is not None:
            meshes.append(sm)

    if not meshes:
        raise ValueError("no mesh geometry found in FBX")
    return meshes, mat_names
