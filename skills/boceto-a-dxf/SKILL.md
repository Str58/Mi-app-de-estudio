---
name: "boceto-a-dxf"
description: "Convertir bocetos a mano de plantas de vivienda en planos DXF para AutoCAD (muros rellenos, medianeras, pilares, puertas, ventanas, mobiliario y superficies útiles), de forma autónoma, sin preguntas y en menos de 5 minutos, con auditoría automática de que el plano sea construible y habitable."
---

# Boceto a DXF (planos de vivienda)

Convierte el boceto a mano alzada de una planta en un DXF que AutoCAD 2020 o posterior abre directamente.
Si Ester da instrucciones nuevas sobre sus bocetos, esas instrucciones prevalecen sobre esta skill y conviene actualizarla.

## Reglas de oro
1. **No preguntar nunca.** Toda ambigüedad se resuelve con la tabla de decisiones de abajo, se dibuja y se anota en `"supuestos"`.
2. **Menos de 5 minutos.** No escribas código de geometría: el motor `scripts/plano.py` ya dibuja, comprueba y exporta. Tu trabajo es **leer el boceto y escribir un JSON**.
3. **No se entrega con errores.** Solo se entrega cuando el informe da **0 errores** y cada aviso está revisado.

## Flujo (con tiempos objetivo)
**0. Preparar (en paralelo, unos 20 s).** `SKILL_DIR` es la carpeta de esta skill. Las dos órdenes se lanzan en la misma respuesta:
```bash
pip install -q ezdxf shapely matplotlib pillow     # en segundo plano
python3 SKILL_DIR/scripts/zonas.py BOCETO.jpg TRABAJO/zonas      # completo + 4 zonas ampliadas + cotas_rojas.png
```

**1. Leer (unos 90 s).** Una sola pasada, en este orden:
1. Mira `completo.jpg` para entender la distribución: qué estancias hay y cuál es vecina de cuál.
2. Mira las 4 `zona_*.jpg` para leer cada cota, puerta y ventana.
3. Abre `cotas_rojas.png` solo si algún número no se lee.

Apunta mentalmente, para cada estancia:
- sus cotas interiores;
- sus vecinas por cada lado;
- sus puertas (con qué estancia comunican, en qué pared, posición y lado del arco);
- sus ventanas (pared, ancho y distancia a la esquina);
- sus pilares y sus muebles.

**2. Escribir `TRABAJO/planta.json` (unos 90 s).** Formato en `references/formato_json.md`. Para que las cuentas salgan solas:
- Coloca **una** estancia en el origen (la de la esquina SO o NO) y encadena el resto con `"pegado"`. Así no sumas coordenadas a mano y los tabiques salen siempre de 0,08.
- Las estancias en L, en U o con quiebros se describen con `"contorno"`, paso a paso **siguiendo las cotas del boceto**. Nunca las aproximes con un rectángulo.
- Pon en `"control"` las cotas totales del boceto, si las hay, para que el motor las compruebe.

**3. Generar y auditar (unos 30 s por vuelta, 3 vueltas como máximo).**
```bash
python3 SKILL_DIR/scripts/plano.py TRABAJO/planta.json TRABAJO/salida
```
- Corrige en el JSON cada error `E#`. El mensaje dice qué falla y la vista previa lo marca con un círculo rojo numerado.
- Revisa cada aviso `A#`. Corrígelo si es una mala lectura; si es fiel al boceto, explícalo al entregar.

**4. Mirar `plano.png` una vez (unos 20 s).** Repasa la lista de comprobación de abajo.

**5. Entregar.** Envía `plano.dxf` y `plano.png` con SendUserFile. Después, en pocas líneas: la tabla de superficies del informe, los supuestos tomados y los avisos que se mantienen. Las dudas se presentan como «supuse X; si es Y, dímelo y lo regenero» y nunca bloquean la entrega.

## Cómo leer el boceto (convenciones de Ester)
- **Negro: paredes.**
  - Tabique interior: 0,08, salvo otra cota.
  - **Medianera: 0,20.** Es la pared exterior sin estancia contigua y sin ventanas. El motor la deduce sola: una alineación de fachada sin ningún hueco pasa a ser medianera.
  - **Cerramiento exterior: 0,30.**
- **Rojo: cotas, siempre en metros.** El apóstrofe es la coma decimal: 2'5 = 2,50 y 0'53 = 0,53. Las cotas de estancia son **luces libres interiores**. Las cotas totales exteriores incluyen los muros.
- **Las líneas no están a escala**: manda la cota, nunca la proporción del dibujo. Los ángulos son de 90° salvo que se indique otra cosa.
- **Verde: puertas**, dibujadas como un triángulo o un arco.
  - El vértice en ángulo recto sobre la pared es la **bisagra**.
  - El lado perpendicular a la pared es la **hoja**.
  - El triángulo queda dentro de la estancia hacia la que **abre**.
  - Anchos: **0,80** las interiores y **0,90** la de entrada, salvo cota.
