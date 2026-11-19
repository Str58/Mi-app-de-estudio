# -*- coding: utf-8 -*-
"""
cadenas.py - cuadre automatico de cotas para boceto-a-dxf.

Permite describir la planta como en el boceto: cada estancia con sus cotas
(dx, dy) y filas/columnas de estancias encadenadas con sus muros. El motor
calcula todas las coordenadas, detecta que cota rompe cada cadena y reparte
las diferencias:
  - los muros son fijos (tabique 0,08 por defecto, o el que se indique);
  - las estancias de circulacion (o "flexible": true) absorben primero;
  - si una cota normal no cuadra, el ajuste robusto (L1) la concentra en esa
    cota en vez de repartirla por todo el plano, y se avisa;
  - una cota dudosa se escribe con alternativas (["1,58","1,28"]) y se elige
    la que hace cerrar las cadenas.
"""
import itertools
import math

import numpy as np
from shapely.geometry import box
from shapely.ops import unary_union

FIJO = 1e9      # peso de las ecuaciones duras (alineaciones, fachadas, partes que se tocan)
NORMAL = 50.0   # peso de la cota de una estancia: intocable (antes que tocarla, engorda un tabique)
FLEX = 0.2      # peso de la cota de una estancia de circulacion / flexible: absorbe primero
HUMEDA = 0.3    # banos, aseos, cocinas, lavaderos: pueden CRECER hasta 10 cm (alicatado: el boceto se queda corto)
MAX_HUMEDA = 0.10
MURO = 0.6      # muro grueso (fachada, galeria, medianera): puede engordar (= saliente)
CIRCULA = 1.5   # pasillo / vestibulo / distribuidor con cota: cede antes que un tabique
TABIQUE = 3.0   # tabique (<= 0,12): solo engorda como ultimo recurso
TRAMO = 20.0    # peso de un tramo acotado {"cota": x}
TOTAL = 20.0    # peso de una cota total de cadena
CIRC = ("pasillo", "distrib", "recib", "hall", "vestib", "entrada")


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).strip().replace("'", ".").replace(",", "."))


def _fmt(v):
    return f"{v:.2f}".replace(".", ",")


def es_modo_cadena(r):
    geo = ("rect" in r) or ("contorno" in r) or ("poligono" in r)
    return not geo and (("dx" in r and "dy" in r) or "union" in r)


