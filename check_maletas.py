import math, sys, numpy as np, trimesh
from maletas import BUILDS, T

def solid_plate(p):
    m = trimesh.creation.extrude_polygon(p.poly, T)
    M = np.eye(4); M[:3,0], M[:3,1], M[:3,2], M[:3,3] = p.U, p.V, p.W, p.o
    m.apply_transform(M)
    if m.volume < 0: m.invert()
    return m

def solid_prod(d, shrink=1.0):
    s = np.array(d["s"]) - 2*shrink
    if d["t"] == "coberta":
        m = trimesh.creation.cylinder(radius=s[1]/2, height=s[0], sections=48)
        m.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2, [0,1,0]))
    else:
        m = trimesh.creation.box(extents=s)
    M = np.eye(4); M[:3,0], M[:3,1], M[:3,2], M[:3,3] = d["U"], d["V"], d["W"], d["c"]
    m.apply_transform(M)
    if m.volume < 0: m.invert()
    return m

def rot(m, pv, ang):
    axis = [1,0,0] if pv["axis"] == "x" else [0,1,0]
    m = m.copy(); m.apply_transform(trimesh.transformations.rotation_matrix(math.radians(ang), axis, pv["p"])); return m

def overlap(a, b):
    if (a.bounds[0] > b.bounds[1]).any() or (b.bounds[0] > a.bounds[1]).any(): return 0
    try: return abs(a.intersection(b, check_volume=False).volume)
    except Exception: return -1

only = sys.argv[1:] or None
for b in BUILDS:
    if only and b.key not in only: continue
    for state in ("aberta", "fechada"):
        ang_key = "open" if state == "aberta" else "closed"
        items = []
        for i, p in enumerate(b.plates):
            s = solid_plate(p)
            if p.group: s = rot(s, b.pivot, b.pivot[ang_key])
            items.append((f"{p.name}#{i}", s, "p"))
        for i, d in enumerate(b.products):
            s = solid_prod(d)
            if d["g"]: s = rot(s, b.pivot, b.pivot[ang_key])
            items.append((f'{d["t"]}#{i}', s, "q"))
        for i, h in enumerate(b.hw):
            if h["k"] != "box": continue
            s = solid_prod(dict(t="box", s=h["s"], U=h["U"], V=h["V"], W=h["W"], c=h["c"]), shrink=0.3)
            if h["g"]: s = rot(s, b.pivot, b.pivot[ang_key])
            items.append((f"ferragem#{i}", s, "h"))
        bad = []
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                if items[i][2] == "q" and items[j][2] == "q": continue
                if items[i][2] == "h" and items[j][2] == "h": continue
                v = overlap(items[i][1], items[j][1])
                if v > 30 or v < 0: bad.append((items[i][0], items[j][0], round(v)))
        print(b.key, state, len(b.plates), "pecas", "->", bad if bad else "sem colisao")
