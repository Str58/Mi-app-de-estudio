#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
plano.py - motor de la skill boceto-a-dxf.

Lee una descripcion JSON de la planta (ver references/formato_json.md) y genera:
  plano.dxf    plano para AutoCAD (metros, capas, muros rellenos)
  plano.png    vista previa con las incidencias marcadas y numeradas
  informe.txt  superficies, errores (E#), avisos (A#) y supuestos

Uso:   python3 plano.py planta.json [carpeta_salida]
Salida: codigo 0 = sin errores, 2 = hay errores que corregir en el JSON.

El motor deduce solo: contorno, muros exteriores (cerramiento / medianera /
antepecho), tabiques (el hueco entre estancias), huecos de puertas y ventanas,
lado de bisagra y sentido de apertura cuando no se indican, y audita que el
plano sea construible y habitable.
"""
import json
import math
import os
import re
import sys

import importlib.util
import subprocess

_FALTAN = [p for m, p in (("ezdxf", "ezdxf"), ("shapely", "shapely"), ("matplotlib", "matplotlib"),
                          ("numpy", "numpy")) if importlib.util.find_spec(m) is None]
if _FALTAN:  # instalacion automatica la primera vez
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *_FALTAN], check=False)

from shapely.geometry import Polygon, box, Point, LineString
from shapely.geometry.polygon import orient
from shapely.ops import unary_union, polylabel

DIRV = {"N": (0, 1), "S": (0, -1), "E": (1, 0), "O": (-1, 0)}
OPUESTO = {"N": "S", "S": "N", "E": "O", "O": "E"}
TOL = 0.015
ESP_DEF = {"cerramiento": 0.30, "medianera": 0.20, "antepecho": 0.12, "tabique": 0.08}


# ----------------------------------------------------------------- utilidades
def nd(d):
    d = str(d).strip().upper()
    return {"W": "O", "OESTE": "O", "ESTE": "E", "NORTE": "N", "SUR": "S"}.get(d, d)


def num(v):
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).strip().replace("'", ".").replace(",", "."))


def fmt(v, n=2):
    return f"{v:.{n}f}".replace(".", ",")


def partes(g):
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    out = []
    for x in getattr(g, "geoms", []):
        out.extend(partes(x))
    return out


def limpia(p):
    p = p.buffer(0)
    return p.simplify(0.0005) if not p.is_empty else p


def sg(e):
    return 1 if e.dir in ("N", "E") else -1


def sbox(axis, s0, s1, c0, c1):
    s0, s1 = sorted((s0, s1))
    c0, c1 = sorted((c0, c1))
    return box(s0, c0, s1, c1) if axis == "h" else box(c0, s0, c1, s1)


def xy(axis, s, c):
    return (s, c) if axis == "h" else (c, s)


class Edge:
    """Lado de un poligono orientado CCW; n = normal hacia fuera del poligono."""

    def __init__(self, p1, p2):
        self.p1, self.p2 = p1, p2
        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
        self.L = math.hypot(dx, dy)
        self.u = (dx / self.L, dy / self.L)
        self.n = (self.u[1], -self.u[0])
        self.dir = None
        for k, (a, b) in DIRV.items():
            if abs(self.n[0] - a) < 1e-6 and abs(self.n[1] - b) < 1e-6:
                self.dir = k
        if self.dir in ("N", "S"):
            self.axis, self.c = "h", p1[1]
            self.s0, self.s1 = sorted((p1[0], p2[0]))
        elif self.dir in ("E", "O"):
            self.axis, self.c = "v", p1[0]
            self.s0, self.s1 = sorted((p1[1], p2[1]))
        else:
            self.axis = None


def ring_edges(coords):
    out = []
    for a, b in zip(coords[:-1], coords[1:]):
        if math.hypot(b[0] - a[0], b[1] - a[1]) > 1e-6:
            out.append(Edge(tuple(a), tuple(b)))
    return out


def poly_edges(p):
    return ring_edges(list(orient(p, 1.0).exterior.coords))


class Auditoria:
    def __init__(self):
        self.err, self.avi = [], []

    def e(self, msg, pt=None):
        self.err.append((msg, pt))

    def a(self, msg, pt=None):
        self.avi.append((msg, pt))


# ------------------------------------------------------------------ estancias
TIPOS = [
    ("terraza", ["terraza", "balcon", "balcón", "tendedero", "galeria", "galería", "porche", "patio"]),
    ("bano", ["baño", "bano", "aseo", "wc", "ducha"]),
    ("cocina", ["cocina", "office"]),
    ("dormitorio", ["dorm", "habitaci", "suite", "cuarto"]),
    ("salon", ["salon", "salón", "estar", "comedor", "living"]),
    ("circulacion", ["pasillo", "distrib", "recib", "hall", "entrada", "vestibulo", "vestíbulo", "escalera"]),
    ("almacen", ["despensa", "trastero", "lavadero", "vestidor", "armario", "cuarto de", "instalac"]),
]

MINIMOS = {  # (superficie m2, anchura libre m) por debajo de los cuales se avisa
    "dormitorio": (5.0, 1.9), "salon": (9.0, 2.4), "cocina": (4.0, 1.5),
    "bano": (1.5, 0.9), "circulacion": (0.0, 0.75),
}


def tipo_de(r):
    if r.get("tipo"):
        return r["tipo"].lower()
    txt = (r.get("id", "") + " " + r.get("nombre", "")).lower()
    for t, claves in TIPOS:
        if any(k in txt for k in claves):
            return t
    return "otro"


class Estancia:
    def __init__(self, spec, poly):
        self.id = spec["id"]
        self.nombre = spec.get("nombre", spec["id"])
        self.tipo = tipo_de(spec)
        self.spec = spec
        self.poly0 = limpia(poly)
        self.poly = self.poly0
        self.edges = poly_edges(self.poly) if not self.poly.is_empty else []

    def recalcula(self):
        self.poly = limpia(self.poly)
        ps = partes(self.poly)
        self.poly = max(ps, key=lambda q: q.area) if ps else self.poly
        self.edges = poly_edges(self.poly)


def esquina(b, k):
    k = nd(k)
    x = b[2] if "E" in k else b[0]
    y = b[3] if "N" in k else b[1]
    return x, y


def punto_inicio(ini, est):
    if isinstance(ini, dict):
        ref = est[ini["desde"]].poly0.bounds
        x, y = esquina(ref, ini.get("esquina", "SO"))
        return x + num(ini.get("dx", 0)), y + num(ini.get("dy", 0))
    return num(ini[0]), num(ini[1])


def construye_estancia(r, est, aud):
    rid = r["id"]
    if "rect" in r:
        q = r["rect"]
        dx, dy = num(q["dx"]), num(q["dy"])
        if "pegado" in r:
            pg = r["pegado"]
            ref = est[pg["a"]].poly0.bounds
            lado = nd(pg["lado"])
            m = num(pg.get("muro", ESP_DEF["tabique"]))
            df = num(pg.get("desfase", 0))
            al = nd(pg.get("alinear", "S" if lado in ("E", "O") else "O"))
            if lado == "E":
                x = ref[2] + m
            elif lado == "O":
                x = ref[0] - m - dx
            elif lado == "N":
                y = ref[3] + m
            else:
                y = ref[1] - m - dy
            if lado in ("E", "O"):
                y = ref[1] + df if al == "S" else (ref[3] - dy - df if al == "N" else (ref[1] + ref[3] - dy) / 2)
            else:
                x = ref[0] + df if al == "O" else (ref[2] - dx - df if al == "E" else (ref[0] + ref[2] - dx) / 2)
        else:
            x, y = num(q.get("x", 0)), num(q.get("y", 0))
        return box(x, y, x + dx, y + dy)
    if "contorno" in r:
        c = r["contorno"]
        x, y = punto_inicio(c["inicio"], est)
        pts = [(x, y)]
        for paso in c["pasos"]:
            m = re.match(r"\s*([NSEOW])\s*([-+]?[\d.,']+)\s*$", str(paso).upper())
            if not m:
                aud.e(f"'{rid}': paso de contorno ilegible «{paso}» (usa p.ej. 'E3,20')", (x, y))
                continue
            vx, vy = DIRV[nd(m.group(1))]
            L = num(m.group(2))
            x, y = x + vx * L, y + vy * L
            pts.append((x, y))
        gx, gy = pts[-1][0] - pts[0][0], pts[-1][1] - pts[0][1]
        if math.hypot(gx, gy) <= 0.02:
            pts = pts[:-1]
        elif min(abs(gx), abs(gy)) > 0.02:
            aud.e(f"El contorno de '{rid}' no cierra: queda un desfase de {fmt(gx)} m en X y {fmt(gy)} m en Y. "
                  f"Revisa las cotas de sus pasos.", pts[0])
        return Polygon(pts)
    if "poligono" in r:
        return Polygon([(num(a), num(b)) for a, b in r["poligono"]])
    raise ValueError(f"Estancia '{rid}' sin geometria (usa rect, contorno o poligono)")


def caja_en_estancia(spec, est, dflt=0.30):
    """Rectangulo para pilares/patinillos: absoluto, en esquina o contra una pared."""
    dx, dy = num(spec.get("dx", dflt)), num(spec.get("dy", dflt))
    if "x" in spec:
        x, y = num(spec["x"]), num(spec["y"])
        return box(x, y, x + dx, y + dy)
    R = est[spec["estancia"]]
    if "esquina" in spec:
        bx, by = esquina(R.poly0.bounds, spec["esquina"])
        # vertice real de la estancia mas proximo a esa esquina del rectangulo envolvente
        vx, vy = min(list(R.poly0.exterior.coords), key=lambda p: math.hypot(p[0] - bx, p[1] - by))
        k = nd(spec["esquina"])
        x0 = vx - dx if "E" in k else vx
        y0 = vy - dy if "N" in k else vy
        return box(x0, y0, x0 + dx, y0 + dy)
    if "contra" in spec:
        d = nd(spec["contra"])
        e = elige_lado(R, d, spec.get("en"))
        ancho = dx if e.axis == "h" else dy
        fondo = dy if e.axis == "h" else dx
        s0 = posicion(spec, e.s0, e.s1, ancho)
        return sbox(e.axis, s0, s0 + ancho, e.c, e.c - sg(e) * fondo)
    raise ValueError("pilar/patinillo sin posicion (x,y | estancia+esquina | estancia+contra)")


def elige_lado(R, d, en=None, filtro=None):
    cand = [e for e in R.edges if e.dir == d and (filtro is None or filtro(e))]
    if not cand:
        return None
    if en is not None:
        en = num(en)
        dentro = [e for e in cand if e.s0 - TOL <= en <= e.s1 + TOL]
        if dentro:
            return max(dentro, key=lambda e: e.L)
    return max(cand, key=lambda e: e.L)


def posicion(spec, a, b, w):
    """Inicio (coordenada menor) de un elemento de anchura w sobre el tramo [a,b]."""
    if "desde" in spec:
        return a + num(spec["desde"])
    if "desde_fin" in spec:
        return b - num(spec["desde_fin"]) - w
    if "en" in spec:
        return num(spec["en"]) - w / 2
    return (a + b) / 2 - w / 2


# ------------------------------------------------------------------ mobiliario
MUEBLES = {  # ancho (a lo largo de la pared), fondo
    "cama": (1.50, 2.00), "cama_individual": (0.90, 1.90), "cama_doble": (1.50, 2.00),
    "sofa": (2.00, 0.90), "sillon": (0.80, 0.80), "mesa": (1.60, 0.90), "mesa_redonda": (1.10, 1.10),
    "armario": (1.20, 0.60), "mesita": (0.45, 0.40), "escritorio": (1.20, 0.60), "comoda": (1.00, 0.50),
    "inodoro": (0.40, 0.70), "bide": (0.40, 0.55), "lavabo": (0.60, 0.45), "ducha": (0.80, 0.80),
    "banera": (1.60, 0.70), "encimera": (2.40, 0.60), "fregadero": (0.80, 0.50), "placa": (0.60, 0.55),
    "frigorifico": (0.60, 0.65), "lavadora": (0.60, 0.60), "rect": (1.00, 0.60), "mueble_tv": (1.60, 0.45),
}


def elipse(cx, cy, rx, ry, n=28):
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rect(a, b, c, d):
    return [(a, b), (c, b), (c, d), (a, d)]


def dibujo_mueble(t, W, D):
    P = [("pl", rect(0, 0, W, D), True)]
    if t.startswith("cama"):
        n = 2 if W >= 1.3 else 1
        aw = (W - 0.15 * (n + 1)) / n
        for i in range(n):
            x0 = 0.15 + i * (aw + 0.15)
            P.append(("pl", rect(x0, 0.08, x0 + aw, 0.38), True))
        P.append(("ln", (0, 0.60), (W, 0.60)))
    elif t in ("sofa", "sillon"):
        P += [("ln", (0, 0.22), (W, 0.22)), ("ln", (0.18, 0.22), (0.18, D)), ("ln", (W - 0.18, 0.22), (W - 0.18, D))]
    elif t == "mesa_redonda":
        P = [("ci", (W / 2, D / 2), min(W, D) / 2)]
    elif t == "armario":
        P += [("ln", (0, 0), (W, D)), ("ln", (W, 0), (0, D))]
    elif t == "inodoro":
        P = [("pl", rect(0.02, 0, W - 0.02, 0.18), True), ("pl", elipse(W / 2, 0.44, W / 2 - 0.02, 0.25), True)]
    elif t == "bide":
        P = [("pl", elipse(W / 2, D / 2, W / 2 - 0.02, D / 2 - 0.02), True), ("ci", (W / 2, 0.15), 0.03)]
    elif t == "lavabo":
        P.append(("pl", elipse(W / 2, D / 2 + 0.02, W / 2 - 0.08, D / 2 - 0.08), True))
    elif t == "ducha":
        P += [("ln", (0, 0), (W, D)), ("ci", (W / 2, D / 2), 0.04)]
    elif t == "banera":
        P += [("pl", rect(0.07, 0.07, W - 0.07, D - 0.07), True), ("ci", (W - 0.20, D / 2), 0.03)]
    elif t == "fregadero":
        P = [("pl", rect(0, 0, W, D), True), ("pl", rect(0.06, 0.06, W - 0.06, D - 0.06), True), ("ci", (W / 2, D / 2), 0.03)]
    elif t == "placa":
        r = min(W, D) / 5
        P += [("ci", (W * a, D * b), r) for a in (0.28, 0.72) for b in (0.28, 0.72)]
    elif t in ("frigorifico",):
        P.append(("ln", (0, 0), (W, D)))
    elif t == "lavadora":
        P.append(("ci", (W / 2, D / 2), min(W, D) * 0.35))
    return P


# --------------------------------------------------------------------- motor
def genera(spec, salida):
    aud = Auditoria()
    for m in spec.pop("_avisos_cadenas", []):
        aud.a(m)
    esp = dict(ESP_DEF)
    esp.update({k: num(v) for k, v in spec.get("espesores", {}).items()})
    ESP_DEF.update(esp)  # 'pegado' usa el tabique configurado

    # 1. estancias -----------------------------------------------------------
    est = {}
    for r in spec["estancias"]:
        if r["id"] in est or r["id"] == "exterior":
            aud.e(f"Id de estancia repetido o reservado: '{r['id']}'")
            continue
        est[r["id"]] = Estancia(r, construye_estancia(r, est, aud))
    E = list(est.values())
    for R in E:
        if not R.poly0.is_valid or R.poly0.area < 0.2:
            aud.e(f"'{R.id}' tiene una geometria invalida o casi nula", R.poly0.centroid.coords[0])

    pilares = [caja_en_estancia(p, est) for p in spec.get("pilares", [])]
    patinillos = [caja_en_estancia(p, est, 0.40) if "rect" not in p else
                  box(num(p["rect"]["x"]), num(p["rect"]["y"]), num(p["rect"]["x"]) + num(p["rect"]["dx"]),
                      num(p["rect"]["y"]) + num(p["rect"]["dy"])) for p in spec.get("patinillos", [])]
    if pilares:
        PU = unary_union(pilares)
        for R in E:
            if R.poly.intersects(PU):
                R.poly = R.poly.difference(PU)
                R.recalcula()

    abiertas = {frozenset(p) for p in spec.get("abiertas", [])}

    # 2. auditoria de estancias entre si --------------------------------------
    for i, A in enumerate(E):
        for B in E[i + 1:]:
            inter = A.poly.intersection(B.poly)
            if inter.area > 0.002:
                aud.e(f"'{A.id}' y '{B.id}' se solapan {fmt(inter.area)} m2: revisa sus cotas/coordenadas",
                      inter.centroid.coords[0])
                continue
            if A.poly.distance(B.poly) < 0.01 and frozenset((A.id, B.id)) not in abiertas:
                comun = A.poly.boundary.intersection(B.poly.boundary.buffer(0.01))
                if comun.length > 0.05:
                    aud.e(f"'{A.id}' y '{B.id}' estan pegadas sin tabique ({fmt(comun.length)} m). Separalas el "
                          f"espesor del tabique o declaralas en \"abiertas\" si es un espacio abierto.",
                          comun.centroid.coords[0])

    # 3. contorno del edificio ------------------------------------------------
    RU = unary_union([R.poly0 for R in E])
    cerrado = RU.buffer(0.21, join_style=2, mitre_limit=10).buffer(-0.21, join_style=2, mitre_limit=10)
    patios = [construye_estancia(dict(p, id="patio"), est, aud) for p in spec.get("patios", [])]
    piezas = []
    for P in partes(cerrado):
        holes = []
        for ring in P.interiors:
            h = Polygon(ring)
            if any(h.intersection(pt).area > 0.01 for pt in patios):
                holes.append(ring)
            elif h.area < 1.5:
                pat = h.buffer(-esp["tabique"], join_style=2)
                if not pat.is_empty and pat.area > 0.04:
                    patinillos.append(pat)
                aud.a(f"Hueco de {fmt(h.area)} m2 entre estancias sin asignar: se dibuja como patinillo de "
                      f"instalaciones", h.centroid.coords[0])
            else:
                aud.e(f"Hueco de {fmt(h.area)} m2 rodeado de estancias pero sin estancia asignada: falta una "
                      f"estancia o las cotas no cuadran (se ha macizado)", h.representative_point().coords[0])
        piezas.append(Polygon(P.exterior, holes))
    if len(piezas) > 1:
        for P in sorted(piezas, key=lambda q: q.area)[:-1]:
            aud.e("Volumen suelto: este grupo de estancias no esta adosado al resto de la vivienda",
                  P.representative_point().coords[0])
    cerrado = unary_union(piezas)
    for P in piezas:
        for e in poly_edges(P):
            if e.L < 0.06:
                aud.a(f"Quiebro de {fmt(e.L * 100, 0)} cm en el contorno exterior: probable descuadre de cotas",
                      e.p1)
    otras = lambda R: unary_union([X.poly for X in E if X is not R])

    # 4. caras exteriores (muestreo) -----------------------------------------
    def muestras_ext(R, e, a=None, b=None, prof=0.6):
        a = e.s0 if a is None else a
        b = e.s1 if b is None else b
        n = max(2, int((b - a) / 0.05))
        ok = []
        O = otras(R)
        for i in range(n + 1):
            s = a + (b - a) * (i + 0.5) / (n + 1)
            seg = LineString([xy(e.axis, s, e.c + sg(e) * 0.005), xy(e.axis, s, e.c + sg(e) * prof)])
            fin = Point(xy(e.axis, s, e.c + sg(e) * prof))
            ok.append(not cerrado.buffer(-1e-4).contains(fin) and not seg.intersects(O))
        return ok

    def es_exterior(R, e):
        m = muestras_ext(R, e)
        return sum(m) / len(m)

    # 5. ventanas (posicion) --------------------------------------------------
    ventanas = []
    for k, v in enumerate(spec.get("ventanas", []), 1):
        R = est.get(v.get("estancia"))
        if R is None:
            aud.e(f"Ventana {k}: estancia '{v.get('estancia')}' no existe")
            continue
        lado = nd(v["lado"]) if v.get("lado") else None
        cand = [e for e in R.edges if e.axis and (lado is None or e.dir == lado) and es_exterior(R, e) > 0.2]
        if not cand:
            aud.e(f"Ventana {k} de '{R.id}': el lado {lado or '(cualquiera)'} no da al exterior. Las ventanas solo "
                  f"van en cerramientos.", R.poly.centroid.coords[0])
            continue
        if lado is None and len({e.dir for e in cand}) > 1:
            aud.a(f"Ventana {k} de '{R.id}' sin lado: se coloca en la fachada mas larga")
        e = (elige_lado(R, cand[0].dir, v.get("en"), lambda x: x in cand) if lado else max(cand, key=lambda x: x.L))
        if v.get("ancho") == "corrido":  # acristalamiento de pared entera: 0,10 de pared a cada lado
            v = dict(v, desde=0.10)
            w = max(0.4, e.L - 0.20)
        else:
            w = num(v.get("ancho", 1.20))
        if w > e.L + 0.005:
            aud.a(f"Ventana {k} de '{R.id}': ancho {fmt(w)} no cabe en {fmt(e.L)} m; se reduce")
            w = max(0.4, e.L)
        s0 = posicion(v, e.s0, e.s1, w)
        if "desde" not in v and "desde_fin" not in v and "en" not in v:
            m = muestras_ext(R, e)
            idx = [i for i, ok in enumerate(m) if ok]
            if idx:
                a = e.s0 + (e.s1 - e.s0) * (idx[0] + 0.5) / len(m)
                b = e.s0 + (e.s1 - e.s0) * (idx[-1] + 0.5) / len(m)
                s0 = (a + b) / 2 - w / 2
        mg = min(0.05, max(0.0, (e.L - w) / 2))  # una ventana puede ocupar la pared entera
        s0c = min(max(s0, e.s0 + mg), e.s1 - mg - w)
        if abs(s0c - s0) > 0.02:
            aud.a(f"Ventana {k} de '{R.id}' se salia de la pared: desplazada {fmt(abs(s0c - s0))} m")
        s0 = s0c
        m = muestras_ext(R, e, s0, s0 + w)
        if sum(m) < len(m):
            aud.e(f"Ventana {k} de '{R.id}': parte del hueco cae sobre una pared que no es de fachada",
                  xy(e.axis, s0 + w / 2, e.c))
        ventanas.append(dict(R=R, e=e, s0=s0, s1=s0 + w, tipo=v.get("tipo", "ventana"), k=k))

    # 6. puertas (geometria del hueco, antes de muros exteriores) -------------
    def caras_comunes(A, B):
        res = []
        for ea in A.edges:
            for eb in B.edges:
                if ea.axis is None or ea.axis != eb.axis or eb.dir != OPUESTO.get(ea.dir):
                    continue
                gap = (eb.c - ea.c) * sg(ea)
                o0, o1 = max(ea.s0, eb.s0), min(ea.s1, eb.s1)
                if -TOL <= gap <= 0.45 and o1 - o0 >= 0.25:
                    res.append((ea, eb, gap, o0, o1))
        return res

    puertas = []
    for k, p in enumerate(spec.get("puertas", []), 1):
        a, b = p["entre"]
        if a == "exterior":
            a, b = b, a
        tipo = p.get("tipo", "abatible")
        if a not in est or (b not in est and b != "exterior"):
            aud.e(f"Puerta {k}: estancia inexistente en {p['entre']}")
            continue
        A = est[a]
        if b == "exterior":
            lado = nd(p["lado"]) if p.get("lado") else None
            cand = [e for e in A.edges if e.axis and (lado is None or e.dir == lado) and es_exterior(A, e) > 0.2]
            if not cand:
                aud.e(f"Puerta {k} (entrada a '{a}'): el lado {lado or '?'} de '{a}' no da al exterior",
                      A.poly.centroid.coords[0])
                continue
            e = elige_lado(A, cand[0].dir, p.get("en"), lambda x: x in cand) if lado else max(cand, key=lambda x: x.L)
            o0, o1 = e.s0, e.s1
            w = (o1 - o0) if p.get("ancho") == "total" else num(p.get("ancho", 0.90))
            puertas.append(dict(k=k, A=A, B=None, ea=e, eb=None, o0=o0, o1=o1, w=w, tipo=tipo, spec=p))
        else:
            B = est[b]
            cc = caras_comunes(A, B)
            lado = nd(p["lado"]) if p.get("lado") else None
            if lado:
                cc = [c for c in cc if c[0].dir == lado] or cc
            cc = [c for c in cc if c[2] > 0.01]
            if not cc:
                aud.e(f"Puerta {k}: '{a}' y '{b}' no comparten ninguna pared (o estan pegadas sin tabique): una "
                      f"puerta entre ellas es imposible", A.poly.centroid.coords[0])
                continue
            if p.get("en") is not None:
                en = num(p["en"])
                c2 = [c for c in cc if c[3] - TOL <= en <= c[4] + TOL]
                cc = c2 or cc
            ea, eb, gap, o0, o1 = max(cc, key=lambda c: c[4] - c[3])
            w = o1 - o0 if p.get("ancho") == "total" else num(p.get("ancho", 0.80))
            puertas.append(dict(k=k, A=A, B=B, ea=ea, eb=eb, o0=o0, o1=o1, w=w, tipo=tipo, spec=p))
    for d in puertas:
        if d["w"] > d["o1"] - d["o0"] + 1e-6:
            aud.e(f"Puerta {d['k']}: ancho {fmt(d['w'])} no cabe en el tramo comun de {fmt(d['o1'] - d['o0'])} m; "
                  f"se reduce", xy(d["ea"].axis, (d["o0"] + d["o1"]) / 2, d["ea"].c))
            d["w"] = d["o1"] - d["o0"]
        s0 = posicion(d["spec"], d["o0"], d["o1"], d["w"])
        s0c = min(max(s0, d["o0"]), d["o1"] - d["w"])
        if abs(s0c - s0) > 0.02:
            aud.a(f"Puerta {d['k']} se salia del tramo de pared comun: desplazada {fmt(abs(s0c - s0))} m")
        d["s0"], d["s1"] = s0c, s0c + d["w"]

    # 7. muros exteriores: tipo y espesor por tramo ---------------------------
    especs = []
    for x in spec.get("medianeras", []):
        especs.append({"lado": x, "tipo": "medianera"} if isinstance(x, str) else dict({"tipo": "medianera"}, **x))
    especs += spec.get("muros_exteriores", [])
    auto_med = spec.get("medianeras_auto", True)

    def tipo_tramo(P, e, sm):
        bx = P.bounds
        t = None
        for R in E:
            for re_ in R.edges:
                if re_.dir == e.dir and abs(re_.c - e.c) < TOL and re_.s0 - TOL <= sm <= re_.s1 + TOL:
                    t = "antepecho" if R.tipo == "terraza" else "cerramiento"
        if t is None:
            return None
        if auto_med and t == "cerramiento":
            # medianera automatica: alineacion de fachada sin ningun hueco
            linea_con_huecos = False
            for v in ventanas:
                if v["e"].dir == e.dir and abs(v["e"].c - e.c) < 0.02:
                    linea_con_huecos = True
            for d in puertas:
                if d["B"] is None and d["ea"].dir == e.dir and abs(d["ea"].c - e.c) < 0.02:
                    linea_con_huecos = True
            if not linea_con_huecos:
                t = "medianera"
        for s in especs:
            if nd(s.get("lado", "")) != e.dir:
                continue
            ok = False
            if "estancia" in s:
                R = est.get(s["estancia"])
                ok = R is not None and any(re_.dir == e.dir and abs(re_.c - e.c) < TOL and
                                           re_.s0 - TOL <= sm <= re_.s1 + TOL for re_ in R.edges)
            elif "de" in s and "a" in s:
                (x1, y1), (x2, y2) = s["de"], s["a"]
                p1, p2 = (num(x1), num(y1)), (num(x2), num(y2))
                if e.axis == "h":
                    ok = min(p1[0], p2[0]) - TOL <= sm <= max(p1[0], p2[0]) + TOL and abs(p1[1] - e.c) < 0.45
                else:
                    ok = min(p1[1], p2[1]) - TOL <= sm <= max(p1[1], p2[1]) + TOL and abs(p1[0] - e.c) < 0.45
            else:
                ext = {"N": bx[3], "S": bx[1], "E": bx[2], "O": bx[0]}[e.dir]
                ok = abs(e.c - ext) < TOL
            if ok:
                t = s.get("tipo", "medianera")
                if "espesor" in s:
                    return (t, num(s["espesor"]))
        return t

    bandas, tramos_info = [], []
    for P in piezas:
        rings = [list(orient(P, 1.0).exterior.coords)] + [list(r.coords) for r in orient(P, 1.0).interiors]
        for ri, ring in enumerate(rings):
            eds = ring_edges(ring)
            trozos = []
            for e in eds:
                if e.axis is None:
                    trozos.append([(0, e.L, esp["cerramiento"], "cerramiento")])
                    continue
                cortes = {e.s0, e.s1}
                for R in E:
                    for (x, y) in R.poly0.exterior.coords:
                        sv = x if e.axis == "h" else y
                        if e.s0 < sv < e.s1:
                            cortes.add(sv)
                for s in especs:
                    for key in ("de", "a"):
                        if key in s:
                            sv = num(s[key][0] if e.axis == "h" else s[key][1])
                            if e.s0 < sv < e.s1:
                                cortes.add(sv)
                cortes = sorted(cortes)
                ps1 = e.p1[0] if e.axis == "h" else e.p1[1]
                us = e.u[0] if e.axis == "h" else e.u[1]
                tr = []
                for s_a, s_b in zip(cortes[:-1], cortes[1:]):
                    if s_b - s_a < 1e-4:
                        continue
                    r = tipo_tramo(P, e, (s_a + s_b) / 2) if ri == 0 else "cerramiento"
                    if isinstance(r, tuple):
                        tt, th = r
                    else:
                        tt, th = r, (esp[r] if r else None)
                    ta, tb = sorted(((s_a - ps1) * us, (s_b - ps1) * us))
                    tr.append([ta, tb, th, tt])
                tr.sort()
                for i, x in enumerate(tr):  # tramos sin estancia (cabeza de tabique): heredan del vecino
                    if x[2] is None:
                        vec = [y for y in tr if y[2] is not None]
                        cer = min(vec, key=lambda y: min(abs(y[0] - x[1]), abs(y[1] - x[0]))) if vec else None
                        x[2], x[3] = (cer[2], cer[3]) if cer else (esp["cerramiento"], "cerramiento")
                trozos.append([tuple(x) for x in tr])
            for i, e in enumerate(eds):
                t_prev = trozos[i - 1][-1][2]
                t_next = trozos[(i + 1) % len(eds)][0][2]
                for j, (ta, tb, th, tt) in enumerate(trozos[i]):
                    xa = ta - (t_prev if j == 0 else 0)
                    xb = tb + (t_next if j == len(trozos[i]) - 1 else 0)
                    A_ = (e.p1[0] + e.u[0] * xa, e.p1[1] + e.u[1] * xa)
                    B_ = (e.p1[0] + e.u[0] * xb, e.p1[1] + e.u[1] * xb)
                    C_ = (B_[0] + e.n[0] * th, B_[1] + e.n[1] * th)
                    D_ = (A_[0] + e.n[0] * th, A_[1] + e.n[1] * th)
                    bp = Polygon([A_, B_, C_, D_])
                    bandas.append(bp)
                    nucleo = Polygon([(e.p1[0] + e.u[0] * ta, e.p1[1] + e.u[1] * ta),
                                      (e.p1[0] + e.u[0] * tb, e.p1[1] + e.u[1] * tb),
                                      (e.p1[0] + e.u[0] * tb + e.n[0] * th, e.p1[1] + e.u[1] * tb + e.n[1] * th),
                                      (e.p1[0] + e.u[0] * ta + e.n[0] * th, e.p1[1] + e.u[1] * ta + e.n[1] * th)])
                    tramos_info.append((nucleo, tt, th))
    exterior = limpia(unary_union([cerrado] + bandas))

    # 8. huecos ---------------------------------------------------------------
    huecos, prims = [], []

    def hueco_exterior(e, s0, s1):
        # profundidad = espesor real del muro en ese punto (no recorta muros vecinos)
        medidas = []
        for sm in (s0 + 0.02, (s0 + s1) / 2, s1 - 0.02):
            ray = LineString([xy(e.axis, sm, e.c), xy(e.axis, sm, e.c + sg(e) * 0.8)]).intersection(exterior)
            trozos = [ray] if ray.geom_type == "LineString" else list(getattr(ray, "geoms", []))
            ini = Point(xy(e.axis, sm, e.c))
            for t in trozos:
                if t.distance(ini) < 1e-3:
                    medidas.append(t.length)
        prof = (min(medidas) if medidas else 0.8) + 0.002
        g = sbox(e.axis, s0, s1, e.c - sg(e) * 0.002, e.c + sg(e) * prof).intersection(exterior)
        g = max(partes(g), key=lambda q: q.area) if partes(g) else g
        return g

    for v in ventanas:
        e = v["e"]
        g = hueco_exterior(e, v["s0"], v["s1"])
        huecos.append(g)
        b = g.bounds
        c0, c1 = (b[1], b[3]) if e.axis == "h" else (b[0], b[2])
        v["c0"], v["c1"], v["geom"] = c0, c1, g
        for nucleo, tt, th in tramos_info:
            if tt == "medianera" and nucleo.intersection(g).area > 0.002:
                aud.e(f"Ventana {v['k']} de '{v['R'].id}' sobre una medianera: no es posible abrir huecos en "
                      f"medianeras", xy(e.axis, (v["s0"] + v["s1"]) / 2, e.c))
                break
        for fr in (0.25, 0.5, 0.75):
            c = c0 + (c1 - c0) * fr
            prims.append(dict(L="VENTANAS", k="pl", pts=[xy(e.axis, v["s0"], c), xy(e.axis, v["s1"], c)], cerr=False))
        for s in (v["s0"], v["s1"]):
            prims.append(dict(L="VENTANAS", k="pl", pts=[xy(e.axis, s, c0), xy(e.axis, s, c1)], cerr=False))

    for d in puertas:
        ea = d["ea"]
        if d["B"] is None:
            g = hueco_exterior(ea, d["s0"], d["s1"])
            b = g.bounds
            c0, c1 = (b[1], b[3]) if ea.axis == "h" else (b[0], b[2])
            d["c_other"] = c1 if sg(ea) > 0 else c0
        else:
            g = sbox(ea.axis, d["s0"], d["s1"], ea.c - sg(ea) * 0.002, d["eb"].c + sg(ea) * 0.002)
            d["c_other"] = d["eb"].c
        d["geom"] = g
        huecos.append(g)

    # 9. mobiliario -----------------------------------------------------------
    muebles = []
    for k, m in enumerate(spec.get("mobiliario", []), 1):
        t = m.get("tipo", "rect").lower()
        W0, D0 = MUEBLES.get(t, MUEBLES["rect"])
        W, D = num(m.get("ancho", W0)), num(m.get("fondo", D0))
        R = est.get(m.get("estancia"))
        contra = nd(m.get("contra", "S"))
        if R is None and "x" not in m:
            aud.e(f"Mueble {k} ({t}): estancia '{m.get('estancia')}' no existe")
            continue
        sep = num(m.get("sep", 0))
        if m.get("centro") or "x" in m:
            if "x" in m:
                cx, cy = num(m["x"]), num(m["y"])
            else:
                cp = polylabel(R.poly, 0.01)
                cx, cy = cp.x, cp.y
            vx, vy = -DIRV[contra][0], -DIRV[contra][1]
            ux, uy = (1, 0) if contra in ("N", "S") else (0, 1)
            ox, oy = cx - ux * W / 2 - vx * D / 2, cy - uy * W / 2 - vy * D / 2
        else:
            e = elige_lado(R, contra, m.get("en"))
            if e is None:
                aud.e(f"Mueble {k} ({t}) en '{R.id}': la estancia no tiene pared al {contra}")
                continue
            s0 = posicion(m, e.s0, e.s1, W)
            ux, uy = (1, 0) if e.axis == "h" else (0, 1)
            vx, vy = -DIRV[contra][0], -DIRV[contra][1]
            bx, by = xy(e.axis, s0, e.c)
            ox, oy = bx + vx * sep, by + vy * sep

        def T(p, ox=ox, oy=oy, ux=ux, uy=uy, vx=vx, vy=vy):
            return (ox + ux * p[0] + vx * p[1], oy + uy * p[0] + vy * p[1])

        for pr in dibujo_mueble(t, W, D):
            if pr[0] == "pl":
                prims.append(dict(L="MOBILIARIO", k="pl", pts=[T(q) for q in pr[1]], cerr=pr[2]))
            elif pr[0] == "ln":
                prims.append(dict(L="MOBILIARIO", k="pl", pts=[T(pr[1]), T(pr[2])], cerr=False))
            else:
                prims.append(dict(L="MOBILIARIO", k="ci", c=T(pr[1]), r=pr[2]))
        foot = Polygon([T((0, 0)), T((W, 0)), T((W, D)), T((0, D))])
        muebles.append((k, t, foot, R))
        if R is not None and foot.difference(R.poly).area > 0.01:
            aud.a(f"Mueble {k} ({t}) se sale de '{R.id}' o choca con un muro/pilar", foot.centroid.coords[0])
    for i, (k1, t1, f1, _) in enumerate(muebles):
        for (k2, t2, f2, _) in muebles[i + 1:]:
            if f1.intersection(f2).area > 0.01 and not ({t1, t2} & {"fregadero", "placa"}):
                aud.a(f"Muebles {k1} ({t1}) y {k2} ({t2}) se solapan", f1.intersection(f2).centroid.coords[0])
    MU = unary_union([f for (_, _, f, _) in muebles]) if muebles else Polygon()

    # 10. hojas de puerta: sentido y bisagra con comprobacion ----------------
    CIRC = ("circulacion",)
    barridos = []

    def sector(axis, sh, cf, vs, us, w):
        pts = [xy(axis, sh, cf)]
        for i in range(19):
            th = math.radians(i * 5)
            pts.append(xy(axis, sh + us * w * math.sin(th), cf + vs * w * math.cos(th)))
        return Polygon(pts)

    for d in puertas:
        ea, A, B = d["ea"], d["A"], d["B"]
        sp = d["spec"]
        if d["tipo"] in ("paso", "balconera", "ventana"):
            if d["tipo"] in ("balconera", "ventana"):
                c0, c1 = sorted((ea.c, d["c_other"]))
                for fr in (0.25, 0.5, 0.75):
                    c = c0 + (c1 - c0) * fr
                    prims.append(dict(L="VENTANAS", k="pl", pts=[xy(ea.axis, d["s0"], c), xy(ea.axis, d["s1"], c)], cerr=False))
            continue
        lados = []  # (estancia hacia la que abre, c de su cara, signo hacia dentro)
        if B is None:
            lados = [(A, ea.c, -sg(ea))]
        else:
            la = (A, ea.c, -sg(ea))
            lb = (B, d["eb"].c, sg(ea))
            pref = sp.get("abre_hacia")
            if pref == B.id:
                lados = [lb, la]
            elif pref == A.id:
                lados = [la, lb]
            else:  # abre hacia la pieza que no es de paso; si ambas iguales, hacia la mas pequena
                ta, tb = A.tipo in CIRC, B.tipo in CIRC
                lados = [lb, la] if (ta and not tb) or (ta == tb and B.poly.area < A.poly.area) else [la, lb]
        if d["tipo"] == "corredera":
            Rr, cf, vs = lados[0]
            c = (ea.c + d["c_other"]) / 2
            prims.append(dict(L="PUERTAS", k="pl", cerr=True,
                              pts=[xy(ea.axis, d["s0"], c - 0.02), xy(ea.axis, d["s1"], c - 0.02),
                                   xy(ea.axis, d["s1"], c + 0.02), xy(ea.axis, d["s0"], c + 0.02)]))
            d["abre"] = Rr
            continue
        bis_pref = nd(sp["bisagra"]) if sp.get("bisagra") else None
        cerca_ini = (d["s0"] - d["o0"]) <= (d["o1"] - d["s1"])
        bis_orden = [cerca_ini, not cerca_ini]  # True = bisagra en el extremo de coordenada menor (O/S)
        if bis_pref:
            menor = bis_pref in ("O", "S")
            bis_orden = [menor, not menor]
        cands = []
        orden = 0
        for (Rr, cf, vs) in lados:
            for menor in bis_orden:
                sh = d["s0"] if menor else d["s1"]
                us = 1 if menor else -1
                secp = sector(ea.axis, sh, cf, vs, us, d["w"])
                fuera = secp.difference(Rr.poly).area
                cruce = sum(secp.intersection(b).area for b in barridos)
                mueb = secp.intersection(MU).area
                score = fuera * 100 + cruce * 10 + mueb * 5
                cands.append((score, orden, Rr, cf, vs, sh, us, secp, fuera, cruce, mueb))
                orden += 1
        best = min(cands, key=lambda c: (round(c[0], 3), c[1]))
        primero = cands[0]
        score, _, Rr, cf, vs, sh, us, secp, fuera, cruce, mueb = best
        pdesc = f"Puerta {d['k']} ({A.id}{'-' + B.id if B else '-exterior'})"
        if fuera > 0.01:
            aud.e(f"{pdesc}: la hoja no cabe al abrir, choca con un muro o con el limite de la estancia en "
                  f"cualquier sentido. Cambia su posicion o su ancho.", secp.centroid.coords[0])
        elif best is not primero and (sp.get("abre_hacia") or sp.get("bisagra")) and primero[8] > 0.01:
            aud.a(f"{pdesc}: con el sentido/bisagra indicados chocaba con un muro; se ha invertido", secp.centroid.coords[0])
        if cruce > 0.02:
            aud.a(f"{pdesc}: su barrido se cruza con el de otra puerta", secp.centroid.coords[0])
        if mueb > 0.02:
            aud.a(f"{pdesc}: al abrir choca con un mueble", secp.centroid.coords[0])
        barridos.append(secp)
        d["abre"] = Rr
        d["cf"], d["vs"] = cf, vs
        w = d["w"]
        tip = xy(ea.axis, sh, cf + vs * w)
        hing = xy(ea.axis, sh, cf)
        hoja = [hing, tip, xy(ea.axis, sh + us * 0.04, cf + vs * w), xy(ea.axis, sh + us * 0.04, cf)]
        prims.append(dict(L="PUERTAS", k="pl", pts=hoja, cerr=True))
        a_leaf = math.degrees(math.atan2(tip[1] - hing[1], tip[0] - hing[0])) % 360
        jam = xy(ea.axis, sh + us * w, cf)
        a_cl = math.degrees(math.atan2(jam[1] - hing[1], jam[0] - hing[0])) % 360
        a0, a1 = (a_cl, a_leaf) if (a_leaf - a_cl) % 360 == 90 or abs((a_leaf - a_cl) % 360 - 90) < 1 else (a_leaf, a_cl)
        prims.append(dict(L="PUERTAS", k="arc", c=hing, r=w, a0=a0, a1=a1))
        # paso libre delante de la puerta
        frente = sbox(ea.axis, d["s0"], d["s1"], cf, cf + vs * 0.6)
        if MU.intersection(frente).area > 0.05:
            aud.a(f"{pdesc}: un mueble obstruye el paso por la puerta", frente.centroid.coords[0])

    # 11. muros finales ---------------------------------------------------------
    muros = exterior.difference(unary_union([R.poly for R in E] + patinillos))
    if huecos:
        muros = muros.difference(unary_union(huecos))
    # elimina astillas y lineas sueltas de menos de 1 cm que dejan los recortes
    muros = muros.buffer(-0.005, join_style=2, mitre_limit=10).buffer(0.005, join_style=2, mitre_limit=10)
    muros = limpia(unary_union([p for p in partes(muros) if p.area > 0.002]))

    # 12. auditoria funcional -------------------------------------------------
    grafo = {R.id: set() for R in E}
    grafo["exterior"] = set()
    for d in puertas:
        if d["tipo"] == "ventana":  # ventana interior: ilumina pero no da acceso
            continue
        a = d["A"].id
        b = d["B"].id if d["B"] else "exterior"
        grafo[a].add(b)
        grafo[b].add(a)
    for par in abiertas:
        par = list(par)
        if len(par) == 2 and all(x in grafo for x in par):
            grafo[par[0]].add(par[1])
            grafo[par[1]].add(par[0])
    if not grafo["exterior"] and not spec.get("sin_entrada"):
        aud.e("No hay puerta de entrada a la vivienda (puerta con \"exterior\")")
    visto, pila = {"exterior"}, ["exterior"]
    while pila:
        x = pila.pop()
        for y in grafo[x]:
            if y not in visto:
                visto.add(y)
                pila.append(y)
    for R in E:
        c = polylabel(R.poly, 0.02).coords[0]
        if not grafo[R.id] and not R.spec.get("sin_puerta"):
            aud.e(f"'{R.id}' no tiene puerta ni paso: es inaccesible", c)
        elif R.id not in visto and grafo["exterior"] and not R.spec.get("sin_puerta"):
            aud.e(f"'{R.id}' no es accesible desde la entrada recorriendo puertas y pasos", c)
        tiene_v = any(v["R"] is R for v in ventanas) or any(
            d["tipo"] == "balconera" and (d["A"] is R or d["B"] is R) for d in puertas) or any(
            R.id in par and any(v["R"].id in par and v["R"] is not R for v in ventanas) for par in abiertas)
        if R.tipo in ("dormitorio", "salon") and not tiene_v and not R.spec.get("sin_ventana"):
            aud.a(f"'{R.id}' es habitable y no tiene ventana", c)
        mn = MINIMOS.get(R.tipo)
        if mn:
            if R.poly.area < mn[0]:
                aud.a(f"'{R.id}' mide solo {fmt(R.poly.area)} m2 (minimo razonable {fmt(mn[0], 1)} m2): revisa cotas", c)
            if R.poly.buffer(-mn[1] / 2 + 0.005, join_style=2).is_empty:
                aud.a(f"'{R.id}' tiene menos de {fmt(mn[1])} m de anchura libre: revisa cotas", c)
    for d in puertas:
        if d["B"] is not None and {d["A"].tipo, d["B"].tipo} == {"bano", "cocina"}:
            aud.a(f"Puerta {d['k']}: un baño no deberia abrir directamente a la cocina",
                  xy(d["ea"].axis, (d["s0"] + d["s1"]) / 2, d["ea"].c))
    # tabiques demasiado finos y macizos sospechosos
    for i, A in enumerate(E):
        for B in E[i + 1:]:
            for (ea, eb, gap, o0, o1) in caras_comunes(A, B):
                if 0.01 < gap < 0.05:
                    aud.a(f"Tabique de solo {fmt(gap * 100, 0)} cm entre '{A.id}' y '{B.id}': probable descuadre",
                          xy(ea.axis, (o0 + o1) / 2, ea.c))
    exc = unary_union([p.buffer(0.12) for p in pilares + patinillos]) if (pilares or patinillos) else Polygon()
    for g in partes(muros.buffer(-0.19, join_style=2).difference(exc)):
        if g.area > 0.01:
            aud.a("Macizo de muro de mas de 0,38 m de grueso: ¿falta una estancia, un patinillo o hay un "
                  "descuadre de cotas?", g.centroid.coords[0])
    ctrl = spec.get("control", {})
    bx = exterior.bounds
    bi = RU.bounds
    for key, val, ref in (("exterior_dx", bx[2] - bx[0], "exterior"), ("exterior_dy", bx[3] - bx[1], "exterior"),
                          ("interior_dx", bi[2] - bi[0], "interior"), ("interior_dy", bi[3] - bi[1], "interior")):
        if key in ctrl and abs(num(ctrl[key]) - val) > 0.03:
            aud.a(f"Cota total {key.replace('_', ' ')}: el boceto dice {fmt(num(ctrl[key]))} m y el plano da "
                  f"{fmt(val)} m (diferencia {fmt(val - num(ctrl[key]))} m)")

    # 13. textos ----------------------------------------------------------------
    for R in E:
        libre = R.poly.difference(MU.buffer(0.05)) if muebles else R.poly
        zona = max(partes(libre), key=lambda q: q.area) if partes(libre) else R.poly
        c = polylabel(zona if zona.area > 0.6 else R.poly, 0.01)
        if spec.get("rotular_nombres", True):
            prims.append(dict(L="ESTANCIAS", k="tx", p=(c.x, c.y + 0.14), h=0.16, t=R.nombre.upper()))
            prims.append(dict(L="ESTANCIAS", k="tx", p=(c.x, c.y - 0.14), h=0.20, t=f"{fmt(R.poly.area)} m2"))
        else:
            prims.append(dict(L="ESTANCIAS", k="tx", p=(c.x, c.y), h=0.20, t=f"{fmt(R.poly.area)} m2"))
        R.etiqueta = (c.x, c.y)
    util = sum(R.poly.area for R in E if R.tipo != "terraza")
    terr = sum(R.poly.area for R in E if R.tipo == "terraza")
    resumen = f"SUP. UTIL: {fmt(util)} m2" + (f"  +  TERRAZAS: {fmt(terr)} m2" if terr else "") + \
              f"   SUP. CONSTRUIDA (contorno): {fmt(exterior.area)} m2"
    prims.append(dict(L="TEXTOS", k="tx", p=((bx[0] + bx[2]) / 2, bx[1] - 0.7), h=0.22, t=resumen))
    titulo = spec.get("titulo")
    if titulo:
        prims.append(dict(L="TEXTOS", k="tx", p=((bx[0] + bx[2]) / 2, bx[1] - 1.1), h=0.28, t=titulo.upper()))
    for p in patinillos:
        b = p.bounds
        prims.append(dict(L="PATINILLOS", k="pl", pts=list(p.exterior.coords)[:-1], cerr=True))
        prims.append(dict(L="PATINILLOS", k="pl", pts=[(b[0], b[1]), (b[2], b[3])], cerr=False))
        prims.append(dict(L="PATINILLOS", k="pl", pts=[(b[0], b[3]), (b[2], b[1])], cerr=False))

    cotas = calcula_cotas(E, ventanas, puertas, exterior, spec.get("_cotas_partes", []),
                          spec.get("_cotas_cadenas", []), pilares) if spec.get("acotar", True) else []
    os.makedirs(salida, exist_ok=True)
    escribe_dxf(os.path.join(salida, "plano.dxf"), muros, prims, cotas)
    escribe_png(os.path.join(salida, "plano.png"), muros, E, prims, aud, spec.get("titulo", "Plano"))
    if cotas:
        escribe_png(os.path.join(salida, "plano_cotas.png"), muros, E,
                    [p for p in prims if p["L"] not in ("MOBILIARIO",)], None, spec.get("titulo", "Plano"), cotas)
    informe = escribe_informe(os.path.join(salida, "informe.txt"), E, aud, util, terr, exterior, spec)
    return aud, informe


# --------------------------------------------------------------------- cotas
def calcula_cotas(E, ventanas, puertas, exterior, partes_cad=(), cadenas_cot=(), pilares=()):
    """Cotas lineales en metros: estancias, ventanas y totales (las puertas no se acotan).
    Cada cota: p1, p2 (puntos medidos), base (punto por donde pasa la linea) y ang."""
    cotas = []

    def luz(R, horizontal, desp):
        cx, cy = R.etiqueta
        b = R.poly.bounds
        for d in (desp, -desp, desp / 2, 0):
            if horizontal:
                y = cy + d
                linea = LineString([(b[0] - 1, y), (b[2] + 1, y)])
            else:
                x = cx + d
                linea = LineString([(x, b[1] - 1), (x, b[3] + 1)])
            seg = linea.intersection(R.poly)
            segs = [seg] if seg.geom_type == "LineString" else [g for g in getattr(seg, "geoms", []) if g.geom_type == "LineString"]
            segs = [g for g in segs if g.length > 0.3]
            if not segs:
                continue
            g = max(segs, key=lambda q: q.length)
            (x1, y1), (x2, y2) = g.coords[0], g.coords[-1]
            return dict(p1=(x1, y1), p2=(x2, y2), base=(x1, y1), ang=0 if horizontal else 90)
        return None

    # estancias del modo cadenas: se acota cada parte con la medida del boceto, por dentro
    por_estancia = {}
    for pc in partes_cad:
        por_estancia.setdefault(pc["estancia"], []).append(pc)
    estancias = {R.id: R for R in E}
    for rid, lst in por_estancia.items():
        R = estancias.get(rid)
        if R is None:
            continue
        zona = R.poly.buffer(0.005)
        for pc in lst:
            x0, y0, x1, y1 = pc["rect"]
            if pc["dx"]:
                for d in (0.35, (y1 - y0) - 0.35, (y1 - y0) / 2):
                    y = y0 + d
                    if zona.contains(LineString([(x0, y), (x1, y)])):
                        cotas.append(dict(p1=(x0, y), p2=(x1, y), base=(x0, y), ang=0))
                        break
            if pc["dy"]:
                for d in (0.35, (x1 - x0) - 0.35, (x1 - x0) / 2):
                    x = x0 + d
                    if zona.contains(LineString([(x, y0), (x, y1)])):
                        cotas.append(dict(p1=(x, y0), p2=(x, y1), base=(x, y0), ang=90))
                        break
    for R in E:
        if R.poly.area < 0.6 or R.id in por_estancia:
            continue
        for horizontal, desp in ((True, -0.45), (False, 0.75)):
            c = luz(R, horizontal, desp)
            if c:
                cotas.append(c)
    def extremos_pared(R, e, s0, s1):
        """Caras de las paredes perpendiculares mas proximas (ignora pilares de esquina): asi la
        posicion de la ventana se mide como en el boceto, desde la cara de la estancia."""
        franja = sbox(e.axis, e.s0 - 6, e.s1 + 6, e.c, e.c - sg(e) * 0.6).intersection(R.poly)
        pm = Point(xy(e.axis, (s0 + s1) / 2, e.c - sg(e) * 0.01))
        trozo = min(partes(franja), key=lambda q: q.distance(pm)) if partes(franja) else None
        if trozo is None:
            return e.s0, e.s1
        b_ = trozo.bounds
        return (b_[0], b_[2]) if e.axis == "h" else (b_[1], b_[3])

    def cadena_hueco(e, s0, s1, c_med, c_base, R=None):
        """esquina - hueco - esquina, como en el boceto (posicion y ancho de la ventana)"""
        ang = 0 if e.axis == "h" else 90
        a0, a1 = extremos_pared(R, e, s0, s1) if R is not None else (e.s0, e.s1)
        for a, b in ((a0, s0), (s0, s1), (s1, a1)):
            if b - a > 0.03:
                cotas.append(dict(p1=xy(e.axis, a, c_med), p2=xy(e.axis, b, c_med), base=xy(e.axis, a, c_base), ang=ang))

    for v in ventanas:
        e = v["e"]
        cext = v["c1"] if sg(e) > 0 else v["c0"]
        cadena_hueco(e, v["s0"], v["s1"], cext, cext + sg(e) * 0.45, v["R"])
    for d in puertas:  # balconeras y ventanas entre estancias (p. ej. hacia una galeria)
        if d["tipo"] in ("balconera", "ventana") and d["B"] is not None:
            ea = d["ea"]
            cadena_hueco(ea, d["s0"], d["s1"], ea.c, ea.c - sg(ea) * 0.30, d["A"])  # por dentro de la estancia
    # totales y tramos acotados de las cadenas
    for cc in cadenas_cot:
        if cc["b"] - cc["a"] < 0.05:
            continue
        if cc["eje"] == "x":
            cotas.append(dict(p1=(cc["a"], cc["perp"]), p2=(cc["b"], cc["perp"]), base=(cc["a"], cc["perp"]), ang=0))
        else:
            cotas.append(dict(p1=(cc["perp"], cc["a"]), p2=(cc["perp"], cc["b"]), base=(cc["perp"], cc["a"]), ang=90))
    # pilares y salientes: su tamano
    zona_est = unary_union([R.poly for R in E]).buffer(0.001)
    def tramo_libre(linea, extremo):
        g = linea.intersection(zona_est)
        segs = [g] if g.geom_type == "LineString" else [q for q in getattr(g, "geoms", []) if q.geom_type == "LineString"]
        segs = [q for q in segs if q.length > 0.03 and Point(extremo).distance(q) < 0.02]
        return segs[0] if segs else None

    for pl in pilares:
        x0, y0, x1, y1 = pl.bounds
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        # saliente largo (>= 0,5 m a lo largo de la pared): fondo libre que deja hasta la pared opuesta
        if (x1 - x0) >= 0.5 and (x1 - x0) > (y1 - y0):
            for ya, yb in ((y0, y0 - 8), (y1, y1 + 8)):
                g = tramo_libre(LineString([(cx, ya), (cx, yb)]), (cx, ya))
                if g is not None and g.length < 4:
                    (_, a_), (_, b_) = g.coords[0], g.coords[-1]
                    cotas.append(dict(p1=(cx, min(a_, b_)), p2=(cx, max(a_, b_)), base=(cx, min(a_, b_)), ang=90))
        elif (y1 - y0) >= 0.5:
            for xa, xb in ((x0, x0 - 8), (x1, x1 + 8)):
                g = tramo_libre(LineString([(xa, cy), (xb, cy)]), (xa, cy))
                if g is not None and g.length < 4:
                    (a_, _), (b_, _) = g.coords[0], g.coords[-1]
                    cotas.append(dict(p1=(min(a_, b_), cy), p2=(max(a_, b_), cy), base=(min(a_, b_), cy), ang=0))
        # posicion: solo a lo largo de la pared en la que se apoya (si esta en una esquina, ninguna)
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        libre = lambda px, py: zona_est.contains(Point(px, py))
        toca_ns = not libre(cx, y1 + 0.03) or not libre(cx, y0 - 0.03)
        toca_eo = not libre(x1 + 0.03, cy) or not libre(x0 - 0.03, cy)
        cand = [(tramo_libre(LineString([(x0 - 8, cy), (x0, cy)]), (x0, cy)), 0),
                (tramo_libre(LineString([(x1, cy), (x1 + 8, cy)]), (x1, cy)), 0)]
        cand = [c for c in cand if c[0] is not None and c[0].length < 4]
        if toca_ns and not toca_eo and cand and min(c[0].length for c in cand) > 0.03:
            g = min(cand, key=lambda c: c[0].length)[0]
            (ax_, ay_), (bx_, by_) = g.coords[0], g.coords[-1]
            cotas.append(dict(p1=(min(ax_, bx_), cy), p2=(max(ax_, bx_), cy), base=(min(ax_, bx_), cy), ang=0))
        cand = [(tramo_libre(LineString([(cx, y0 - 8), (cx, y0)]), (cx, y0)), 0),
                (tramo_libre(LineString([(cx, y1), (cx, y1 + 8)]), (cx, y1)), 0)]
        cand = [c for c in cand if c[0] is not None and c[0].length < 4]
        if toca_eo and not toca_ns and cand and min(c[0].length for c in cand) > 0.03:
            g = min(cand, key=lambda c: c[0].length)[0]
            (ax_, ay_), (bx_, by_) = g.coords[0], g.coords[-1]
            cotas.append(dict(p1=(cx, min(ay_, by_)), p2=(cx, max(ay_, by_)), base=(cx, min(ay_, by_)), ang=90))
        for yb in (y0 - 0.12, y1 + 0.12):
            if zona_est.contains(Point((x0 + x1) / 2, yb)):
                cotas.append(dict(p1=(x0, yb), p2=(x1, yb), base=(x0, yb), ang=0))
                break
        for xb in (x0 - 0.12, x1 + 0.12):
            if zona_est.contains(Point(xb, (y0 + y1) / 2)):
                cotas.append(dict(p1=(xb, y0), p2=(xb, y1), base=(xb, y0), ang=90))
                break
    bx = exterior.bounds
    cotas.append(dict(p1=(bx[0], bx[3]), p2=(bx[2], bx[3]), base=(bx[0], bx[3] + 0.8), ang=0))
    cotas.append(dict(p1=(bx[0], bx[1]), p2=(bx[0], bx[3]), base=(bx[0] - 0.8, bx[1]), ang=90))
    # extremos al centimetro cuando caen a menos de 2,5 mm (quita el milimetro de margen de calculo)
    sn = lambda z: round(z, 2) if abs(z - round(z, 2)) < 0.0025 else z
    for c in cotas:
        c["p1"], c["p2"] = tuple(sn(z) for z in c["p1"]), tuple(sn(z) for z in c["p2"])
    return cotas


def valor_cota(c):
    return abs(c["p2"][0] - c["p1"][0]) if c["ang"] == 0 else abs(c["p2"][1] - c["p1"][1])


# ------------------------------------------------------------------- salidas
def escribe_dxf(ruta, muros, prims, cotas=()):
    import ezdxf
    from ezdxf import const
    from ezdxf.enums import TextEntityAlignment
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.header["$MEASUREMENT"] = 1
    if "CALIBRI" not in doc.styles:
        doc.styles.add("CALIBRI", font="calibri.ttf")
    capas = {"MUROS": 7, "MUROS_RELLENO": 8, "PUERTAS": 3, "VENTANAS": 5, "MOBILIARIO": 2, "TEXTOS": 7,
             "ESTANCIAS": 4, "COTAS": 1, "PATINILLOS": 9}
    for n, c in capas.items():
        if n not in doc.layers:
            doc.layers.add(n, color=c)
    doc.layers.get("MOBILIARIO").dxf.lineweight = 13
    doc.layers.get("PUERTAS").dxf.lineweight = 13
    doc.layers.get("VENTANAS").dxf.lineweight = 13
    doc.layers.get("MUROS").dxf.lineweight = 50
    msp = doc.modelspace()
    for P in partes(muros):
        P = orient(P, 1.0)
        msp.add_lwpolyline(list(P.exterior.coords)[:-1], close=True, dxfattribs={"layer": "MUROS"})
        for r in P.interiors:
            msp.add_lwpolyline(list(r.coords)[:-1], close=True, dxfattribs={"layer": "MUROS"})
        h = msp.add_hatch(color=8, dxfattribs={"layer": "MUROS_RELLENO"})
        h.set_solid_fill(color=8)
        h.dxf.hatch_style = const.HATCH_STYLE_OUTERMOST
        h.paths.add_polyline_path(list(P.exterior.coords)[:-1], is_closed=True, flags=const.BOUNDARY_PATH_EXTERNAL)
        for r in P.interiors:
            h.paths.add_polyline_path(list(r.coords)[:-1], is_closed=True, flags=const.BOUNDARY_PATH_OUTERMOST)
    for p in prims:
        at = {"layer": p["L"]}
        if p["k"] == "pl":
            msp.add_lwpolyline(p["pts"], close=p["cerr"], dxfattribs=at)
        elif p["k"] == "ci":
            msp.add_circle(p["c"], p["r"], dxfattribs=at)
        elif p["k"] == "arc":
            msp.add_arc(p["c"], p["r"], p["a0"], p["a1"], dxfattribs=at)
        elif p["k"] == "tx":
            msp.add_text(p["t"], height=p["h"], dxfattribs=dict(at, style="CALIBRI")).set_placement(
                p["p"], align=TextEntityAlignment.MIDDLE_CENTER)
    estilo = {"dimtxsty": "CALIBRI", "dimlfac": 1.0, "dimpost": "", "dimlunit": 2, "dimtxt": 0.10, "dimasz": 0.06, "dimexe": 0.04, "dimexo": 0.0, "dimdec": 2, "dimdsep": ord(","),
              "dimtad": 1, "dimgap": 0.02, "dimtsz": 0.05, "dimclrd": 1, "dimclre": 1, "dimclrt": 1, "dimzin": 0}
    for c in cotas:
        dim = msp.add_linear_dim(base=c["base"], p1=c["p1"], p2=c["p2"], angle=c["ang"], dimstyle="EZDXF",
                                 override=estilo, dxfattribs={"layer": "COTAS"})
        dim.render()
    doc.saveas(ruta)


def escribe_png(ruta, muros, E, prims, aud, titulo, cotas=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import glob
    import logging
    from matplotlib import font_manager
    logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)
    for f_ in glob.glob("/usr/share/fonts/**/Carlito*.ttf", recursive=True) + \
            glob.glob("/usr/share/fonts/**/[Cc]alibri*.ttf", recursive=True):
        try:
            font_manager.fontManager.addfont(f_)
        except Exception:
            pass
    nombres = {f_.name for f_ in font_manager.fontManager.ttflist}
    # Calibri si existe; si no, Carlito (mismas medidas que Calibri); si no, la de serie
    plt.rcParams["font.family"] = [n for n in ("Calibri", "Carlito") if n in nombres] or ["DejaVu Sans"]
    from matplotlib.path import Path
    from matplotlib.patches import PathPatch, Arc, Circle
    b = muros.bounds
    W, H = b[2] - b[0] + 2.5, b[3] - b[1] + 3.0
    k = 15 / max(W, H)
    fig, ax = plt.subplots(figsize=(max(6, W * k), max(6, H * k)))
    for R in E:
        ax.add_patch(PathPatch(Path(list(R.poly.exterior.coords)), fc="#f4f1ea", ec="none"))
    for P in partes(muros):
        verts, codes = [], []
        for ring in [P.exterior] + list(P.interiors):
            cs = list(ring.coords)
            verts += cs
            codes += [Path.MOVETO] + [Path.LINETO] * (len(cs) - 2) + [Path.CLOSEPOLY]
        ax.add_patch(PathPatch(Path(verts, codes), fc="#4a4a4a", ec="black", lw=0.8))
    col = {"PUERTAS": "#1b7f2a", "VENTANAS": "#1f5fbf", "MOBILIARIO": "#b08900", "PATINILLOS": "#777777"}
    for p in prims:
        c = col.get(p["L"], "black")
        if p["k"] == "pl":
            pts = p["pts"] + ([p["pts"][0]] if p["cerr"] else [])
            ax.plot([q[0] for q in pts], [q[1] for q in pts], color=c, lw=0.7)
        elif p["k"] == "ci":
            ax.add_patch(Circle(p["c"], p["r"], fill=False, ec=c, lw=0.7))
        elif p["k"] == "arc":
            ax.add_patch(Arc(p["c"], 2 * p["r"], 2 * p["r"], theta1=p["a0"], theta2=p["a1"], ec=c, lw=0.6))
        elif p["k"] == "tx":
            ax.text(p["p"][0], p["p"][1], p["t"], ha="center", va="center", fontsize=6.5 if p["h"] < 0.21 else 8)
    for c in cotas or []:
        if c["ang"] == 0:
            yb = c["base"][1]
            a, b_ = (c["p1"][0], yb), (c["p2"][0], yb)
            for p, q in ((c["p1"], a), (c["p2"], b_)):
                ax.plot([p[0], q[0]], [p[1], q[1]], color="#c62828", lw=0.3)
            tx, ty, rot = (a[0] + b_[0]) / 2, yb + 0.07, 0
        else:
            xb = c["base"][0]
            a, b_ = (xb, c["p1"][1]), (xb, c["p2"][1])
            for p, q in ((c["p1"], a), (c["p2"], b_)):
                ax.plot([p[0], q[0]], [p[1], q[1]], color="#c62828", lw=0.3)
            tx, ty, rot = xb - 0.07, (a[1] + b_[1]) / 2, 90
        ax.plot([a[0], b_[0]], [a[1], b_[1]], color="#c62828", lw=0.6)
        for p in (a, b_):
            ax.plot([p[0] - 0.04, p[0] + 0.04], [p[1] - 0.04, p[1] + 0.04], color="#c62828", lw=0.8)
        ax.text(tx, ty, fmt(valor_cota(c)), color="#c62828", fontsize=5.5, ha="center", va="center", rotation=rot)
    for lista, pref, color in (((aud.err, "E", "red"), (aud.avi, "A", "darkorange")) if aud else ()):
        for i, (msg, pt) in enumerate(lista, 1):
            if pt is not None:
                ax.add_patch(Circle(pt, 0.22, fill=False, ec=color, lw=1.6))
                ax.text(pt[0] + 0.25, pt[1] + 0.25, f"{pref}{i}", color=color, fontsize=8, weight="bold")
    ax.set_aspect("equal")
    ax.set_xlim(b[0] - 1, b[2] + 1)
    ax.set_ylim(b[1] - 1.5, b[3] + 1)
    ax.set_title(f"{titulo} - {len(aud.err)} errores, {len(aud.avi)} avisos" if aud else f"{titulo} - cotas", fontsize=10)
    ax.axis("off")
    fig.savefig(ruta, dpi=170, bbox_inches="tight")
    plt.close(fig)


def escribe_informe(ruta, E, aud, util, terr, exterior, spec):
    L = ["INFORME DEL PLANO", "=" * 60, "", "SUPERFICIES UTILES"]
    for R in E:
        L.append(f"  {R.nombre:<28} {fmt(R.poly.area):>8} m2   ({R.tipo})")
    L.append(f"  {'TOTAL UTIL':<28} {fmt(util):>8} m2")
    if terr:
        L.append(f"  {'TERRAZAS':<28} {fmt(terr):>8} m2")
    L.append(f"  {'CONSTRUIDA (contorno)':<28} {fmt(exterior.area):>8} m2")
    L += ["", f"ERRORES ({len(aud.err)}) - hay que corregirlos en el JSON:"]
    L += [f"  E{i}. {m}" for i, (m, _) in enumerate(aud.err, 1)] or ["  ninguno"]
    L += ["", f"AVISOS ({len(aud.avi)}) - revisar; si son correctos, explicarlos al entregar:"]
    L += [f"  A{i}. {m}" for i, (m, _) in enumerate(aud.avi, 1)] or ["  ninguno"]
    sup = spec.get("supuestos", [])
    if sup:
        L += ["", "SUPUESTOS DE LECTURA DEL BOCETO:"] + [f"  - {s}" for s in sup]
    txt = "\n".join(L) + "\n"
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(txt)
    return txt


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        spec = json.load(f)
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(sys.argv[1]))
    os.makedirs(salida, exist_ok=True)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from cadenas import resolver
    spec, avisos_cad, errores_cad = resolver(spec, num(spec.get("espesores", {}).get("tabique", 0.08)))
    if errores_cad:
        print("ERRORES EN LAS CADENAS DE COTAS - corrige el JSON:")
        for i, m in enumerate(errores_cad, 1):
            print(f"  C{i}. {m}")
        sys.exit(2)
    with open(os.path.join(salida, "planta_resuelta.json"), "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
    spec["_avisos_cadenas"] = avisos_cad
    aud, informe = genera(spec, salida)
    try:
        import ezdxf
        from ezdxf import recover
        _, auditor = recover.readfile(os.path.join(salida, "plano.dxf"))
        informe += f"\nAuditoria DXF (ezdxf.recover): {len(auditor.errors)} errores\n"
        if auditor.errors:
            aud.e("El DXF tiene errores internos de formato")
    except Exception as ex:  # pragma: no cover
        informe += f"\nNo se pudo auditar el DXF: {ex}\n"
    print(informe)
    print(f"Archivos en: {os.path.abspath(salida)}  (plano.dxf, plano.png, plano_cotas.png, informe.txt, planta_resuelta.json)")
    sys.exit(2 if aud.err else 0)


if __name__ == "__main__":
    main()
