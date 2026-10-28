import json, math, numpy as np, trimesh
from shapely.geometry import Polygon
d = json.load(open("modelo.json"))
def solid(part, place, T=15):
    poly = Polygon(part["shape"]["o"], part["shape"]["h"])
    m = trimesh.creation.extrude_polygon(poly, T)
    o, U, V, W = [np.array(v, float) for v in place]
    M = np.eye(4); M[:3,0]=U; M[:3,1]=V; M[:3,2]=W; M[:3,3]=o
    m.apply_transform(M)
    if m.volume < 0: m.invert()
    return m
def rot(m, pv, ang):
    a = math.radians(ang); p = np.array(pv["p"], float)
    axis = [1,0,0] if pv["axis"]=="x" else [0,1,0]
    R = trimesh.transformations.rotation_matrix(a, axis, p)
    m = m.copy(); m.apply_transform(R); return m
for key, mod in d["models"].items():
    for state in ("aberto", "fechado"):
        sols = []
        for part in mod["parts"]:
            for i, pl in enumerate(part["places"]):
                s = solid(part, pl)
                if part.get("g") and mod["pivot"]:
                    ang = mod["pivot"]["open" if state=="aberto" else "closed"]
                    s = rot(s, mod["pivot"], ang)
                sols.append((f'{part["name"]}#{i}', s))
        bad = []
        for i in range(len(sols)):
            for j in range(i+1, len(sols)):
                a, b = sols[i][1], sols[j][1]
                if not a.bounds[0].__le__(b.bounds[1]).all() or not b.bounds[0].__le__(a.bounds[1]).all(): continue
                v = abs(a.intersection(b, check_volume=False).volume)
                if v > 50: bad.append((sols[i][0], sols[j][0], round(v)))
        print(key, state, "interferencias:", bad if bad else "nenhuma")
        if not mod["pivot"]: break
