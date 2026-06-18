"""GLSL for the recolour viewport, camera math, and a synthetic Pattern Coat generator.

The fragment shader transcribes recolor_core.recolor(): PatternCoat.B/A drive the two 5-stop
colour gradients, R/G the placement masks, overlaid onto the detail albedo. Simple
lambert+ambient preview lighting (not the game's PBR).
"""

from __future__ import annotations
import numpy as np

VERTEX_SHADER = """
#version 330
uniform mat4 uMVP;
uniform mat3 uNormalMat;
uniform float uFlipV;
in vec3 in_pos;
in vec3 in_nrm;
in vec2 in_uv;
out vec3 vN;
out vec3 vP;            // model-space position (for screen-space-derivative tangent frame)
out vec2 vUV;
void main() {
    vN = normalize(uNormalMat * in_nrm);
    vP = in_pos;
    vUV = vec2(in_uv.x, mix(in_uv.y, 1.0 - in_uv.y, uFlipV));
    gl_Position = uMVP * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330
uniform sampler2D uColor;       // _d  (detail albedo)
uniform sampler2D uMaterial;    // _m  (PBR; .b drives overlay show-through)
uniform sampler2D uPatternCoat; // 4ch zone texture (R,G pattern masks; B,A coat selectors)
uniform vec3  uColors[10];      // myColor1..10 (rgb, 0..1)
uniform float uInvert1;
uniform float uInvert2;
uniform float uLevel1;
uniform float uLevel2;
uniform vec2  uDesat;
uniform int   uRecolor;         // 1 = recolour, 0 = flat/textured
uniform int   uTextured;        // 1 = sample uColor as plain albedo (non-recolour meshes)
uniform int   uUseTexAlpha;     // 1 = output sampled texture alpha (transparent meshes, e.g. wings)
uniform vec3  uFlat;            // flat colour when uRecolor==0 && uTextured==0
uniform vec3  uLightDir;        // world-space, normalised, points toward surface

uniform sampler2D uNormalTex;        // _n       base normal (X=R, Y=A; Z reconstructed)
uniform sampler2D uDetail1;          // skin_detail_1_nr (X=R, Y=G), tiled
uniform sampler2D uDetail2;          // skin_detail_2_nr
uniform sampler2D uDetail3;          // skin_detail_4_nr
uniform sampler2D uDetailMask;       // _dn_mask  (rgb = per-detail blend weights)
uniform int   uUseNormalMap;    // 1 = perturb the geometric normal with the normal maps
uniform float uNormalStrength;  // base-normal XY scale
uniform vec3  uDetailTiling;    // UV tiling per detail normal
uniform float uDetailWeight;    // overall detail-normal strength
uniform float uNormalYFlip;     // +1 keep green, -1 flip (DirectX-style normal maps)

in vec3 vN;
in vec3 vP;
in vec2 vUV;
out vec4 frag;

// reconstruct Z from a tangent XY (snowdrop "unpack normal xy")
vec3 unpackXY(vec2 xy) { return vec3(xy, sqrt(clamp(1.0 - dot(xy, xy), 0.0, 1.0))); }
// reoriented normal mapping (snowdrop "combine normal maps.h")
vec3 rnm(vec3 a, vec3 b) { a += vec3(0.0, 0.0, 1.0); b *= vec3(-1.0, -1.0, 1.0); return a * dot(a, b) / a.z - b; }

const vec3 GREY = vec3(0.698, 0.686, 0.663);

float smoothstep_(float e0, float e1, float x){
    float t = clamp((x - e0) / max(e1 - e0, 1e-6), 0.0, 1.0);
    return t*t*(3.0 - 2.0*t);
}
vec3 overlay(vec3 base, vec3 blend){
    return mix(2.0*base*blend, 1.0 - 2.0*(1.0-base)*(1.0-blend), step(0.5, base));
}

vec3 recolour(){
    vec4 pc = texture(uPatternCoat, vUV);
    // Coat 1 gradient (B)
    float t = pc.b * 4.0;
    vec3 c1 = mix(uColors[0], uColors[1], clamp(t-0.0,0.0,1.0));
    c1 = mix(c1, uColors[2], clamp(t-1.0,0.0,1.0));
    c1 = mix(c1, uColors[3], clamp(t-2.0,0.0,1.0));
    c1 = mix(c1, uColors[4], clamp(t-3.0,0.0,1.0));
    // Coat 2 gradient (A)
    float t2 = pc.a * 4.0;
    vec3 c2 = mix(uColors[5], uColors[6], clamp(t2-0.0,0.0,1.0));
    c2 = mix(c2, uColors[7], clamp(t2-1.0,0.0,1.0));
    c2 = mix(c2, uColors[8], clamp(t2-2.0,0.0,1.0));
    c2 = mix(c2, uColors[9], clamp(t2-3.0,0.0,1.0));
    // placement masks
    float hi1 = uLevel1 * 0.25;
    float m1 = smoothstep_(hi1-0.25, hi1, pc.r) * uInvert1 - min(0.0, uInvert1);
    float hi2 = uLevel2 * 0.25;
    float m2 = smoothstep_(hi2-0.25, hi2, pc.g) * uInvert2 - min(0.0, uInvert2);
    float mask = clamp(m1 + m2, 0.0, 1.0);
    vec3 coat = sqrt(max(mix(c1, c2, mask), 0.0));
    // detail albedo path
    vec3 alb = texture(uColor, vUV).rgb;
    float ds = clamp(uDesat.y + 1.0, 0.0, 1.0);
    alb = sqrt(max(mix(GREY, alb, ds), 0.0));
    // overlay coat onto albedo, masked by Material.b
    float om = clamp(texture(uMaterial, vUV).b + uDesat.x, 0.0, 1.0);
    vec3 outc = mix(alb, overlay(alb, coat), om);
    vec3 result = clamp(outc*outc, 0.0, 1.0);
    return clamp(result, 0.0, 1.0);
}

void main(){
    vec3 albedo;
    float alpha = 1.0;
    if (uRecolor == 1) {
        albedo = recolour();
        if (uUseTexAlpha == 1) {              // body membrane transparency from _d alpha
            alpha = texture(uColor, vUV).a;
            if (alpha < 0.02) discard;        // fully-transparent membrane: cut out cleanly
        }
    }
    else if (uTextured == 1) {
        vec4 c = texture(uColor, vUV);
        albedo = c.rgb;
        if (uUseTexAlpha == 1) {              // wing membrane transparency from texture alpha
            alpha = c.a;
            if (alpha < 0.02) discard;
        }
    }
    else                     albedo = uFlat;
    vec3 N = normalize(vN);
    if (uUseNormalMap == 1) {
        // base normal (_n): tangent XY in R and A
        vec2 bxy = (texture(uNormalTex, vUV).ra * 2.0 - 1.0) * uNormalStrength;
        bxy.y *= uNormalYFlip;
        vec3 nTS = unpackXY(bxy);
        // three tiling detail normals (skin_detail_*_nr, XY in R/G), weighted by _dn_mask
        vec3 dm = texture(uDetailMask, vUV).rgb * uDetailWeight;
        vec2 d1 = texture(uDetail1, vUV * uDetailTiling.x).rg * 2.0 - 1.0; d1.y *= uNormalYFlip;
        vec2 d2 = texture(uDetail2, vUV * uDetailTiling.y).rg * 2.0 - 1.0; d2.y *= uNormalYFlip;
        vec2 d3 = texture(uDetail3, vUV * uDetailTiling.z).rg * 2.0 - 1.0; d3.y *= uNormalYFlip;
        nTS = rnm(nTS, unpackXY(d1 * dm.r));   // RNM, scaled by mask channel (0 => identity)
        nTS = rnm(nTS, unpackXY(d2 * dm.g));
        nTS = rnm(nTS, unpackXY(d3 * dm.b));
        // tangent frame from screen-space derivatives (snowdrop "tangent from uv.h")
        vec3 dpx = dFdx(vP), dpy = dFdy(vP);
        vec2 dux = dFdx(vUV), duy = dFdy(vUV);
        vec3 r1 = cross(N, dpy), r2 = cross(dpx, N);
        vec3 T = normalize(r1 * dux.x + r2 * duy.x);
        vec3 B = normalize(r1 * dux.y + r2 * duy.y);
        N = normalize((-T) * nTS.x + B * nTS.y + N * nTS.z);   // ColumnMatrix(-t, b, n)
    }
    float ndl = max(dot(N, -normalize(uLightDir)), 0.0);
    float lit = 0.30 + 0.70 * ndl;            // ambient + key (preview only)
    frag = vec4(albedo * lit, alpha);
}
"""


