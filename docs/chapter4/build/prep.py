"""Collect the chapter's figures in document order, number them, and record their pixel sizes."""
import json, os, shutil, sys
from PIL import Image

REPO = r"W:/Disk E/Collage/5/مشروع التخرج/Smart-Facilities-Monitor-System"
SRC = REPO + "/docs/chapter4/chapter4-source.txt"
SEARCH = [REPO + "/docs/chapter3-data/figures",
          REPO + "/Diagrams/AI/ModelsPipeline/FireAndSmoke",
          REPO + "/Diagrams/AI/ModelsPipeline/Intrusion",
          REPO + "/Diagrams/AI/ModelsPipeline/ANPR"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT)

manifest, n = {}, 0
for line in open(SRC, encoding="utf8"):
    if not line.startswith("@fig "):
        continue
    key, name, caption, width = [p.strip() for p in line[5:].split("|")]
    path = next(os.path.join(d, name) for d in SEARCH if os.path.exists(os.path.join(d, name)))
    n += 1
    stem, ext = os.path.splitext(name)
    dest = f"Figure_4.{n:02d}_{stem}{ext.lower()}"
    shutil.copy(path, os.path.join(OUT, dest))
    w, h = Image.open(path).size
    manifest[key] = dict(num=n, file=dest, w=w, h=h, width_cm=float(width), caption=caption, source=path)
json.dump(manifest, open(os.path.join(os.path.dirname(OUT), "manifest.json"), "w", encoding="utf8"),
          ensure_ascii=False, indent=1)
print(n, "figures")
