"""Expositores Zambo em MDF cru — encaixe com cunhas (sem parafuso, sem cola).
Gera: DXF de corte (por modelo e chapa unica), JSON para o 3D, SVG do plano de corte.
Unidades: mm. Eixos 3D: X largura, Y altura, Z profundidade (0 = fundo, + = frente).
"""
import json, math
from shapely.geometry import box, Point, Polygon
from shapely.ops import unary_union
from shapely import affinity
import ezdxf

T = 15.0        # espessura MDF
TOL = 0.3       # folga dos encaixes
TAB = 50.0      # quanto a lingueta passa da face interna da lateral
HOLE_IN = 2.0   # furo da cunha entra 2mm "dentro" da lateral -> aperta
HOLE_W = 20.0
SHEET = (2750.0, 1840.0)

def bone(cx, cy, L, w):
    r = w * 0.32
    core = box(cx - L/2 + r, cy - w*0.2, cx + L/2 - r, cy + w*0.2)
    circ = [Point(cx + sx*(L/2 - r), cy + sy*(w/2 - r)).buffer(r, 24)
            for sx in (-1, 1) for sy in (-1, 1)]
    return unary_union([core] + circ)

def wedge_poly():
    return Polygon([(0, 0), (10, 0), (22, 90), (30, 90), (30, 100), (0, 100)])

