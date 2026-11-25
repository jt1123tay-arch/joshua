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
ap.add_argument("--still", type=int, default=0)
ap.add_argument("--samples", type=int, default=64)
ap.add_argument("--res", default="960x540")
ap.add_argument("--blend", default="")
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
M["glove"] = node_mat("glove", (0.045, 0.05, 0.058), rough=0.6, bump=(2500, 0.35, 6))
M["sleeve"] = node_mat("sleeve", (0.025, 0.045, 0.11), rough=0.9, bump=(700, 0.5, 8))
M["cuff"] = node_mat("cuff", (0.02, 0.022, 0.03), rough=0.85, bump=(1800, 0.4))
M["enclosure"] = node_mat("enclosure", (0.62, 0.63, 0.6), rough=0.35, bump=(300, 0.05))
M["estop_red"] = node_mat("estop_red", (0.55, 0.02, 0.02), rough=0.25, coat=0.6)
M["estop_yel"] = node_mat("estop_yel", (0.9, 0.65, 0.02), rough=0.4)
M["esd"] = node_mat("esd", (0.12, 0.2, 0.17), rough=0.8, bump=(120, 0.15))
M["benchframe"] = node_mat("benchframe", (0.25, 0.27, 0.3), metal=0.6, rough=0.4)
M["wire_colors"] = [node_mat(f"w{i}", c, rough=0.4) for i, c in enumerate([
    (0.9, 0.85, 0.8), (0.9, 0.3, 0.02), (0.9, 0.9, 0.85), (0.05, 0.12, 0.7),
    (0.9, 0.9, 0.9), (0.05, 0.5, 0.08), (0.9, 0.88, 0.85), (0.25, 0.12, 0.04)])]

# ------------------------------------------------------------- ARK-1252 box
BASE_Z = 1.12          # bottom of the box (it sits on an enclosure on the bench)
W, D, H = 0.200, 0.140, 0.050
ZC = BASE_Z + H / 2    # port centre line
LAN1 = Vector((-0.040, 0.0, ZC))

chassis = boxes("ARK-1252", [((0, D / 2, ZC), (W, D, H))], M["chassis"], bevel=0.0015)
# fins
fins = []
n = 20
for i in range(n):
    x = -0.094 + i * (0.188 / (n - 1))
    fins.append(((x, D / 2, BASE_Z + H + 0.005), (0.0016, D - 0.01, 0.010)))
boxes("fins", fins, M["fins"], bevel=0.0003)
# side mounting brackets
boxes("brackets", [((-W / 2 - 0.009, 0.03, BASE_Z + 0.001), (0.018, 0.03, 0.002)),
                   ((W / 2 + 0.009, 0.03, BASE_Z + 0.001), (0.018, 0.03, 0.002)),
                   ((-W / 2 - 0.009, 0.11, BASE_Z + 0.001), (0.018, 0.03, 0.002)),
                   ((W / 2 + 0.009, 0.11, BASE_Z + 0.001), (0.018, 0.03, 0.002))],
      M["fins"], bevel=0.0004)

# port openings (cutters)
cut = []
DEP = 0.022
def opening(x, z, w, h):
    cut.append(((x, DEP / 2 - 0.004, z), (w, DEP + 0.008, h)))
for x in (-0.040, -0.022):                      # LAN1, LAN2 (RJ45)
    opening(x, ZC, 0.0146, 0.0122)
    opening(x, ZC - 0.0072, 0.0064, 0.0030)     # latch notch (bottom)
opening(-0.003, ZC - 0.0066, 0.0134, 0.0060)    # USB lower
opening(-0.003, ZC + 0.0066, 0.0134, 0.0060)    # USB upper
opening(0.018, ZC, 0.0152, 0.0058)              # HDMI
cutter = boxes("cutter", cut, M["blackplastic"])
cutter.hide_render = True; cutter.display_type = "WIRE"
bo = chassis.modifiers.new("ports", "BOOLEAN")
bo.object = cutter; bo.solver = "EXACT"; bo.use_self = True; bo.use_hole_tolerant = True
try:
    bo.material_mode = "TRANSFER"
