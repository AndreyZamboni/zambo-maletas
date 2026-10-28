# Maletas-mostruário Zambo

Display de balcão em formato de mala para levar o mostruário da Zambo (cobertas, bandanas, gravatas e pelúcias) até lojas e empresas. MDF cru de 6 ou 8 mm, cortado a laser, montado só por encaixe de meia-madeira (rasgo), sem cola e sem parafuso na estrutura.

## Online
O site publicado na Vercel abre o `index.html` (cópia da página de `entrega/`).

## Arquivos para usar
- `entrega/Maletas-Zambo.html`: página completa (3D, disposição dos produtos, peças, montagem e plano de corte), pronta para enviar.
- `maletas/maleta_B_escada_corte_6mm.dxf` e `_8mm.dxf`: corte a laser da Maleta Escada (a recomendada), mesa de 1300 × 900 mm.
- `maletas/maleta_A_vitrine_corte_*.dxf` e `maletas/maleta_C_bau_corte_*.dxf`: as outras duas maletas.
- `renders/`: imagens das vistas.

Camadas dos DXF: `CORTE_INTERNO` (cortar primeiro), `CORTE_EXTERNO`, `GRAVACAO` e `GRAVACAO_VERSO` (gravar com a peça virada).

## Gerar de novo
```
pip install shapely ezdxf numpy trimesh manifold3d
MALETA_T=6 python3 export_maletas.py   # ou MALETA_T=8
MALETA_T=8 python3 export_maletas.py
python3 build_page.py                  # monta maletas-zambo.html
MALETA_T=6 python3 check_maletas.py    # confere colisões aberta e fechada
```
`maletas.py` tem a geometria das três maletas; `logo/` tem os logos vetorizados.

Os arquivos `expositor_*`, `chapa_unica_*`, `projeto.py` e `expositores-zambo.html` são a primeira versão (expositores de chão e bancada em MDF 15 mm).
