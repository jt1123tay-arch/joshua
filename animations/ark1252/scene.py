"""
ARK-1252 plug-in animation (Blender / bpy, Cycles).

A gloved worker's hand plugs an RJ45 network cable into the LAN1 port of an
ARK-1252 fanless box PC sitting on a workbench in a factory hall.

Usage (bpy installed via `pip install bpy`):
    python scene.py --out DIR [--frames 1-120] [--samples 64] [--res 960x540]
    python scene.py --out DIR --still 60 --samples 24      # one preview frame
Then:  ffmpeg -framerate 24 -i DIR/f_%04d.png -c:v libx264 -pix_fmt yuv420p -crf 18 out.mp4

The ARK-1252 chassis and port layout are an approximation (the real datasheet
was not reachable from the build machine); adjust PORTS below to match.
"""
import argparse, math, random, sys
import bpy, bmesh
from mathutils import Vector, Matrix, Euler, Quaternion

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--frames", default="1-120")
ap.add_argument("--step", type=int, default=1)
ap.add_argument("--check", action="store_true", help="print cable/hand clearance per frame and exit")
ap.add_argument("--still", type=int, default=0)
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--res", default="960x540")
ap.add_argument("--blend", default="")
ap.add_argument("--cam", default="", help="debug: x,y,z,tx,ty,tz[,lens] fixed camera")
args = ap.parse_args(argv)

FPS = 24
F_END = 120
random.seed(7)

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
prefs = bpy.context.preferences.edit

# ----------------------------------------------------------------- helpers
def node_mat(name, base, metal=0.0, rough=0.5, coat=0.0, emit=None, emit_str=0.0,
             trans=0.0, ior=1.45, bump=None, sheen=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*base, 1) if len(base) == 3 else base
    b.inputs["Metallic"].default_value = metal
    b.inputs["Roughness"].default_value = rough
    b.inputs["Coat Weight"].default_value = coat
    b.inputs["Transmission Weight"].default_value = trans
    b.inputs["IOR"].default_value = ior
    b.inputs["Sheen Weight"].default_value = sheen
    b.inputs["Specular IOR Level"].default_value = spec
    if emit:
        b.inputs["Emission Color"].default_value = (*emit, 1)
        b.inputs["Emission Strength"].default_value = emit_str
    if bump:  # (scale, strength, detail)
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = bump[0]
        nz.inputs["Detail"].default_value = bump[2] if len(bump) > 2 else 4
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump[1]
        bp.inputs["Distance"].default_value = 0.0005
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m

def link(ob):
    sc.collection.objects.link(ob)
    return ob

