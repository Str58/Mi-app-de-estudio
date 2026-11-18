#!/usr/bin/env python3
"""zonas.py - prepara el boceto para leerlo rapido y sin errores.

Uso: python3 zonas.py boceto.jpg carpeta_salida [filas columnas]   (por defecto 2 2)
Genera en la carpeta:
  completo.jpg        imagen entera reducida (vision de conjunto)
  zona_F_C.jpg        recortes ampliados x2 con 12 % de solape y contraste realzado
  cotas_rojas.png     solo los trazos rojos (cotas) sobre blanco, para leer numeros sin ruido
"""
import os, sys
from PIL import Image, ImageOps, ImageEnhance

src, out = sys.argv[1], sys.argv[2]
F, C = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (2, 2)
os.makedirs(out, exist_ok=True)
im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
W, H = im.size
c = im.copy(); c.thumbnail((1600, 1600)); c.save(os.path.join(out, "completo.jpg"), quality=88)
sx, sy = W / C, H / F
for f in range(F):
    for k in range(C):
        x0, y0 = max(0, int(k * sx - 0.12 * sx)), max(0, int(f * sy - 0.12 * sy))
        x1, y1 = min(W, int((k + 1) * sx + 0.12 * sx)), min(H, int((f + 1) * sy + 0.12 * sy))
        z = im.crop((x0, y0, x1, y1))
        esc = min(2.0, 1800 / max(z.size))
        z = z.resize((int(z.width * esc), int(z.height * esc)), Image.LANCZOS)
        z = ImageEnhance.Contrast(ImageOps.autocontrast(z, cutoff=1)).enhance(1.3)
        z.save(os.path.join(out, f"zona_{f + 1}_{k + 1}.jpg"), quality=90)
hsv = im.convert("HSV")
h, s, v = hsv.split()
mask = Image.eval(h, lambda p: 255 if (p < 14 or p > 235) else 0)
mask = Image.composite(mask, Image.new("L", im.size, 0), Image.eval(s, lambda p: 255 if p > 70 else 0))
mask = Image.composite(mask, Image.new("L", im.size, 0), Image.eval(v, lambda p: 255 if p > 60 else 0))
rojo = Image.new("RGB", im.size, "white"); rojo.paste((200, 0, 0), mask=mask)
rojo.thumbnail((2000, 2000)); rojo.save(os.path.join(out, "cotas_rojas.png"))
print("Generado en", out, ":", sorted(os.listdir(out)))
