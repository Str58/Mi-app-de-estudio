#!/usr/bin/env python3
"""zonas.py - prepara el boceto para leerlo rapido y sin errores.

Uso: python3 zonas.py boceto.jpg carpeta_salida [filas columnas]   (por defecto 2 2)

1. Recorta solo la zona dibujada (quita los margenes en blanco).
2. Genera en la carpeta:
   completo.jpg          dibujo entero con cuadricula de referencia A-J / 1-10
   zona_F_C.jpg          recortes ampliados (hasta x2) con 12 % de solape y contraste realzado
   cotas_rojas.png       solo los trazos rojos (cotas) sobre blanco
   cotas_rojas_giro_izq.png / _giro_der.png   lo mismo girado 90 grados: las cotas
                         verticales se leen en horizontal
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps

src, out = sys.argv[1], sys.argv[2]
F, C = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (2, 2)
os.makedirs(out, exist_ok=True)
im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")

# 1. recorte automatico de la zona con tinta (ignora motas sueltas)
# se guia por las paredes: filas/columnas con trazos negros largos (los textos sueltos no los tienen)
a = np.asarray(im.convert("L"))
hsv = np.asarray(im.convert("HSV"))
negro = (a < 110) & (hsv[..., 1] < 90)
fl = np.where(negro.sum(axis=1) > negro.shape[1] * 0.08)[0]   # filas con paredes horizontales largas
cl = np.where(negro.sum(axis=0) > negro.shape[0] * 0.06)[0]   # columnas con paredes verticales largas
if len(fl) and len(cl):
    xs = np.where(negro[fl].any(axis=0))[0]     # alcance horizontal de esas paredes
    ys = np.where(negro[:, cl].any(axis=1))[0]  # alcance vertical
    x0, x1 = min(xs[0], cl[0]), max(xs[-1], cl[-1])
    y0, y1 = min(ys[0], fl[0]), max(ys[-1], fl[-1])
    m = int(0.10 * max(x1 - x0, y1 - y0))  # margen para las cotas exteriores
    im = im.crop((max(0, x0 - m), max(0, y0 - m), min(im.width, x1 + m), min(im.height, y1 + m)))
W, H = im.size

# 2. vista completa con cuadricula
c = im.copy()
c.thumbnail((1600, 1600))
d = ImageDraw.Draw(c)
for i in range(1, 10):
    x, y = c.width * i / 10, c.height * i / 10
    d.line([(x, 0), (x, c.height)], fill=(150, 150, 150), width=1)
    d.line([(0, y), (c.width, y)], fill=(150, 150, 150), width=1)
for i in range(10):
    d.text((c.width * (i + 0.45) / 10, 2), "ABCDEFGHIJ"[i], fill=(90, 90, 90))
    d.text((2, c.height * (i + 0.45) / 10), str(i + 1), fill=(90, 90, 90))
c.save(os.path.join(out, "completo.jpg"), quality=88)

# 3. zonas ampliadas
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

# 4. cotas rojas (y giradas)
h, s, v = im.convert("HSV").split()
mask = Image.eval(h, lambda p: 255 if (p < 14 or p > 235) else 0)
mask = Image.composite(mask, Image.new("L", im.size, 0), Image.eval(s, lambda p: 255 if p > 70 else 0))
mask = Image.composite(mask, Image.new("L", im.size, 0), Image.eval(v, lambda p: 255 if p > 60 else 0))
rojo = Image.new("RGB", im.size, "white")
rojo.paste((200, 0, 0), mask=mask)
rojo.thumbnail((2000, 2000))
rojo.save(os.path.join(out, "cotas_rojas.png"))
rojo.rotate(90, expand=True, fillcolor="white").save(os.path.join(out, "cotas_rojas_giro_izq.png"))
rojo.rotate(-90, expand=True, fillcolor="white").save(os.path.join(out, "cotas_rojas_giro_der.png"))
# 5. solo azul: ventanas (marcas, lineas sobre la pared y circulos alrededor de cotas rojas)
azul = Image.eval(h, lambda p: 255 if 140 <= p <= 185 else 0)
azul = Image.composite(azul, Image.new("L", im.size, 0), Image.eval(s, lambda p: 255 if p > 70 else 0))
azul = Image.composite(azul, Image.new("L", im.size, 0), Image.eval(v, lambda p: 255 if p > 50 else 0))
base = ImageEnhance.Brightness(im.convert("L").convert("RGB")).enhance(1.0)
base = Image.blend(Image.new("RGB", im.size, "white"), base, 0.25)  # planta muy tenue de fondo
base.paste((0, 60, 230), mask=azul)
base.thumbnail((2000, 2000))
base.save(os.path.join(out, "ventanas_azul.png"))
print("Generado en", out, ":", sorted(os.listdir(out)))
