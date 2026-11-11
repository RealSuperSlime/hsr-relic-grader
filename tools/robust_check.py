import os, tempfile
from PIL import Image
from relic_grades.ocr import parse_relic_image
SRC = r"C:/Users/RealS/AppData/Local/hermes/cache/documents/native-inputs/0d1b9320b77fbc13f03226d04780f71099f6ffa7b2e722d48f70ac0ac49153cf/dashboard_20261111_094029_d890ec43_image_243760.png"
base = Image.open(SRC).convert('RGB')
for scale, ext in ((0.75, 'png'), (1.0, 'jpg'), (1.5, 'png'), (2.0, 'jpg'), (2.5, 'png')):
    im = base.resize((int(base.width*scale), int(base.height*scale)), Image.LANCZOS)
    p = os.path.join(tempfile.gettempdir(), f'rob_{scale}.{ext}')
    im.save(p, quality=92)
    r = parse_relic_image(p)
    print(f"scale={scale} {ext}: part={r['part']} set={bool(r['set'])} main={r['mainStat']} "
          f"{r['mainValue']} lvl={r['level']} grade={r['grade']} "
          f"subs={[(s['stat'], s['value']) for s in r['substats']]} warn={r['warnings']}")
