"""Blender renders of the case with the board in it (img/*.png).

    blender -b -P hardware/case/render.py -- BOARD.glb [VIEW ...]

BOARD.glb: KiCad's export of the board without J6/J15 (check.py makes one); the stand-ins for
those, the SOM, its heatsink (an estimate) and the XIAO come from out/standins.json (check.py).
Views: closed (back), front, open (lid off), exploded. Cycles, on the GPU when there is one.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
IMG = os.path.join(HERE, "img")
args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
GLB = args[0]
VIEWS = args[1:] or ["closed", "front", "open", "exploded"]
META = json.load(open(os.path.join(OUT, "meta.json")))
STANDINS = json.load(open(os.path.join(OUT, "standins.json")))

CASE_RGB = (0.62, 0.64, 0.66)
PANEL_RGB = (0.20, 0.21, 0.23)
KEY_RGB = (0.85, 0.35, 0.10)


def material(name, rgb, rough=0.55, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.samples = 96
    sc.cycles.use_denoising = True
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for kind in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = kind
                prefs.get_devices()
                if any(d.type == kind for d in prefs.devices):
                    for d in prefs.devices:
                        d.use = d.type == kind
                    sc.cycles.device = "GPU"
                    break
            except TypeError:
                pass
    except KeyError:
        pass
    sc.render.resolution_x, sc.render.resolution_y = 1280, 880
    sc.render.film_transparent = False
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.93, 0.93, 0.94, 1)
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    sc.view_settings.view_transform = "AgX"


def load_board():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=GLB)
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("board", None)
    bpy.context.scene.collection.objects.link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    # KiCad's exported materials come in see-through in Cycles: make every one opaque
    for o in new:
        for slot in getattr(o, "material_slots", []):
            m = slot.material
            if m and m.use_nodes:
                for n in m.node_tree.nodes:
                    if n.type == "BSDF_PRINCIPLED":
                        n.inputs["Alpha"].default_value = 1.0
                        for k in ("Transmission Weight", "Transmission"):
                            if k in n.inputs:
                                n.inputs[k].default_value = 0.0
                for l in list(m.node_tree.links):
                    if l.to_socket.name == "Alpha":
                        m.node_tree.links.remove(l)
                m.blend_method = "OPAQUE" if hasattr(m, "blend_method") else None
    root.scale = (1000, 1000, 1000)
    root.location = (-META["CX"], META["CY"], 0)
    mats = {"som": material("som", (0.05, 0.25, 0.12), 0.4), "metal": material("metal", (0.75, 0.76, 0.78), 0.3, 1.0),
            "xiao": material("xiao", (0.08, 0.08, 0.09), 0.5), "sink": material("sink", (0.06, 0.06, 0.07), 0.35, 0.6)}
    pick = {"J6 HDMI shell": "metal", "J15 USB-C": "metal", "SOM board": "som", "SOM parts": "xiao",
            "heatsink (est.)": "sink", "XIAO": "xiao", "XIAO USB-C": "metal",
            "J6 HDMI mouth": "xiao", "J15 USB-C mouth": "xiao"}
    for k, (x0, x1, y0, y1, z0, z1) in STANDINS.items():
        bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        o = bpy.context.object
        o.scale = (x1 - x0, y1 - y0, z1 - z0)
        o.name = k
        o.data.materials.append(mats[pick[k]])
    return root


def load_part(name, mat, offset=(0, 0, 0)):
    bpy.ops.wm.stl_import(filepath=os.path.join(OUT, name + "-fitted.stl"))
    o = bpy.context.object
    o.data.materials.append(mat)
    o.location = offset
    bpy.ops.object.shade_auto_smooth(angle=math.radians(30))
    return o


def camera(loc, target, lens=50):
    cam = bpy.data.cameras.new("cam")
    cam.lens = lens
    cam.clip_start, cam.clip_end = 1, 5000
    o = bpy.data.objects.new("cam", cam)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.camera = o


def lights():
    for loc, energy, size in (((-250, 300, 400), 9e5, 300), ((300, -200, 250), 4e5, 250), ((0, 0, 500), 3e5, 400)):
        L = bpy.data.lights.new("area", "AREA")
        L.energy, L.size = energy, size
        o = bpy.data.objects.new("area", L)
        bpy.context.scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector((0, 0, 0)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    bpy.ops.mesh.primitive_plane_add(size=3000, location=(0, 0, META["Z_BOT"] - 0.01))
    bpy.context.object.data.materials.append(material("floor", (0.9, 0.9, 0.91), 0.8))


def view(name):
    reset()
    lights()
    case = material("case", CASE_RGB)
    panel = material("panel", PANEL_RGB, 0.6)
    key = material("key", KEY_RGB, 0.5)
    load_board()
    up = 0
    if name == "exploded":
        up = 1
    lid_z = 45 if up else 0
    parts = {"base": (case, (0, 0, 0)), "back": (panel, (0, 35 * up, 0)), "front": (panel, (0, -35 * up, 0))}
    if name != "open":
        parts["lid"] = (case, (0, 0, lid_z))
        for sw in ("SW1", "SW2", "SW3"):
            parts["button-" + sw] = (key, (0, 0, lid_z))
    for p, (m, off) in parts.items():
        load_part(p, m, off)
    fx, fy, fs = META.get("fan", [0, 0, 0])
    if fs and name == "exploded":
        # a fan (a stand-in) above the lid
        z = META["Z_TOP"] + lid_z + 18
        bpy.ops.mesh.primitive_cube_add(size=1, location=(fx, fy, z + 5))
        frame = bpy.context.object
        frame.scale = (fs, fs, 10)
        bpy.ops.mesh.primitive_cylinder_add(radius=fs / 2 - 1.5, depth=14, location=(fx, fy, z + 5))
        cut = bpy.context.object
        mod = frame.modifiers.new("hole", "BOOLEAN")
        mod.operation, mod.object = "DIFFERENCE", cut
        cut.hide_render = True
        frame.data.materials.append(material("fan", (0.05, 0.05, 0.06), 0.5))
        bpy.ops.mesh.primitive_cylinder_add(radius=fs * 0.2, depth=8, location=(fx, fy, z + 5))
        bpy.context.object.data.materials.append(material("hub", (0.08, 0.08, 0.09), 0.4))
    if name == "closed":
        camera((210, 260, 170), (0, 0, 8))
    elif name == "front":
        camera((-200, -270, 190), (0, 0, 8))
    elif name == "open":
        camera((-150, -200, 260), (0, 0, 0))
    elif name == "exploded":
        camera((-300, -330, 260), (0, 0, 22), 45)
    bpy.context.scene.render.filepath = os.path.join(IMG, "case-%s.png" % name)
    bpy.ops.render.render(write_still=True)


os.makedirs(IMG, exist_ok=True)
for v in VIEWS:
    view(v)
