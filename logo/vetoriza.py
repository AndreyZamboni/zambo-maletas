"""Logo PNG -> (1) PNG transparente marrom para o 3D, (2) contornos vetoriais normalizados para gravação."""
import json, cv2, numpy as np
from PIL import Image
from shapely.geometry import Polygon
from shapely.ops import unary_union
out = {}
for name in ("principal", "selo"):
    im = Image.open(f"logo/{name}.png").convert("RGBA")
    a = np.array(im).astype(float)
    # tinta = pixels escuros e opacos
    lum = a[..., :3].mean(axis=2)
    ink = ((lum < 140) & (a[..., 3] > 128)).astype(np.uint8) * 255
    ys, xs = np.where(ink > 0)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    ink = ink[y0:y1 + 1, x0:x1 + 1]
    h, w = ink.shape
    # PNG para textura (marrom queimado, fundo transparente), reduzido
    sc = 900 / w
    small = cv2.resize(ink, (int(w * sc), int(h * sc)), interpolation=cv2.INTER_AREA)
    rgba = np.zeros((*small.shape, 4), np.uint8); rgba[..., 0], rgba[..., 1], rgba[..., 2] = 70, 36, 20; rgba[..., 3] = small
    Image.fromarray(rgba).save(f"logo/{name}_tex.png", optimize=True)
    # vetores
    cnts, hier = cv2.findContours(ink, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    polys = []
    for i, c in enumerate(cnts):
        if hier[0][i][3] != -1: continue
        c = cv2.approxPolyDP(c, 1.2, True)[:, 0, :]
        if len(c) < 3: continue
        holes = []
        ch = hier[0][i][2]
        while ch != -1:
            hc = cv2.approxPolyDP(cnts[ch], 1.2, True)[:, 0, :]
            if len(hc) >= 3: holes.append(hc)
            ch = hier[0][ch][0]
        p = Polygon(c, holes).buffer(0)
        if p.area > 30: polys.append(p)
    g = unary_union(polys)
    # normaliza: largura 1, origem no centro, y para cima
    def norm(ring): return [[round((x - w/2) / w, 5), round((h/2 - y) / w, 5)] for x, y in ring.coords]
    geoms = list(g.geoms) if g.geom_type == "MultiPolygon" else [g]
    out[name] = dict(aspect=h / w, polys=[dict(o=norm(p.exterior), h=[norm(r) for r in p.interiors]) for p in geoms])
    print(name, w, h, len(geoms), "formas", sum(len(p.exterior.coords) for p in geoms), "pts")
json.dump(out, open("logo/logo_vec.json", "w"))