def boxes(name, items, mat, bevel=0.0):
    """items: list of (center xyz, size xyz). One mesh object."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for c, s in items:
        r = bmesh.ops.create_cube(bm, size=1.0)
        bmesh.ops.scale(bm, vec=Vector(s), verts=r["verts"])
        bmesh.ops.translate(bm, vec=Vector(c), verts=r["verts"])
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    me.materials.append(mat)
    if bevel:
        bv = ob.modifiers.new("bev", "BEVEL")
        bv.width = bevel; bv.segments = 2; bv.limit_method = "ANGLE"
    return ob

def cyl(name, loc, r, depth, mat, axis="Y", verts=32, rot=None):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=loc, vertices=verts)
    ob = bpy.context.object; ob.name = name
    if rot is not None:
        ob.rotation_euler = rot
    elif axis == "Y":
        ob.rotation_euler = (math.radians(90), 0, 0)
    elif axis == "X":
        ob.rotation_euler = (0, math.radians(90), 0)
    ob.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return ob

def text(body, loc, size, mat, align="LEFT"):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body; cu.size = size; cu.extrude = 0.00005
    cu.align_x = align
    ob = link(bpy.data.objects.new("txt_" + body, cu))
    ob.location = loc
    ob.rotation_euler = (math.radians(90), 0, 0)   # face -Y (towards camera)
    cu.materials.append(mat)
    return ob

def empty(name, loc=(0, 0, 0)):
    e = link(bpy.data.objects.new(name, None))
    e.location = loc
    return e

def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)

def smoother(t):
    t = max(0.0, min(1.0, t))
    return t * t * t * (t * (6 * t - 15) + 10)

def lerp(a, b, t):
    return a + (b - a) * t

def vlerp(a, b, t):
    return Vector(a).lerp(Vector(b), t)

# ------------------------------------------------------------- materials
M = {}
M["chassis"] = node_mat("chassis", (0.035, 0.037, 0.042), metal=0.85, rough=0.42, bump=(900, 0.08))
M["fins"] = node_mat("fins", (0.03, 0.032, 0.036), metal=0.8, rough=0.38)
M["blackplastic"] = node_mat("blackplastic", (0.012, 0.012, 0.013), rough=0.55)
M["silver"] = node_mat("silver", (0.75, 0.75, 0.76), metal=1.0, rough=0.25)
M["gold"] = node_mat("gold", (1.0, 0.76, 0.35), metal=1.0, rough=0.2)
M["print"] = node_mat("print", (0.85, 0.86, 0.86), rough=0.6)
M["usbblue"] = node_mat("usbblue", (0.02, 0.12, 0.6), rough=0.4)
M["termgreen"] = node_mat("termgreen", (0.06, 0.32, 0.1), rough=0.45)
M["pwr_led"] = node_mat("pwr_led", (0.1, 0.2, 0.6), rough=0.3, emit=(0.15, 0.4, 1.0), emit_str=12)
M["led_link"] = node_mat("led_link", (0.02, 0.035, 0.02), rough=0.3, emit=(0.2, 1.0, 0.15), emit_str=0)
M["led_act"] = node_mat("led_act", (0.04, 0.03, 0.012), rough=0.3, emit=(1.0, 0.55, 0.05), emit_str=0)
M["led_off"] = node_mat("led_off", (0.03, 0.035, 0.03), rough=0.3)
M["clear"] = node_mat("clearplastic", (0.95, 0.95, 0.95), rough=0.12, trans=1.0, ior=1.49)
M["boot"] = node_mat("boot", (0.03, 0.16, 0.55), rough=0.55, bump=(1500, 0.05))
M["cable"] = node_mat("cable", (0.025, 0.14, 0.5), rough=0.45, coat=0.2)
M["sleeve"] = node_mat("sleeve", (0.018, 0.030, 0.072), rough=0.85, bump=(900, 0.45, 8), sheen=0.35)
M["esd"] = node_mat("esd", (0.12, 0.2, 0.17), rough=0.8, bump=(120, 0.15))
M["benchframe"] = node_mat("benchframe", (0.25, 0.27, 0.3), metal=0.6, rough=0.4)
M["wire_colors"] = [node_mat(f"w{i}", c, rough=0.4) for i, c in enumerate([
    (0.9, 0.85, 0.8), (0.9, 0.3, 0.02), (0.9, 0.9, 0.85), (0.05, 0.12, 0.7),
    (0.9, 0.9, 0.9), (0.05, 0.5, 0.08), (0.9, 0.88, 0.85), (0.25, 0.12, 0.04)])]

# ------------------------------------------------------------- ARK-1252 box
# Upright "book" chassis modelled from the reference photo (reference/ark1252_front.png).
# Front-panel layout is given in mm: u = from the left edge, v = from the top edge.
BW, BD, BH = 0.072, 0.130, 0.200      # width (front), depth, height
BX0, BZ0 = -BW / 2, 1.0               # left edge, bottom (stands on the bench mat)
BZ1 = BZ0 + BH

def fp(u, v):
    return BX0 + u / 1000.0, BZ1 - v / 1000.0

M["panel"] = node_mat("panel", (0.035, 0.036, 0.038), metal=0.3, rough=0.55, bump=(1200, 0.06))
M["portmetal"] = node_mat("portmetal", (0.55, 0.56, 0.58), metal=1.0, rough=0.32)
M["band"] = node_mat("band", (0.80, 0.81, 0.82), metal=1.0, rough=0.28, bump=(80, 0.03))
M["labelblue"] = node_mat("labelblue", (0.015, 0.04, 0.16), rough=0.4)
M["white"] = node_mat("white", (0.9, 0.9, 0.9), rough=0.5)
M["audio_g"] = node_mat("audio_g", (0.35, 0.75, 0.25), rough=0.35)
M["audio_p"] = node_mat("audio_p", (0.8, 0.4, 0.65), rough=0.35)
M["pwr_white"] = node_mat("pwr_white", (0.85, 0.85, 0.85), rough=0.3, emit=(1, 1, 1), emit_str=0.6)

LAN_U = 11.0
LAN_V = (70.3, 97.1, 124.4)
x, z = fp(LAN_U, LAN_V[0]); LAN1 = Vector((x, 0.0, z))

chassis = boxes("ARK-1252", [((0, BD / 2, BZ0 + BH / 2), (BW, BD, BH))], M["panel"], bevel=0.0012)
# vertical cooling fins on both sides
fins = []
y = 0.017
while y < BD - 0.004:
    for sx in (-1, 1):
        fins.append(((sx * (BW / 2 + 0.0025), y, BZ0 + BH / 2), (0.005, 0.0019, BH - 0.0015)))
    y += 0.0046
boxes("fins", fins, M["fins"], bevel=0.0004)
# brushed band on the right edge of the front, thin edge on the left
boxes("band_r", [((0.0292, 0.0065, BZ0 + BH / 2), (0.0148, 0.0146, BH))], M["band"], bevel=0.0009)
boxes("band_l", [((-0.0352, 0.0065, BZ0 + BH / 2), (0.0022, 0.0146, BH))], M["band"], bevel=0.0004)
boxes("panel_lip", [((-0.0068, -0.0003, BZ1 - 0.0016), (0.0546, 0.0006, 0.0028)),
                    ((-0.0068, -0.0003, BZ0 + 0.0016), (0.0546, 0.0006, 0.0028))], M["fins"])

# openings: (u, v, w, h) in mm
OPEN = []
for v in LAN_V:
    OPEN += [(LAN_U, v, 8.7, 12.2), (LAN_U + 5.45, v, 2.2, 6.4),       # RJ45 + latch notch (+x side)
             (21.6, v, 5.9, 12.8), (30.0, v, 5.9, 12.8)]                # USB pair (vertical)
OPEN += [(21.6, 152.5, 5.9, 12.8), (30.3, 152.5, 3.0, 8.8),            # USB 7, Type-C
         (19.5, 177.0, 5.2, 16.4), (31.0, 177.5, 6.0, 15.2)]            # DP, HDMI
DEP = 0.020
def cut_items(pad=0.0):
    out = []
    for u, v, w_, h_ in OPEN:
        cx, cz = fp(u, v)
        out.append(((cx, DEP / 2 - 0.006, cz), ((w_ + pad) / 1000, DEP + 0.012, (h_ + pad) / 1000)))
    return out
cutter = boxes("cutter", cut_items(), M["portmetal"])
cutter.hide_render = True; cutter.display_type = "WIRE"
def bool_cut(ob):
    bo = ob.modifiers.new("ports", "BOOLEAN")
    bo.object = cutter; bo.solver = "EXACT"; bo.use_self = True; bo.use_hole_tolerant = True
    try:
        bo.material_mode = "TRANSFER"
    except Exception:
        pass
bool_cut(chassis)
# grey metal port frames (one block per LAN row, single frames elsewhere)
frames_ = []
for v in LAN_V:
    cx, cz = fp(18.8, v); frames_.append(((cx, -0.0003, cz), (0.0308, 0.0006, 0.0160)))
for u, v, w_, h_ in ((21.6, 152.5, 5.9, 12.8), (19.5, 177.0, 5.2, 16.4), (31.0, 177.5, 6.0, 15.2)):
    cx, cz = fp(u, v); frames_.append(((cx, -0.0003, cz), ((w_ + 2.2) / 1000, 0.0006, (h_ + 2.2) / 1000)))
pf = boxes("port_frames", frames_, M["portmetal"], bevel=0.0002)
bool_cut(pf)
# dark interiors
backs = []
for u, v, w_, h_ in OPEN:
    cx, cz = fp(u, v); backs.append(((cx, 0.0135, cz), (w_ / 1000, 0.001, h_ / 1000)))
boxes("port_backs", backs, M["blackplastic"])
# RJ45 inside: dark body + gold contacts on the left ("top") side
rj, gold = [], []
for v in LAN_V:
    cx, cz = fp(LAN_U, v)
    rj.append(((cx + 0.0015, 0.0105, cz), (0.0050, 0.006, 0.0110)))
    for k in range(8):
        gold.append(((cx - 0.0036, 0.0085, cz - 0.00357 + k * 0.00102), (0.0007, 0.009, 0.00035)))
boxes("rj45_inner", rj, M["blackplastic"]); boxes("rj45_contacts", gold, M["gold"])
# tongues: USB (black / blue), Type-C, DP, HDMI
tg_black, tg_blue = [], []
for i, v in enumerate(LAN_V):
    for u in (21.6, 30.0):
        cx, cz = fp(u, v)
        (tg_blue if (i == 2 and u == 30.0) else tg_black).append(((cx - 0.0011, 0.007, cz), (0.0018, 0.012, 0.0112)))
cx, cz = fp(21.6, 152.5); tg_blue.append(((cx - 0.0011, 0.007, cz), (0.0018, 0.012, 0.0112)))
cx, cz = fp(30.3, 152.5); tg_black.append(((cx, 0.006, cz), (0.0007, 0.010, 0.0066)))
cx, cz = fp(19.5, 177.0); tg_black.append(((cx + 0.0008, 0.007, cz), (0.0013, 0.012, 0.0140)))
cx, cz = fp(31.0, 177.5); tg_black.append(((cx + 0.0008, 0.007, cz), (0.0013, 0.012, 0.0130)))
boxes("tongues_black", tg_black, M["blackplastic"]); boxes("tongues_blue", tg_blue, M["usbblue"])

# LAN LEDs on the left of each jack (top = link, bottom = activity)
def led_box(u, v):
    cx, cz = fp(u, v); return ((cx, -0.0004, cz), (0.0016, 0.0008, 0.0030))
link_led = boxes("led_link", [led_box(5.2, LAN_V[0] - 4.4)], M["led_link"])
act_led = boxes("led_act", [led_box(5.2, LAN_V[0] + 4.4)], M["led_act"])
boxes("led_other", [led_box(5.2, v + d) for v in LAN_V[1:] for d in (-4.4, 4.4)], M["led_off"])

# power button, screw holes, audio jacks
cx, cz = fp(29.3, 18.75)
cyl("pwr_btn", (cx, -0.0006, cz), 0.0046, 0.0014, M["blackplastic"])
cyl("pwr_dot", (cx, -0.0014, cz), 0.0015, 0.0003, M["pwr_white"])
for u, v in ((8.6, 14.4), (9.4, 160.6)):
    cx, cz = fp(u, v)
    cyl("screw_hole", (cx, -0.0001, cz), 0.0030, 0.0004, node_mat("hole", (0.01, 0.01, 0.01), rough=0.8))
for v, mat in ((33.1, M["audio_g"]), (48.8, M["audio_p"])):
    cx, cz = fp(25.2, v)
    cyl("audio", (cx, -0.0009, cz), 0.0034, 0.0018, mat)
    cyl("audio_hole", (cx, -0.0019, cz), 0.0017, 0.0003, M["blackplastic"])

# DIO (DE-9, vertical)
def prism_xz(name, pts, y0, y1, mat):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    rings = [[bm.verts.new((px, yy, pz)) for px, pz in pts] for yy in (y0, y1)]
    n_ = len(pts)
    for i in range(n_):
        j = (i + 1) % n_
        bm.faces.new([rings[0][i], rings[0][j], rings[1][j], rings[1][i]])
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me)); me.materials.append(mat)
    return ob
dx, dz = fp(7.5, 41.3)
boxes("dio_flange", [((dx, -0.0005, dz), (0.0125, 0.0010, 0.0310))], M["portmetal"], bevel=0.0004)
prism_xz("dio_shell", [(dx - 0.0041, dz - 0.0085), (dx - 0.0041, dz + 0.0085),
                       (dx + 0.0041, dz + 0.0071), (dx + 0.0041, dz - 0.0071)], -0.0062, -0.0008, M["portmetal"])
prism_xz("dio_insert", [(dx - 0.0032, dz - 0.0075), (dx - 0.0032, dz + 0.0075),
                        (dx + 0.0032, dz + 0.0063), (dx + 0.0032, dz - 0.0063)], -0.0064, -0.0010, M["blackplastic"])
dpins = [((dx - 0.0014, -0.0072, dz - 0.00554 + k * 0.00277), (0.0010, 0.0020, 0.0010)) for k in range(5)]
dpins += [((dx + 0.0014, -0.0072, dz - 0.004155 + k * 0.00277), (0.0010, 0.0020, 0.0010)) for k in range(4)]
boxes("dio_pins", dpins, M["gold"])
for ddz in (-0.0125, 0.0125):
    cyl("standoff", (dx, -0.0028, dz + ddz), 0.0025, 0.0050, M["portmetal"], verts=6)

# printing (vertical, reading top-to-bottom like the real unit)
def vtext(body, u_c, v0, size_mm, mat, y=-0.0002):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body; cu.size = size_mm / 1000; cu.extrude = 0.00004
    ob = link(bpy.data.objects.new("vtxt_" + body, cu)); cu.materials.append(mat)
    x0, z0 = fp(u_c - size_mm * 0.36, v0)
    rot = Matrix(((0, 1, 0), (0, 0, -1), (-1, 0, 0)))   # cols: read=-Z, up=+X, normal=-Y
    ob.matrix_world = Matrix.Translation((x0, y, z0)) @ rot.to_4x4()
    return ob
vtext("DIO", 16.4, 36.5, 2.6, M["white"])
for v, lbl in zip(LAN_V, ("USB 1/2", "USB 3/4", "USB 5/6")):
    vtext(lbl, 36.4, v - 6.5, 2.5, M["white"])
vtext("Type-C", 36.0, 145.5, 2.4, M["white"])
vtext("USB 7", 26.6, 147.0, 2.3, M["white"])
vtext("DP", 25.0, 174.5, 2.4, M["white"])
vtext("HDMI", 37.0, 171.5, 2.4, M["white"])
vtext("LAN", 2.0, 93.0, 2.4, M["white"])
lx, _ = fp(2.0, 0)
boxes("lan_line", [((lx, -0.0002, fp(0, 79.0)[1]), (0.0003, 0.0002, 0.024)),
                   ((lx, -0.0002, fp(0, 114.0)[1]), (0.0003, 0.0002, 0.022))], M["white"])
bx, bz = fp(65.2, 28.5)
boxes("brand_label", [((bx, -0.00085, bz), (0.0062, 0.0001, 0.043))], M["labelblue"])
vtext("ADVANTECH", 65.2, 9.0, 5.4, M["white"], y=-0.00092)
vtext("ARK-1252", 65.2, 53.0, 5.0, M["blackplastic"], y=-0.00085)

# ------------------------------------------------------------- bench
boxes("bench_top", [((0.0, 0.05, 0.98), (1.8, 0.8, 0.04))], M["benchframe"], bevel=0.002)
boxes("esd_mat", [((0.0, 0.05, 1.0015), (1.7, 0.72, 0.003))], M["esd"], bevel=0.001)
boxes("bench_legs", [((x, y, 0.48), (0.05, 0.05, 0.96)) for x in (-0.85, 0.85) for y in (-0.3, 0.4)], M["benchframe"])
boxes("bench_shelf", [((0.0, 0.05, 0.22), (1.75, 0.75, 0.02))], M["benchframe"])

# props on the bench (behind / beside, out of focus)
hmi_frame = boxes("hmi", [((0.36, 0.33, 1.17), (0.32, 0.03, 0.23))], M["fins"], bevel=0.004)
hmi_screen = boxes("hmi_screen", [((0.36, 0.3145, 1.175), (0.28, 0.001, 0.18))],
                   node_mat("screen", (0.02, 0.03, 0.05), rough=0.1, emit=(0.25, 0.55, 0.9), emit_str=0.6))
boxes("hmi_stand", [((0.36, 0.36, 1.03), (0.12, 0.08, 0.06))], M["fins"])
boxes("bin", [((-0.42, 0.28, 1.05), (0.2, 0.3, 0.1))], node_mat("bin", (0.05, 0.18, 0.55), rough=0.35), bevel=0.004)
boxes("multimeter", [((0.5, -0.05, 1.02), (0.09, 0.17, 0.04))], node_mat("mm", (0.95, 0.65, 0.03), rough=0.4), bevel=0.006)
boxes("mm_display", [((0.5, -0.09, 1.0405), (0.06, 0.04, 0.001))], node_mat("lcd", (0.25, 0.3, 0.22), rough=0.15))
for i in range(5):   # coiled cable on the bench
    bpy.ops.mesh.primitive_torus_add(major_radius=0.085 + i * 0.004, minor_radius=0.0035,
                                     location=(-0.48, -0.08, 1.006 + i * 0.0045))
    bpy.context.object.data.materials.append(node_mat("coil", (0.4, 0.4, 0.42), rough=0.5))

# ------------------------------------------------------------- factory hall
concrete = bpy.data.materials.new("concrete"); concrete.use_nodes = True
nt = concrete.node_tree; b = nt.nodes["Principled BSDF"]
nz = nt.nodes.new("ShaderNodeTexNoise"); nz.inputs["Scale"].default_value = 1.5; nz.inputs["Detail"].default_value = 8
cr = nt.nodes.new("ShaderNodeValToRGB")
cr.color_ramp.elements[0].color = (0.18, 0.2, 0.19, 1); cr.color_ramp.elements[1].color = (0.34, 0.36, 0.34, 1)
nt.links.new(nz.outputs["Fac"], cr.inputs["Fac"]); nt.links.new(cr.outputs["Color"], b.inputs["Base Color"])
b.inputs["Roughness"].default_value = 0.35
floor = boxes("floor", [((0, 15, -0.01), (60, 60, 0.02))], concrete)
boxes("walkway", [((x, 14, 0.002), (0.12, 40, 0.002)) for x in (-2.2, 2.2)],
      node_mat("yellowline", (0.85, 0.6, 0.02), rough=0.5))
boxes("green_zone", [((0, 14, 0.001), (4.3, 40, 0.001))], node_mat("epoxy", (0.12, 0.3, 0.2), rough=0.2))
boxes("columns", [((x, y, 4.5), (0.45, 0.45, 9)) for x in (-5.5, 5.5) for y in (4, 12, 20, 28)],
      node_mat("colpaint", (0.75, 0.55, 0.05), rough=0.5))
boxes("back_wall", [((0, 32, 5), (60, 0.3, 10))], node_mat("wall", (0.55, 0.57, 0.6), rough=0.8))
win = node_mat("window", (0.8, 0.85, 0.9), emit=(0.75, 0.85, 1.0), emit_str=6)
boxes("windows", [((x, 31.8, 6.5), (3.2, 0.1, 2.2)) for x in (-12, -6, 0, 6, 12)], win)
mach_white = node_mat("machine", (0.78, 0.8, 0.8), rough=0.3)
mach_blue = node_mat("machine_blue", (0.05, 0.2, 0.5), rough=0.35)
mach_orange = node_mat("machine_or", (0.9, 0.35, 0.04), rough=0.35)
scr = node_mat("mscreen", (0.02, 0.02, 0.03), emit=(0.4, 0.75, 1.0), emit_str=4)
machines = [(-3.2, 4.5, 2.6, 1.8, 2.2), (3.0, 5.5, 3.0, 2.0, 2.4), (-3.4, 9.5, 2.4, 2.0, 2.0),
            (3.4, 11, 2.8, 2.2, 2.6), (-3.0, 15, 2.6, 2.0, 2.3), (3.2, 17, 2.4, 2.0, 2.1)]
for i, (x, y, w, d, h) in enumerate(machines):
    boxes(f"mach{i}", [((x, y, h / 2), (w, d, h))], mach_white, bevel=0.03)
    boxes(f"mstripe{i}", [((x, y - d / 2 - 0.01, h * 0.82), (w * 0.98, 0.02, 0.18))],
          mach_blue if i % 2 == 0 else mach_orange)
    boxes(f"mscr{i}", [((x + w * 0.3, y - d / 2 - 0.02, h * 0.6), (0.35, 0.02, 0.25))], scr)
    boxes(f"mdoor{i}", [((x - w * 0.15, y - d / 2 - 0.012, h * 0.45), (w * 0.45, 0.01, h * 0.55))],
          node_mat(f"glass{i}", (0.1, 0.12, 0.13), rough=0.05, metal=0.3))
# pallet racks with boxes
rack = node_mat("rack_or", (0.85, 0.3, 0.03), rough=0.4)
beam = node_mat("rack_bl", (0.04, 0.15, 0.5), rough=0.4)
card = node_mat("carton", (0.55, 0.38, 0.2), rough=0.8)
for y in (22.0,):
    boxes("rack_up", [((x, y, 3), (0.1, 1.1, 6)) for x in range(-10, 11, 3)], rack)
    boxes("rack_beam", [((0, y - 0.5, z), (21, 0.08, 0.12)) for z in (0.2, 2.0, 3.8, 5.6)], beam)
    cartons = []
    for z in (0.3, 2.1, 3.9):
        for x in range(-10, 10):
            if random.random() < 0.8:
                hh = random.uniform(0.6, 1.4)
                cartons.append(((x + 0.5, y, z + hh / 2), (random.uniform(0.7, 0.95), 0.9, hh)))
    boxes("cartons", cartons, card)
# conveyor in the middle distance
boxes("conveyor", [((0, 7.5, 0.85), (6, 0.6, 0.08)), ((0, 7.5, 0.45), (5.8, 0.1, 0.8))],
      node_mat("conv", (0.2, 0.21, 0.22), metal=0.5, rough=0.4))
boxes("conv_belt", [((0, 7.5, 0.895), (6, 0.5, 0.01))], node_mat("belt", (0.03, 0.03, 0.03), rough=0.7))
boxes("conv_boxes", [((x, 7.5, 1.05), (0.4, 0.35, 0.3)) for x in (-2.0, -0.6, 1.3)], card)
# high-bay lights
hb = node_mat("highbay", (1, 1, 1), emit=(1.0, 0.95, 0.88), emit_str=30)
lamps = []
for x in (-7, -2.5, 2.5, 7):
    for y in (2, 8, 14, 20, 26):
        lamps.append(((x, y, 8.5), (0.5, 1.4, 0.06)))
boxes("highbays", lamps, hb)

# lights
def area(name, loc, rot, size, energy, color=(1, 1, 1), shape="RECTANGLE", size_y=None):
    ld = bpy.data.lights.new(name, "AREA"); ld.energy = energy; ld.color = color
    ld.shape = shape; ld.size = size
    if size_y: ld.size_y = size_y
    ob = link(bpy.data.objects.new(name, ld)); ob.location = loc; ob.rotation_euler = rot
    return ob
area("bench_lamp", (0.05, -0.05, 2.0), (0, 0, 0), 1.2, 70, (1.0, 0.96, 0.9), size_y=0.25)
area("key", (-0.9, -0.9, 1.9), (math.radians(55), 0, math.radians(-40)), 0.8, 45, (1.0, 0.93, 0.85))
area("rim", (0.6, 1.2, 1.7), (math.radians(-60), 0, math.radians(200)), 1.0, 40, (0.75, 0.85, 1.0))
for x in (-4.5, 4.5):
    for y in (6, 16):
        area(f"hall{x}{y}", (x, y, 8.0), (0, 0, 0), 4.0, 1800, (1.0, 0.95, 0.88))
w = bpy.data.worlds.new("world"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.35, 0.4, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35

# ------------------------------------------------------------- RJ45 plug (local: tip at origin, +Y = insert)
plug = empty("PlugRoot")
parts = []
parts.append(boxes("plug_body", [((0, -0.0105, 0), (0.0117, 0.021, 0.0080))], M["clear"], bevel=0.0006))
cts = [((-0.00357 + k * 0.00102, -0.0025, 0.0028), (0.00030, 0.0040, 0.0022)) for k in range(8)]
parts.append(boxes("plug_contacts", cts, M["gold"]))
for k in range(8):
    o = cyl(f"plug_wire{k}", (-0.00357 + k * 0.00102, -0.013, 0.0004), 0.00045, 0.016,
            M["wire_colors"][k], verts=8)
    parts.append(o)
latch = boxes("plug_latch", [((0, -0.0105, -0.0052), (0.0060, 0.013, 0.0011))], M["clear"], bevel=0.0003)
latch.rotation_euler = (math.radians(-9), 0, 0); latch.location = (0, 0.0, 0.0006)
parts.append(latch)
# boot: tapered tube
bpy.ops.mesh.primitive_cone_add(radius1=0.0068, radius2=0.0037, depth=0.026, vertices=32,
                                location=(0, -0.034, 0), rotation=(math.radians(90), 0, 0))
boot = bpy.context.object; boot.name = "plug_boot"; boot.data.materials.append(M["boot"])
boot.scale = (1.0, 1.0, 0.82)
bpy.ops.object.shade_smooth(); parts.append(boot)
parts.append(boxes("boot_front", [((0, -0.0225, 0), (0.0128, 0.004, 0.0094))], M["boot"], bevel=0.0012))
for p in parts:
    p.parent = plug

# ------------------------------------------------------------- gloved hand
# Right hand in its own frame H (metres): origin = wrist centre, +Y towards the
# fingers, +Z = back of the hand, thumb on the -X side. Fingers and palm are
# tapered capsules / ellipsoids merged with a voxel remesh, then smoothed and
# given fabric wrinkles. White knit glove with grey PU coating on the palm side
# and fingertips; letting go of the plug is a shape key.
import numpy as np
from mathutils import noise as mnoise

def _fib(n):
    ga = math.pi * (3 - math.sqrt(5)); out = []
    for i in range(n):
        y = 1 - 2 * (i + 0.5) / n; rr = math.sqrt(max(0.0, 1 - y * y))
        out.append(Vector((math.cos(ga * i) * rr, y, math.sin(ga * i) * rr)))
    return out
UNIT = _fib(120)
HV, HF = [], []

def ball(c, rad, rot=None):
    rx, ry, rz = rad if isinstance(rad, (tuple, list)) else (rad, rad, rad)
    R = rot if rot is not None else Matrix.Identity(3)
    c = Vector(c)
    return [c + R @ Vector((u.x * rx, u.y * ry, u.z * rz)) for u in UNIT]

def hull(pts):
    bm = bmesh.new()
    for p in pts:
        bm.verts.new(p)
    res = bmesh.ops.convex_hull(bm, input=list(bm.verts))
    junk = list({g for g in res["geom_interior"] + res["geom_unused"] if isinstance(g, bmesh.types.BMVert)})
    if junk:
        bmesh.ops.delete(bm, geom=junk, context="VERTS")
    bm.verts.index_update()
    off = len(HV)
    HV.extend(v.co.copy() for v in bm.verts)
    HF.extend([off + v.index for v in f.verts] for f in bm.faces)
    bm.free()

SEGS = []   # (chain, i, a, b, ra, rb, dorsal, s0) -> coat mask + release weights
def chain(name, pts, radii, dorsals):
    s = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        hull(ball(a, radii[i]) + ball(b, radii[i + 1]))
        SEGS.append((name, i, a.copy(), b.copy(), radii[i], radii[i + 1], dorsals[i].copy(), s))
        s += (b - a).length
    for i in range(1, len(pts) - 1):            # knuckles bulge on the back
        hull(ball(pts[i] + dorsals[i - 1] * radii[i] * 0.18, radii[i] * 1.0))

def finger_fk(base, d, flex, lens):
    d = Vector(d).normalized(); n = Vector((0, 0, 1)); n = (n - d * n.dot(d)).normalized()
    side = d.cross(n)
    pts, dors = [Vector(base)], []
    for L, a in zip(lens, flex):
        R = Matrix.Rotation(math.radians(-a), 3, side)
        d = R @ d; n = R @ n
        pts.append(pts[-1] + d * L); dors.append(n.copy())
    return pts, dors, side

def ik2(root, target, l1, l2, pole):
    v = target - root; D = min(v.length, (l1 + l2) * 0.995); vh = v.normalized()
    ca = max(-1.0, min(1.0, (l1 * l1 + D * D - l2 * l2) / (2 * l1 * D)))
    p = (pole - vh * pole.dot(vh)).normalized()
    j = root + vh * (l1 * ca) + p * (l1 * math.sqrt(1 - ca * ca))
    return j, j + (root + vh * D - j).normalized() * l2

FING = {   # MCP, base direction, phalanx lengths (centre to centre), radii MCP/PIP/DIP/tip, flexion
    "index":  ((-0.031, 0.092, 0.000), (-0.07, 1, 0), (0.040, 0.023, 0.014), (0.0092, 0.0085, 0.0077, 0.0069), (45, 55, 25)),
    "middle": ((-0.010, 0.097, 0.000), (0.00, 1, 0), (0.044, 0.027, 0.015), (0.0094, 0.0087, 0.0078, 0.0070), (72, 88, 42)),
    "ring":   ((0.010, 0.093, -0.001), (0.04, 1, 0), (0.041, 0.025, 0.014), (0.0089, 0.0082, 0.0073, 0.0066), (78, 90, 42)),
    "little": ((0.029, 0.083, -0.003), (0.09, 1, 0), (0.033, 0.018, 0.012), (0.0079, 0.0072, 0.0064, 0.0057), (84, 88, 38)),
}
# how the hand sits in the world when the plug is seated: palm down, then
# yaw (fingers point forward-left), pitch (fingers down), roll (thumb side up)
PSI, PHI, RHO = 28.0, 10.0, 30.0
W_HAND = (Matrix.Rotation(math.radians(PSI), 3, "Z") @ Matrix.Rotation(math.radians(-PHI), 3, "X")
          @ Matrix.Rotation(math.radians(RHO), 3, "Y"))
U_H = W_HAND.transposed() @ Vector((0, 1, 0))          # plug axis in H
GRIP = 0.036                                           # grip point behind the plug tip
BOOT_R = 0.0068 - (GRIP - 0.0235) / 0.021 * 0.0031       # tapered boot radius there

FK = {nm: finger_fk(*spec[:2], spec[4], spec[2]) for nm, spec in FING.items()}
for nm, spec in FING.items():
    pts, dors, side = FK[nm]
    chain(nm, pts, spec[3], dors)
    hull(ball(pts[0] + Vector((0, 0.002, 1)) * spec[3][0] * 0.32, spec[3][0] * 0.95))   # MCP knuckle

# boot sits against the radial side of the index middle phalanx, thumb presses from the other side
ipts, idors, iside = FK["index"]
mid = ipts[1].lerp(ipts[2], 0.65)
c_dir = (-iside * math.cos(math.radians(30)) - idors[1] * math.sin(math.radians(30)))
N_P = (c_dir - U_H * c_dir.dot(U_H)).normalized()      # index -> thumb across the boot
G_H = mid + N_P * (0.0081 + BOOT_R)
T_TIP = G_H + N_P * (BOOT_R + 0.0089)
CMC = Vector((-0.026, 0.034, -0.015))
meta_dir = ((T_TIP - CMC).normalized() + Vector((-0.30, -0.10, -0.30))).normalized()
T_MCP = CMC + meta_dir * 0.046
T_IP, T_END = ik2(T_MCP, T_TIP, 0.035, 0.021, Vector((-0.6, 0.0, 0.6)))
tpts = [CMC, T_MCP, T_IP, T_END]
tdors = []
for i in range(3):
    d = (tpts[i + 1] - tpts[i]).normalized()
    up = (N_P if i else (Vector((-1, 0, 1)).normalized()))
    tdors.append((up - d * up.dot(d)).normalized())
chain("thumb", tpts, (0.0125, 0.0110, 0.0100, 0.0089), tdors)

# palm, thenar / hypothenar pads, first web, wrist and glove cuff
hull(ball((-0.019, 0.018, -0.002), 0.013) + ball((0.019, 0.018, -0.002), 0.013)
     + ball((-0.031, 0.090, 0.0), 0.0112) + ball((-0.010, 0.095, 0.0), 0.0116)
     + ball((0.010, 0.091, -0.001), 0.0110) + ball((0.029, 0.081, -0.003), 0.0098)
     + ball((-0.016, 0.058, -0.002), 0.0138) + ball((0.017, 0.055, -0.003), 0.0138)
     + ball((0.032, 0.050, -0.004), 0.0102))
hull(ball((-0.023, 0.042, -0.012), (0.015, 0.026, 0.014), Matrix.Rotation(math.radians(-25), 3, "Z")))
hull(ball((0.024, 0.044, -0.009), (0.011, 0.025, 0.011)))
hull(ball(CMC, 0.009) + ball(T_MCP.lerp(T_IP, 0.12), 0.0062) + ball(Vector((-0.031, 0.088, -0.002)), 0.0072))
hull(ball((0, 0.006, -0.001), (0.030, 0.006, 0.0205)) + ball((0, -0.052, -0.001), (0.034, 0.006, 0.0240)))

me_src = bpy.data.meshes.new("hand_src"); me_src.from_pydata([tuple(v) for v in HV], [], HF)
src = link(bpy.data.objects.new("hand_src", me_src))
mr = src.modifiers.new("remesh", "REMESH"); mr.mode = "VOXEL"; mr.voxel_size = 0.0007; mr.adaptivity = 0.0
ms = src.modifiers.new("smooth", "SMOOTH"); ms.factor = 0.6; ms.iterations = 6
wtex = bpy.data.textures.new("wrinkle", "CLOUDS"); wtex.noise_scale = 0.011; wtex.noise_depth = 3
md = src.modifiers.new("wrinkle", "DISPLACE"); md.texture = wtex; md.texture_coords = "LOCAL"
md.strength = 0.0014; md.mid_level = 0.5
md.show_viewport = False     # classify coat / weights on the un-wrinkled surface
me0 = bpy.data.meshes.new_from_object(src.evaluated_get(bpy.context.evaluated_depsgraph_get()))
md.show_viewport = True
me = bpy.data.meshes.new_from_object(src.evaluated_get(bpy.context.evaluated_depsgraph_get()))
bpy.data.objects.remove(src); bpy.data.meshes.remove(me_src)
assert len(me0.vertices) == len(me.vertices)
me.name = "glove"; me.shade_smooth()
glove = link(bpy.data.objects.new("glove", me))

# per-vertex: nearest bone -> PU coat mask and release weights
nv = len(me.vertices)
P = np.empty(nv * 3); me.vertices.foreach_get("co", P); P = P.reshape(-1, 3)
NN = np.empty(nv * 3); me0.vertex_normals.foreach_get("vector", NN); NN = NN.reshape(-1, 3)
bpy.data.meshes.remove(me0)
SA = np.array([s[2] for s in SEGS]); SB = np.array([s[3] for s in SEGS])
SRA = np.array([s[4] for s in SEGS]); SRB = np.array([s[5] for s in SEGS])
SD = np.array([s[6] for s in SEGS]); S0 = np.array([s[7] for s in SEGS])
AB = SB - SA; L2 = (AB ** 2).sum(1)
kmin = np.zeros(nv, int); dmin = np.zeros(nv); tmin = np.zeros(nv)
for c0 in range(0, nv, 30000):
    p = P[c0:c0 + 30000]
    rel = p[:, None, :] - SA[None]
    t = np.clip((rel * AB[None]).sum(2) / L2[None], 0, 1)
    d = np.linalg.norm(rel - t[..., None] * AB[None], axis=2) - (SRA[None] + t * (SRB - SRA)[None])
    k = d.argmin(1)
    kmin[c0:c0 + 30000] = k; dmin[c0:c0 + 30000] = d[np.arange(len(k)), k]
    tmin[c0:c0 + 30000] = t[np.arange(len(k)), k]
on_finger = dmin < 0.0025
seg_i = np.array([s[1] for s in SEGS])[kmin]
dot_d = (NN * SD[kmin]).sum(1)
def _ss(x):
    x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)
coat_f = np.maximum(_ss((0.05 - dot_d) / 0.20), (seg_i == 2) * _ss((tmin - 0.50) / 0.12))
coat_p = _ss((-NN[:, 2] - 0.15) / 0.30)
coat = np.where(on_finger, coat_f, coat_p) * _ss((P[:, 1] - 0.012) / 0.008)
att = me.attributes.new("coat", "FLOAT", "POINT"); att.data.foreach_set("value", coat.astype(np.float32))

def rotate_about(pts, piv, axis, ang):
    a = np.array(axis.normalized()); v = pts - np.array(piv)
    c, s = np.cos(ang)[:, None], np.sin(ang)[:, None]
    return np.array(piv) + v * c + np.cross(a, v) * s + a * (v @ a)[:, None] * (1 - c)

def smoothstep(x):
    x = np.clip(x, 0, 1); return x * x * (3 - 2 * x)

names = np.array([s[0] for s in SEGS])[kmin]
s_par = S0[kmin] + tmin * np.sqrt(L2[kmin])
REL_P = P.copy()
m_t = on_finger & (names == "thumb")
w_t = smoothstep((s_par[m_t] - 0.038) / 0.018)
REL_P[m_t] = rotate_about(P[m_t], T_MCP, (T_END - T_MCP).cross(N_P), np.radians(22) * w_t)
m_i = on_finger & (names == "index")
w_i = smoothstep((s_par[m_i] - 0.002) / 0.016)
REL_P[m_i] = rotate_about(P[m_i], ipts[0], (ipts[3] - ipts[0]).cross(-N_P), np.radians(14) * w_i)
glove.shape_key_add(name="Basis", from_mix=False)
SK_REL = glove.shape_key_add(name="release", from_mix=False)
SK_REL.data.foreach_set("co", REL_P.ravel())

gm = bpy.data.materials.new("glove"); gm.use_nodes = True
gn = gm.node_tree.nodes; gl = gm.node_tree.links.new
gn.remove(gn["Principled BSDF"])
knit = gn.new("ShaderNodeBsdfPrincipled"); pu = gn.new("ShaderNodeBsdfPrincipled")
knit.inputs["Base Color"].default_value = (0.50, 0.51, 0.52, 1); knit.inputs["Roughness"].default_value = 0.92
knit.inputs["Sheen Weight"].default_value = 0.45; knit.inputs["Sheen Roughness"].default_value = 0.4
knit.inputs["Specular IOR Level"].default_value = 0.3
pu.inputs["Base Color"].default_value = (0.055, 0.058, 0.064, 1); pu.inputs["Roughness"].default_value = 0.48
tco = gn.new("ShaderNodeTexCoord")
fuzz = gn.new("ShaderNodeTexNoise"); fuzz.inputs["Scale"].default_value = 2600; fuzz.inputs["Detail"].default_value = 6
gl(tco.outputs["Object"], fuzz.inputs["Vector"])
rows = gn.new("ShaderNodeTexWave"); rows.wave_type = "BANDS"; rows.bands_direction = "Y"
rows.inputs["Scale"].default_value = 700; rows.inputs["Distortion"].default_value = 3.0
gl(tco.outputs["Object"], rows.inputs["Vector"])
hgt = gn.new("ShaderNodeMath"); hgt.operation = "MULTIPLY_ADD"; hgt.inputs[1].default_value = 0.5
gl(rows.outputs["Fac"], hgt.inputs[0]); gl(fuzz.outputs["Fac"], hgt.inputs[2])
bmp = gn.new("ShaderNodeBump"); bmp.inputs["Strength"].default_value = 0.6; bmp.inputs["Distance"].default_value = 0.0004
gl(hgt.outputs[0], bmp.inputs["Height"])
gl(bmp.outputs["Normal"], knit.inputs["Normal"]); gl(bmp.outputs["Normal"], pu.inputs["Normal"])
attr = gn.new("ShaderNodeAttribute"); attr.attribute_name = "coat"
edge = gn.new("ShaderNodeTexNoise"); edge.inputs["Scale"].default_value = 140; edge.inputs["Detail"].default_value = 2
gl(tco.outputs["Object"], edge.inputs["Vector"])
jit = gn.new("ShaderNodeMath"); jit.operation = "MULTIPLY_ADD"; jit.inputs[1].default_value = 0.07
gl(edge.outputs["Fac"], jit.inputs[0]); gl(attr.outputs["Fac"], jit.inputs[2])
mr2 = gn.new("ShaderNodeMapRange")
mr2.inputs["From Min"].default_value = 0.52; mr2.inputs["From Max"].default_value = 0.56
gl(jit.outputs[0], mr2.inputs["Value"])
mix = gn.new("ShaderNodeMixShader")
gl(mr2.outputs["Result"], mix.inputs["Fac"]); gl(knit.outputs[0], mix.inputs[1]); gl(pu.outputs[0], mix.inputs[2])
gl(mix.outputs[0], gn["Material Output"].inputs["Surface"])
me.materials.append(gm)

# work-jacket sleeve with a rib-knit cuff, running back along -Y towards the elbow
SV, SF = [], []
ring_n, seg_n, y0, y1 = 90, 160, -0.022, -0.48
for i in range(ring_n):
    s = i / (ring_n - 1); y = y0 + (y1 - y0) * s
    cuffw = 1 - smooth(min(max((s - 0.045) / 0.05, 0), 1))
    rx = lerp(0.050, 0.036, cuffw) + 0.010 * s; rz = lerp(0.045, 0.030, cuffw) + 0.008 * s
    bend = Vector((0.11 * s * s, 0, -0.03 * s))      # sags towards the elbow
    for j in range(seg_n):
        a = 2 * math.pi * j / seg_n; ca, sa = math.cos(a), math.sin(a)
        q = Vector((ca * 1.4, y * 16, sa * 1.4))
        fold = (0.07 * mnoise.noise(q) + 0.03 * mnoise.noise(q * 2.9)) * (1 - cuffw)
        fold += 0.05 * max(0.0, math.sin(y * 210 + 1.7 * mnoise.noise(q * 0.7))) * (1 - cuffw) * (1 - s) ** 2
        rib = 0.025 * cuffw * (0.5 + 0.5 * math.cos(a * 44))
        k = 1 + fold + rib
        SV.append(Vector((ca * rx * k, y + 0.003 * mnoise.noise(q * 1.7), sa * rz * k)) + bend)
for i in range(ring_n - 1):
    for j in range(seg_n):
        SF.append((i * seg_n + j, i * seg_n + (j + 1) % seg_n, (i + 1) * seg_n + (j + 1) % seg_n, (i + 1) * seg_n + j))
sme = bpy.data.meshes.new("sleeve"); sme.from_pydata([tuple(v) for v in SV], [], SF); sme.shade_smooth()
M["cuff"] = node_mat("cuff", (0.016, 0.026, 0.06), rough=0.9, bump=(2200, 0.5, 6), sheen=0.3)
sme.materials.append(M["sleeve"]); sme.materials.append(M["cuff"])
sme.polygons.foreach_set("material_index", [1 if (pi // seg_n) <= int(0.05 * (ring_n - 1)) else 0
                                            for pi in range(len(SF))])
sleeve = link(bpy.data.objects.new("sleeve", sme))
so = sleeve.modifiers.new("thick", "SOLIDIFY"); so.thickness = 0.0025; so.offset = -1
sleeve.modifiers.new("sub", "SUBSURF").levels = 1
sleeve.modifiers["sub"].render_levels = 1

# H -> plug-local, so the boot lands between thumb and index when the plug is seated
SEAT = LAN1 + Vector((0, 0.0135, 0))
R0 = Matrix.Rotation(math.radians(-90), 4, "Y")   # plug top -> -X, latch -> +X
PM_SEAT = Matrix.Translation(SEAT) @ R0
B_W = PM_SEAT @ Vector((0, -GRIP, 0))
HW_SEAT = Matrix.Translation(B_W - W_HAND @ G_H) @ W_HAND.to_4x4()
HP = PM_SEAT.inverted() @ HW_SEAT
hand = empty("HandRoot")
for ob in (glove, sleeve):
    ob.parent = hand; ob.matrix_basis = HP
BACK_W = (W_HAND @ Vector((0, -1, 0))).normalized()  # forearm direction in the world

# report clearances at the seated pose
_pw = np.array([tuple(HW_SEAT @ Vector(v)) for v in P[::7]])
_inbox = (np.abs(_pw[:, 0]) < BW / 2) & (_pw[:, 2] > BZ0) & (_pw[:, 2] < BZ1)
_ib = np.where(_inbox)[0]; _k = _ib[_pw[_ib, 1].argmax()] if len(_ib) else None
print("[hand] verts", nv, "| nearest to panel (mm):", round(-_pw[_k, 1] * 1000, 1) if _k is not None else None,
      "at H", tuple(np.round(P[::7][_k] * 1000, 1)) if _k is not None else "")
_pl = np.array([tuple(PM_SEAT.inverted() @ Vector(v)) for v in _pw])
_bt = (_pl[:, 1] < -0.020) & (_pl[:, 1] > -0.047) & (np.hypot(_pl[:, 0], _pl[:, 2]) < BOOT_R - 0.0008)
_bd = (np.abs(_pl[:, 0]) < 0.0055) & (_pl[:, 1] < 0) & (_pl[:, 1] > -0.021) & (np.abs(_pl[:, 2]) < 0.0037)
print("[hand] verts inside boot:", int(_bt.sum()), "inside plug body:", int(_bd.sum()))
print("[hand] forearm dir (world):", tuple(round(c, 3) for c in BACK_W), "thumb reach ok:",
      round((T_END - T_TIP).length * 1000, 2), "mm off")

# ------------------------------------------------------------- cable (bezier, keyed per frame)
ccu = bpy.data.curves.new("cable", "CURVE"); ccu.dimensions = "3D"
ccu.bevel_depth = 0.0029; ccu.bevel_resolution = 6; ccu.resolution_u = 24
csp = ccu.splines.new("BEZIER"); csp.bezier_points.add(4)
for p in csp.bezier_points:
    p.handle_left_type = p.handle_right_type = "FREE"
cable = link(bpy.data.objects.new("cable", ccu)); ccu.materials.append(M["cable"])

# ------------------------------------------------------------- camera
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50; cam_d.clip_start = 0.01
cam_d.dof.use_dof = True; cam_d.dof.aperture_fstop = 4.0; cam_d.dof.aperture_blades = 7
cam = link(bpy.data.objects.new("camera", cam_d)); sc.camera = cam
look = empty("look"); focus = empty("focus", LAN1 + Vector((0, -0.006, 0)))
cam_d.dof.focus_object = focus
tc = cam.constraints.new("TRACK_TO"); tc.target = look
tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"

# ------------------------------------------------------------- animation
def plug_pose(f):
    """returns (location, euler) of plug tip"""
    start = SEAT + BACK_W * 0.22 + Vector((0, 0, 0.05))
    near = SEAT + Vector((0.0, -0.030, 0.002))
    align = SEAT + Vector((0.0, -0.0155, 0.0))
    r0 = Vector((0.20, -0.35, 0.55)); r1 = Vector((0.03, 0.05, 0.06))
    if f <= 42:
        t = smoother((f - 1) / 41)
        # arc in through a mid point
        mid = SEAT + BACK_W * 0.11 + Vector((0, -0.025, 0.03))
        a = vlerp(start, mid, t); b_ = vlerp(mid, near, t)
        loc = a.lerp(b_, t)
        rot = r0.lerp(r1, smooth(t))
    elif f <= 60:
        t = smooth((f - 42) / 18)
        wig = math.sin(t * math.pi * 2.2) * (1 - t)
        loc = near.lerp(align, t) + Vector((0.0016 * wig, 0, 0.0008 * wig))
        rot = r1.lerp(Vector((0, 0, 0)), t) + Vector((0, 0.01 * wig, 0.015 * wig))
    elif f <= 71:
        t = (f - 60) / 11
        # slow entry, resistance at latch, final push
        t = 0.55 * smooth(min(t / 0.6, 1)) + 0.45 * smoother(max((t - 0.55) / 0.45, 0))
        loc = align.lerp(SEAT, t); rot = Vector((0, 0, 0))
    else:
        loc = SEAT.copy(); rot = Vector((0, 0, 0))
    return loc, Euler(rot)

def plug_matrix(f):
    loc, rot = plug_pose(f)
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4() @ R0

def hand_matrix(f):
    REL = 80
    if f <= REL:
        m = plug_matrix(f)
        if f > 71:   # push-through: hand settles after the click
            m = Matrix.Translation((0, -0.0006 * smooth((f - 71) / 9), 0)) @ m
        return m
    t = smoother((f - REL) / (F_END - REL))
    base = hand_matrix(REL)
    off = BACK_W * 0.30 * t + Vector((0, 0, 0.02)) * t
    rot = Euler((0.0, 0.0, -0.15 * t)).to_matrix().to_4x4()
    piv = base.to_translation()
    return Matrix.Translation(piv + off) @ rot @ Matrix.Translation(-piv) @ base

def cam_loc(f):
    t = smooth((f - 1) / (F_END - 1))
    shake = Vector((math.sin(f * 0.37) + 0.5 * math.sin(f * 0.91 + 1.3),
                    0.4 * math.sin(f * 0.23 + 0.7),
                    math.sin(f * 0.29 + 2.1) + 0.4 * math.sin(f * 1.07))) * 0.0006
    return vlerp((-0.30, -0.50, 1.235), (-0.20, -0.355, 1.205), t) + shake

def look_loc(f):
    t = smooth((f - 1) / (F_END - 1))
    return vlerp((0.005, -0.02, 1.098), (-0.012, -0.005, 1.128), t)

def tangent_pts(pts, t0):
    """free handles: Catmull-Rom; first tangent forced to t0"""
    hl, hr = [], []
    n = len(pts)
    for i in range(n):
        if i == 0:
            tg = t0
        elif i == n - 1:
            tg = (pts[i] - pts[i - 1]) * 0.5
        else:
            tg = (pts[i + 1] - pts[i - 1]) * 0.5
        seg = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).length * 0.22
        tgn = tg.normalized() * seg if tg.length > 1e-6 else tg
        hl.append(pts[i] - tgn); hr.append(pts[i] + tgn)
    return hl, hr

CABLE_P1 = Vector((-0.030, -0.095, 0.012))   # plug-local: drops under the hand

def cable_pts(f):
    m = plug_matrix(f)
    p0 = m @ Vector((0, -0.044, 0))
    p1 = m @ CABLE_P1
    axis = (m.to_3x3() @ Vector((0, -1, 0))).normalized()
    p4 = Vector((-0.70, -0.33, 1.0035))
    p3 = Vector((-0.20, -0.30, 1.0035))
    p2 = (p1 + p3) / 2 + Vector((0, -0.03, -0.06))
    p2.z = max(p2.z, 1.0035)
    pts = [p0, p1, p2, p3, p4]
    hl, hr = tangent_pts(pts, axis * 0.07)
    return pts, hl, hr

frames = range(1, F_END + 1)
prefs.keyframe_new_interpolation_type = "LINEAR"
for f in frames:
    for ob, m in ((plug, plug_matrix(f)), (hand, hand_matrix(f))):
        ob.matrix_world = m
        ob.keyframe_insert("location", frame=f); ob.keyframe_insert("rotation_euler", frame=f)
    cam.location = cam_loc(f); cam.keyframe_insert("location", frame=f)
    look.location = look_loc(f); look.keyframe_insert("location", frame=f)
    pts, hl, hr = cable_pts(f)
    for i, p in enumerate(csp.bezier_points):
        p.co, p.handle_left, p.handle_right = pts[i], hl[i], hr[i]
        p.keyframe_insert("co", frame=f); p.keyframe_insert("handle_left", frame=f)
        p.keyframe_insert("handle_right", frame=f)

# release grip: thumb and index open (shape key)
for f in [1] + list(range(74, 85)):
    SK_REL.value = smooth((f - 74) / 10); SK_REL.keyframe_insert("value", frame=f)

# LEDs: link turns on when the plug clicks in, activity blinks after that (keyed every frame)
lk = M["led_link"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
ak = M["led_act"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
on = False
for f in range(1, F_END + 1):
    lk.default_value = 14 if f >= 73 else 0
    lk.keyframe_insert("default_value", frame=f)
    if f >= 77 and random.random() < 0.45:
        on = not on
    ak.default_value = 12 if (on and f >= 77) else 0
    ak.keyframe_insert("default_value", frame=f)
prefs.keyframe_new_interpolation_type = "BEZIER"

if args.check:
    from mathutils.geometry import interpolate_bezier
    for f in range(1, F_END + 1, 3):
        sc.frame_set(f)
        ev = glove.evaluated_get(bpy.context.evaluated_depsgraph_get())
        em = ev.to_mesh(); nvv = len(em.vertices)
        Q = np.empty(nvv * 3); em.vertices.foreach_get("co", Q); ev.to_mesh_clear()
        Q = Q.reshape(-1, 3)[::4]
        Mw = np.array(glove.matrix_world)
        Q = Q @ Mw[:3, :3].T + Mw[:3, 3]
        pts, hl, hr = cable_pts(f)
        cs = []
        for i in range(len(pts) - 1):
            cs += interpolate_bezier(pts[i], hr[i], hl[i + 1], pts[i + 1], 24)
        C = np.array([tuple(c) for c in cs])
        dmin_c = min(np.linalg.norm(Q - c, axis=1).min() for c in C) - 0.0029
        inb = (np.abs(Q[:, 0]) < BW / 2) & (Q[:, 2] > BZ0) & (Q[:, 2] < BZ1) & (Q[:, 1] > -0.0005)
        print(f"[check] f{f:3d} cable-hand gap {dmin_c * 1000:6.1f} mm | hand verts in box: {int(inb.sum())}")
    sys.exit(0)

# ------------------------------------------------------------- render settings
rx, ry = (int(v) for v in args.res.split("x"))
r = sc.render
r.engine = "CYCLES"; sc.cycles.device = "CPU"
r.resolution_x, r.resolution_y = rx, ry; r.resolution_percentage = 100
r.fps = FPS
sc.cycles.samples = args.samples
sc.cycles.use_adaptive_sampling = True; sc.cycles.adaptive_threshold = 0.02
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6; sc.cycles.transmission_bounces = 8
sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
r.use_motion_blur = True; r.motion_blur_shutter = 0.4
r.use_persistent_data = True
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.view_settings.exposure = 0.0
r.image_settings.file_format = "PNG"
r.filepath = args.out.rstrip("/") + "/f_"
if args.blend:
    bpy.ops.wm.save_as_mainfile(filepath=args.blend)
if args.cam:
    v = [float(c) for c in args.cam.split(",")]
    cam.animation_data_clear(); look.animation_data_clear()
    cam.location = v[:3]; look.location = v[3:6]
    if len(v) > 6: cam_d.lens = v[6]
    cam_d.dof.use_dof = False
if args.still:
    sc.frame_set(args.still)
    r.filepath = args.out.rstrip("/") + f"/still_{args.still:04d}.png"
    bpy.ops.render.render(write_still=True)
else:
    a, b_ = (int(v) for v in args.frames.split("-"))
    sc.frame_start, sc.frame_end = a, b_
    sc.frame_step = args.step
    bpy.ops.render.render(animation=True)
