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
   hoja_cotas_N.png      hojas con cada numero rojo recortado, numerado (C1, C2...) y en sus 4 giros:
                         se leen todas las cotas de una vez, sin buscar ni girar nada
   mapa_cotas.jpg        el boceto con un recuadro y su numero C# sobre cada cota: dice a que pared va cada una
   lista_cotas.json      ids de las cotas detectadas y datos del recorte (para que el motor compruebe que
                         ninguna se queda sin usar y para superponer el plano al boceto)
"""
import json
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
    caja = (max(0, x0 - m), max(0, y0 - m), min(im.width, x1 + m), min(im.height, y1 + m))
    im = im.crop(caja)
    paredes = [int(x0 - caja[0]), int(y0 - caja[1]), int(x1 - caja[0]), int(y1 - caja[1])]  # extremos de las paredes
else:
    paredes = [0, 0, im.width, im.height]
W, H = im.size
im.save(os.path.join(out, "recorte.jpg"), quality=90)
_g = np.asarray(im.convert("L")); _hs = np.asarray(im.convert("HSV"))
negro_c = (_g < 110) & (_hs[..., 1] < 90)

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
rojo.rotate(180, expand=True, fillcolor="white").save(os.path.join(out, "cotas_rojas_giro_180.png"))  # numeros boca abajo
# 5. solo azul: ventanas (marcas, lineas sobre la pared y circulos alrededor de cotas rojas)
azul = Image.eval(h, lambda p: 255 if 140 <= p <= 185 else 0)
azul = Image.composite(azul, Image.new("L", im.size, 0), Image.eval(s, lambda p: 255 if p > 70 else 0))
azul = Image.composite(azul, Image.new("L", im.size, 0), Image.eval(v, lambda p: 255 if p > 50 else 0))
base = ImageEnhance.Brightness(im.convert("L").convert("RGB")).enhance(1.0)
base = Image.blend(Image.new("RGB", im.size, "white"), base, 0.25)  # planta muy tenue de fondo
base.paste((0, 60, 230), mask=azul)
base.thumbnail((2000, 2000))
base.save(os.path.join(out, "ventanas_azul.png"))


# 6. cotas rojas una a una: hoja de lectura + mapa ---------------------------------------
def tramos(m, k, eje):
    """pixeles que forman parte de un trazo recto de al menos k px a lo largo del eje"""
    m = m.astype(np.int32)
    if eje == 1:
        m = m.T
    c = np.cumsum(np.pad(m, ((0, 0), (1, 0))), axis=1)
    lleno = (c[:, k:] - c[:, :-k]) == k                  # ventanas de k px completamente rojas
    i = np.cumsum(np.pad(lleno.astype(np.int32), ((0, 0), (1, 0))), axis=1)
    n = lleno.shape[1]
    r = np.zeros_like(m, dtype=bool)
    for x in range(m.shape[1]):                           # pixel x cubierto por alguna ventana que empieza en [x-k+1, x]
        a, b = max(0, x - k + 1), min(n, x + 1)
        if b > a:
            r[:, x] = (i[:, b] - i[:, a]) > 0
    return r.T if eje == 1 else r


def etiqueta(m):
    """componentes conexas (8-vecinos) sin scipy"""
    lab = np.zeros(m.shape, dtype=np.int32)
    n = 0
    ys, xs = np.nonzero(m)
    for y, x in zip(ys, xs):
        if lab[y, x]:
            continue
        n += 1
        pila = [(y, x)]
        lab[y, x] = n
        while pila:
            cy, cx = pila.pop()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < m.shape[0] and 0 <= nx < m.shape[1] and m[ny, nx] and not lab[ny, nx]:
                        lab[ny, nx] = n
                        pila.append((ny, nx))
    return lab, n


f = 3                                                     # trabajo a 1/3 de resolucion: rapido y suficiente
rm = np.asarray(mask.resize((W // f, H // f), Image.BOX)) > 40
L = max(rm.shape)
def engorda(m, r, eje):
    """dilata r px en perpendicular al eje (tolera lineas a mano algo inclinadas)"""
    o = m.copy()
    for k in range(1, r + 1):
        if eje == 0:
            o[k:] |= m[:-k]
            o[:-k] |= m[k:]
        else:
            o[:, k:] |= m[:, :-k]
            o[:, :-k] |= m[:, k:]
    return o


# extremos reales de las paredes: pixeles negros en trazos rectos largos (los textos no los tienen)
ng = np.asarray(Image.fromarray((negro_c * 255).astype(np.uint8)).resize((W // f, H // f), Image.BOX)) > 60
bm = max(2, max(ng.shape) // 60)                          # ignora marcos y bordes de la captura
ng[:bm], ng[-bm:], ng[:, :bm], ng[:, -bm:] = False, False, False, False
kp, tp = max(12, max(ng.shape) // 14), max(1, max(ng.shape) // 350)
lp = tramos(engorda(ng, tp, 0), kp, 0) | tramos(engorda(ng, tp, 1), kp, 1)
yy_, xx_ = np.nonzero(lp & ng)
if len(yy_):
    paredes = [int(xx_.min() * f), int(yy_.min() * f), int((xx_.max() + 1) * f), int((yy_.max() + 1) * f)]
# contorno para superponer el plano: paredes negras + lineas azules largas (las galerias suelen ir en azul)
az_c = np.asarray(azul.resize((W // f, H // f), Image.BOX)) > 60
lz = tramos(engorda(az_c, tp, 0), kp, 0) | tramos(engorda(az_c, tp, 1), kp, 1)
yy_, xx_ = np.nonzero((lp & ng) | (lz & az_c))
contorno = [int(xx_.min() * f), int(yy_.min() * f), int((xx_.max() + 1) * f), int((yy_.max() + 1) * f)] if len(yy_) else paredes
k_lin, tol = max(12, L // 22), max(1, L // 350)
lin = (tramos(engorda(rm, tol, 0), k_lin, 0) | tramos(engorda(rm, tol, 1), k_lin, 1))
rm = rm & ~lin                                            # quita las lineas de cota (rectas o casi)
d = max(2, L // 260)                                      # une las cifras de un mismo numero
c = np.cumsum(np.cumsum(np.pad(rm.astype(np.int32), ((d + 1, d), (d + 1, d))), 0), 1)
dil = (c[2 * d + 1:, 2 * d + 1:] - c[:-2 * d - 1, 2 * d + 1:] - c[2 * d + 1:, :-2 * d - 1] + c[:-2 * d - 1, :-2 * d - 1]) > 0
lab, n = etiqueta(dil)
cajas = []
for k in range(1, n + 1):
    yy, xx = np.nonzero((lab == k) & rm)
    if len(yy) < 6:
        continue
    x0_, x1_, y0_, y1_ = xx.min(), xx.max(), yy.min(), yy.max()
    w_, h_ = x1_ - x0_ + 1, y1_ - y0_ + 1
    if max(w_, h_) < L / 70 or max(w_, h_) > L / 5 or max(w_, h_) / max(1, min(w_, h_)) > 7:
        continue                                          # motas, circulos grandes o flechas sueltas
    cajas.append([int(x0_ * f), int(y0_ * f), int((x1_ + 1) * f), int((y1_ + 1) * f)])
# ventanas de lectura de tamano fijo (unas 3 alturas de cifra) centradas en los numeros: unen las cifras
# sueltas de un mismo numero y trocean las zonas con muchas cotas juntas
if cajas:
    h0 = float(np.median([max(b[2] - b[0], b[3] - b[1]) for b in cajas]))
    S = int(1.7 * h0)
    px0, py0, px1, py1 = paredes
    mx, my = 0.15 * (px1 - px0), 0.15 * (py1 - py0)
    centros = []
    for b in sorted(cajas, key=lambda b: (b[2] - b[0]) * (b[3] - b[1])):
        nx, ny = max(1, int(np.ceil((b[2] - b[0]) / (0.8 * S)))), max(1, int(np.ceil((b[3] - b[1]) / (0.8 * S))))
        for i in range(nx):
            for j in range(ny):
                cx = b[0] + (b[2] - b[0]) * (i + 0.5) / nx
                cy = b[1] + (b[3] - b[1]) * (j + 0.5) / ny
                if not (px0 - mx <= cx <= px1 + mx and py0 - my <= cy <= py1 + my):
                    continue                              # notas fuera de la planta (titulo, anotaciones)
                if all(abs(cx - u) > 0.4 * S or abs(cy - v) > 0.4 * S for u, v in centros):
                    centros.append((cx, cy))
    cajas = [[int(cx - S / 2), int(cy - S / 2), int(cx + S / 2), int(cy + S / 2)] for cx, cy in centros]
cajas.sort(key=lambda b: (round((b[1] + b[3]) / 2 / (H / 14)), (b[0] + b[2]) / 2))  # por filas, de arriba abajo
from PIL import ImageFont
try:
    fuente = ImageFont.truetype("DejaVuSans-Bold.ttf", 22)
except OSError:
    fuente = ImageFont.load_default()
T = 150
celdas = []
for i, b in enumerate(cajas, 1):
    z = im.crop((max(0, b[0]), max(0, b[1]), min(W, b[2]), min(H, b[3])))
    z = ImageEnhance.Contrast(z).enhance(1.4)
    vistas = []
    for g in (0, 90, 180, 270):
        v = z.rotate(g, expand=True, fillcolor="white")
        e = T / max(v.size)
        vistas.append(v.resize((max(1, int(v.width * e)), max(1, int(v.height * e))), Image.LANCZOS))
    celdas.append((f"C{i}", vistas))
cw, ch, cols = 64 + 4 * (T + 6), T + 10, 2
por_hoja = cols * 9                                       # 9 filas por hoja: se lee sin reducir
for h_i in range(0, max(1, len(celdas)), por_hoja):
    lote = celdas[h_i:h_i + por_hoja]
    hoja = Image.new("RGB", (cols * cw, max(1, (len(lote) + cols - 1) // cols) * ch), "white")
    dh = ImageDraw.Draw(hoja)
    for j, (nom, vistas) in enumerate(lote):
        ox, oy = (j % cols) * cw, (j // cols) * ch
        dh.rectangle([ox, oy, ox + cw - 1, oy + ch - 1], outline=(200, 200, 200))
        dh.text((ox + 6, oy + T // 2 - 8), nom, fill=(0, 0, 160), font=fuente)
        for q, v in enumerate(vistas):
            hoja.paste(v, (ox + 64 + q * (T + 6) + (T - v.width) // 2, oy + 5 + (T - v.height) // 2))
    hoja.save(os.path.join(out, f"hoja_cotas_{h_i // por_hoja + 1}.png"))
mapa = im.copy()
mapa.thumbnail((1600, 1600))
e = mapa.width / W
dm = ImageDraw.Draw(mapa)
for i, b in enumerate(cajas, 1):
    r = [int(v * e) for v in b]
    dm.rectangle(r, outline=(0, 0, 220), width=2)
    dm.text((r[2] + 2, r[1] - 4), f"C{i}", fill=(0, 0, 220), font=fuente)
mapa.save(os.path.join(out, "mapa_cotas.jpg"), quality=88)
with open(os.path.join(out, "lista_cotas.json"), "w", encoding="utf-8") as fh:
    json.dump({"ids": [nm for nm, _ in celdas], "cajas": cajas, "paredes_px": paredes, "contorno_px": contorno, "tam": [W, H]}, fh)
print(f"{len(cajas)} recuadros con cotas rojas: lee mapa_cotas.jpg y hoja_cotas_*.png")
print("Generado en", out, ":", sorted(os.listdir(out)))