class Model:
    def __init__(self, key, nome, W_in, D, H):
        self.key, self.nome, self.W_in, self.D, self.H = key, nome, W_in, D, H
        self.Wtot = W_in + 2*TAB
        self.mortises = []     # em coords da lateral (u=z, v=y)
        self.parts = []        # {name, poly, places:[(origin,U,V,W)], engrave:[], cut_qty}
        self.wedges = []       # posicoes 3D das cunhas
        self.anchors = {}

    def _holes(self, centers_v):
        hs = []
        for c in centers_v:
            a = TAB - T + HOLE_IN
            hs.append(box(a - HOLE_W, c - (T+TOL)/2, a, c + (T+TOL)/2))
            b = TAB + self.W_in + T - HOLE_IN
            hs.append(box(b, c - (T+TOL)/2, b + HOLE_W, c + (T+TOL)/2))
        return hs

    def shelf(self, name, y_b, z0, z1, tabs):
        body = box(TAB, z0, TAB + self.W_in, z1)
        tl = [box(0, a, TAB, b) for a, b in tabs] + \
             [box(TAB + self.W_in, a, self.Wtot, b) for a, b in tabs]
        poly = unary_union([body] + tl).difference(unary_union(self._holes([(a+b)/2 for a, b in tabs])))
        for a, b in tabs:
            self.mortises.append(box(a - TOL/2, y_b - TOL/2, b + TOL/2, y_b + T + TOL/2))
            for s in (-1, 1):
                self.wedges.append(dict(kind="h", x=s*(self.W_in/2 + T), s=s, y=y_b + T/2, z=(a+b)/2))
        self.parts.append(dict(name=name, poly=poly, engrave=[],
            places=[((-self.Wtot/2, y_b, 0), (1,0,0), (0,0,1), (0,1,0))]))

    def vpanel(self, name, y0, h, zp, tabs, notches=False):
        body = box(TAB, 0, TAB + self.W_in, h)
        tl = [box(0, a, TAB, b) for a, b in tabs] + \
             [box(TAB + self.W_in, a, self.Wtot, b) for a, b in tabs]
        poly = unary_union([body] + tl).difference(unary_union(self._holes([(a+b)/2 for a, b in tabs])))
        if notches:
            n = int(self.W_in // 45)
            off = TAB + (self.W_in - (n-1)*45)/2
            cuts = []
            for i in range(n):
                cx = off + i*45
                cuts.append(box(cx - 5, h - 14, cx + 5, h + 1).union(Point(cx, h - 14).buffer(5, 16)))
            poly = poly.difference(unary_union(cuts))
        for a, b in tabs:
            self.mortises.append(box(zp - TOL/2, y0 + a - TOL/2, zp + T + TOL/2, y0 + b + TOL/2))
            for s in (-1, 1):
                self.wedges.append(dict(kind="v", x=s*(self.W_in/2 + T), s=s, y=y0 + (a+b)/2, z=zp + T/2))
        self.parts.append(dict(name=name, poly=poly, engrave=[],
            places=[((-self.Wtot/2, y0, zp), (1,0,0), (0,1,0), (0,0,1))]))

    def header(self, Wh, Hh, zh, a, b, text_h):
        y0 = self.H - a - b
        poly = box(0, 0, Wh, Hh)
        # cantos superiores arredondados
        poly = poly.buffer(-25, join_style=1).buffer(25, join_style=1)
        slots = []
        for x0 in (-self.W_in/2 - T, self.W_in/2):
            u0 = x0 + Wh/2
            slots.append(box(u0 - TOL/2, -1, u0 + T + TOL/2, b))
        poly = poly.difference(unary_union(slots))
        self.header_slot = box(zh - TOL/2, self.H - a, zh + T + TOL/2, self.H + 1)
        ty = (self.H - y0) + (Hh - (self.H - y0)) / 2
        self.parts.append(dict(name="Painel logo", poly=poly,
            engrave=[dict(text="ZAMBO", x=Wh/2, y=ty, h=text_h)],
            places=[((-Wh/2, y0, zh), (1,0,0), (0,1,0), (0,0,1))]))
        self.anchors["logo"] = dict(x=0, y=y0 + ty, z=zh + T, w=Wh, h=text_h)

    def lateral(self, outline, foot, bone_spec):
        poly = Polygon(outline)
        f0, f1, fh = foot
        pts = [(f0 + (f1-f0)*(i/40), fh*math.sin(math.pi*i/40)) for i in range(41)]
        poly = poly.difference(Polygon([(f0, -1)] + pts + [(f1, -1)]))
        poly = poly.difference(unary_union(self.mortises + [self.header_slot, bone(*bone_spec)]))
        hx = self.W_in/2
        self.parts.insert(0, dict(name="Lateral", poly=poly, engrave=[],
            places=[((-hx - T, 0, 0), (0,0,1), (0,1,0), (1,0,0)),
                    ((hx, 0, 0), (0,0,1), (0,1,0), (1,0,0))]))

    def add_wedges(self):
        wp = wedge_poly()
        places = []
        for w in self.wedges:
            # cunha com face reta encostada na lateral; trava onde a largura = 18mm (v = 60)
            if w["kind"] == "h":   # lingueta horizontal: cunha desce na vertical
                places.append(((w["x"], w["y"] - 60, w["z"] - T/2), (w["s"],0,0), (0,1,0), (0,0,1)))
            else:                  # lingueta vertical: cunha entra pela frente
                places.append(((w["x"], w["y"] - T/2, w["z"] - 60), (w["s"],0,0), (0,0,1), (0,1,0)))
        self.parts.append(dict(name="Cunha", poly=wp, engrave=[], places=places))


def build_chao():
    m = Model("chao", "Expositor de chão", W_in=520, D=380, H=1500)
    yb, ys = 80, 600
    m.shelf("Fundo do cesto (pelúcias)", yb, 10, 350, [(60, 140), (230, 310)])
    m.vpanel("Frente do cesto", yb + T, 180, 335, [(40, 140)])
    m.vpanel("Costas", yb + T, ys - yb - T, 25, [(60, 180), (325, 445)])
    m.shelf("Prateleira mantas", ys, 10, 350, [(60, 140), (230, 310)])
    m.vpanel("Travessa bandanas", 1020, 80, 320, [(15, 65)])
    m.vpanel("Travessa gravatas", 1300, 80, 320, [(15, 65)], notches=True)
    m.header(Wh=610, Hh=380, zh=30, a=150, b=150, text_h=95)
    m.lateral([(0,0), (380,0), (380,1500), (0,1500)], (70, 310, 30), (190, 830, 230, 75))
    m.add_wedges()
    m.anchors.update(bin=dict(y=yb+T, z0=10, z1=335, top=yb+T+180), shelf=dict(y=ys+T, z0=10, z1=350),
                     band=dict(y=1100, z=320+T/2), grav=dict(y=1380, z=320+T/2))
    import random; random.seed(7)
    pr = []
    for k in range(26):
        pr.append(dict(t="bone", x=random.uniform(-200, 200), y=yb + T + 25 + (k // 9)*38, z=random.uniform(60, 300),
                       r=random.uniform(0, 3.14), s=random.choice([0.9, 1.1, 1.3])))
    for xx in (-130, 130):
        for k in range(4):
            pr.append(dict(t="manta", x=xx, y=ys + T + k*45, z=180, w=230, h=42, d=260))
    for k in range(6):
        pr.append(dict(t="bandana", x=-200 + k*80, y=1100, z=320 + T/2))
    n = int(520 // 45)
    for k in range(0, n, 2):
        pr.append(dict(t="gravata", x=-(n - 1)*45/2 + k*45, y=1380 - 14, z=320 + T/2))
    m.products = pr
    m.pivot = None
    m.closed_dims = m.open_dims = dict(L=520 + 2*TAB, P=380, A=1580)
    return m

def tabs(lo, hi, n):
    s = (hi - lo) / (2*n + 1)
    return [(lo + s*(2*i+1), lo + s*(2*i+2)) for i in range(n)]

def U(lst, extra=()):
    return unary_union(list(lst) + list(extra))

def build_maleta():
    """Bancada estilo baú: corpo (caixa aberta na frente) + porta-caixa articulada."""
    m = Model("bau", "Bancada baú", W_in=440 - 2*T, D=250, H=460)
    W, H, D, dd, t = 440.0, 460.0, 250.0, 130.0, TOL/2
    ys, zs, zdiv = 230.0, 210.0, 210.0          # prateleira, frente baixa, fim da divisória
    m.Wtot = W; m.kind = "maleta"
    X, Y, Z = (1,0,0), (0,1,0), (0,0,1)
    P = m.parts
    tz = tabs(T + 10, D - 10, 2)                 # topo/base -> laterais
    by = tabs(T, H - T, 3)                       # fundo -> laterais
    bx = tabs(T, W - T, 3)                       # fundo -> topo/base
    shz = [(50, 110), (155, 215)]                # prateleira -> laterais
    dvz = [(50, 110), (140, 195)]                # divisória -> base e prateleira
    stv = [(15, 55)]                             # frente baixa (altura 70)
    hs = 70.0
    # --- lateral do corpo
    side = box(0, 0, D, H)
    cuts = [box(a - t, H - T - t, b + t, H + 1) for a, b in tz] + \
           [box(a - t, -1, b + t, T + t) for a, b in tz] + \
           [box(-1, a - t, T + t, b + t) for a, b in by] + \
           [box(a - t, ys - t, b + t, ys + T + t) for a, b in shz] + \
           [box(zs - t, T + a - t, zs + T + t, T + b + t) for a, b in stv]
    handle = box(D/2 - 55, H - 75, D/2 + 55, H - 45).buffer(0)
    handle = box(D/2 - 40, H - 75, D/2 + 40, H - 45).union(Point(D/2 - 40, H - 60).buffer(15, 16)).union(Point(D/2 + 40, H - 60).buffer(15, 16))
    P.append(dict(name="Lateral corpo (com alça)", poly=side.difference(U(cuts + [handle])), engrave=[],
                  places=[((-W/2, 0, 0), Z, Y, X), ((W/2 - T, 0, 0), Z, Y, X)]))
    # --- topo e base
    def topbase(is_base):
        p = U([box(T, 0, W - T, D)] + [box(0, a, T, b) for a, b in tz] + [box(W - T, a, W, b) for a, b in tz])
        c = [box(a - t, -1, b + t, T + t) for a, b in bx]
        if is_base:
            c += [box(W/2 - T/2 - t, a - t, W/2 + T/2 + t, b + t) for a, b in dvz]
        return p.difference(U(c))
    P.append(dict(name="Topo corpo", poly=topbase(False),
                  engrave=[dict(text="ZAMBO", x=W/2, y=D/2 + 10, h=60, face=1, flip=True)],
                  places=[((-W/2, H - T, 0), X, Z, Y)]))
    P.append(dict(name="Base corpo", poly=topbase(True), engrave=[], places=[((-W/2, 0, 0), X, Z, Y)]))
    # --- fundo
    back = U([box(T, T, W - T, H - T)] + [box(0, a, T, b) for a, b in by] + [box(W - T, a, W, b) for a, b in by] +
             [box(a, 0, b, T) for a, b in bx] + [box(a, H - T, b, H) for a, b in bx])
    P.append(dict(name="Fundo corpo", poly=back, engrave=[], places=[((-W/2, 0, 0), X, Y, Z)]))
    # --- prateleira (mantas em cima)
    shelf = U([box(T, T, W - T, D - 15)] + [box(0, a, T, b) for a, b in shz] + [box(W - T, a, W, b) for a, b in shz])
    shelf = shelf.difference(U([box(W/2 - T/2 - t, a - t, W/2 + T/2 + t, b + t) for a, b in dvz]))
    P.append(dict(name="Prateleira corpo", poly=shelf, engrave=[], places=[((-W/2, ys, 0), X, Z, Y)]))
    # --- divisória dos nichos de baixo (pelúcias)
    div = U([box(T, T, zdiv, ys)] + [box(a, 0, b, T) for a, b in dvz] + [box(a, ys, b, ys + T) for a, b in dvz])
    P.append(dict(name="Divisória nichos", poly=div, engrave=[], places=[((-T/2, 0, 0), Z, Y, X)]))
    # --- frente baixa (segura as pelúcias)
    strip = U([box(T, 0, W - T, hs)] + [box(0, a, T, b) for a, b in stv] + [box(W - T, a, W, b) for a, b in stv])
    P.append(dict(name="Frente baixa nichos", poly=strip, engrave=[], places=[((-W/2, T, zs), X, Y, Z)]))
    # divisória recebe a frente baixa: rasgo de cima pra baixo? -> divisória termina em zdiv; frente encosta. ok.

    # ===== PORTA-CAIXA (coords com a maleta fechada) =====
    fy = tabs(T, H - T, 3)           # aros laterais -> frente
    fx = tabs(T, W - T, 3)           # aros topo/base -> frente
    rz = tabs(0, dd - T, 1)          # aros topo/base -> aros laterais
    tv1, tv2 = (H - 110, 45.0), (175.0, 45.0)   # travessas: (y0, altura)
    zt = D + 25                      # travessas a 25mm da borda aberta
    tvt = [(10, 35)]
    fp = box(0, 0, W, H)
    fpc = [box(-1, a - t, T + t, b + t) for a, b in fy] + [box(W - T - t, a - t, W + 1, b + t) for a, b in fy] + \
          [box(a - t, -1, b + t, T + t) for a, b in fx] + [box(a - t, H - T - t, b + t, H + 1) for a, b in fx]
    P.append(dict(name="Frente porta (logo)", poly=fp.difference(U(fpc)), group="door",
                  engrave=[dict(text="ZAMBO", x=W/2, y=H/2, h=85)],
                  places=[((-W/2, 0, D + dd - T), X, Y, Z)]))
    rim = U([box(0, 0, dd - T, H)] + [box(dd - T, a, dd, b) for a, b in fy])
    rc = [box(a - t, -1, b + t, T + t) for a, b in rz] + [box(a - t, H - T - t, b + t, H + 1) for a, b in rz]
    for y0, h in (tv1, tv2):
        rc += [box(zt - D - t, y0 + a - t, zt - D + T + t, y0 + b + t) for a, b in tvt]
    P.append(dict(name="Aro lateral porta", poly=rim.difference(U(rc)), group="door", engrave=[],
                  places=[((-W/2, 0, D), Z, Y, X), ((W/2 - T, 0, D), Z, Y, X)]))
    rtb = U([box(T, 0, W - T, dd - T)] + [box(0, a, T, b) for a, b in rz] + [box(W - T, a, W, b) for a, b in rz] +
            [box(a, dd - T, b, dd) for a, b in fx])
    P.append(dict(name="Aro topo/base porta", poly=rtb, group="door", engrave=[],
                  places=[((-W/2, H - T, D), X, Z, Y), ((-W/2, 0, D), X, Z, Y)]))
    for nm, (y0, h), notch in (("Travessa bandanas (porta)", tv1, False), ("Travessa gravatas (porta)", tv2, True)):
        p = U([box(T, 0, W - T, h)] + [box(0, a, T, b) for a, b in tvt] + [box(W - T, a, W, b) for a, b in tvt])
        if notch:
            n = int((W - 2*T - 30) // 45); off = W/2 - (n - 1)*45/2
            p = p.difference(U([box(off + i*45 - 5, h - 14, off + i*45 + 5, h + 1).union(Point(off + i*45, h - 14).buffer(5, 16)) for i in range(n)]))
        P.append(dict(name=nm, poly=p, group="door", engrave=[], places=[((-W/2, y0, zt), X, Y, Z)]))
    m.anchors = dict(kind="maleta", W=W, H=H, D=D, dd=dd, ys=ys, T=T, zs=zs, hs=hs,
                     hinge=dict(x=W/2, z=D), band=dict(y=tv1[0] + tv1[1], z=zt + T/2),
                     grav=dict(y=tv2[0] + tv2[1], z=zt + T/2),
                     logo=dict(x=0, y=H/2, z=D + dd, w=W, h=85))
    m.header_slot = None
    m.pivot = dict(axis="y", p=[W/2, 0, D], open=170, closed=0)
    import random; random.seed(5)
    pr = []
    for sx in (-1, 1):
        for k in range(6):
            pr.append(dict(t="bone", x=sx*random.uniform(40, 160), y=T + 25 + (k // 3)*35, z=random.uniform(50, 180),
                           r=random.uniform(0, 3.14), s=random.choice([0.8, 1.0])))
    for xx in (-105, 105):
        for k in range(4):
            pr.append(dict(t="manta", x=xx, y=ys + T + k*40, z=130, w=170, h=38, d=180))
    for k in range(5):
        pr.append(dict(t="bandana", x=-160 + k*80, y=tv1[0] + tv1[1], z=zt + T/2, g="mov"))
    n = int((W - 2*T - 30) // 45)
    for k in range(0, n, 2):
        pr.append(dict(t="gravata", x=-(n - 1)*45/2 + k*45, y=tv2[0] + tv2[1] - 14, z=zt + T/2, g="mov"))
    m.products = pr
    m.closed_dims = dict(L=W, P=D + dd, A=H); m.open_dims = dict(L=2*W, P=D + dd, A=H)
    return m


def build_escada():
    """Bancada escada: corpo trapezoidal (bandeja + degrau) e tampa que vira 180° e forma mais um andar.
    Geometria em posição ABERTA. Fechada vira caixa D x Hb."""
    W, D, Dt, hl, Hb, t = 460.0, 360.0, 180.0, 100.0, 360.0, TOL/2
    L = Hb - hl
    m = Model("escada", "Bancada escada", W_in=W - 2*T, D=D, H=Hb)
    m.Wtot = W; m.kind = "escada"
    X, Y, Z = (1,0,0), (0,1,0), (0,0,1)
    P = m.parts
    ysh, zsh = 200.0, 235.0
    tzb = tabs(T + 10, D - 10, 2); tzt = tabs(T + 10, Dt - 10, 2)
    by = tabs(T, Hb - T, 3); bx = tabs(T, W - T, 3)
    shz = [(40, 100), (150, 210)]
    lip_z, lip_y0, lip_h, lipv = 320.0, T, 85.0, [(15, 60)]
    side = Polygon([(0, 0), (D, 0), (D, hl), (Dt, Hb), (0, Hb)])
    hd = box(55, 268, 125, 296).union(Point(55, 282).buffer(14, 16)).union(Point(125, 282).buffer(14, 16))
    cuts = [box(a - t, Hb - T - t, b + t, Hb + 1) for a, b in tzt] + \
           [box(a - t, -1, b + t, T + t) for a, b in tzb] + \
           [box(-1, a - t, T + t, b + t) for a, b in by] + \
           [box(a - t, ysh - t, b + t, ysh + T + t) for a, b in shz] + \
           [box(lip_z - t, lip_y0 + a - t, lip_z + T + t, lip_y0 + b + t) for a, b in lipv] + [hd]
    P.append(dict(name="Lateral corpo (com alça)", poly=side.difference(U(cuts)), engrave=[],
                  places=[((-W/2, 0, 0), Z, Y, X), ((W/2 - T, 0, 0), Z, Y, X)]))
    def plate(z1, tz, notch=True):
        p = U([box(T, 0, W - T, z1)] + [box(0, a, T, b) for a, b in tz] + [box(W - T, a, W, b) for a, b in tz])
        return p.difference(U([box(a - t, -1, b + t, T + t) for a, b in bx])) if notch else p
    P.append(dict(name="Base corpo", poly=plate(D, tzb), engrave=[], places=[((-W/2, 0, 0), X, Z, Y)]))
    P.append(dict(name="Topo corpo", poly=plate(Dt, tzt), engrave=[], places=[((-W/2, Hb - T, 0), X, Z, Y)]))
    back = U([box(T, T, W - T, Hb - T)] + [box(0, a, T, b) for a, b in by] + [box(W - T, a, W, b) for a, b in by] +
             [box(a, 0, b, T) for a, b in bx] + [box(a, Hb - T, b, Hb) for a, b in bx])
    P.append(dict(name="Fundo corpo", poly=back, engrave=[], places=[((-W/2, 0, 0), X, Y, Z)]))
    sh = U([box(T, T, W - T, zsh)] + [box(0, a, T, b) for a, b in shz] + [box(W - T, a, W, b) for a, b in shz])
    P.append(dict(name="Degrau (mantas)", poly=sh, engrave=[], places=[((-W/2, ysh, 0), X, Z, Y)]))
    lip = U([box(T, 0, W - T, lip_h)] + [box(0, a, T, b) for a, b in lipv] + [box(W - T, a, W, b) for a, b in lipv])
    P.append(dict(name="Frente bandeja (logo)", poly=lip, engrave=[dict(text="ZAMBO", x=W/2, y=lip_h/2, h=48)],
                  places=[((-W/2, lip_y0, lip_z), X, Y, Z)]))
    # ===== TAMPA (aberta, apoiada sobre o topo) =====
    fz = tabs(T + 5, Dt - 30, 2); wy = tabs(T, L - 70, 2)
    tb = (100.0, 40.0, 45.0); tg = (25.0, 40.0, 95.0)       # (v0, altura, z)
    tvt = [(10, 30)]
    lside = Polygon([(0, 0), (Dt, 0), (0, L)])
    lc = [box(a - t, -1, b + t, T + t) for a, b in fz] + [box(-1, a - t, T + t, b + t) for a, b in wy]
    for v0, h, zz in (tb, tg):
        lc += [box(zz - t, v0 + a - t, zz + T + t, v0 + b + t) for a, b in tvt]
    P.append(dict(name="Lateral tampa", poly=lside.difference(U(lc)), group="mov", engrave=[],
                  places=[((-W/2, Hb, 0), Z, Y, X), ((W/2 - T, Hb, 0), Z, Y, X)]))
    fl = U([box(T, 0, W - T, Dt)] + [box(0, a, T, b) for a, b in fz] + [box(W - T, a, W, b) for a, b in fz])
    wx = tabs(T, W - T, 3)
    fl = fl.difference(U([box(a - t, -1, b + t, T + t) for a, b in wx]))
    P.append(dict(name="Piso tampa", poly=fl, group="mov", engrave=[], places=[((-W/2, Hb, 0), X, Z, Y)]))
    wall = U([box(T, T, W - T, L)] + [box(0, a, T, b) for a, b in wy] + [box(W - T, a, W, b) for a, b in wy] +
             [box(a, 0, b, T) for a, b in wx])
    P.append(dict(name="Parede tampa (logo fechada)", poly=wall, group="mov",
                  engrave=[dict(text="ZAMBO", x=W/2, y=L/2 + 10, h=80, face=0, flip=True)], places=[((-W/2, Hb, 0), X, Y, Z)]))
    for nm, (v0, h, zz), notch in (("Travessa bandanas (tampa)", tb, False), ("Travessa gravatas (tampa)", tg, True)):
        p = U([box(T, 0, W - T, h)] + [box(0, a, T, b) for a, b in tvt] + [box(W - T, a, W, b) for a, b in tvt])
        if notch:
            n = int((W - 2*T - 30) // 45); off = W/2 - (n - 1)*45/2
            p = p.difference(U([box(off + i*45 - 5, h - 14, off + i*45 + 5, h + 1).union(Point(off + i*45, h - 14).buffer(5, 16)) for i in range(n)]))
        P.append(dict(name=nm, poly=p, group="mov", engrave=[], places=[((-W/2, Hb + v0, zz), X, Y, Z)]))
    m.pivot = dict(axis="x", p=[0, Hb, Dt], open=0, closed=180)
    m.header_slot = None
    # produtos
    pr = []
    import random; random.seed(3)
    for i in range(14):
        pr.append(dict(t="bone", x=random.uniform(-180, 180), y=T + 25 + (i // 7)*35, z=random.uniform(60, 300),
                       r=random.uniform(0, 3.14), s=random.choice([0.8, 1.0, 1.2])))
    for i, xx in enumerate((-120, 0, 120)):
        for k in range(2):
            pr.append(dict(t="manta", x=xx, y=ysh + T + k*32, z=150, w=110, h=30, d=150))
    for i in range(5):
        pr.append(dict(t="bandana", x=-160 + i*80, y=Hb + tb[0] + tb[1], z=tb[2] + T/2, g="mov"))
    n = int((W - 2*T - 30) // 45)
    for i in range(0, n, 2):
        pr.append(dict(t="gravata", x=-(n - 1)*45/2 + i*45, y=Hb + tg[0] + tg[1] - 14, z=tg[2] + T/2, g="mov"))
    m.products = pr
    m.closed_dims = dict(L=W, P=D, A=Hb); m.open_dims = dict(L=W, P=D, A=Hb + L)
    return m

MODELS = [build_chao(), build_escada(), build_maleta()]

DOGBONE_R = 3.25   # fresa de 6mm (raio 3mm + folga). Mude se a fresa for outra.
from shapely.geometry.polygon import orient
def dogbone(poly, r=DOGBONE_R):
    poly = orient(poly, 1.0)
    circles = []
    for ring in [poly.exterior] + list(poly.interiors):
        pts = list(ring.coords)[:-1]; n = len(pts)
        for i in range(n):
            px, py = pts[i-1]; vx, vy = pts[i]; nx, ny = pts[(i+1) % n]
            e1 = (vx-px, vy-py); e2 = (nx-vx, ny-vy)
            l1, l2 = math.hypot(*e1), math.hypot(*e2)
            if l1 < 1 or l2 < 1: continue
            u1 = (e1[0]/l1, e1[1]/l1); u2 = (e2[0]/l2, e2[1]/l2)
            cross = u1[0]*u2[1] - u1[1]*u2[0]; dot = u1[0]*u2[0] + u1[1]*u2[1]
            if cross < -0.9 and abs(dot) < 0.15:
                d = (u2[0]-u1[0], u2[1]-u1[1]); L = math.hypot(*d); d = (d[0]/L, d[1]/L)
                if poly.contains(Point(vx + 0.6*d[0], vy + 0.6*d[1])): d = (-d[0], -d[1])
                circles.append(Point(vx + r*d[0], vy + r*d[1]).buffer(r, 16))
    return poly.difference(unary_union(circles)) if circles else poly

for m in MODELS:
    for p in m.parts:
        if p["name"] != "Cunha":
            p["poly"] = dogbone(p["poly"])

# ---------- checagens ----------
for m in MODELS:
    if getattr(m, "kind", "") in ("maleta", "escada"):
        for p in m.parts:
            assert p["poly"].is_valid and p["poly"].geom_type == "Polygon", (p["name"], p["poly"].geom_type)
        continue
    lat = m.parts[0]["poly"]
    assert lat.is_valid and lat.geom_type == "Polygon", (m.key, lat.geom_type)
    for mt in m.mortises + [m.header_slot]:
        ring = Polygon(lat.exterior).buffer(0)
        # material minimo entre furo e borda
        d = Polygon(lat.exterior).exterior.distance(mt)
        if mt is not m.header_slot and d < 20:
            print("ATENCAO borda fina", m.key, round(d, 1))
    for p in m.parts:
        assert p["poly"].is_valid, p["name"]

# ---------- nesting simples (prateleiras) ----------
def nest(items, sheet=SHEET, margin=12, gap=14):
    W, H = sheet
    # item: (label, poly) -> deita a peca no maior lado
    prepared = []
    for label, poly in items:
        minx, miny, maxx, maxy = poly.bounds
        w, h = maxx - minx, maxy - miny
        if h > w:
            poly = affinity.rotate(poly, 90, origin=(0, 0))
        minx, miny, maxx, maxy = poly.bounds
        poly = affinity.translate(poly, -minx, -miny)
        prepared.append((label, poly, maxx - minx, maxy - miny))
    prepared.sort(key=lambda t: (-t[3], -t[2]))
    sheets, shelves = [[]], [[]]
    def place(sheet_i, label, poly, w, h):
        sh = shelves[sheet_i]
        for s in sh:   # s: [y, height, x_cursor]
            if h <= s[1] and s[2] + w <= W - margin:
                sheets[sheet_i].append((label, affinity.translate(poly, s[2], s[0]), poly))
                s[2] += w + gap; return True
        y = (sh[-1][0] + sh[-1][1] + gap) if sh else margin
        if y + h <= H - margin and margin + w <= W - margin:
            sh.append([y, h, margin + w + gap])
            sheets[sheet_i].append((label, affinity.translate(poly, margin, y), poly))
            return True
        return False
    for label, poly, w, h in prepared:
        # pecas pequenas tentam preencher sobras de prateleiras ja abertas
        done = False
        for i in range(len(sheets)):
            if place(i, label, poly, w, h): done = True; break
        if not done:
            sheets.append([]); shelves.append([])
            assert place(len(sheets)-1, label, poly, w, h)
    return sheets

def expand(m):
    out = []
    for p in m.parts:
        for i, _ in enumerate(p["places"]):
            out.append((f'{m.key.upper()} - {p["name"]}', p))
    return out

def write_dxf(path, sheets):
    doc = ezdxf.new("R2010"); doc.units = ezdxf.units.MM
    doc.layers.add("CORTE_INTERNO", color=5)
    doc.layers.add("CORTE_EXTERNO", color=1)
    doc.layers.add("GRAVACAO", color=3)
    doc.layers.add("CHAPA_NAO_CORTAR", color=8)
    doc.layers.add("ETIQUETAS_NAO_CORTAR", color=8)
    msp = doc.modelspace()
    for si, sheet in enumerate(sheets):
        ox = si * (SHEET[0] + 300)
        msp.add_lwpolyline([(ox,0),(ox+SHEET[0],0),(ox+SHEET[0],SHEET[1]),(ox,SHEET[1])], close=True,
                           dxfattribs={"layer": "CHAPA_NAO_CORTAR"})
        for label, placed, part in sheet:
            pl = affinity.translate(placed, ox, 0)
            msp.add_lwpolyline(list(pl.exterior.coords), close=True, dxfattribs={"layer": "CORTE_EXTERNO"})
            for r in pl.interiors:
                msp.add_lwpolyline(list(r.coords), close=True, dxfattribs={"layer": "CORTE_INTERNO"})
            c = pl.representative_point()
            msp.add_text(label, height=14, dxfattribs={"layer": "ETIQUETAS_NAO_CORTAR"}).set_placement((c.x, c.y))
            # gravacao: transforma do local da peca para a posicao na chapa
            if part["engrave"]:
                e = part["engrave"][0]
                # mesma transformacao aplicada ao poligono: descobre por bounds
                minx0, miny0, maxx0, maxy0 = part["poly"].bounds
                minx1, miny1, maxx1, maxy1 = pl.bounds
                if abs((maxx1-minx1) - (maxx0-minx0)) < 0.5:
                    tx, ty, rot = minx1 + e["x"] - minx0, miny1 + e["y"] - miny0, 0
                else:
                    tx, ty, rot = maxx1 - (e["y"] - miny0), miny1 + (e["x"] - minx0), 90
                msp.add_text(e["text"], height=e["h"], rotation=rot,
                             dxfattribs={"layer": "GRAVACAO", "style": "Standard"}).set_placement(
                             (tx, ty), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    doc.saveas(path)

OUT = "/home/claude/zambo/"
all_items, report = [], {}
for m in MODELS:
    items = [(lab, p) for lab, p in expand(m)]
    sheets = nest([(lab, p["poly"]) for lab, p in items])
    # reanexa a peca original para gravacao
    lookup = iter(items)
    s2 = [[(l, pl, next(p for lb, p in items if lb == l)) for (l, pl, _) in s] for s in sheets]
    write_dxf(OUT + f"expositor_{m.key}_corte.dxf", s2)
    report[m.key] = len(sheets)
    all_items += items

combos = {}
for combo in (("chao", "escada"), ("chao", "bau")):
    its = [(l, p) for l, p in all_items if l.split(" - ")[0].lower() in combo]
    sh = nest([(lab, p["poly"]) for lab, p in its])
    s2 = [[(l, pl, next(p for lb, p in its if lb == l)) for (l, pl, _) in s] for s in sh]
    write_dxf(OUT + f"chapa_unica_{combo[0]}_{combo[1]}.dxf", s2)
    used = sum(pl.area for s in sh for _, pl, _ in s)
    combos["_".join(combo)] = (s2, len(sh), round(100*used/(SHEET[0]*SHEET[1]*len(sh)), 1))
report["combos"] = {k: dict(chapas=v[1], aproveitamento=v[2]) for k, v in combos.items()}
print("chapas:", report)
# ---------- SVG do plano de corte ----------
def svg_sheet(sheet):
    W, H = SHEET
    out = [f'<svg viewBox="-10 -10 {W+20} {H+20}" xmlns="http://www.w3.org/2000/svg" class="sheet">',
           f'<rect x="0" y="0" width="{W}" height="{H}" class="chapa"/>']
    for label, pl, part in sheet:
        def path(poly):
            d = ""
            for ring in [poly.exterior] + list(poly.interiors):
                cs = list(ring.coords)
                d += "M" + " L".join(f"{x:.1f},{H-y:.1f}" for x, y in cs) + " Z "
            return d
        cls = label.split(" - ")[0].lower()
        out.append(f'<path d="{path(pl)}" class="peca {cls}" fill-rule="evenodd"><title>{label}</title></path>')
    out.append("</svg>")
    return "\n".join(out)
for k, v in combos.items(): open(OUT + f"plano_{k}.svg", "w").write(svg_sheet(v[0][0]))

# ---------- JSON 3D ----------
def poly_js(p):
    return dict(o=[[round(x,2), round(y,2)] for x, y in p.exterior.coords[:-1]],
                h=[[[round(x,2), round(y,2)] for x, y in r.coords[:-1]] for r in p.interiors])
data, bom = {}, []
for m in MODELS:
    parts = []
    for p in m.parts:
        minx, miny, maxx, maxy = p["poly"].bounds
        eng = []
        for e in p["engrave"]:
            for (o, Uu, Vv, Ww) in p["places"]:
                f = e.get("face", 1); s = -1 if e.get("flip") else 1
                c = [o[k] + Uu[k]*e["x"] + Vv[k]*e["y"] + Ww[k]*(f*T + (0.6 if f else -0.6)) for k in range(3)]
                eng.append(dict(c=c, n=[Ww[k]*(1 if f else -1) for k in range(3)], up=[Vv[k]*s for k in range(3)], h=e["h"], g=p.get("group")))
        parts.append(dict(name=p["name"], shape=poly_js(p["poly"]), places=p["places"], g=p.get("group"), eng=eng))
        bom.append(dict(modelo=m.key, peca=p["name"], qtd=len(p["places"]), dim=f"{maxx-minx:.0f} × {maxy-miny:.0f}"))
    area = sum(p["poly"].area*len(p["places"]) for p in m.parts)/1e6
    data[m.key] = dict(nome=m.nome, parts=parts, products=m.products, pivot=m.pivot,
                       area_m2=round(area, 2), peso_kg=round(area*0.015*720, 1),
                       pecas=sum(len(p["places"]) for p in m.parts),
                       fechado=m.closed_dims, aberto=m.open_dims, chapas=report[m.key])
json.dump(dict(models=data, bom=bom, report=report), open(OUT + "modelo.json", "w"))
for b in bom: print(b)
for k, v in data.items(): print(k, v["area_m2"], "m2", v["peso_kg"], "kg", v["pecas"], "pecas", v["chapas"], "chapa(s)")