except Exception:
    pass
chassis.data.materials.append(M["blackplastic"])

# RJ45 contacts inside the jacks
det = []
for x0 in (-0.040, -0.022):
    for k in range(8):
        x = x0 - 0.00357 + k * 0.00102
        det.append(((x, 0.012, ZC + 0.0046), (0.00035, 0.012, 0.0006)))
boxes("rj45_contacts", det, M["gold"])
# USB tongues, HDMI tongue
boxes("usb_tongues", [((-0.003, 0.010, ZC - 0.0066 + 0.0012), (0.0112, 0.016, 0.0018)),
                      ((-0.003, 0.010, ZC + 0.0066 + 0.0012), (0.0112, 0.016, 0.0018))], M["usbblue"])
boxes("usb_shell", [((-0.003, 0.0004, ZC - 0.0066), (0.0136, 0.0008, 0.0062)),
                    ((-0.003, 0.0004, ZC + 0.0066), (0.0136, 0.0008, 0.0062))], M["silver"])
boxes("hdmi_tongue", [((0.018, 0.010, ZC + 0.0004), (0.0118, 0.016, 0.0015))], M["blackplastic"])

# LAN LEDs (top corners of each jack)
link_led = boxes("led_link", [((-0.040 - 0.0050, -0.0002, ZC + 0.0082), (0.0030, 0.0008, 0.0018))], M["led_link"])
act_led = boxes("led_act", [((-0.040 + 0.0050, -0.0002, ZC + 0.0082), (0.0030, 0.0008, 0.0018))], M["led_act"])
boxes("led_lan2", [((-0.022 - 0.0050, -0.0002, ZC + 0.0082), (0.0030, 0.0008, 0.0018)),
                   ((-0.022 + 0.0050, -0.0002, ZC + 0.0082), (0.0030, 0.0008, 0.0018))], M["led_off"])

# COM (DE-9 male)
cx = 0.054
boxes("db9_flange", [((cx, -0.0005, ZC), (0.0310, 0.0010, 0.0125))], M["silver"], bevel=0.0004)
def trapezoid(name, cx, y0, y1, zc, top, bot, h, mat):
    me = bpy.data.meshes.new(name); bm = bmesh.new()
    pts = [(-top / 2, h / 2), (top / 2, h / 2), (bot / 2, -h / 2), (-bot / 2, -h / 2)]
    vs = []
    for y in (y0, y1):
        vs.append([bm.verts.new((cx + px, y, zc + pz)) for px, pz in pts])
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new([vs[0][i], vs[0][j], vs[1][j], vs[1][i]])
    bm.faces.new(vs[0][::-1]); bm.faces.new(vs[1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me)); me.materials.append(mat)
    return ob
trapezoid("db9_shell", cx, -0.0062, -0.0008, ZC, 0.0170, 0.0142, 0.0082, M["silver"])
trapezoid("db9_insert", cx, -0.0064, -0.0010, ZC, 0.0150, 0.0124, 0.0064, M["blackplastic"])
pins = []
for k in range(5):
    pins.append(((cx - 0.0055 + k * 0.00277, -0.0072, ZC + 0.0014), (0.0010, 0.0020, 0.0010)))
for k in range(4):
    pins.append(((cx - 0.0042 + k * 0.00277, -0.0072, ZC - 0.0014), (0.0010, 0.0020, 0.0010)))
boxes("db9_pins", pins, M["gold"])
for dx in (-0.0125, 0.0125):
    cyl("standoff", (cx + dx, -0.0028, ZC), 0.0025, 0.0050, M["silver"], verts=6)