# ---------------- camera / matrix math (numpy, column-major for moderngl) ---


def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / np.tan(np.radians(fovy_deg) * 0.5)
    m = np.zeros((4, 4), np.float32)
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = (2 * far * near) / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up):
    eye = np.asarray(eye, np.float32)
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4, dtype=np.float32)
    m[0, :3] = s
    m[1, :3] = u
    m[2, :3] = -f
    m[0, 3] = -np.dot(s, eye)
    m[1, 3] = -np.dot(u, eye)
    m[2, 3] = np.dot(f, eye)
    return m


def orbit_eye(center, azimuth_deg, elevation_deg, distance):
    az = np.radians(azimuth_deg)
    el = np.radians(elevation_deg)
    d = np.array(
        [np.cos(el) * np.sin(az), np.sin(el), np.cos(el) * np.cos(az)], np.float32
    )
    return np.asarray(center, np.float32) + d * distance


def camera_basis(center, az, el, dist):
    """Return (right, up) world vectors of the orbit camera, for panning."""
    eye = orbit_eye(center, az, el, dist)
    f = np.asarray(center, np.float32) - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, np.array([0, 1, 0], np.float32))
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    return s, u


def mvp(center, az, el, dist, aspect, radius, pan=None):
    c = np.asarray(center, np.float32)
    if pan is not None:
        c = c + np.asarray(pan, np.float32)
    eye = orbit_eye(c, az, el, dist)
    view = look_at(eye, c, np.array([0, 1, 0], np.float32))
    near = max(dist - radius * 2.0, radius * 0.02)
    far = dist + radius * 2.0
    proj = perspective(45.0, aspect, near, far)
    return (proj @ view).astype(np.float32), eye


