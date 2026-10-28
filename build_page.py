import json, base64
V = json.load(open("logo/logo_vec.json"))
logos = json.dumps({k: dict(aspect=V[k]["aspect"], src="data:image/png;base64," + base64.b64encode(open(f"logo/{k}_tex.png","rb").read()).decode()) for k in ("principal", "selo")})
t = open("template_maletas.html").read()
t = t.replace("__DATASETS__", "{\"6\":" + open("maletas/maletas_6mm.json").read() + ",\"8\":" + open("maletas/maletas_8mm.json").read() + "}").replace("__BONE__", open("maletas/bone.json").read()).replace("__LOGOS__", logos)
open("maletas-zambo.html", "w").write(t); print(len(t))
