#!/usr/bin/env python3
import base64, os, sys

W = "/Users/apple/SeedIQ/.iconwork"

def b64(name):
    with open(os.path.join(W, name), "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

items = sys.argv[1:]  # list of "path:label"

parts = []
parts.append("""<!doctype html><html><head><meta charset="utf-8"><title>SeedIQ workbench</title><style>
body{background:#1b1b1b;color:#eee;font:13px/1.45 -apple-system,Helvetica,Arial;margin:0;padding:16px}
.grid{display:flex;flex-wrap:wrap;gap:18px;align-items:flex-start}
.cell{background:#2a2a2a;padding:10px;border-radius:8px;text-align:center;max-width:340px}
.cell img{display:block;margin:0 auto 6px}
.cap{font-size:11px;color:#9a9;word-break:break-all}
.bg-light{background:#FEFAE0;padding:8px;border-radius:6px;display:inline-block}
.bg-dark{background:#060606;padding:8px;border-radius:6px;display:inline-block}
.bg-white{background:#ffffff;padding:8px;border-radius:6px;display:inline-block}
h3{margin:20px 0 8px;font-size:13px;color:#8fd}
.mask{width:132px;height:132px;border-radius:50%;overflow:hidden}
.mask img{width:100%;height:100%;object-fit:cover;display:block}
.sq{width:132px;height:132px;border-radius:30% / 30%;overflow:hidden}
.sq img{width:100%;height:100%;object-fit:cover;display:block}
</style></head><body>""")

for it in items:
    path, label = it.split("::")
    data = b64(path)
    parts.append('<h3>%s</h3><div class="grid">' % label)
    for cls in ("bg-light", "bg-dark", "bg-white"):
        parts.append('<div class="cell"><div class="%s"><img src="%s" width="220"></div><div class="cap">%s</div></div>' % (cls, data, cls))
    # masked variants
    parts.append('<div class="cell"><div class="mask"><img src="%s"></div><div class="cap">circle mask</div></div>' % data)
    parts.append('<div class="cell"><div class="sq"><img src="%s"></div><div class="cap">squircle mask</div></div>' % data)
    parts.append('</div>')

parts.append("</body></html>")
out = os.path.join(W, "preview.html")
with open(out, "w") as f:
    f.write("\n".join(parts))
print("wrote", out, os.path.getsize(out), "bytes")
