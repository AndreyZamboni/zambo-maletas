import ezdxf, glob, os
for f in glob.glob("maletas/maleta_B_escada_corte_*mm.dxf"):
    doc = ezdxf.readfile(f)
    doc.layers.add("POSICAO_CARIMBO_NAO_CORTAR", color=8)
    n = 0
    for e in doc.modelspace():
        if e.dxf.layer in ("GRAVACAO", "GRAVACAO_VERSO"):
            e.dxf.layer = "POSICAO_CARIMBO_NAO_CORTAR"; n += 1
    for l in ("GRAVACAO", "GRAVACAO_VERSO"):
        if l in doc.layers: doc.layers.remove(l)
    out = f.replace("_corte_", "_corte_carimbo_")
    doc.saveas(out)
    layers = {}
    for e in ezdxf.readfile(out).modelspace(): layers[e.dxf.layer] = layers.get(e.dxf.layer, 0) + 1
    print(out, layers)
