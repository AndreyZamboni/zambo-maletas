"""Maletas-mostruário Zambo — MDF cru 6 mm, montagem por encaixe (espiga passante + cunha,
como no reel da Omniless). Sem cola, sem parafuso na estrutura; ferragens só para dobradiça,
fecho e alça. Unidades mm. X largura (centro 0), Y altura (chão 0), Z profundidade (0 = fundo).
"""
import json, math, random
import numpy as np
from shapely.geometry import box, Point, Polygon
from shapely.ops import unary_union
from shapely import affinity
import ezdxf

import os
T = float(os.environ.get("MALETA_T", "6"))   # espessura da chapa (6 ou 8 mm)
TOL = 0.15       # folga do rasgo (laser)
M = 8.0          # recuo do fundo/topo (as paredes viram "pé")
TAB_W = 36.0     # largura da espiga
PROT = 22.0      # quanto a espiga com cunha passa da face externa
HOLE_IN, HOLE_L = 1.0, 14.0
SHEET = (1300.0, 900.0)   # mesa de laser

AX = {"x": 0, "y": 1, "z": 2}
UNIT = [np.array(v, float) for v in ((1,0,0), (0,1,0), (0,0,1))]

# produtos reais (mm) — da lista enviada
COB = dict(L=300, D=160)               # coberta enrolada 30 x 16
BG = dict(w=240, h=190)                # bandana G 24 x 19
BP = dict(w=200, h=160)                # bandana P 20 x 16
GR = dict(w=120, h=60, t=35)           # gravata 12 x 6
PP = dict(L=170, w=90, t=40)           # pelúcia osso P 17 x 4 (largura estimada pela foto)
PG = dict(L=270, w=140, t=60)          # pelúcia osso G 27 x 6 (largura estimada pela foto)


