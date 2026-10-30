"""Plano de corte em chapa inteira de MDF (2750 x 1840), sem logos (carimbo à parte)."""
import os, ezdxf
from shapely import affinity
from maletas import BUILDS, T
SW, SH = 2750.0, 1840.0
MARGIN, GAP = 15.0, 15.0
COPIES = int(os.environ.get("COPIES", "1"))

def nest(plates):
    prep = []
    for i, p in enumerate(plates):
        poly = p.poly
        minx, miny, maxx, maxy = poly.bounds
        if (maxy-miny) > (maxx-minx): poly = affinity.rotate(poly, 90, origin=(0, 0))
        minx, miny, maxx, maxy = poly.bounds
        prep.append(dict(n=i // len(b.plates) + 1, p=p, poly=affinity.translate(poly, -minx, -miny), w=maxx-minx, h=maxy-miny))
    prep.sort(key=lambda d: (-d["h"], -d["w"]))
    sheets, shelves = [], []
    def place(i, d):
        for s in shelves[i]:
            if d["h"] <= s[1] and s[2] + d["w"] <= SW - MARGIN:
                d["at"] = (s[2], s[0]); s[2] += d["w"] + GAP; sheets[i].append(d); return True
        y = (shelves[i][-1][0] + shelves[i][-1][1] + GAP) if shelves[i] else MARGIN
        if y + d["h"] <= SH - MARGIN:
            shelves[i].append([y, d["h"], MARGIN + d["w"] + GAP]); d["at"] = (MARGIN, y); sheets[i].append(d); return True
        return False
    for d in prep:
        if not any(place(i, dict(d)) for i in range(len(sheets))):
            sheets.append([]); shelves.append([]); assert place(len(sheets)-1, dict(d))
    return sheets

KEY = os.environ.get("KEY", "B")
b = [x for x in BUILDS if x.key == KEY][0]
SLUG = {"B": "B_escada", "D": "D_escada_parafusada"}[KEY]
plates = [p for _ in range(COPIES) for p in b.plates]
sheets = nest(plates)
doc = ezdxf.new("R2010"); doc.units = ezdxf.units.MM
for nm, col in (("CORTE_INTERNO", 5), ("CORTE_EXTERNO", 1), ("CHAPA_NAO_CORTAR", 8), ("ETIQUETAS_NAO_CORTAR", 8)):
    doc.layers.add(nm, color=col)
msp = doc.modelspace()
for si, sh in enumerate(sheets):
    ox = si*(SW + 200)
    msp.add_lwpolyline([(ox, 0), (ox+SW, 0), (ox+SW, SH), (ox, SH)], close=True, dxfattribs={"layer": "CHAPA_NAO_CORTAR"})
    for d in sh:
        pl = affinity.translate(d["poly"], d["at"][0] + ox, d["at"][1])
        msp.add_lwpolyline(list(pl.exterior.coords), close=True, dxfattribs={"layer": "CORTE_EXTERNO"})
        for r in pl.interiors:
            msp.add_lwpolyline(list(r.coords), close=True, dxfattribs={"layer": "CORTE_INTERNO"})
        c = pl.representative_point()
        msp.add_text(f'{KEY}{d["n"]} {d["p"].name}' if COPIES > 1 else f'{KEY} {d["p"].name}', height=14, dxfattribs={"layer": "ETIQUETAS_NAO_CORTAR"}).set_placement((c.x, c.y))
out = f"maletas/maleta_{SLUG}_chapa_2750x1840_{T:g}mm" + (f"_{COPIES}x" if COPIES > 1 else "") + ".dxf"
doc.saveas(out)
used = sum(p.poly.area for p in plates)
print(out, "| chapas", len(sheets), "| pecas", len(plates), "| aproveitamento", round(100*used/(SW*SH*len(sheets))), "%")