# DC-in terminal block (green, 2-pin) + power button with blue ring LED
boxes("dc_term", [((-0.066, -0.004, ZC), (0.0102, 0.0085, 0.0105))], M["termgreen"], bevel=0.0005)
boxes("dc_holes", [((-0.0685, -0.0084, ZC - 0.0018), (0.0032, 0.0010, 0.0032)),
                   ((-0.0635, -0.0084, ZC - 0.0018), (0.0032, 0.0010, 0.0032))], M["blackplastic"])
cyl("dc_screws1", (-0.0685, -0.0060, ZC + 0.0055), 0.0015, 0.0005, M["silver"], rot=(0, 0, 0))
cyl("dc_screws2", (-0.0635, -0.0060, ZC + 0.0055), 0.0015, 0.0005, M["silver"], rot=(0, 0, 0))
cyl("pwr_btn", (-0.085, -0.0008, ZC), 0.0036, 0.0016, M["silver"])
bpy.ops.mesh.primitive_torus_add(major_radius=0.0046, minor_radius=0.0005, location=(-0.085, -0.0002, ZC),
                                 rotation=(math.radians(90), 0, 0))
bpy.context.object.data.materials.append(M["pwr_led"])

# printing
text("ARK-1252", (-0.093, -0.0002, BASE_Z + H - 0.0105), 0.0060, M["print"])
for lbl, x in (("LAN1", -0.040), ("LAN2", -0.022), ("USB", -0.003), ("HDMI", 0.018), ("COM", 0.054),
               ("DC IN", -0.066), ("PWR", -0.085)):
    text(lbl, (x, -0.0002, BASE_Z + 0.0045), 0.0024, M["print"], align="CENTER")

# ------------------------------------------------------------- bench / enclosure
boxes("enclosure", [((0.0, 0.11, 1.06), (0.34, 0.26, 0.12))], M["enclosure"], bevel=0.003)
boxes("enc_gasket", [((0.0, -0.0205, 1.06), (0.33, 0.001, 0.11))], M["blackplastic"])
cyl("estop_base", (0.125, -0.024, 1.06), 0.022, 0.006, M["estop_yel"])
cyl("estop_cap", (0.125, -0.034, 1.06), 0.016, 0.014, M["estop_red"])
cyl("lamp_g", (0.07, -0.022, 1.075), 0.007, 0.004, node_mat("lamp_g", (0.1, 0.4, 0.1), rough=0.2, emit=(0.2, 1, 0.2), emit_str=6))
cyl("lamp_w", (0.07, -0.022, 1.045), 0.007, 0.004, M["silver"])
text("MAIN CONTROL", (-0.15, -0.021, 1.085), 0.009, M["blackplastic"])

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

# ------------------------------------------------------------- gloved hand (plug-local coordinates)
hand = empty("HandRoot")
mb = bpy.data.metaballs.new("glove")
mb.resolution = 0.004; mb.render_resolution = 0.0016; mb.threshold = 0.6
glove = link(bpy.data.objects.new("glove", mb)); glove.parent = hand
mb.materials.append(M["glove"])
STIFF = 5.0
K = 0.808  # surface radius / metaball radius at this stiffness
def capsule(a, b, r):
    a, b = Vector(a), Vector(b)
    e = mb.elements.new(type="CAPSULE")
    e.co = (a + b) / 2; e.radius = r / K; e.stiffness = STIFF
    d = b - a
    e.size_x = d.length / 2
    e.rotation = Vector((1, 0, 0)).rotation_difference(d.normalized())
    return e
def ellipsoid(c, half, rot=None):
    e = mb.elements.new(type="ELLIPSOID")
    e.co = c; e.radius = 0.05; e.stiffness = STIFF
    e.size_x, e.size_y, e.size_z = (h / (K * 0.05) for h in half)
    if rot: e.rotation = rot
    return e
