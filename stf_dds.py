"""Read AFoP ".dds" textures.

AFoP ships textures in a Snowdrop "STF" container (magic b"STF\\x02") that uses the .dds
extension but isn't a standard DirectDraw Surface: a small header, the BCn payload, a
smallest-first mip chain, and a 20-byte footer. Standard b"DDS " files are also handled.
Returns HxWx4 uint8 RGBA. Decodes BCn via Pillow, falling back to texture2ddecoder.
"""

from __future__ import annotations
import math
import os
import io
import struct
import numpy as np

_FOOTER = 20  # legacy fallback trailer size (bytes after mip 0)
_STF_HEADER = 76  # fixed STF\x02 front header; trailer = (len - chain) - this

try:
    from PIL import Image as _PILImage  # primary BCn decoder (already a dep)
except Exception:  # pragma: no cover
    _PILImage = None
try:
    import texture2ddecoder as _t2d  # optional fallback
except Exception:  # pragma: no cover
    _t2d = None

# DXGI_FORMAT codes for the DX10 DDS header wrapper used by the Pillow path.
_DXGI = {"bc1": 71, "bc2": 74, "bc3": 77, "bc4": 80, "bc5": 83, "bc7": 98}


def _mip_chain_bytes(w, h, bb):
    """Total bytes of a full mip chain for a BCn surface (block bytes bb)."""
    s = 0
    while True:
        s += max(1, math.ceil(w / 4)) * max(1, math.ceil(h / 4)) * bb
        if w == 1 and h == 1:
            break
        w = max(1, w // 2)
        h = max(1, h // 2)
    return s


def _solve_dims(payload_len):
    """Find (w, h, block_bytes, header) so header + full reverse mip chain == file length; prefer square, then largest."""
    cands = []
    dims = [1 << k for k in range(2, 13)]  # 4 .. 4096
    for bb in (8, 16):
        for w in dims:
            for h in dims:
                chain = _mip_chain_bytes(w, h, bb)
                header = payload_len - chain
                if 0 <= header <= 4096:
                    cands.append((w, h, bb, header))
    if not cands:
        return None
    # prefer square, then larger area, then smaller header
    cands.sort(key=lambda c: (c[0] != c[1], -(c[0] * c[1]), c[3]))
    return cands[0]


def _guess_codec(stem, bb):
    s = stem.lower()
    if bb == 8:
        # single-channel masks/grayscale -> BC4, else colour -> BC1
        if any(k in s for k in ("grayscale", "mask", "smalleye", "_h")) or s.endswith(
            "_h"
        ):
            return "bc4"
        return "bc1"
    # 16-byte blocks: AFoP stores colour AND normal surfaces (_d/_m/_pc/_n/_nr/dn_mask)
    # as BC7. A few colour maps are actually BC3 (e.g. the insect-wing albedo); those are
    # caught by the BC7->BC3 quality check in _load_stf. BC5 is not used by this game.
    return "bc7"


def _dds_wrap(payload, w, h, codec):
    """Wrap a single BCn mip surface in a minimal DX10 .dds so Pillow can decode it."""
    hdr = bytearray(128)
    hdr[0:4] = b"DDS "
    struct.pack_into("<I", hdr, 4, 124)
    struct.pack_into("<I", hdr, 8, 0x1007 | 0x80000)  # caps|h|w|pixfmt|linearsize
    struct.pack_into("<I", hdr, 12, h)
    struct.pack_into("<I", hdr, 16, w)
    struct.pack_into("<I", hdr, 20, len(payload))
    struct.pack_into("<I", hdr, 28, 1)  # mip count
    struct.pack_into("<I", hdr, 76, 32)  # pixelformat size
    struct.pack_into("<I", hdr, 80, 0x4)  # FOURCC flag
    hdr[84:88] = b"DX10"
    struct.pack_into("<I", hdr, 108, 0x1000)  # caps TEXTURE
    dx10 = struct.pack("<5I", _DXGI[codec], 3, 0, 1, 0)  # fmt, TEX2D, 0, arr1, 0
    return bytes(hdr) + dx10 + payload


def _decode_blocks(payload, w, h, codec):
    # Primary: Pillow's BCn decoder (ships wheels for current Pythons).
    if _PILImage is not None:
        try:
            im = _PILImage.open(io.BytesIO(_dds_wrap(payload, w, h, codec)))
            im.load()
            return np.ascontiguousarray(np.asarray(im.convert("RGBA")))
        except Exception:
            pass
    # Fallback: texture2ddecoder, if installed.
    if _t2d is not None:
        fn = {
            "bc1": _t2d.decode_bc1,
            "bc3": _t2d.decode_bc3,
            "bc4": _t2d.decode_bc4,
            "bc5": _t2d.decode_bc5,
            "bc7": _t2d.decode_bc7,
        }[codec]
        bgra = np.frombuffer(fn(payload, w, h), np.uint8).reshape(h, w, 4)
        rgba = bgra[..., [2, 1, 0, 3]].copy()
        if codec == "bc4":
            g = rgba[..., 0]
            rgba = np.dstack([g, g, g, np.full_like(g, 255)])
        elif codec == "bc5":
            rgba[..., 2] = 255
            rgba[..., 3] = 255
        return np.ascontiguousarray(rgba)
    raise RuntimeError(
        "no BCn decoder available - install Pillow (>=10.4) to read .dds"
    )


def _dims_from_header(data):
    """STF\\x02 surface size from the front header: width u16 at offset 6 (units of 64 px), height u16 at offset 8 (units of 128 px). Returns (w, h) or None."""
    if len(data) < 10:
        return None
    w = struct.unpack_from("<H", data, 6)[0] * 64
    h = struct.unpack_from("<H", data, 8)[0] * 128
    if 0 < w <= 16384 and 0 < h <= 16384:
        return w, h
    return None


def _rgb_noise(arr):
    """Mean horizontal neighbour difference over RGB; low for a coherent decode, high when the BCn codec is wrong."""
    return float(np.abs(np.diff(arr[..., :3].astype(np.float32), axis=1)).mean())


def _load_stf(data, stem, fmt):
    # 1) dimensions + block size: trust the STF header, fall back to size-solving
    dims = _dims_from_header(data)
    bb = footer = None
    if dims:
        w, h = dims
        for cand in (16, 8):
            extra = len(data) - _mip_chain_bytes(w, h, cand)
            if _STF_HEADER <= extra <= _STF_HEADER + 4096:
                bb, footer = cand, extra - _STF_HEADER
                break
        if bb is None:
            dims = None  # header dims didn't yield a clean chain
    if not dims:
        sol = _solve_dims(len(data))
        if sol is None:
            raise RuntimeError("could not determine STF texture dimensions")
        w, h, bb, header = sol
        footer = header - _STF_HEADER
        if not (0 <= footer <= 4096):
            footer = _FOOTER

    mip0 = max(1, math.ceil(w / 4)) * max(1, math.ceil(h / 4)) * bb
    end = len(data) - footer  # trailer after mip 0 (varies; 76-byte front header)
    payload = data[end - mip0 : end]  # mip 0 is the last surface in the chain

    # 2) codec: explicit fmt wins; else name-based guess. Colour surfaces at 16-byte
    #    blocks are usually BC7 but some are BC3 (DXT5, e.g. the insect-wing albedo);
    #    if BC7 decodes to noise, fall back to BC3 by decode quality.
    codec = (fmt or _guess_codec(stem, bb)).lower()
    if (codec in ("bc1", "bc4")) != (bb == 8):
        codec = _guess_codec(stem, bb)
    if fmt is None and bb == 16 and codec == "bc7":
        out = _decode_blocks(payload, w, h, "bc7")
        if _rgb_noise(out) > 25.0:
            alt = _decode_blocks(payload, w, h, "bc3")
            if _rgb_noise(alt) < _rgb_noise(out):
                return alt
        return out
    return _decode_blocks(payload, w, h, codec)


_DXGI_BC = {
    70: "bc1",
    71: "bc1",
    72: "bc1",
    73: "bc2",
    74: "bc2",
    75: "bc2",
    76: "bc3",
    77: "bc3",
    78: "bc3",
    79: "bc4",
    80: "bc4",
    81: "bc4",
    82: "bc5",
    83: "bc5",
    84: "bc5",
    97: "bc7",
    98: "bc7",
    99: "bc7",
}
_FOURCC = {
    b"DXT1": "bc1",
    b"DXT3": "bc3",
    b"DXT5": "bc3",
    b"BC4U": "bc4",
    b"ATI1": "bc4",
    b"BC5U": "bc5",
    b"ATI2": "bc5",
}


def _load_standard_dds(data, stem, fmt):
    h, w = struct.unpack_from("<II", data, 12)
    fourcc = data[84:88]
    off = 128
    codec = _FOURCC.get(fourcc)
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", data, 128)[0]
        codec = _DXGI_BC.get(dxgi)
        off = 148
    codec = (fmt or codec or _guess_codec(stem, 16)).lower()
    bb = 8 if codec in ("bc1", "bc4") else 16
    mip0 = max(1, math.ceil(w / 4)) * max(1, math.ceil(h / 4)) * bb
    return _decode_blocks(data[off : off + mip0], w, h, codec)


def load_dds(path, fmt=None):
    """Load an AFoP STF .dds (or standard .dds) -> HxWx4 uint8 RGBA. `fmt` optionally forces a codec ('bc1'/'bc3'/'bc4'/'bc5'/'bc7')."""
    with open(path, "rb") as f:
        data = f.read()
    stem = os.path.splitext(os.path.basename(path))[0]
    if data[:3] == b"STF":
        return _load_stf(data, stem, fmt)
    if data[:4] == b"DDS ":
        return _load_standard_dds(data, stem, fmt)
    raise RuntimeError(f"not an STF or DDS texture: {os.path.basename(path)}")
