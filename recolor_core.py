"""Reimplementation of px_wildlife_skin_banshee's colour path (10 palette colours ->
recoloured albedo), ported from the compiled .mshader. Sampled at UV0:

  PatternCoat.B/A -> 5-stop gradients across Coat1 (myColor1..5) / Coat2 (myColor6..10)
  PatternCoat.R/G -> Coat1/Coat2 placement masks (Level/Invert)
  coat = lerp(coat1, coat2, saturate(mask1+mask2)); out = Overlay(coat, albedo, Material.B)

The shader's sqrt/overlay/square gamma is replicated; values are sRGB-normalised for display.
"""

from __future__ import annotations
import numpy as np

GREY = np.array([0.698, 0.686, 0.663], np.float32)  # desaturation target (from shader)


def _sat(x):
    return np.clip(x, 0.0, 1.0)


def _lerp(a, b, t):
    return a + (b - a) * t


def _overlay_channel(base, blend):
    # standard overlay (snowdrop overlay.h)
    return np.where(
        base < 0.5, 2 * base * blend, 1.0 - 2.0 * (1.0 - base) * (1.0 - blend)
    )


def recolor(
    color,
    material,
    patterncoat,
    palette,
    invert1=None,
    invert2=1.0,
    level1=1.0,
    level2=1.0,
    desat=(0.0, 0.0),
):
    """color/material/patterncoat: HxWx(3|4) float arrays in [0,1] (sampled at UV0).
    palette: 10 (r,g,b) floats in [0,1] (myColor1..10). invert1: 1.0 (neutral) if None.
    Returns recoloured albedo HxWx3 in [0,1]."""
    pc = patterncoat.astype(np.float32)
    R, G, B, A = pc[..., 0], pc[..., 1], pc[..., 2], pc[..., 3]
    C = [np.asarray(c, np.float32) for c in palette]
    if invert1 is None:
        invert1 = 1.0

    # ---- Coat 1 gradient from B ----
    t = B[..., None] * 4.0
    c1 = _lerp(C[0], C[1], _sat(t - 0.0))
    c1 = _lerp(c1, C[2], _sat(t - 1.0))
    c1 = _lerp(c1, C[3], _sat(t - 2.0))
    c1 = _lerp(c1, C[4], _sat(t - 3.0))
    # ---- Coat 2 gradient from A ----
    t2 = A[..., None] * 4.0
    c2 = _lerp(C[5], C[6], _sat(t2 - 0.0))
    c2 = _lerp(c2, C[7], _sat(t2 - 1.0))
    c2 = _lerp(c2, C[8], _sat(t2 - 2.0))
    c2 = _lerp(c2, C[9], _sat(t2 - 3.0))

    # ---- pattern placement masks ----
    hi1 = level1 * 0.25
    m1 = _smoothstep(hi1 - 0.25, hi1, R) * invert1 - min(0.0, invert1)
    hi2 = level2 * 0.25
    m2 = _smoothstep(hi2 - 0.25, hi2, G) * invert2 - min(0.0, invert2)
    mask = _sat(m1 + m2)[..., None]

    coat = _lerp(c1, c2, mask)
    coat = np.sqrt(np.clip(coat, 0, None))

    # ---- albedo path (detail texture, optional desaturation) ----
    alb = color[..., :3].astype(np.float32)
    ds = _sat(desat[1] + 1.0)
    alb = _lerp(GREY, alb, ds)
    alb = np.sqrt(np.clip(alb, 0, None))

    # ---- overlay coat onto albedo, masked by Material.B ----
    om = _sat(material[..., 2] + desat[0])[..., None]
    blended = _overlay_channel(alb, coat)  # base=albedo, blend=coat
    out = _lerp(alb, blended, om)
    out = out * out  # undo sqrt (shader pow 2)
    return _sat(out)


def _smoothstep(e0, e1, x):
    t = _sat((x - e0) / np.maximum(e1 - e0, 1e-6))
    return t * t * (3.0 - 2.0 * t)


def palette_from_pattern(cp):
    """Build the 10 (r,g,b) palette from a ColorPattern object."""
    pal = []
    for v in cp.colors:
        pal.append(
            ((v >> 16 & 0xFF) / 255.0, (v >> 8 & 0xFF) / 255.0, (v & 0xFF) / 255.0)
        )
    return pal