class Plate:
    def __init__(self, name, poly, o, U, V, W, group=None, kind="mdf"):
        self.name, self.poly, self.group, self.kind = name, poly, group, kind
        self.o, self.U, self.V, self.W = [np.array(v, float) for v in (o, U, V, W)]
        self.eng = []

    def loc(self, p):
        d = np.array(p, float) - self.o
        return float(d @ self.U), float(d @ self.V)

    def rect(self, lo, hi):
        pts = [self.loc((x, y, z)) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        return box(min(us), min(vs), max(us), max(vs))


def mk(name, x0, x1, y0, y1, z0, z1, group=None):
    d = [x1 - x0, y1 - y0, z1 - z0]
    thin = int(np.argmin(d))
    assert abs(d[thin] - T) < 1e-6, (name, d)
    if thin == 0:   U, V, W = (0,0,1), (0,1,0), (1,0,0)
    elif thin == 1: U, V, W = (1,0,0), (0,0,1), (0,1,0)
    else:           U, V, W = (1,0,0), (0,1,0), (0,0,1)
    p = Plate(name, None, (x0, y0, z0), U, V, W, group)
    p.lo, p.hi = np.array([x0, y0, z0]), np.array([x1, y1, z1])
    p.poly = p.rect(p.lo, p.hi)
    return p


def thin_axis(p):
    return int(np.argmax(np.abs(p.W)))


class Build:
    def __init__(self, key):
        self.key, self.plates, self.products, self.notes = key, [], [], {}
        self.nwedge = 0; self.nlap = 0; self.hw = []

    def add(self, p):
        self.plates.append(p); return p

    def tenon(self, inner, host, axis_e, centers, wedge=False, w=TAB_W):
        a = thin_axis(host); t = thin_axis(inner); e = AX[axis_e]
        h0, h1 = host.lo[a], host.hi[a]
        # lado do host em relação ao miolo da peça interna
        s = 1 if (h0 + h1) / 2 > (inner.lo[a] + inner.hi[a]) / 2 else -1
        extra = PROT if wedge else 0.0
        for c in centers:
            lo, hi = np.zeros(3), np.zeros(3)
            lo[t], hi[t] = inner.lo[t], inner.hi[t]
            lo[e], hi[e] = c - w/2, c + w/2
            lo[a], hi[a] = (h0, h1 + extra) if s > 0 else (h0 - extra, h1)
            inner.poly = unary_union([inner.poly, inner.rect(lo, hi)])
            slo, shi = lo.copy(), hi.copy()
            slo[a], shi[a] = h0 - 1, h1 + 1
            slo[e] -= TOL; shi[e] += TOL; slo[t] -= TOL; shi[t] += TOL
            host.poly = host.poly.difference(host.rect(slo, shi))
            if wedge:
                fo = h1 if s > 0 else h0
                hl = sorted([fo - s*HOLE_IN, fo + s*(HOLE_L - HOLE_IN)])
                hlo, hhi = lo.copy(), hi.copy()
                hlo[a], hhi[a] = hl
                hlo[e], hhi[e] = c - (T + 0.2)/2, c + (T + 0.2)/2
                hlo[t], hhi[t] = inner.lo[t] - 1, inner.hi[t] + 1
                inner.poly = inner.poly.difference(inner.rect(hlo, hhi))
                o = np.zeros(3)
                o[a] = fo; o[t] = (inner.lo[t] + inner.hi[t])/2 - 53; o[e] = c - T/2
                wp = Polygon([(0, 0), (5, 0), (14, 60), (19, 60), (19, 68), (0, 68)])
                self.add(Plate("Cunha", wp, o, s*UNIT[a], UNIT[t], UNIT[e], inner.group, "wedge"))
                self.nwedge += 1

    def lap(self, uw, dw, drop="top"):
        """Encaixe de meia-madeira (rasgo até a metade) entre duas paredes que se cruzam.
        uw = parede da base do 'U' (fica parada); dw = parede que desce (drop='top') ou sobe."""
        lo = np.maximum(uw.lo, dw.lo); hi = np.minimum(uw.hi, dw.hi)
        assert (hi - lo > 0).all(), (uw.name, dw.name)
        ym = (lo[1] + hi[1]) / 2
        for p, top in ((uw, drop == "top"), (dw, drop != "top")):
            a, b_ = lo.copy(), hi.copy()
            for k in (0, 2):
                a[k] -= TOL; b_[k] += TOL
            if top: a[1], b_[1] = ym - TOL, 1e4      # rasgo vai até a borda de cima da peça
            else:   a[1], b_[1] = -1e4, ym + TOL     # rasgo vai até a borda de baixo
            p.poly = p.poly.difference(p.rect(a, b_))
        self.nlap += 1

    def lap_ax(self, a, b, ax, a_open="high"):
        """Meia-madeira ao longo do eixo 'x'/'y'/'z': 'a' abre o rasgo para o lado a_open, 'b' para o outro."""
        k = AX[ax]
        lo = np.maximum(a.lo, b.lo); hi = np.minimum(a.hi, b.hi)
        assert (hi - lo > 0).all(), (a.name, b.name)
        mid = (lo[k] + hi[k]) / 2
        for p, high in ((a, a_open == "high"), (b, a_open != "high")):
            l, h = lo.copy(), hi.copy()
            for j in range(3):
                if j != k: l[j] -= TOL; h[j] += TOL
            if high: l[k], h[k] = mid - TOL, 1e4
            else:    l[k], h[k] = -1e4, mid + TOL
            p.poly = p.poly.difference(p.rect(l, h))
        self.nlap += 1

    def drop_tab(self, inner, host, axis_e, centers, edge, w=40.0, ear=20.0):
        """Lingueta da peça 'inner' que encaixa num rasgo ABERTO na borda de cima ('top') ou de baixo ('bottom')
        da parede 'host'. A lingueta atravessa a parede e sobra 'ear' mm para fora. Montagem só na vertical."""
        a = thin_axis(host); t = thin_axis(inner); e = AX[axis_e]
        h0, h1 = host.lo[a], host.hi[a]
        s_ = 1 if (h0 + h1)/2 > (inner.lo[a] + inner.hi[a])/2 else -1
        for c in centers:
            lo, hi = np.zeros(3), np.zeros(3)
            lo[t], hi[t] = inner.lo[t], inner.hi[t]
            lo[e], hi[e] = c - w/2, c + w/2
            lo[a], hi[a] = (h0, h1 + ear) if s_ > 0 else (h0 - ear, h1)
            inner.poly = unary_union([inner.poly, inner.rect(lo, hi)])
            sl, sh = lo.copy(), hi.copy()
            sl[a], sh[a] = h0 - 1, h1 + 1
            sl[e] -= TOL; sh[e] += TOL
            if edge == "top": sl[t] -= TOL; sh[t] = 1e4
            else:             sl[t] = -1e4; sh[t] += TOL
            host.poly = host.poly.difference(host.rect(sl, sh))

    def tooth(self, post, shelf, centers, w=30.0):
        """Dente no alto da peça vertical 'post' que entra num rasgo da prateleira apoiada em cima."""
        t = thin_axis(post); e = 2 if t == 0 else 0
        y0 = post.hi[1]
        for c in centers:
            lo, hi = post.lo.copy(), post.hi.copy()
            lo[e], hi[e] = c - w/2, c + w/2
            lo[1], hi[1] = y0 - 0.01, shelf.hi[1]
            post.poly = unary_union([post.poly, post.rect(lo, hi)])
            sl, sh = lo.copy(), hi.copy()
            sl[e] -= TOL; sh[e] += TOL; sl[t] -= TOL; sh[t] += TOL; sl[1] -= 1; sh[1] += 1
            shelf.poly = shelf.poly.difference(shelf.rect(sl, sh))
        post.hi[1] = shelf.hi[1]

    def boxset(self, pre, X0, X1, Y0, Y1, Z0, Z1, walls=("L","R","Ba","Fr"), plates=("Bo","To"),
               u="x", drop="top", group=None, no_ear=(), E=20.0):
        P = {}
        has = lambda k: k in walls
        ear = lambda k: E if (has(k) and k not in no_ear) else 0.0
        zi0 = Z0 + (T if has("Ba") else 0); zi1 = Z1 - (T if has("Fr") else 0)
        xi0 = X0 + (T if has("L") else 0);  xi1 = X1 - (T if has("R") else 0)
        za, zb = Z0 - ear("Ba"), Z1 + ear("Fr")
        xa, xb = X0 - ear("L"), X1 + ear("R")
        if has("L"):  P["L"]  = mk(pre+"lateral esq.", X0, X0+T, Y0, Y1, za, zb, group)
        if has("R"):  P["R"]  = mk(pre+"lateral dir.", X1-T, X1, Y0, Y1, za, zb, group)
        if has("Ba"): P["Ba"] = mk(pre+"fundo", xa, xb, Y0, Y1, Z0, Z0+T, group)
        if has("Fr"): P["Fr"] = mk(pre+"frente", xa, xb, Y0, Y1, Z1-T, Z1, group)
        for k in P: self.add(P[k])
        U_keys = ("L", "R") if u == "x" else ("Ba", "Fr")
        for xk in ("L", "R"):
            for zk in ("Ba", "Fr"):
                if xk in P and zk in P:
                    uw, dw = (P[xk], P[zk]) if u == "x" else (P[zk], P[xk])
                    self.lap(uw, dw, drop)
        for pk, (ya, yb) in (("Bo", (Y0+M, Y0+M+T)), ("To", (Y1-M-T, Y1-M))):
            if pk not in plates: continue
            p = self.add(mk(pre+("base" if pk == "Bo" else "tampo"), xi0, xi1, ya, yb, zi0, zi1, group))
            P[pk] = p
            nz = max(2, round((zi1-zi0)/160)); nx = max(2, round((xi1-xi0)/160))
            zc = [zi0 + (zi1-zi0)*(i+0.5)/nz for i in range(nz)]
            xc = [xi0 + (xi1-xi0)*(i+0.5)/nx for i in range(nx)]
            for k in U_keys:
                if k in P: self.tenon(p, P[k], "z" if k in ("L", "R") else "x", zc if k in ("L", "R") else xc)
        return P

    def engr(self, p, text, c, n, up, h, sub=None):
        p.eng.append(dict(text=text, c=list(map(float, c)), n=list(map(float, n)), up=list(map(float, up)), h=h, sub=sub))

    def prod(self, t, c, s, U=(1,0,0), V=(0,1,0), W=(0,0,1), g=None, **kw):
        d = dict(t=t, c=list(map(float, c)), s=list(map(float, s)), U=U, V=V, W=W, g=g); d.update(kw)
        self.products.append(d)


def hbox(b, c, s, U=(1,0,0), V=(0,1,0), W=(0,0,1), m="metal", g=None):
    b.hw.append(dict(k="box", c=list(map(float, c)), s=list(map(float, s)), U=U, V=V, W=W, m=m, g=g))

def hcyl(b, c, r, ln, axis, m="metal", g=None):
    b.hw.append(dict(k="cyl", c=list(map(float, c)), r=float(r), l=float(ln), a=list(axis), m=m, g=g))

def pivot_hinge(b, xface, sgn, yp, zp, dir_fix, dir_mov, L=96.0, w=24.0):
    """Dobradiça pivô externa na face lateral (plano YZ). dir_* = direção (dy,dz) da aba a partir do pino."""
    for k, (d, g, off) in enumerate(((dir_fix, None, 1.0), (dir_mov, "mov", 3.6))):
        dy, dz = d; n = math.hypot(dy, dz); dy, dz = dy/n, dz/n
        x = xface + sgn*off
        c = (x, yp + dy*(L/2 - 4), zp + dz*(L/2 - 4))
        U = (0.0, dy, dz); V = (0.0, -dz, dy); Wv = (1.0, 0.0, 0.0)
        hbox(b, c, (L, w, 2.2), U=U, V=V, W=Wv, g=g)
        for t in (L*0.32, L*0.72):     # parafusos
            hcyl(b, (x + sgn*1.4, yp + dy*(t - 4), zp + dz*(t - 4)), 3.4, 1.6, (1,0,0), m="screw", g=g)
    hcyl(b, (xface + sgn*3.0, yp - 1, zp), 4.5, 6.0, (1,0,0))
    hcyl(b, (xface + sgn*6.4, yp - 1, zp), 3.2, 1.6, (1,0,0), m="screw")

def leather_handle(b, y, z, span=200.0, rise=46.0, g=None, flat=False, axis="x"):
    pts = []
    for i in range(25):
        t = i/24; x = -span/2 + span*t
        h = rise*math.sin(math.pi*min(1, max(0, (t - 0.06)/0.88))) + 5
        pts.append([x, y + h, z] if axis == "x" else [z, y + h, x])
    b.hw.append(dict(k="strap", pts=pts, w=28.0, th=7.0, m="leather", g=g, flat=flat, y0=float(y)))
    for sx in (-1, 1):
        cx = sx*(span/2 - 4)
        c = (cx, y + 7, z) if axis == "x" else (z, y + 7, cx)
        hbox(b, c, (30, 14, 34), m="metal", g=g)
        for dz in (-9, 9):
            cc = (cx, y + 14.2, z + dz) if axis == "x" else (z + dz, y + 14.2, cx)
            hcyl(b, cc, 3.2, 1.4, (0,1,0), m="screw", g=g)

def tabs_c(lo, hi, n):
    return [lo + (hi - lo)*(i + 0.5)/n for i in range(n)]

FLAT_X = dict(U=(1,0,0), V=(0,0,-1), W=(0,1,0))   # objeto deitado, comprimento em X
FLAT_Z = dict(U=(0,0,1), V=(1,0,0), W=(0,1,0))    # objeto deitado, comprimento em Z
ROLL_Z = dict(U=(0,0,1), V=(0,1,0), W=(-1,0,0))   # rolo deitado frente-trás
ROLL_Y = dict(U=(0,1,0), V=(-1,0,0), W=(0,0,1))   # rolo em pé

BAND_PATS = ["buffalo_red", "gingham_bw", "buffalo_blue"]
COB_COLS = ["sage", "navy", "oat"]


# =====================================================================================
# A — MALETA VITRINE (estilo caixa laranja): base + tampa que abre 100° e vira vitrine
# =====================================================================================
def build_A():
    b = Build("A"); W, D, Hb, Hl = 630.0, 380.0, 180.0, 75.0
    X0, X1 = -W/2, W/2
    base = b.boxset("Base ", X0, X1, 0, Hb, 0, D, plates=("Bo",), u="z", drop="top", no_ear=("Ba",))
    lid = b.boxset("Tampa ", X0, X1, Hb, Hb + Hl, 0, D, plates=("To",), u="x", drop="bottom", group="mov", no_ear=("Ba",))
    fl = M + T                     # piso interno
    xi0, xi1 = X0 + T, X1 - T
    # zonas: rolos | gravatas (piso elevado) | ossos
    xr1 = xi0 + 2*COB["D"] + T + 6           # fim zona rolos
    d1 = b.add(mk("Divisória 1", xr1, xr1 + T, fl, Hb - 20, T, D - T))
    xg1 = xr1 + T + 126
    d2 = b.add(mk("Divisória 2", xg1, xg1 + T, fl, Hb - 20, T, D - T))
    for d in (d1, d2):
        b.tenon(d, base["Bo"], "z", tabs_c(T, D - T, 3))
        b.tenon(d, base["Ba"], "y", [fl + 70]); b.tenon(d, base["Fr"], "y", [fl + 70])
    # berços dos rolos (meia-lua) — seguram as cobertas no transporte
    rc = [xi0 + 3 + COB["D"]/2, xi0 + 3 + COB["D"]*1.5 + T]
    for k, zc in enumerate((70.0, D - 70.0)):
        cr = b.add(mk(f"Berço dos rolos {k+1}", xi0, xr1, fl, fl + 60, zc - T/2, zc + T/2))
        cuts = [Point(cr.loc((x, fl + COB["D"]/2 + 2, zc))).buffer(COB["D"]/2 + 2, 48) for x in rc]
        cr.poly = cr.poly.difference(unary_union(cuts))
        b.tenon(cr, base["Bo"], "x", rc)
        b.tenon(cr, d1, "y", [fl + 25])
    # piso elevado das gravatas + 2 separadores
    ye = 105.0
    pe = b.add(mk("Piso elevado gravatas", xr1 + T, xg1, ye, ye + T, T, D - T))
    b.tenon(pe, d1, "z", tabs_c(T, D - T, 2)); b.tenon(pe, d2, "z", tabs_c(T, D - T, 2))
    b.tenon(pe, base["Ba"], "x", [(xr1 + T + xg1)/2]); b.tenon(pe, base["Fr"], "x", [(xr1 + T + xg1)/2])
    cell = (D - 2*T - 2*T) / 3
    for k in range(2):
        zc = T + cell*(k + 1) + T*k
        sp = b.add(mk(f"Separador gravatas {k+1}", xr1 + T, xg1, ye + T, ye + T + 35, zc, zc + T))
        b.tenon(sp, pe, "x", [(xr1 + T + xg1)/2])
    # varão da tampa (prateleira-cabide paralela ao tampo)
    yv = Hb + Hl - M - T - 22
    zv0, zv1 = D - 95, D - 65
    rail = b.add(mk("Varão da tampa", xi0, xi1, yv - T, yv, zv0, zv1, "mov"))
    b.tenon(rail, lid["L"], "z", [(zv0 + zv1)/2], w=20); b.tenon(rail, lid["R"], "z", [(zv0 + zv1)/2], w=20)
    # gravação
    b.engr(lid["To"], "principal", (0, Hb + Hl - M, D/2), (0,1,0), (0,0,-1), 300)
    b.engr(lid["To"], "selo", (18, Hb + Hl - M - T, 140), (0,-1,0), (0,0,1), 150)
    b.engr(base["Fr"], "principal", (0, 95, D), (0,0,1), (0,1,0), 200)
    # ---------- produtos ----------
    for k, x in enumerate(rc):
        b.prod("coberta", (x, fl + 80 + 2, D/2), (COB["L"], COB["D"], COB["D"]), **ROLL_Z, col=COB_COLS[k])
    gx = (xr1 + T + xg1)/2
    for k in range(3):
        zc = T + cell*(k + 0.5) + T*k
        b.prod("gravata", (gx, ye + T + GR["t"]/2 + 1, zc), (GR["w"], GR["h"], GR["t"]), **FLAT_X, pat=["ladybug","polka_teal","ladybug"][k])
    bx = (xg1 + T + xi1)/2
    b.prod("osso", (bx, fl + PG["t"]/2, D/2), (PG["L"], PG["w"], PG["t"]), **FLAT_Z, col="navy")
    b.prod("osso", (bx, fl + PG["t"] + PP["t"]/2, D/2), (PP["L"], PP["w"], PP["t"]), **FLAT_Z, col="sage")
    # tampa (coords fechada): 'para baixo' quando aberta = -Z; 'frente' = -Y
    LIDB = dict(U=(1,0,0), V=(0,0,1), W=(0,-1,0))
    ytop = yv - T
    for x, spec, pat in ((-175, BG, "buffalo_red"), (190, BP, "gingham_bw")):
        b.prod("bandana", (x, ytop - 4, zv1 - spec["h"]/2), (spec["w"], spec["h"], 6), **LIDB, g="mov", pat=pat)
    b.prod("gravata", (18, ytop - GR["t"]/2 - 1, zv1 - 10 - GR["h"]/2), (GR["w"], GR["h"], GR["t"]), **LIDB, g="mov", pat="polka_teal")
    b.pivot = dict(axis="x", p=[0, Hb, -4.0], open=-100, closed=0)
    for xc in (-205.0, 205.0):      # dobradiças de topo na traseira
        hbox(b, (xc, Hb - 26, -1.1), (54, 48, 2.2))
        hbox(b, (xc, Hb + 26, -1.1), (54, 48, 2.2), g="mov")
        hcyl(b, (xc, Hb, -4.0), 4.2, 54, (1,0,0))
        for dx in (-15, 15):
            for dy, g in ((-34, None), (34, "mov")):
                hcyl(b, (xc + dx, Hb + dy*0.75, -2.6), 3.0, 1.4, (0,0,1), m="screw", g=g)
    leather_handle(b, Hb + Hl - M, D/2, g="mov")
    b.closed = dict(L=W + 40, P=D + 20, A=Hb + Hl); b.opened = dict(L=W + 40, P=D + 80, A=Hb + D)
    b.kit = dict(cobertas=2, bandanas=2, gravatas=4, pelucias=2)
    return b


# =====================================================================================
# B — MALETA ESCADA (esboço): tampa vira 180° e continua a rampa; fechada é uma caixa
# =====================================================================================
def build_B():
    b = Build("B"); W, D, Hb, hl = 560.0, 340.0, 400.0, 60.0          # fechada: 60 x 38 x 40 cm com as pontas
    Dt = D/2; L = Hb - hl; X0, X1 = -W/2, W/2; E = 20.0
    xi0, xi1 = X0 + T, X1 - T
    # laterais pentagonais
    def side(name, x0):
        p = Plate(name, Polygon([(-E,0), (D+E,0), (D+E,hl), (D-T,hl), (Dt,Hb), (-E,Hb)]), (x0, 0, 0), (0,0,1), (0,1,0), (1,0,0))
        p.lo, p.hi = np.array([x0, 0, -E]), np.array([x0 + T, Hb, D + E])
        return b.add(p)
    Ls, Rs = side("Base lateral esq.", X0), side("Base lateral dir.", X1 - T)
    for sd in (Ls, Rs):   # alça vazada nas laterais
        hd = box(27, 342, 153, 368)   # recorte retangular, cantos retos
        sd.poly = sd.poly.difference(hd)
    back = b.add(mk("Base fundo", X0 - E, X1 + E, 0, Hb, 0, T))
    lip = b.add(mk("Bandeja frente (logo)", X0 - E, X1 + E, 0, hl, D - T, D))
    for s in (Ls, Rs):
        b.lap(s, back, "top"); b.lap(s, lip, "top")
    # ---- só rasgo, sem nenhuma aba: cada chapa deitada cruza a lateral num rasgo de meia-madeira ----
    fl = T; MR = 12.0
    bo = b.add(mk("Base piso", X0 - E, X1 + E, 0, T, T, D - T))
    for sd in (Ls, Rs): b.lap_ax(sd, bo, "z", "low")          # piso entra por trás; o fundo desce e trava
    top = b.add(mk("Base tampo (alça)", X0 - E, X1 + E, Hb - MR - T, Hb - MR, T, Dt))
    for sd in (Ls, Rs): b.lap_ax(sd, top, "z", "high")        # tampo entra pela frente
    # cobertas em pé no fundo | prateleira alta com bandanas P | bandeja da frente com os ossos
    rx = [xi0 + 3 + COB["D"]/2 + k*(COB["D"] + 6) for k in range(3)]   # cobertas deitadas no piso
    zr = T + COB["L"]/2
    ysh = 180.0                                                          # prateleira no meio da base
    zsf = D - (ysh + T/2 - hl)/(L/Dt) - 3                               # vai até a rampa da lateral
    shelf = b.add(mk("Prateleira do meio (ossos e bandanas P)", X0 - E, X1 + E, ysh, ysh + T, T, zsf))
    b.lap_ax(Ls, shelf, "z", "high"); b.lap_ax(Rs, shelf, "z", "high")   # entra pela frente
    # ---- tampa (posição ABERTA) ----
    def tri(name, x0):
        p = Plate(name, Polygon([(-E,0), (Dt,0), (0,L), (-E,L)]), (x0, Hb, 0), (0,0,1), (0,1,0), (1,0,0), "mov")
        p.lo, p.hi = np.array([x0, Hb, -E]), np.array([x0 + T, Hb + L, Dt])
        return b.add(p)
    tL, tR = tri("Tampa lateral esq.", X0), tri("Tampa lateral dir.", X1 - T)
    par = b.add(mk("Tampa painel (logo fechada)", X0 - E, X1 + E, Hb, Hb + L, 0, T, "mov"))
    for s in (tL, tR): b.lap(s, par, "top")
    piso = b.add(mk("Tampa piso", X0 - E, X1 + E, Hb + MR, Hb + MR + T, T, Dt, "mov"))
    for s in (tL, tR): b.lap_ax(s, piso, "z", "high")
    # varões (prateleiras-cabide) no painel
    rails = {}
    # varões em pé (tiras), meia-madeira vertical com as laterais da tampa; a bandana dobra por cima
    yGt = Hb + L - 42.0                                  # bandanas G no alto da tampa
    yGb = yGt - BG["h"]                                  # ponta das bandanas G
    ygt = (yGb + (Hb + MR + T)) / 2 + GR["h"]/2          # gravatas centradas no espaço livre abaixo
    for nm, y0, how in (("Varão bandanas G", yGt - 30, "top"), ("Varão gravatas", ygt - 30, "bottom")):
        r = b.add(mk(nm, X0 - E, X1 + E, y0, y0 + 30, 14, 14 + T, "mov"))
        for s in (tL, tR): b.lap(s, r, how)
        rails[nm] = y0 + 30
    # gravação
    b.engr(lip, "principal", (0, hl/2, D), (0,0,1), (0,1,0), 92)
    b.engr(back, "principal", (0, Hb*0.5, 0), (0,0,-1), (0,1,0), 360)   # logo no fundo da base, em pé quando aberta
    # logo na face de dentro do fundo da base, acima da prateleira: visível de frente com os produtos no lugar
    b.engr(back, "principal", (xi1 - 128, ysh + T + 95, T), (0,0,1), (0,1,0), 150)   # à direita, acima das bandanas P
    b.engr(Ls, "selo", (X0, 98, 140), (-1,0,0), (0,1,0), 118)
    b.engr(Rs, "selo", (X1, 98, 140), (1,0,0), (0,1,0), 118)
    # ---------- produtos ----------
    for k, x in enumerate(rx):
        b.prod("coberta", (x, fl + COB["D"]/2, zr), (COB["L"], COB["D"], COB["D"]), **ROLL_Z, col=COB_COLS[k])
    # prateleira: ossos à esquerda (P em cima do G), bandanas P em leque à direita
    zo = T + PG["L"]/2 + 2; ysf = ysh + T
    bx = [xi0 + 3 + PG["w"]/2, xi0 + 3 + PG["w"]*1.5 + 5]
    for x, c1, c2 in ((bx[0], "navy", "sage"), (bx[1], "sage", "navy")):
        b.prod("osso", (x, ysf + PG["t"]/2, zo), (PG["L"], PG["w"], PG["t"]), **FLAT_Z, col=c1)
        b.prod("osso", (x, ysf + PG["t"] + PP["t"]/2, zo + 30), (PP["L"], PP["w"], PP["t"]), **FLAT_Z, col=c2)
    xs = bx[1] + PG["w"]/2 + 8; stp = (xi1 - 4 - xs - BP["w"]) / 2
    for k in range(3):
        b.prod("bandana", (xs + BP["w"]/2 + k*stp, ysf + 4 + k*1.2, (T + zsf)/2 + 10 - k*12), (BP["w"], BP["h"], 6),
               U=(1,0,0), V=(0,0,-1), W=(0,1,0), pat=BAND_PATS[k])
    yG = rails["Varão bandanas G"]
    for k, x in enumerate((-(xi1 - 122), 0.0, xi1 - 122)):
        b.prod("bandana", (x, yG - BG["h"]/2, 25 + k*1.2), (BG["w"], BG["h"], 6), g="mov", pat=BAND_PATS[k])
    yg = rails["Varão gravatas"]
    for k, x in enumerate((-195.0, -65.0, 65.0, 195.0)):
        b.prod("gravata", (x, yg - GR["h"]/2, 22 + GR["t"]/2 + 1), (GR["w"], GR["h"], GR["t"]), g="mov",
               pat=["ladybug", "polka_teal", "ladybug", "polka_teal"][k])
    b.pivot = dict(axis="x", p=[0, Hb, Dt], open=0, closed=180)
    leather_handle(b, Hb - MR, 95.0, flat=True)
    # 2 fechos de pressão (tipo maleta) na frente, na emenda entre a tampa fechada e a frente da bandeja
    def to_open(c):                 # tampa é desenhada aberta: converte coordenada "fechada" -> "aberta"
        return (c[0], 2*Hb - c[1], 2*Dt - c[2])
    for xc in (-200.0, 200.0):
        # parte fixa (gancho) na frente da bandeja
        hbox(b, (xc, hl - 13, D + 1.2), (30, 22, 2.4))
        hbox(b, (xc, hl - 5, D + 4.5), (12, 6, 5))
        # corpo + alavanca na tampa (fica na frente quando fechada)
        hbox(b, to_open((xc, hl + 22, D + 1.4)), (38, 40, 2.8), g="mov")
        hbox(b, to_open((xc, hl + 18, D + 5.0)), (26, 30, 4.4), g="mov")
        hbox(b, to_open((xc, hl + 2, D + 7.2)), (20, 10, 3.0), g="mov")
        for dx in (-12.0, 12.0):
            hcyl(b, to_open((xc + dx, hl + 36, D + 3.0)), 2.6, 1.2, (0,0,1), m="screw", g="mov")
            hcyl(b, (xc + dx, hl - 19, D + 2.6), 2.4, 1.2, (0,0,1), m="screw")
    # 2 dobradiças comuns de chapa (76 x 50 mm aberta), uma em cada canto da emenda do tampo
    ysf = Hb - MR                   # face de cima dos tampos (rebaixo de 12 mm)
    HL, HW = 76.0, 25.0             # comprimento da dobradiça e largura de cada aba
    for xc in (xi0 + 18 + HL/2, xi1 - 18 - HL/2):
        hbox(b, (xc, ysf + 0.8, Dt - HW/2), (HL, 1.6, HW))                   # aba no tampo da alça
        hbox(b, (xc, Hb + MR - 0.8, Dt - HW/2), (HL, 1.6, HW), g="mov")      # aba no piso da tampa (posição aberta)
        hcyl(b, (xc, Hb, Dt), 4.0, HL, (1,0,0))                              # eixo (canudo)
        for dx in (-26.0, 0.0, 26.0):
            hcyl(b, (xc + dx, ysf + 1.9, Dt - 13), 3.2, 1.2, (0,1,0), m="screw")
            hcyl(b, (xc + dx, Hb + MR - 1.9, Dt - 13), 3.2, 1.2, (0,1,0), m="screw", g="mov")
    b.closed = dict(L=W + 40, P=D + 40, A=Hb); b.opened = dict(L=W + 40, P=D + 40, A=Hb + L)
    b.kit = dict(cobertas=3, bandanas=6, gravatas=4, pelucias=4)
    return b


# =====================================================================================
# C — MALETA BAÚ (livro): corpo + porta-caixa que abre de lado
# =====================================================================================
def build_C():
    b = Build("C"); W, H, D, dd = 560.0, 480.0, 300.0, 140.0
    X0, X1 = -W/2, W/2; xi0, xi1 = X0 + T, X1 - T
    body = b.boxset("Corpo ", X0, X1, 0, H, 0, D, walls=("L","R","Ba"), u="x", no_ear=("R",))
    door = b.boxset("Porta ", X0, X1, 0, H, D, D + dd, walls=("L","R","Fr"), u="x", group="mov", no_ear=("R",))
    fl = M + T
    # suporte dos rolos em pé (U aberto para a frente)
    rx = [-166.0, 0.0, 166.0]; zr = D - 92
    hold = b.add(mk("Suporte dos rolos", xi0, xi1, 130, 130 + T, T, D - 10))
    cuts = []
    for x in rx:
        c = Point(hold.loc((x, 130, zr))).buffer(COB["D"]/2 + 3, 48)
        cuts.append(c.union(hold.rect(np.array([x - 83, 129, zr]), np.array([x + 83, 131 + T, 600]))))
    hold.poly = hold.poly.difference(unary_union(cuts))
    b.tenon(hold, body["L"], "z", [50.0]); b.tenon(hold, body["R"], "z", [50.0])
    ysh = 322.0
    sh = b.add(mk("Prateleira (ossos)", xi0, xi1, ysh, ysh + T, T, D))
    b.tenon(sh, body["L"], "z", [80.0, 220.0]); b.tenon(sh, body["R"], "z", [80.0, 220.0])
    lipb = b.add(mk("Frente da prateleira", xi0, xi1, ysh + T, ysh + T + 30, D - T, D))
    b.tenon(lipb, sh, "x", tabs_c(xi0, xi1, 3))
    # varões na porta (perpendiculares à frente)
    zf = D + dd - T
    rails = {}
    for nm, y0 in (("Varão bandanas G", 449.0), ("Varão bandanas P", 252.0), ("Varão gravatas", 84.0)):
        r = b.add(mk(nm, xi0, xi1, y0, y0 + T, zf - 24, zf, "mov"))
        b.tenon(r, door["L"], "z", [zf - 12], w=16); b.tenon(r, door["R"], "z", [zf - 12], w=16)
        rails[nm] = y0 + T
    b.engr(door["Fr"], "principal", (0, H*0.55, D + dd), (0,0,1), (0,1,0), 400)
    b.engr(body["L"], "selo", (X0, H*0.5, D/2), (-1,0,0), (0,1,0), 180)
    # ---------- produtos ----------
    for k, x in enumerate(rx):
        b.prod("coberta", (x, fl + COB["L"]/2, zr), (COB["L"], COB["D"], COB["D"]), **ROLL_Y, col=COB_COLS[k])
    xs = -267.0
    for (spec, col) in ((PG, "navy"), (PG, "sage"), (PP, "sage"), (PP, "navy")):
        b.prod("osso", (xs + spec["w"]/2, ysh + T + spec["t"]/2, D - 8 - spec["L"]/2), (spec["L"], spec["w"], spec["t"]), **FLAT_Z, col=col)
        xs += spec["w"] + 12
    DOORB = dict(U=(-1,0,0), V=(0,1,0), W=(0,0,-1))
    zb = zf - 24 - 4
    for k, x in enumerate((-152.0, 0.0, 152.0)):
        b.prod("bandana", (x, rails["Varão bandanas G"] - BG["h"]/2, zb - k*1.2), (BG["w"], BG["h"], 6), **DOORB, g="mov", pat=BAND_PATS[k])
    for k, x in enumerate((-171.0, 0.0, 171.0)):
        b.prod("bandana", (x, rails["Varão bandanas P"] - BP["h"]/2, zb - k*1.2), (BP["w"], BP["h"], 6), **DOORB, g="mov", pat=BAND_PATS[k])
    for k, x in enumerate((-195.0, -65.0, 65.0, 195.0)):
        b.prod("gravata", (x, rails["Varão gravatas"] - GR["h"]/2, zf - 24 - GR["t"]/2 - 1), (GR["w"], GR["h"], GR["t"]), **DOORB, g="mov",
               pat=["ladybug", "polka_teal", "ladybug", "polka_teal"][k])
    b.pivot = dict(axis="y", p=[W/2 + 4, 0, D], open=178, closed=0)
    for yc in (95.0, 385.0):
        hbox(b, (W/2 + 1.1, yc, D - 26), (2.2, 64, 46))
        hbox(b, (W/2 + 1.1, yc, D + 26), (2.2, 64, 46), g="mov")
        hcyl(b, (W/2 + 4, yc, D), 4.2, 64, (0,1,0))
        for dz in (-34, 34):
            for dy in (-18, 18):
                hcyl(b, (W/2 + 2.4, yc + dy, D + dz), 3.0, 1.4, (1,0,0), m="screw", g=("mov" if dz > 0 else None))
    leather_handle(b, H - M, 165.0)
    b.closed = dict(L=W + 20, P=D + dd + 40, A=H); b.opened = dict(L=2*W + 40, P=D + 20, A=H)
    b.kit = dict(cobertas=3, bandanas=6, gravatas=4, pelucias=4)
    return b


# =====================================================================================
# D — MALETA ESCADA PARAFUSADA (teste): mesma maleta B, sem rasgo e sem cantoneira.
# Chapas retas de topo, unidas por sarrafos de pinus 15 x 15 mm colados/parafusados por dentro.
# O parafuso atravessa a chapa (furo de 4 mm já no corte) e morde o sarrafo — MDF de 6/8 mm
# não segura parafuso pelo topo, então todo parafuso entra pela face.
# =====================================================================================
SR = 15.0          # sarrafo 15 x 15
HOLE_D = 4.0       # furo de passagem p/ parafuso 3,5 mm

def _drill(p, pt, d=HOLE_D):
    p.poly = p.poly.difference(Point(p.loc(pt)).buffer(d/2, 16))

def batten(b, lo, hi, attach, g=None, step=120.0, inset=20.0):
    """sarrafo (caixa lo..hi) parafusado nas chapas de 'attach' = [(chapa, eixo, lado)];
    eixo = eixo da espessura da chapa; lado = +1 se a chapa fica do lado + do sarrafo."""
    lo, hi = np.array(lo, float), np.array(hi, float)
    hbox(b, (lo + hi)/2, hi - lo, m="wood", g=g)
    k = int(np.argmax(hi - lo)); L = hi[k] - lo[k]
    b.sarr.append(round(L))
    n = 1 if L < 2*inset + 10 else max(2, int(math.ceil((L - 2*inset)/step)) + 1)
    for (pl, ax, sd) in attach:
        i = AX[ax]
        for m_ in range(n):
            t = (lo[k] + hi[k])/2 if n == 1 else lo[k] + inset + (L - 2*inset)*m_/(n - 1)
            pt = (lo + hi)/2; pt[k] = t
            face = pl.hi[i] if sd > 0 else pl.lo[i]      # face externa da chapa
            pt[i] = face - sd*1e-3
            _drill(pl, pt)
            nv = [0, 0, 0]; nv[i] = sd
            hcyl(b, tuple(pt), 3.6, 1.2, tuple(nv), m="screw", g=g)
            b.fix["madeira"] = b.fix.get("madeira", 0) + 1


def build_D():
    b = Build("D"); b.fix = {}; b.sarr = []; b.al = []; b.nbr = 0
    W, D, Hb, hl = 560.0, 340.0, 400.0, 60.0
    Dt = D/2; L = Hb - hl; X0, X1 = -W/2, W/2
    xi0, xi1 = X0 + T, X1 - T
    MR = 12.0
    # ---------------- base ----------------
    bo = b.add(mk("Base piso", X0, X1, 0, T, 0, D))
    def side(name, x0):
        p = Plate(name, Polygon([(0, T), (D, T), (D, hl), (Dt, Hb), (0, Hb)]), (x0, 0, 0), (0,0,1), (0,1,0), (1,0,0))
        p.lo, p.hi = np.array([x0, T, 0]), np.array([x0 + T, Hb, D])
        return b.add(p)
    Ls, Rs = side("Base lateral esq.", X0), side("Base lateral dir.", X1 - T)
    for sd in (Ls, Rs):
        sd.poly = sd.poly.difference(box(27, 342, 153, 368))
    back = b.add(mk("Base fundo", xi0, xi1, T, Hb, 0, T))
    lip = b.add(mk("Bandeja frente", xi0, xi1, T, hl, D - T, D))
    ytop = Hb - MR - T
    top = b.add(mk("Base tampo (alça)", xi0, xi1, ytop, Hb - MR, T, Dt))
    ysh = 180.0
    zsf = D - (ysh + T/2 - hl)/(L/Dt) - 3
    shelf = b.add(mk("Prateleira do meio (ossos e bandanas P)", xi0, xi1, ysh, ysh + T, T, zsf))
    for sd, x0, sx in ((Ls, xi0, 1), (Rs, xi1 - SR, -1)):
        side_at = (sd, "x", -sx)                      # lateral fica do lado -sx do sarrafo
        x1 = x0 + SR
        # pé: sarrafo no piso, ao longo da lateral (piso embaixo)
        batten(b, (x0, T, T + SR), (x1, T + SR, D - T), [side_at, (bo, "y", -1)])
        # quina de trás, vertical (lateral + fundo)
        batten(b, (x0, T + SR, T), (x1, ysh, T + SR), [side_at, (back, "z", -1)])
        batten(b, (x0, ysh + T, T), (x1, ytop - SR, T + SR), [side_at, (back, "z", -1)])
        # quina da frente, toquinho na bandeja (abaixo da curva do rolo)
        batten(b, (x0, T + SR, D - T - SR), (x1, T + SR + 22, D - T), [side_at, (lip, "z", 1)])
        # apoio do tampo da alça (acima da alça vazada) e da prateleira
        batten(b, (x0, ytop - SR, T + SR), (x1, ytop, Dt), [side_at, (top, "y", 1)])
        batten(b, (x0, ysh - SR, T + SR), (x1, ysh, zsf), [side_at, (shelf, "y", 1)])
    # fundo x tampo da alça
    batten(b, (xi0 + SR, ytop - SR, T), (xi1 - SR, ytop, T + SR), [(back, "z", -1), (top, "y", 1)])
    # ---------------- tampa (posição ABERTA) ----------------
    def tri(name, x0):
        p = Plate(name, Polygon([(0, 0), (Dt, 0), (0, L)]), (x0, Hb, 0), (0,0,1), (0,1,0), (1,0,0), "mov")
        p.lo, p.hi = np.array([x0, Hb, 0]), np.array([x0 + T, Hb + L, Dt])
        return b.add(p)
    tL, tR = tri("Tampa lateral esq.", X0), tri("Tampa lateral dir.", X1 - T)
    par = b.add(mk("Tampa painel", xi0, xi1, Hb, Hb + L, 0, T, "mov"))
    ypf = Hb + MR + T
    piso = b.add(mk("Tampa piso", xi0, xi1, Hb + MR, ypf, T, Dt, "mov"))
    ytip = min(Hb + L*(1 - (T + SR + 4)/Dt), 2*Hb - 135)    # largura p/ o sarrafo e, fechada, acima dos rolos
    for sd, x0, sx in ((tL, xi0, 1), (tR, xi1 - SR, -1)):
        side_at = (sd, "x", -sx); x1 = x0 + SR
        batten(b, (x0, ypf, T + SR), (x1, ypf + SR, Dt - 28), [side_at, (piso, "y", -1)], g="mov")
        batten(b, (x0, ypf, T), (x1, ytip, T + SR), [side_at, (par, "z", -1)], g="mov")
    batten(b, (xi0 + SR, ypf, T), (xi1 - SR, ypf + SR, T + SR), [(par, "z", -1), (piso, "y", -1)], g="mov")
    # varões: tira de MDF colada no painel, entre os sarrafos, parafusada por trás do painel
    rails = {}
    yGt = Hb + L - 42.0; yGb = yGt - BG["h"]; ygt = (yGb + (Hb + MR + T)) / 2 + GR["h"]/2
    zr0 = T
    for nm, y0 in (("Varão bandanas G", yGt - 30), ("Varão gravatas", ygt - 30)):
        r = b.add(mk(nm, xi0 + SR, xi1 - SR, y0, y0 + 30, zr0, zr0 + T, "mov"))
        rails[nm] = y0 + 30
        for x in (xi0 + SR + 30, 0.0, xi1 - SR - 30):
            pt = (x, y0 + 15, 1e-3); _drill(par, pt, 3.0)
            hcyl(b, (x, y0 + 15, -0.6), 3.6, 1.2, (0, 0, 1), m="screw", g="mov")
            b.fix["curto"] = b.fix.get("curto", 0) + 1
    # ---------- produtos ----------
    fl = T
    rx = [xi0 + 3 + COB["D"]/2 + k*(COB["D"] + 6) for k in range(3)]; zr = T + SR + 1 + COB["L"]/2
    for k, x in enumerate(rx):
        b.prod("coberta", (x, fl + COB["D"]/2, zr), (COB["L"], COB["D"], COB["D"]), **ROLL_Z, col=COB_COLS[k])
    zo = T + SR + PG["L"]/2 + 2; ysf = ysh + T
    bx = [xi0 + 3 + PG["w"]/2, xi0 + 3 + PG["w"]*1.5 + 5]
    for x, c1, c2 in ((bx[0], "navy", "sage"), (bx[1], "sage", "navy")):
        b.prod("osso", (x, ysf + PG["t"]/2, zo), (PG["L"], PG["w"], PG["t"]), **FLAT_Z, col=c1)
        b.prod("osso", (x, ysf + PG["t"] + PP["t"]/2, zo + 30), (PP["L"], PP["w"], PP["t"]), **FLAT_Z, col=c2)
    xs = bx[1] + PG["w"]/2 + 8; stp = (xi1 - 4 - xs - BP["w"]) / 2
    for k in range(3):
        b.prod("bandana", (xs + BP["w"]/2 + k*stp, ysf + 4 + k*1.2, (T + zsf)/2 + 10 - k*12), (BP["w"], BP["h"], 6),
               U=(1,0,0), V=(0,0,-1), W=(0,1,0), pat=BAND_PATS[k])
    zp = zr0 + T + 5
    yG = rails["Varão bandanas G"]
    for k, x in enumerate((-(xi1 - SR - 124), 0.0, xi1 - SR - 124)):
        b.prod("bandana", (x, yG - BG["h"]/2, zp + 3 + k*1.2), (BG["w"], BG["h"], 6), g="mov", pat=BAND_PATS[k])
    yg = rails["Varão gravatas"]
    for k, x in enumerate((-195.0, -65.0, 65.0, 195.0)):
        b.prod("gravata", (x, yg - GR["h"]/2, zp + GR["t"]/2), (GR["w"], GR["h"], GR["t"]), g="mov",
               pat=["ladybug", "polka_teal", "ladybug", "polka_teal"][k])
    b.pivot = dict(axis="x", p=[0, Hb, Dt], open=0, closed=180)
    leather_handle(b, Hb - MR, 95.0, flat=True)
    def to_open(c): return (c[0], 2*Hb - c[1], 2*Dt - c[2])
    for xc in (-200.0, 200.0):
        hbox(b, (xc, hl - 13, D + 1.2), (30, 22, 2.4))
        hbox(b, (xc, hl - 5, D + 4.5), (12, 6, 5))
        hbox(b, to_open((xc, hl + 22, D + 1.4)), (38, 40, 2.8), g="mov")
        hbox(b, to_open((xc, hl + 18, D + 5.0)), (26, 30, 4.4), g="mov")
        hbox(b, to_open((xc, hl + 2, D + 7.2)), (20, 10, 3.0), g="mov")
    ysf2 = Hb - MR; HL, HW = 76.0, 25.0
    for xc in (xi0 + 18 + HL/2, xi1 - 18 - HL/2):
        hbox(b, (xc, ysf2 + 0.8, Dt - HW/2), (HL, 1.6, HW))
        hbox(b, (xc, Hb + MR - 0.8, Dt - HW/2), (HL, 1.6, HW), g="mov")
        hcyl(b, (xc, Hb, Dt), 4.0, HL, (1,0,0))
    b.closed = dict(L=W, P=D, A=Hb); b.opened = dict(L=W, P=D, A=Hb + L)
    b.kit = dict(cobertas=3, bandanas=6, gravatas=4, pelucias=4)
    return b

BUILDS = [build_A(), build_B(), build_C(), build_D()]
for bld in BUILDS:
    for p in bld.plates:
        if p.poly.geom_type != "Polygon" or not p.poly.is_valid:
            raise SystemExit(f"{bld.key} {p.name}: {p.poly.geom_type} valid={p.poly.is_valid}")
print("geometria ok")
