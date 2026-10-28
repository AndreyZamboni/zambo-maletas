import json, math, numpy as np, ezdxf
from shapely import affinity
from shapely.geometry import box
from maletas import BUILDS, SHEET, T
LOGO = json.load(open('/home/claude/zambo/logo/logo_vec.json'))

OUT = "/home/claude/zambo/maletas/"
TAG = f"_{T:g}mm"
import os; os.makedirs(OUT, exist_ok=True)
NAMES = {"A": "Maleta Vitrine", "B": "Maleta Escada", "C": "Maleta Baú"}

def eng_local(p, e):
    """posição/rotação da gravação no 2D da peça + se a peça precisa ser espelhada no corte"""
    n, up, c = np.array(e["n"]), np.array(e["up"]), np.array(e["c"])
    right = np.cross(up, n)
    mirror = float(n @ np.cross(p.U, p.V)) < 0
    u, v = p.loc(c)
    ru, rv = float(right @ p.U), float(right @ p.V)
    return u, v, ru, rv, mirror

def nest(plates, margin=8, gap=6):
    W, H = SHEET
    prep = []
    for p in plates:
        mirror = bool(p.eng) and eng_local(p, p.eng[0])[4]
        poly = affinity.scale(p.poly, -1, 1, origin=(0, 0)) if mirror else p.poly
        minx, miny, maxx, maxy = poly.bounds
        rot = (maxy - miny) > (maxx - minx) and (maxy - miny) <= W - 2*margin
        if rot: poly = affinity.rotate(poly, 90, origin=(0, 0))
        minx, miny, maxx, maxy = poly.bounds
        prep.append(dict(p=p, poly=affinity.translate(poly, -minx, -miny), w=maxx - minx, h=maxy - miny,
                         mirror=mirror, rot=rot, sh=(-minx, -miny)))
    prep.sort(key=lambda d: (-d["h"], -d["w"]))
    sheets, shelves = [], []
    def place(i, d):
        for s in shelves[i]:
            if d["h"] <= s[1] and s[2] + d["w"] <= W - margin:
                d["at"] = (s[2], s[0]); s[2] += d["w"] + gap; sheets[i].append(d); return True
        y = (shelves[i][-1][0] + shelves[i][-1][1] + gap) if shelves[i] else margin
        if y + d["h"] <= H - margin:
            shelves[i].append([y, d["h"], margin + d["w"] + gap]); d["at"] = (margin, y); sheets[i].append(d); return True
        return False
    for d in prep:
        if not any(place(i, dict(d)) for i in range(len(sheets))):
            sheets.append([]); shelves.append([]); assert place(len(sheets) - 1, dict(d)), d["p"].name
    return sheets

def xf(d, u, v):
    if d["mirror"]: u = -u
    if d["rot"]: u, v = -v, u
    return u + d["sh"][0] + d["at"][0], v + d["sh"][1] + d["at"][1]

def placed(d):
    return affinity.translate(d["poly"], *d["at"])

def write_dxf(path, sheets, key):
    doc = ezdxf.new("R2010"); doc.units = ezdxf.units.MM
    for nm, col in (("CORTE_INTERNO", 5), ("CORTE_EXTERNO", 1), ("GRAVACAO", 3), ("GRAVACAO_VERSO", 4), ("MESA_NAO_CORTAR", 8), ("ETIQUETAS_NAO_CORTAR", 8)):
        doc.layers.add(nm, color=col)
    msp = doc.modelspace()
    for si, sh in enumerate(sheets):
        ox = si*(SHEET[0] + 150)
        msp.add_lwpolyline([(ox, 0), (ox + SHEET[0], 0), (ox + SHEET[0], SHEET[1]), (ox, SHEET[1])], close=True, dxfattribs={"layer": "MESA_NAO_CORTAR"})
        for d in sh:
            pl = affinity.translate(placed(d), ox, 0)
            msp.add_lwpolyline(list(pl.exterior.coords), close=True, dxfattribs={"layer": "CORTE_EXTERNO"})
            for r in pl.interiors:
                msp.add_lwpolyline(list(r.coords), close=True, dxfattribs={"layer": "CORTE_INTERNO"})
            if d["p"].kind != "wedge":
                c = pl.representative_point()
                msp.add_text(f'{key} {d["p"].name}', height=8, dxfattribs={"layer": "ETIQUETAS_NAO_CORTAR"}).set_placement((c.x, c.y))
            for e in d["p"].eng:
                u, v, ru, rv, mir = eng_local(d["p"], e)
                verso = mir != d["mirror"]
                lay = {"layer": "GRAVACAO_VERSO" if verso else "GRAVACAO"}
                up = np.array(e["up"]); uu, uv = float(up @ d["p"].U), float(up @ d["p"].V)
                w = e["h"]; L = LOGO[e["text"]]
                for poly in L["polys"]:
                    for ring in [poly["o"]] + poly["h"]:
                        pts = []
                        for px, py in ring:
                            lu = u + (ru*px + uu*py)*w; lv = v + (rv*px + uv*py)*w
                            x, y = xf(d, lu, lv); pts.append((x + ox, y))
                        msp.add_lwpolyline(pts, close=True, dxfattribs=lay)
    doc.saveas(path)