fingers = {
    "thumb": ([(0.030, -0.112, -0.004), (0.027, -0.086, 0.013), (0.016, -0.060, 0.019), (0.002, -0.035, 0.0145)], 0.0092),
    "index": ([(0.031, -0.070, -0.008), (0.026, -0.047, -0.012), (0.014, -0.034, -0.0150), (0.001, -0.031, -0.0145)], 0.0085),
    "middle": ([(0.032, -0.074, -0.026), (0.028, -0.051, -0.030), (0.013, -0.046, -0.034), (0.009, -0.059, -0.036)], 0.0086),
    "ring": ([(0.032, -0.078, -0.043), (0.029, -0.057, -0.047), (0.015, -0.054, -0.050), (0.012, -0.065, -0.051)], 0.0081),
    "pinky": ([(0.031, -0.083, -0.058), (0.028, -0.068, -0.061), (0.017, -0.064, -0.063), (0.015, -0.072, -0.063)], 0.0072),
}
finger_el = {}
for nm, (pts, r) in fingers.items():
    finger_el[nm] = [capsule(pts[i], pts[i + 1], r * (1 - 0.06 * i)) for i in range(len(pts) - 1)]
ellipsoid((0.033, -0.100, -0.032), (0.0135, 0.036, 0.034))
ellipsoid((0.040, -0.138, -0.031), (0.020, 0.024, 0.029))
ellipsoid((0.050, -0.160, -0.034), (0.028, 0.022, 0.034))       # glove cuff

# forearm in a work-jacket sleeve
fa0 = Vector((0.052, -0.165, -0.034))
fdir = Vector((0.80, -0.48, -0.30)).normalized()
cu = bpy.data.curves.new("sleeve", "CURVE"); cu.dimensions = "3D"
cu.bevel_depth = 0.043; cu.bevel_resolution = 8; cu.use_fill_caps = True
sp = cu.splines.new("BEZIER"); sp.bezier_points.add(2)
for i, (t, rad) in enumerate(((0.0, 1.0), (0.18, 1.12), (0.45, 1.2))):
    p = sp.bezier_points[i]; p.co = fa0 + fdir * t; p.radius = rad
    p.handle_left_type = p.handle_right_type = "AUTO"
sleeve = link(bpy.data.objects.new("sleeve", cu)); sleeve.parent = hand
cu.materials.append(M["sleeve"])
bpy.ops.mesh.primitive_torus_add(major_radius=0.041, minor_radius=0.006,
                                 location=fa0 + fdir * 0.003)
cuff = bpy.context.object; cuff.name = "sleeve_cuff"; cuff.data.materials.append(M["cuff"])
cuff.rotation_mode = "QUATERNION"
cuff.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(fdir)
cuff.parent = hand

# ------------------------------------------------------------- cable (bezier, keyed per frame)
ccu = bpy.data.curves.new("cable", "CURVE"); ccu.dimensions = "3D"
ccu.bevel_depth = 0.0029; ccu.bevel_resolution = 6; ccu.resolution_u = 24
csp = ccu.splines.new("BEZIER"); csp.bezier_points.add(4)
for p in csp.bezier_points:
    p.handle_left_type = p.handle_right_type = "FREE"
cable = link(bpy.data.objects.new("cable", ccu)); ccu.materials.append(M["cable"])

# ------------------------------------------------------------- camera
cam_d = bpy.data.cameras.new("cam"); cam_d.lens = 50
cam_d.dof.use_dof = True; cam_d.dof.aperture_fstop = 4.0; cam_d.dof.aperture_blades = 7
cam = link(bpy.data.objects.new("camera", cam_d)); sc.camera = cam
look = empty("look"); focus = empty("focus", LAN1 + Vector((0, -0.006, 0)))
cam_d.dof.focus_object = focus
tc = cam.constraints.new("TRACK_TO"); tc.target = look
tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"