- **Azul: ventanas**, dibujadas como dos rayitas perpendiculares a la pared que marcan el inicio y el fin del hueco. Junto a ellas suelen venir su ancho y su distancia a una esquina. La altura `h=` se ignora.
- **Amarillo: mobiliario y aparatos sanitarios.** Se colocan contra la pared donde estén dibujados y, si no hay cota, con las medidas por defecto.
- **Pilares y salientes** marcados en las paredes: 0,30×0,30 si no tienen cota.
- **Baños y cocinas**: si a la cadena de cotas le faltan unos centímetros, son baldosas (no hagas nada). Si faltan más, hay un **patinillo de instalaciones** entre las paredes.
- Las estancias pueden tener cualquier forma ortogonal: en L, en U, con quiebros o con remetidos.

## Tabla de decisiones (sustituye a cualquier pregunta)
| Situación | Decisión |
|---|---|
| Cota ilegible | Deducirla de la cadena: total menos el resto de cotas y tabiques. Si no hay cadena, de la cota paralela de la estancia vecina. Si tampoco, por proporción con una cota conocida. Anotar el supuesto. |
| La cadena de cotas no cierra | Hasta 0,10 en baño o cocina: baldosas, se ignora. Entre 0,10 y 0,60 junto a baño o cocina: patinillo. En otro caso, absorber la diferencia en la estancia **sin cota** o en el pasillo. Anotar el supuesto. |
| Estancia con una sola cota | La otra dimensión sale de la vecina alineada (misma fachada o mismo fondo). |
| Puerta sin posición | Junto a la esquina donde esté dibujada (`desde` 0,10 a 0,15). Si está a media pared, centrada. |
| Sentido de apertura dudoso | No indicarlo: el motor elige el que cabe sin chocar. |
| Ventana sin cotas | Centrada en la pared de fachada de esa estancia: 1,20 en dormitorios, 1,50 a 2,00 en el salón, 1,00 en la cocina, 0,60 en el baño. |
| Pasillo o recibidor sin cota de ancho | 1,00 (mínimo 0,90). |
| Cocina abierta al salón (sin línea entre ambos) | Estancias pegadas, declaradas en `"abiertas"`. |
| Galería, tendedero o terraza cerrada | Su pared hacia las estancias interiores es la antigua fachada: **0,30**, que se deja como hueco entre ellas. |
| Una cadena horizontal no cuadra con otra paralela | **Nunca engordar un tabique** para absorberlo: los tabiques son siempre de 0,08 y rectos. La diferencia va a la circulación (vestíbulo o pasillo). Si con eso la pieza queda con un ancho absurdo, va a la galería o al cuerpo saliente, y se anota. |
| Hueco en un tabique sin dibujo de puerta | `"tipo":"paso"`. |
| No se sabe si una pared exterior es medianera | Dejar el modo automático: si no tiene huecos, es medianera. |
| No queda claro dónde está la entrada | La puerta que da a la escalera, el rellano o la calle, normalmente en el recibidor o el pasillo, con 0,90. |
| Estancia sin puerta dibujada | Añadir una de 0,80 hacia la circulación más próxima y anotar el supuesto. |
| Elemento indescifrable que no afecta a la geometría | Omitirlo y anotarlo. |

## Lista de comprobación final (sobre `plano.png`)
El motor ya comprueba casi todo esto. Repasar a la vista:
- Cada estancia está cerrada por paredes en todo su perímetro, salvo los huecos de puertas, pasos y ventanas.
- Todas las estancias tienen puerta y se llega a ellas desde la entrada por pasillos y distribuidores.
- Ninguna puerta abre contra un muro, hacia fuera (salvo la de entrada) o donde no se puede llegar.
- Las ventanas solo están en fachada, nunca en medianeras ni entre estancias.
- No hay volúmenes sueltos. Los cuerpos salientes (despensas, trasteros, galerías) van adosados donde marca el boceto.
- Las formas en L o con quiebros siguen el boceto vértice a vértice.
- Las superficies son razonables: dormitorio de 6 m² o más, baño de 2,5 m² o más, salón de 12 m² o más. Una cifra rara suele ser una cota mal leída.

## Estilo del DXF (lo aplica el motor)
Referencia: plano «boceto-717_final» (arquitecto C. Soto, 1:50).
- R2010, unidades en metros.
- Capas: MUROS, MUROS_RELLENO, PUERTAS, VENTANAS, MOBILIARIO, TEXTOS, COTAS y PATINILLOS.
- Muros con sombreado sólido gris de estilo *outermost*.
- Puertas: hoja como rectángulo de 0,04 más un arco de 90°.
- Ventanas y balconeras: carpintería de 3 líneas finas.
- Armario: rectángulo con una X.
- Cada estancia lleva su nombre y su **superficie útil** («10,93 m2»), sin cotas lineales.
- Al pie, la superficie útil total y la construida.
- Para pasar a DWG: en AutoCAD, `GUARDARCOMO` con formato 2018.

## Si hace falta tocar el motor
`scripts/plano.py` es paramétrico: espesores en `ESP_DEF`, medidas de muebles en `MUEBLES` y mínimos de auditoría en `MINIMOS`. Si se cambia una convención de dibujo, se cambia ahí y en esta skill, no en un script improvisado.