def svg(sheet):
    W, H = SHEET
    out = [f'<svg viewBox="-6 -6 {W+12} {H+12}" xmlns="http://www.w3.org/2000/svg" class="sheet" role="img" aria-label="Plano de corte">',
           f'<rect x="0" y="0" width="{W}" height="{H}" class="mesa"/>']
    for d in sheet:
        pl = placed(d)
        dd = ""
        for ring in [pl.exterior] + list(pl.interiors):
            dd += "M" + " L".join(f"{x:.1f},{H-y:.1f}" for x, y in ring.coords) + " Z "
        cls = "cunha" if d["p"].kind == "wedge" else ("mov" if d["p"].group else "fix")
        out.append(f'<path d="{dd}" class="peca {cls}" fill-rule="evenodd"><title>{d["p"].name}</title></path>')
    out.append("</svg>")
    return "\n".join(out)

def pjs(poly):
    return dict(o=[[round(x, 2), round(y, 2)] for x, y in poly.exterior.coords[:-1]],
                h=[[[round(x, 2), round(y, 2)] for x, y in r.coords[:-1]] for r in poly.interiors])

data = {}
for b in BUILDS:
    sheets = nest(b.plates)
    write_dxf(OUT + f"maleta_{b.key}_{NAMES[b.key].split()[-1].lower().replace('ú','u')}_corte{TAG}.dxf", sheets, b.key)
    area = sum(p.poly.area for p in b.plates) / 1e6
    bom = {}
    for p in b.plates:
        k = p.name
        minx, miny, maxx, maxy = p.poly.bounds
        bom.setdefault(k, dict(peca=k, qtd=0, dim=f"{maxx-minx:.0f} × {maxy-miny:.0f}"))["qtd"] += 1
    used = sum(p.poly.area for p in b.plates)
    parts, shapes, keymap = [], [], {}
    for p in b.plates:
        sig = p.poly.wkt
        if sig not in keymap:
            keymap[sig] = len(shapes); shapes.append(pjs(p.poly))
        eng = [dict(c=e["c"], n=e["n"], up=e["up"], h=e["h"], text=e["text"], sub=e.get("sub")) for e in p.eng]
        parts.append(dict(n=p.name, s=keymap[sig], o=p.o.round(3).tolist(), U=p.U.tolist(), V=p.V.tolist(), W=p.W.tolist(),
                          g=p.group, k=p.kind, e=eng))
    data[b.key] = dict(T=T, nome=NAMES[b.key], shapes=shapes, parts=parts, products=b.products, hw=b.hw, pivot=b.pivot,
                       fechada=b.closed, aberta=b.opened, kit=b.kit, area=round(area, 2),
                       peso=round(area*T/1000*740, 1), pecas=len([p for p in b.plates if p.kind != "wedge"]),
                       cunhas=b.nwedge, encaixes=b.nlap, chapas=len(sheets), aproveitamento=round(100*used/(SHEET[0]*SHEET[1]*len(sheets))),
                       bom=list(bom.values()), sheets=[svg(s) for s in sheets])
    print(b.key, NAMES[b.key], "| pecas", data[b.key]["pecas"], "+", b.nwedge, "cunhas | area", round(area, 2), "m2 | peso",
          data[b.key]["peso"], "kg | chapas", len(sheets), "|", data[b.key]["aproveitamento"], "%")
json.dump(data, open(OUT + f"maletas{TAG}.json", "w"))
if T == 6: json.dump(data, open(OUT + "maletas.json", "w"))