def resolver(spec, tabique=0.08):
    """Devuelve (spec_nuevo, avisos, errores). Si no hay estancias en modo
    cadena, devuelve el spec intacto."""
    ests = spec.get("estancias", [])
    cad = [r for r in ests if es_modo_cadena(r) and "union" not in r]
    if not cad:
        return spec, [], []
    avisos, errores = [], []
    ids = [r["id"] for r in cad]
    R = {r["id"]: r for r in cad}

    # ---------------- variables
    var = {}

    def v(nombre):
        if nombre not in var:
            var[nombre] = len(var)
        return var[nombre]

    for i in ids:
        for k in ("X", "Y", "W", "H"):
            v(f"{k}:{i}")

    duras, previas = [], []   # (coefs{idx:val}, rhs, peso, descripcion)
    alternativas = []         # (indice_variable, [valores], id, eje)

    def flexible(r):
        # toda cota escrita se respeta, tambien la de pasillos y vestibulos: solo absorbe lo que
        # se marca expresamente como flexible (piezas sin medir); el resto lo absorben los muros
        return bool(r.get("flexible", False))

    duenos_u = {p_: u for u in ests if "union" in u for p_ in u["union"]}

    def humeda(r):
        u = duenos_u.get(r["id"], {})
        txt = " ".join(str(z.get(k_, "")) for z in (r, u) for k_ in ("id", "nombre", "tipo")).lower()
        return any(k_ in txt for k_ in ("bano", "baño", "aseo", "cocina", "lavadero", "wc"))

    def circulacion(r):
        u = duenos_u.get(r["id"], {})
        txt = " ".join(str(z.get(k_, "")) for z in (r, u) for k_ in ("id", "nombre", "tipo")).lower()
        return any(k_ in txt for k_ in CIRC) or "circulacion" in txt

    for i in ids:
        r = R[i]
        for eje, k in (("dx", "W"), ("dy", "H")):
            val = r[eje]
            idx = v(f"{k}:{i}")
            if val in ("?", None):
                continue
            peso = FLEX if flexible(r) else NORMAL
            if isinstance(val, list):
                alternativas.append((idx, [_num(x) for x in val], i, eje, peso))
                previas.append([{idx: 1}, _num(val[0]), peso, f"cota {eje} de '{i}'", ("alt", len(alternativas) - 1)])
            elif peso == NORMAL and humeda(r):
                previas.append([{idx: 1}, _num(val), HUMEDA, f"cota {eje} de '{i}'", ("humeda",)])
            elif peso == NORMAL and circulacion(r):
                previas.append([{idx: 1}, _num(val), CIRCULA, f"cota {eje} de '{i}'", ("circ",)])
            else:
                previas.append([{idx: 1}, _num(val), peso, f"cota {eje} de '{i}'", None])

    def extremo(ref, eje):
        """Coeficientes de una cara/fachada: numero, nombre de fachada o {estancia, lado}."""
        if isinstance(ref, (int, float)):
            return {}, -float(ref)
        if isinstance(ref, str):
            try:
                return {}, -_num(ref)
            except ValueError:
                return {v("F:" + ref): 1}, 0.0
        i, lado = ref["estancia"], ref["lado"].upper()
        P, D = ("X", "W") if eje == "x" else ("Y", "H")
        if lado in ("O", "W", "S"):
            return {v(f"{P}:{i}"): 1}, 0.0
        return {v(f"{P}:{i}"): 1, v(f"{D}:{i}"): 1}, 0.0

    # ---------------- cadenas
    union_find = {"x": {}, "y": {}}

    def uf(eje, a, b):
        p = union_find[eje]
        p.setdefault(a, a)
        p.setdefault(b, b)

        def raiz(z):
            while p[z] != z:
                p[z] = p[p[z]]
                z = p[z]
            return z
        p[raiz(a)] = raiz(b)

    anclas = {"x": set(), "y": set()}
    seg_n = 0
    acotar = []  # (eje, coefs_inicio, coefs_fin, estancias de la cadena)
    fachadas = []  # (eje, estancia, "ini"/"fin", nombre de fachada): caras que deben quedar en la fachada
    for nc, c in enumerate(spec.get("cadenas", []), 1):
        eje = c["eje"].lower()
        P, D = ("X", "W") if eje == "x" else ("Y", "H")
        etiqueta = c.get("nombre", f"cadena {nc} ({eje})")
        piezas = []  # (inicio_coefs, fin_coefs) de cada elemento solido, y muros entre ellos
        muro_pend = None
        for it in c["items"]:
            if isinstance(it, dict) and ("muro" in it or "hueco" in it):
                muro_pend = _num(it.get("muro", it.get("hueco")))
                continue
            if isinstance(it, str):
                if it not in R:
                    errores.append(f"{etiqueta}: '{it}' no es una estancia con dx/dy")
                    continue
                ini = {v(f"{P}:{it}"): 1}
                fin = {v(f"{P}:{it}"): 1, v(f"{D}:{it}"): 1}
                nodo = it
            else:  # segmento acotado sin estancia: {"cota": 2.52} o {"cota": "?"}
                seg_n += 1
                s0, sl = v(f"S0:{seg_n}"), v(f"SL:{seg_n}")
                if it.get("cota") not in ("?", None):
                    previas.append([{sl: 1}, _num(it["cota"]), TRAMO, f"{etiqueta}: tramo de {_fmt(_num(it['cota']))}", None])
                ini, fin, nodo = {s0: 1}, {s0: 1, sl: 1}, f"seg{seg_n}"
                if it.get("cota") not in ("?", None):
                    acotar.append([eje, ini, fin, None, None, None])
            if piezas:
                w = tabique if muro_pend is None else muro_pend
                coef = dict(ini)
                for k2, x in piezas[-1][1].items():
                    coef[k2] = coef.get(k2, 0) - x
                if w <= 0:  # partes de una misma estancia: se tocan siempre
                    duras.append([coef, w, FIJO, f"{etiqueta}: union de partes"])
                else:  # el muro puede engordar (saliente) para absorber un descuadre
                    mv = v(f"M:{len(var)}")
                    coef[mv] = coef.get(mv, 0) - 1
                    duras.append([coef, 0.0, FIJO, f"{etiqueta}: muro"])
                    previas.append([{mv: 1}, w, TABIQUE if w <= 0.12 else MURO,
                                    f"{etiqueta}: muro entre '{piezas[-1][2]}' y '{nodo}'", ("muro",)])
                uf(eje, piezas[-1][2], nodo)
            piezas.append((ini, fin, nodo))
            muro_pend = None
        if not piezas:
            continue
        for clave, cara in (("desde", piezas[0][0]), ("hasta", piezas[-1][1])):
            pieza = piezas[0][2] if clave == "desde" else piezas[-1][2]
            if clave in c and isinstance(c[clave], str) and pieza in R:
                try:
                    _num(c[clave])
                except ValueError:
                    fachadas.append((eje, pieza, "ini" if clave == "desde" else "fin", c[clave]))
            if clave in c:
                coefs, k0 = extremo(c[clave], eje)
                coef = dict(cara)
                for k2, x in coefs.items():
                    coef[k2] = coef.get(k2, 0) - x
                duras.append([coef, -k0 if coefs == {} else 0.0, FIJO, f"{etiqueta}: {clave}"])
                if coefs == {}:
                    anclas[eje].add(piezas[0][2] if clave == "desde" else piezas[-1][2])
                else:
                    uf(eje, piezas[0][2] if clave == "desde" else piezas[-1][2], "F:" + str(c[clave]) if isinstance(c[clave], str) else str(c[clave]))
                    if isinstance(c[clave], dict):
                        uf(eje, piezas[0][2], c[clave]["estancia"])
        rooms_c = [p_[2] for p_ in piezas if p_[2] in R]
        for a_ in acotar:
            if a_[3] is None:
                a_[3] = rooms_c
        if "total" in c:
            acotar.append([eje, piezas[0][0], piezas[-1][1], rooms_c, piezas[0][2], piezas[-1][2]])
            coef = dict(piezas[-1][1])
            for k2, x in piezas[0][0].items():
                coef[k2] = coef.get(k2, 0) - x
            # una cota total pesa la mitad que la de una estancia: suele ser la menos fiable
            previas.append([coef, _num(c["total"]), TOTAL * _num(c.get("peso", 1)), f"{etiqueta}: total {_fmt(_num(c['total']))}", None])

    # ---------------- alineaciones: cara de A (+ sep) = cara de B
    for al in spec.get("alineaciones", []):
        eje = al["eje"].lower()
        if "estancias" in al:  # todas con la misma cara
            lst = al["estancias"]
            pares = [((lst[0], al["lado"]), (b, al["lado"]), 0.0) for b in lst[1:]]
        else:
            pares = [((al["a"], al["lado_a"]), (al["b"], al["lado_b"]), _num(al.get("sep", 0)))]
        for (a, la), (b, lb), sep in pares:
            if a not in R or b not in R:
                errores.append(f"Alineacion: '{a}' o '{b}' no es una estancia con dx/dy")
                continue
            ca, _ = extremo({"estancia": a, "lado": la}, eje)
            cb, _ = extremo({"estancia": b, "lado": lb}, eje)
            coef = dict(cb)
            for k2, x in ca.items():
                coef[k2] = coef.get(k2, 0) - x
            duras.append([coef, sep, FIJO, f"alineacion {a}-{b}"])
            uf(eje, a, b)

    # ---------------- comprobar que cada estancia esta ligada en cada eje
    for eje in ("x", "y"):
        p = union_find[eje]

        def raiz(z):
            while p.get(z, z) != z:
                z = p[z]
            return z
        grupos = {}
        for i in ids:
            if i not in p:
                errores.append(f"'{i}' no aparece en ninguna cadena del eje {eje}: su posicion es desconocida")
                continue
            grupos.setdefault(raiz(i), []).append(i)
        anclados = [g for g in grupos.values() if any(raiz(a) == raiz(g[0]) for a in anclas[eje])]
        sueltos = [g for g in grupos.values() if g not in anclados]
        if not anclados and sueltos:  # sin ancla: fachada O (eje x) o S (eje y) = 0
            g = max(sueltos, key=len)
            sueltos.remove(g)
            fach = "F:O" if eje == "x" else "F:S"
            P = "X" if eje == "x" else "Y"
            if fach in var and raiz(fach) == raiz(g[0]):
                duras.append([{var[fach]: 1}, 0.0, FIJO, f"origen {eje}"])
            else:
                duras.append([{v(f"{P}:{g[0]}"): 1}, 0.0, FIJO, f"origen {eje}"])
        for g in sueltos:
            errores.append(f"Eje {eje}: {', '.join(g)} no estan encadenadas con el resto de la planta")

    if errores:
        return spec, avisos, errores

    # ---------------- resolucion robusta (IRLS ~ L1) con alternativas
    n = len(var)
    reg = 1e-6

    def resuelve(prev):
        # conjunto activo: un muro nunca adelgaza; si el ajuste lo intenta, se fija a su espesor
        extra = []
        for _ in range(12):
            x, res, coste = resuelve_base(prev, extra)
            ya = [e[0] for e in extra]
            nuevos = []
            for i, (p, r_) in enumerate(zip(prev, res)):
                if i in ya or p[4] not in (("muro",), ("humeda",)):
                    continue
                if r_ < -0.002:  # no puede adelgazar / encoger
                    nuevos.append((i, p))
                elif p[4] == ("humeda",) and r_ > MAX_HUMEDA + 0.002:  # crece como maximo 10 cm
                    nuevos.append((i, [p[0], p[1] + MAX_HUMEDA, p[2], p[3], p[4]]))
            if not nuevos:
                return x, res, coste
            extra += nuevos
        return x, res, coste

    def resuelve_base(prev, extra):
        fijas = {i for i, _ in extra}
        w = np.array([p[2] for p in prev])
        x = None
        for _ in range(80):
            filas, b = [], []
            for coef, rhs, peso, _d in duras + [[p[0], p[1], FIJO, p[3]] for _i, p in extra]:
                f = np.zeros(n)
                for k2, val in coef.items():
                    f[k2] = val
                filas.append(f * math.sqrt(peso))
                b.append(rhs * math.sqrt(peso))
            for k_, ((coef, rhs, peso, _d, _a), wi) in enumerate(zip(prev, w)):
                if k_ in fijas:
                    continue
                f = np.zeros(n)
                for k2, val in coef.items():
                    f[k2] = val
                filas.append(f * math.sqrt(wi))
                b.append(rhs * math.sqrt(wi))
            A = np.vstack(filas + [np.eye(n) * reg])
            bb = np.concatenate([b, np.zeros(n)])
            x = np.linalg.lstsq(A, bb, rcond=None)[0]
            res = np.array([sum(val * x[k2] for k2, val in c.items()) - r for c, r, _p, _d, _a in prev])
            w = np.array([p[2] for p in prev]) / np.maximum(np.abs(res), 0.002)
        res = np.array([sum(val * x[k2] for k2, val in c.items()) - r for c, r, _p, _d, _a in prev])
        coste = float(sum(p[2] * abs(r_) for p, r_ in zip(prev, res)))
        return x, res, coste

    combos = list(itertools.product(*[a[1] for a in alternativas])) if alternativas else [()]
    if len(combos) > 256:
        combos = combos[:256]
        avisos.append("Demasiadas cotas con alternativas: solo se han probado 256 combinaciones")
    mejor = None
    for combo in combos:
        prev = [list(p) for p in previas]
        for p in prev:
            if p[4] and p[4][0] == "alt":
                p[1] = combo[p[4][1]]
        x, res, coste = resuelve(prev)
        if mejor is None or coste < mejor[2] - 1e-6:
            mejor = (x, res, coste, combo, prev)
    x, res, coste, combo, prev = mejor
    for (idx, vals, i, eje, _p), elegido in zip(alternativas, combo):
        otras = ", ".join(_fmt(z) for z in vals if z != elegido)
        avisos.append(f"Cota dudosa de '{i}' ({eje}): se elige {_fmt(elegido)} (frente a {otras}) porque es la que cierra las cadenas")

    # residuos de ecuaciones duras = cadenas imposibles
    for coef, rhs, peso, d in duras:
        r_ = sum(val * x[k2] for k2, val in coef.items()) - rhs
        if abs(r_) > 0.005:
            errores.append(f"{d}: no se puede cumplir (desfase {_fmt(r_)} m). Revisa esa cadena.")
    # ajustes de cotas
    for (coef, rhs, peso, d, _a), r_ in zip(prev, res):
        if abs(r_) < 0.015:
            continue
        valor = rhs + r_
        if _a == ("humeda",):
            avisos.append(f"Estancia humeda: {d} pasa de {_fmt(rhs)} a {_fmt(valor)} (+{_fmt(r_)}); el boceto "
                          f"se queda corto por el alicatado y absorbe el descuadre")
            continue
        if _a == ("muro",):
            avisos.append(f"Saliente: {d} pasa de {_fmt(rhs)} a {_fmt(valor)} (+{_fmt(r_)}) para respetar las cotas "
                          f"de las estancias. Comprueba en el boceto si hay ahi un saliente o pilar.")
        elif peso in (FLEX, CIRCULA):
            avisos.append(f"Ajuste: {d} pasa de {_fmt(rhs)} a {_fmt(valor)} ({'+' if r_ > 0 else ''}{_fmt(r_)}); "
                          f"absorbe el descuadre de las cadenas por ser circulacion")
        else:
            avisos.append(f"Descuadre: {d} ({_fmt(rhs)}) no cuadra con el resto; queda en {_fmt(valor)} "
                          f"({'+' if r_ > 0 else ''}{_fmt(r_)}). Si el boceto es correcto, revisa otra cota de esa cadena.")

    # ---------------- construir poligonos
    val = lambda k: float(x[var[k]])
    # agrupar caras casi coincidentes (< 3 mm) para que queden exactamente alineadas
    caras = {"x": [], "y": []}
    for i in ids:
        caras["x"] += [val(f"X:{i}"), val(f"X:{i}") + val(f"W:{i}")]
        caras["y"] += [val(f"Y:{i}"), val(f"Y:{i}") + val(f"H:{i}")]
    mapa = {}
    for eje, lst in caras.items():
        lst = sorted(lst)
        grupo = [lst[0]]
        for z in lst[1:] + [None]:
            if z is not None and z - grupo[-1] < 0.003:
                grupo.append(z)
                continue
            m = round(sum(grupo) / len(grupo), 2)  # geometria exacta al centimetro
            for g_ in grupo:
                mapa[(eje, round(g_, 6))] = m
            if z is not None:
                grupo = [z]
    snap = lambda eje, z: mapa.get((eje, round(z, 6)), round(z, 2))
    rects = {}
    for i in ids:
        # caras redondeadas al milimetro: dos caras que deben coincidir quedan identicas
        # origen redondeado al cm y fin = origen + medida al cm: cada estancia mide exactamente su cota
        x0, y0 = snap("x", val(f"X:{i}")), snap("y", val(f"Y:{i}"))
        W, H = round(val(f"W:{i}"), 2), round(val(f"H:{i}"), 2)
        # las estancias que tocan una fachada con nombre quedan exactamente en ella (sin escalones de 1 cm)
        for eje_f, pieza, lado, nombre in fachadas:
            if pieza != i:
                continue
            F = round(val("F:" + nombre), 2)
            if eje_f == "x":
                x0 = F if lado == "ini" else round(F - W, 2)
            else:
                y0 = F if lado == "ini" else round(F - H, 2)
        x1, y1 = round(x0 + W, 2), round(y0 + H, 2)
        X, Y = x0, y0
        if W <= 0.05 or H <= 0.05:
            errores.append(f"'{i}' sale con dimension nula o negativa ({_fmt(W)} x {_fmt(H)}): revisa sus cadenas")
            W, H = max(W, 0.1), max(H, 0.1)
        rects[i] = box(x0, y0, x0 + W, y0 + H)
    rects0 = dict(rects)  # rectangulos completos: son los que lleva la cota del boceto
    for i in ids:
        for rc in R[i].get("recortes", []):
            if "por" in rc:
                m = _num(rc.get("muro", tabique))
                b = rects[rc["por"]].bounds
                rects[i] = rects[i].difference(box(b[0] - m, b[1] - m, b[2] + m, b[3] + m))
            else:
                bx = rects[i].bounds
                k = rc["esquina"].upper().replace("W", "O")
                dx, dy = _num(rc["dx"]), _num(rc["dy"])
                x0 = bx[2] - dx if "E" in k else bx[0]
                y0 = bx[3] - dy if "N" in k else bx[1]
                rects[i] = rects[i].difference(box(x0, y0, x0 + dx, y0 + dy))

    def a_poligono(g, nombre):
        g = g.buffer(0)
        if g.geom_type != "Polygon" and len(getattr(g, "geoms", [])) > 1:
            errores.append(f"'{nombre}' queda partida en varios trozos: sus partes no se tocan")
            g = max(g.geoms, key=lambda q: q.area)
        g = g.simplify(0.0015)
        return [[round(a, 3), round(b_, 3)] for a, b_ in list(g.exterior.coords)[:-1]]

    nuevas, resto = [], []
    for r in ests:
        if es_modo_cadena(r) and "union" not in r:
            if r.get("parte"):
                continue
            nr = {k: vv for k, vv in r.items() if k not in ("dx", "dy", "recortes", "flexible")}
            nr["poligono"] = a_poligono(rects[r["id"]], r["id"])
            nuevas.append(nr)
        elif "union" in r:
            nr = {k: vv for k, vv in r.items() if k != "union"}
            faltan = [p for p in r["union"] if p not in rects]
            if faltan:
                errores.append(f"'{r['id']}': partes inexistentes {faltan}")
                continue
            u = unary_union([rects[p].buffer(0.006, join_style=2) for p in r["union"]]).buffer(-0.006, join_style=2)
            nr["poligono"] = a_poligono(u, r["id"])
            nuevas.append(nr)
        else:
            resto.append(r)
    out = dict(spec)
    out["estancias"] = nuevas + resto
    duenos = {p: r["id"] for r in ests if "union" in r for p in r["union"]}
    ev = lambda cf: sum(val_ * x[k_] for k_, val_ in cf.items())
    out["_cotas_cadenas"] = []
    for eje_, ci, cf, rooms_c, ini_id, fin_id in acotar:
        a_, b_ = ev(ci), ev(cf)
        k_a, k_b = (0, 2) if eje_ == "x" else (1, 3)
        a_ = rects0[ini_id].bounds[k_a] if ini_id in rects0 else snap(eje_, a_)
        b_ = rects0[fin_id].bounds[k_b] if fin_id in rects0 else round(a_ + round(b_ - ev(ci), 2), 2)
        rangos = [rects0[r_].bounds for r_ in rooms_c if r_ in rects0]
        if not rangos:
            continue
        k0, k1 = (1, 3) if eje_ == "x" else (0, 2)
        lo, hi = max(r_[k0] for r_ in rangos), min(r_[k1] for r_ in rangos)
        if lo >= hi:
            lo, hi = rangos[0][k0], rangos[0][k1]
        out["_cotas_cadenas"].append({"eje": eje_, "a": round(a_, 2), "b": round(b_, 2),
                                      "perp": round(lo + (hi - lo) * 0.25, 2)})
    out["_cotas_partes"] = [
        {"estancia": duenos.get(i, i), "rect": [round(z, 3) for z in rects0[i].bounds],
         "dx": R[i]["dx"] not in ("?", None), "dy": R[i]["dy"] not in ("?", None)} for i in ids]
    for k in ("cadenas", "alineaciones"):
        out.pop(k, None)
    return out, avisos, errores