# ------------------------------------------------------------- animation
SEAT = LAN1 + Vector((0, 0.0135, 0))
def plug_pose(f):
    """returns (location, euler) of plug tip"""
    start = SEAT + Vector((0.20, -0.24, 0.085))
    near = SEAT + Vector((0.0, -0.030, 0.002))
    align = SEAT + Vector((0.0, -0.0155, 0.0))
    r0 = Vector((0.20, -0.35, 0.55)); r1 = Vector((0.03, 0.05, 0.06))
    if f <= 42:
        t = smoother((f - 1) / 41)
        # arc in through a mid point
        mid = SEAT + Vector((0.09, -0.12, 0.05))
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
    return Matrix.Translation(loc) @ rot.to_matrix().to_4x4()

def hand_matrix(f):
    REL = 80
    if f <= REL:
        m = plug_matrix(f)
        if f > 71:   # push-through: hand settles after the click
            m = Matrix.Translation((0, -0.0006 * smooth((f - 71) / 9), 0)) @ m
        return m
    t = smoother((f - REL) / (F_END - REL) * 1.25)
    base = hand_matrix(REL)
    off = Vector((0.24, -0.20, 0.09)) * t
    rot = Euler((0.0, -0.25 * t, -0.35 * t)).to_matrix().to_4x4()
    piv = base.to_translation()
    return Matrix.Translation(piv + off) @ rot @ Matrix.Translation(-piv) @ base

def cam_loc(f):
    t = smooth((f - 1) / (F_END - 1))
    shake = Vector((math.sin(f * 0.37) + 0.5 * math.sin(f * 0.91 + 1.3),
                    0.4 * math.sin(f * 0.23 + 0.7),
                    math.sin(f * 0.29 + 2.1) + 0.4 * math.sin(f * 1.07))) * 0.0006
    return vlerp((-0.215, -0.40, 1.225), (-0.165, -0.315, 1.200), t) + shake

def look_loc(f):
    t = smooth((f - 1) / (F_END - 1))
    return vlerp((-0.005, -0.03, 1.150), (-0.025, -0.005, 1.146), t)

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

def cable_pts(f):
    m = plug_matrix(f)
    p0 = m @ Vector((0, -0.040, 0))
    p1 = m @ Vector((0, -0.115, -0.004))
    axis = (m.to_3x3() @ Vector((0, -1, 0))).normalized()
    p4 = Vector((-0.75, -0.30, 1.0035))
    p3 = Vector((-0.28, -0.29, 1.0035))
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

# release grip: thumb lifts, index drops (metaball element keys)
rel_specs = [(finger_el["thumb"][-1], Vector((0.004, -0.004, 0.009))),
             (finger_el["thumb"][-2], Vector((0.002, -0.002, 0.004))),
             (finger_el["index"][-1], Vector((0.004, -0.004, -0.008))),
             (finger_el["index"][-2], Vector((0.002, -0.002, -0.003)))]
bases = [Vector(e.co) for e, _ in rel_specs]
for f in (1, 74, 79, 84):
    rt = smooth((f - 74) / 10)
    for (e, d), b0 in zip(rel_specs, bases):
        e.co = b0 + d * rt
        e.keyframe_insert("co", frame=f)

# LEDs (constant interpolation)
prefs.keyframe_new_interpolation_type = "CONSTANT"
lk = M["led_link"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
ak = M["led_act"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"]
lk.default_value = 0; lk.keyframe_insert("default_value", frame=1)
lk.default_value = 14; lk.keyframe_insert("default_value", frame=73)
ak.default_value = 0; ak.keyframe_insert("default_value", frame=1)
on = False
for f in range(77, F_END + 1):
    if random.random() < 0.45:
        on = not on
        ak.default_value = 12 if on else 0
        ak.keyframe_insert("default_value", frame=f)
prefs.keyframe_new_interpolation_type = "BEZIER"

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
if args.still:
    sc.frame_set(args.still)
    r.filepath = args.out.rstrip("/") + f"/still_{args.still:04d}.png"
    bpy.ops.render.render(write_still=True)
else:
    a, b_ = (int(v) for v in args.frames.split("-"))
    sc.frame_start, sc.frame_end = a, b_
    bpy.ops.render.render(animation=True)