# ---------------- synthetic pattern coat (placeholder) ----------------------


def synthetic_pattern(size=512):
    """Stand-in Pattern Coat: B ramps across U, A across V, R/G soft masks. Replace with the real texture later."""
    u = np.linspace(0, 1, size, dtype=np.float32)[None, :].repeat(size, 0)
    v = np.linspace(0, 1, size, dtype=np.float32)[:, None].repeat(size, 1)
    R = np.clip((u - 0.5) * 3.0 + 0.5, 0, 1)  # coat1 placement
    G = (np.sin(v * np.pi * 3) * 0.5 + 0.5).astype(np.float32)  # coat2 placement
    B = u  # coat1 selector
    A = v  # coat2 selector
    return (np.stack([R, G, B, A], -1) * 255).astype(np.uint8)


# ---------------- ground grid (Blender-style) -------------------------------

GRID_VERTEX_SHADER = """
#version 330
uniform mat4 uMVP;
in vec3 in_pos;
in vec3 in_col;
out vec3 vcol;
void main(){ vcol = in_col; gl_Position = uMVP * vec4(in_pos, 1.0); }
"""

GRID_FRAGMENT_SHADER = """
#version 330
in vec3 vcol;
out vec4 frag;
void main(){ frag = vec4(vcol, 1.0); }
"""


def grid_lines(center, radius, floor_y, divisions=40):
    """Interleaved [x,y,z,r,g,b] float32 line list for a floor grid on the XZ plane at floor_y, with brighter every-5th lines and coloured centre axes (X red, Z blue)."""
    span = radius * 3.2
    step = (2.0 * span) / divisions
    cx, cz = float(center[0]), float(center[2])
    y = float(floor_y)
    minor = (0.26, 0.27, 0.30)
    major = (0.38, 0.40, 0.44)
    x_axis = (0.62, 0.24, 0.26)
    z_axis = (0.24, 0.40, 0.62)
    verts = []

    def seg(p0, p1, c):
        verts.extend(
            (
                p0[0],
                p0[1],
                p0[2],
                c[0],
                c[1],
                c[2],
                p1[0],
                p1[1],
                p1[2],
                c[0],
                c[1],
                c[2],
            )
        )

    for i in range(divisions + 1):
        t = -span + i * step
        on_axis = abs(t) < step * 0.5
        c = major if (i % 5 == 0) else minor
        # lines parallel to Z (vary x); the centre one IS the Z axis -> blue
        seg((cx + t, y, cz - span), (cx + t, y, cz + span), z_axis if on_axis else c)
        # lines parallel to X (vary z); the centre one IS the X axis -> red
        seg((cx - span, y, cz + t), (cx + span, y, cz + t), x_axis if on_axis else c)

    return np.asarray(verts, np.float32)
