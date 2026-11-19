# Formato de `planta.json` (entrada de `scripts/plano.py`)

Ejemplo completo y válido: `ejemplos/piso_ejemplo.json`. Cópialo y adáptalo.

## Convenciones
- Metros. Se admite número o texto con coma o apóstrofe (`"2'5"` = 2,50).
- **Norte = arriba del boceto.** X crece hacia el Este (derecha) e Y hacia el Norte (arriba).
- Las estancias se describen por su **cara interior** (luz libre). **No se dibujan muros**: el tabique
  es el hueco que se deja entre dos estancias (0,08 normalmente) y los muros exteriores los genera el motor.
- `lado` / `contra` / `esquina`: `N`, `S`, `E`, `O` (también vale `W`) y `NE`, `NO`, `SE`, `SO`.
- Posiciones a lo largo de una pared (puertas, ventanas, muebles, pilares):
  - `desde`: distancia desde el extremo **Oeste** (en paredes horizontales) o **Sur** (en verticales) hasta el borde del elemento;
  - `desde_fin`: lo mismo desde el extremo Este o Norte;
  - `en`: coordenada absoluta del **centro**;
  - sin ninguna de las tres, el elemento queda centrado.
  - En las puertas interiores el tramo de referencia es la parte de pared que comparten las dos estancias.

## Modo cadenas (recomendado): el motor cuadra las cotas
Las estancias se describen con sus cotas, sin coordenadas, y se dicen las filas y columnas del boceto. El módulo `scripts/cadenas.py` calcula las posiciones con un ajuste robusto:
- los muros son fijos;
- la circulación absorbe primero los descuadres;
- si una cota normal no cuadra, se concentra el ajuste en esa cota y se avisa;
- de las cotas con alternativas, elige la que cierra.

Ejemplo real completo: `ejemplos/bergamin/planta_cadenas.json`.

```jsonc
"estancias": [
  {"id":"cocina", "dx":3.48, "dy":2.46},
  {"id":"bano", "nombre":"Baño", "dx":3.46, "dy":["1'58","1'28"]},   // cota dudosa: dos lecturas
  {"id":"salon", "dx":4.50, "dy":3.64, "recortes":[{"por":"galeria","muro":0.30}]},   // entrante que deja la galería
  {"id":"despensa", "dx":0.98, "dy":1.59, "recortes":[{"esquina":"NE","dx":0.30,"dy":0.30}]},
  {"id":"pasillo_alto", "parte":true, "tipo":"circulacion", "dx":1.00, "dy":"?"},  // "?" = sin cota
  {"id":"pasillo_bajo", "parte":true, "tipo":"circulacion", "dx":1.28, "dy":"?"},
  {"id":"distribuidor", "nombre":"Pasillo", "union":["pasillo_bajo","pasillo_alto"]}  // forma en L = unión de partes
],
"cadenas": [   // eje x: de oeste a este; eje y: de sur a norte
  {"nombre":"fila cocina", "eje":"x", "items":["galeria", {"muro":0.30}, "cocina", "pasillo_alto", "dorm1"],
   "desde":"O", "hasta":"E"},
  {"nombre":"columna", "eje":"y", "items":["comedor", "salon", "bano", "cocina"], "desde":"S", "hasta":"N"},
  {"nombre":"pasillo 8,43", "eje":"y", "items":["vestibulo", {"muro":0}, "pasillo_bajo"], "total":8.43},
  {"eje":"y", "items":["comedor", {"cota":2.52}, {"muro":0.30}, "galeria"]}   // tramo acotado que no es estancia
],
"alineaciones": [
  {"eje":"x", "lado":"O", "estancias":["pasillo_bajo","pasillo_alto"]},          // misma cara oeste
  {"eje":"y", "a":"pasillo_bajo", "lado_a":"N", "b":"dorm2_alto", "lado_b":"S", "sep":0.08}  // cara + separación
]
```

**Reglas**
- Entre dos elementos consecutivos de una cadena hay un tabique de 0,08, salvo que se ponga `{"muro":x}`. Con `{"muro":0}` las piezas se tocan: son partes de una misma estancia.
- `desde` y `hasta` admiten:
  - una fachada con nombre (`"O"`, `"E"`, `"S"`, `"N"`, u otro nombre como `"Og"` si esa fachada va retranqueada);
  - un número;
  - la cara de una estancia: `{"estancia":"x","lado":"N"}`.

  Las cadenas que comparten un nombre de fachada acaban en la misma línea.
- Cada estancia o parte tiene que aparecer en al menos una cadena de cada eje, o en una alineación. Si no, el motor da un error `C#` y no dibuja.
- **Orden en que se absorben los descuadres**:
  1. `"?"` y `"flexible": true`;
  2. muros gruesos (más de 0,12) y **muros de fachada**: si una estancia de una cadena con `"desde"`/`"hasta"` de fachada no llega a la línea, ese hueco se rellena como muro y la fachada sigue recta;
  3. estancias húmedas (baño, aseo, cocina, lavadero, wc), que **solo crecen**, hasta 10 cm;
  4. pasillos, vestíbulos y distribuidores con cota;
  5. tabiques (0,12 o menos), solo engordando;
  6. totales y tramos `{"cota"}`;
  7. el resto de estancias, que nunca ceden salvo una contradicción imposible, marcada como «Descuadre».

  Las húmedas y la circulación se reconocen por el id, el nombre o el tipo, también en las partes de una `union`.
- `"total"` pesa la mitad que la cota de una estancia, salvo que se indique `"peso"`. `{"cota":x}` pesa como una estancia.
- Las estancias de las cadenas se convierten en polígonos; el resultado se guarda en `salida/planta_resuelta.json`. En el modo cadenas, `puertas`, `ventanas`, `mobiliario`, `pilares` y `medianeras` funcionan igual que en el modo de coordenadas. Las puertas y los muebles se refieren a la estancia completa (el id de la `union`), no a sus partes.
- **Mezcla de modos**: las estancias de coordenadas (`rect`, `contorno`, `pegado`) pueden convivir con las de cadenas y apoyarse en ellas con `pegado`.

## Modo de coordenadas

## Claves
```jsonc
{
  "titulo": "Vivienda calle X - planta baja",      // opcional, se rotula
  "espesores": {"tabique":0.08, "cerramiento":0.30, "medianera":0.20, "antepecho":0.12}, // opcional
  "estancias": [ ... ],      // obligatorio
  "abiertas": [["cocina","salon"]],   // pares de estancias SIN pared entre ellas (espacio abierto): deben tocarse
  "pilares": [ ... ], "patinillos": [ ... ], "patios": [ ... ],
  "medianeras": ["E", {"lado":"N","estancia":"dorm2"}, {"lado":"O","de":[0,0],"a":[0,4.2]}],
  "medianeras_auto": true,   // por defecto: una alineación de fachada sin ningún hueco = medianera 0,20
  "muros_exteriores": [{"lado":"S","estancia":"salon","tipo":"cerramiento","espesor":0.35}], // forzar tipo/espesor
  "puertas": [ ... ], "ventanas": [ ... ], "mobiliario": [ ... ],
  "control": {"exterior_dx": 10.6, "exterior_dy": 8.3, "interior_dx": 10.0, "interior_dy": 7.7},  // cotas totales del boceto
  "rotular_nombres": true,
  "acotar": true,            // capa COTAS: luces interiores, huecos y totales (false = sin cotas)
  "cotas": [{"de":[x1,y1],"a":[x2,y2],"desp":0.3}],   // opcional: cotas explícitas del boceto que el motor no genere solo
  "supuestos": ["texto de cada decisión tomada al leer el boceto"]
}
```

### Estancias (tres formas; `tipo` se deduce del id o el nombre)
```jsonc
{"id":"salon", "nombre":"Salón-comedor", "rect":{"x":0, "y":0, "dx":4.50, "dy":3.80}}
// relativa: pegada a otra con el tabique de por medio (muro por defecto 0.08)
{"id":"cocina", "rect":{"dx":2.60, "dy":2.40},
 "pegado":{"a":"salon", "lado":"E", "alinear":"S", "muro":0.08, "desfase":0}}
// forma ortogonal cualquiera (L, U, quiebros): pasos cota a cota, como en el boceto
{"id":"dorm1", "contorno":{"inicio":{"desde":"salon","esquina":"NO","dx":0,"dy":0.08},
                            "pasos":["E3.20","N1.50","E0.60","N2.10","O3.80"]}}
// polígono libre (solo si hay paredes no ortogonales)
{"id":"x", "poligono":[[0,0],[3,0],[3,2],[0,3]]}
```
- `pegado.lado`: lado de la estancia de referencia junto al que se coloca. `alinear`: N/S (para lados E/O) u O/E (para lados N/S), o `centro`. `desfase`: corrimiento desde esa alineación.
- `contorno.inicio`: punto `[x,y]` o `{"desde":id,"esquina":..,"dx":..,"dy":..}`. El último paso se puede omitir si cierra en línea recta; si el contorno no cierra, el motor lo marca como error.
- Opciones: `"tipo"` (dormitorio, salon, cocina, bano, circulacion, terraza, almacen, otro), `"sin_puerta":true` (hueco técnico), `"sin_ventana":true` (no avisar si un dormitorio o salón no tiene ventana a propósito).
- Tipo **terraza** (terraza, balcón, tendedero, galería, porche): sus bordes exteriores son antepecho de 0,12 y no cuentan como superficie útil.

### Pilares, patinillos y patios
```jsonc
"pilares": [{"estancia":"salon","esquina":"NE","dx":0.30,"dy":0.30},     // en la esquina interior
            {"estancia":"salon","contra":"S","desde":2.0,"dx":0.30,"dy":0.20}, // saliente en una pared
            {"x":4.5,"y":3.8,"dx":0.3,"dy":0.3}],                           // absoluto (esquina SO)
"patinillos": [{"rect":{"x":3.2,"y":2.5,"dx":0.4,"dy":0.6}}],   // hueco de instalaciones (se dibuja con una X)
"patios": [{"rect":{"x":4,"y":4,"dx":2,"dy":3}}]                 // patio de luces interior (con fachadas)
```
Un hueco pequeño (menos de 1,5 m²) que quede rodeado de estancias se convierte solo en patinillo y se marca como aviso.

### Puertas
```jsonc
{"entre":["recibidor","exterior"], "lado":"E"}            // entrada: 0,90 por defecto
{"entre":["pasillo","dorm1"], "desde":0.10}               // interior: 0,80 por defecto
{"entre":["pasillo","bano"], "ancho":0.70, "abre_hacia":"bano", "bisagra":"O"}
{"entre":["recibidor","pasillo"], "tipo":"paso", "ancho":"total"}  // hueco sin hoja
{"entre":["salon","terraza"], "tipo":"balconera", "ancho":1.80}    // carpintería de 3 líneas
{"entre":["cocina","lavadero"], "tipo":"corredera"}
{"entre":["bano","salon"], "lado":"N", "tipo":"cristalera", "ancho":"total"}  // puerta de vidrio o mampara (línea azul sobre tabique): da paso
{"entre":["bano","galeria"], "tipo":"ventana", "ancho":0.50}   // ventana interior: no da acceso
```
- Si se omiten `abre_hacia` y `bisagra`, el motor elige la combinación con la que la hoja barre dentro de la estancia sin chocar con muros, otras puertas ni muebles. Por defecto la puerta abre hacia la estancia que no es de paso, con la bisagra junto a la esquina más próxima.
- Si se indican y la hoja choca con un muro, el motor la invierte y lo deja como aviso.
- `lado`: desambigua cuando dos estancias comparten más de una pared. En la puerta de entrada indica la fachada.

### Ventanas (solo en fachada; nunca en una medianera)
```jsonc
{"estancia":"salon", "lado":"S", "ancho":2.00, "desde":0.60}
{"estancia":"dorm1", "lado":"O", "ancho":1.20, "tipo":"balconera"}   // balconera a la calle
{"estancia":"galeria", "lado":"O", "ancho":"corrido"}               // acristalamiento de pared entera
```
Sin posición, la ventana queda centrada en la parte de esa pared que da al exterior. Si no cabe, se reduce o se desplaza y queda como aviso.

### Mobiliario (contra una pared, centrado en la estancia o absoluto)
```jsonc
{"tipo":"cama", "estancia":"dorm1", "contra":"N"}                  // cabecero en la pared N, centrada
{"tipo":"armario", "estancia":"dorm1", "contra":"E", "desde_fin":0, "ancho":1.80}
{"tipo":"mesa", "estancia":"salon", "centro":true, "contra":"S"}  // centro de la estancia
{"tipo":"fregadero", "estancia":"cocina", "contra":"E", "en":1.2, "sep":0.05} // sep = separación de la pared
{"tipo":"rect", "x":2.0, "y":1.5, "contra":"S", "ancho":1.0, "fondo":0.5}  // absoluto (x,y = centro)
```
Tipos y medidas por defecto (ancho × fondo, en m). El dibujo sigue el estilo del plano final de Carlos Soto:

| Tipo | Medidas | Dibujo |
|---|---|---|
| cama / cama_doble | 1,50 × 2,00 | colchón y franja de cabecero con mesitas (0,40 a cada lado) |
| cama_individual | 0,90 × 1,90 | colchón con línea de cabecera a 0,35 |
| sofa | 2,20 × 0,90 | doble contorno, respaldo, brazos y cojines |
| sofa_chaise | 2,60 × 0,90 | sofá con chaise longue de 0,80 en su extremo inicial |
| sillon | 0,80 × 0,80 | como el sofá |
| mesa_centro | 1,10 × 0,55 | rectángulo |
| mesa | 1,60 × 0,90 | rectángulo |
| mesa_comedor | 1,40 × 0,80 | mesa con sillas a los dos lados largos |
| mesa_redonda | 1,10 | círculo |
| mueble_tv | 2,20 × 0,45 | rectángulo con la pantalla |
| armario | 1,20 × 0,60 | rectángulo con línea doble en el frente |
| mesita | 0,45 × 0,40 | rectángulo |
| escritorio | 1,20 × 0,60 | rectángulo |
| comoda | 1,00 × 0,50 | rectángulo |
| inodoro | 0,38 × 0,68 | cisterna con círculo y taza en U |
| bide | 0,36 × 0,55 | taza en U |
| lavabo | 0,80 × 0,48 | encimera con seno redondeado y grifo |
| ducha / plato_ducha | 0,80 × 0,80 | plato con sumidero cuadrado con rejilla |
| banera | 1,60 × 0,70 | contorno interior redondeado y desagüe |
| encimera | 2,40 × 0,60 | rectángulo |
| fregadero | 0,80 × 0,50 | seno redondeado |
| placa | 0,60 × 0,55 | 4 fuegos |
| frigorifico | 0,60 × 0,65 | rectángulo con línea de puerta |
| lavadora | 0,60 × 0,60 | círculo |
| rect | 1,00 × 0,60 | rectángulo |

Colocación: `contra` es la pared en la que se apoya la parte trasera del mueble (el cabecero, el respaldo o la cisterna). `en` es la coordenada absoluta de su centro a lo largo de esa pared y sirve para elegir el tramo de pared en estancias en L. `sep` es la separación respecto a la pared; por ejemplo, la mesa de centro va a 1,25–1,35 del muro del sofá.

`ancho` y `fondo` sustituyen a las medidas por defecto. El ancho se mide a lo largo de la pared y el fondo, hacia dentro de la estancia.

## Cotas del boceto comprobadas (`"cotas_boceto"`), recomendado
Cada cota roja del boceto se escribe con el `id` de su recuadro en `mapa_cotas.jpg` (zonas.py), su `valor` tal como está escrito y el tramo que mide. El motor **la mide en la geometría dibujada**, la dibuja en la capa COTAS y da **error** si no coincide (tolerancia de 5 mm).
```json
"zonas": "../zonas",                       // carpeta de zonas.py (relativa al JSON): activa la comprobación de recuadros sin usar y superpuesto.jpg
"cotas_boceto": [
  {"id":"C5",  "valor":5.05, "en":[3.0,6.3], "eje":"x"},            // luz libre que pasa por el punto, de pared a pared
  {"id":"C7",  "valor":1.14, "de":[5.09,6.86], "a":[5.09,8.00]},     // entre dos puntos situados sobre caras de muro
  {"id":"C16/C27", "valor":0.53, "de":[4.82,4.24], "a":[4.82,4.77]}, // un mismo número visto en dos recuadros
  {"id":"C15", "valor":2.89, "en":[4.95,6.0], "eje":"y", "no_cuadra":true}  // discrepancia real del boceto: aviso, no error
],
"cotas_descartadas": {"C31/C32": "h=2,15: altura libre", "C20": "puerta de la cocina (en puertas)"}
```
- `en` + `eje`: mide la estancia (o la unión de estancias abiertas entre sí) a lo largo del eje por ese punto. Es lo más cómodo para las cotas interiores.
- `de` + `a`: para pilares, salientes, huecos de ventana, retranqueos y cotas exteriores. Si un extremo queda suelto en medio de una estancia, avisa.
- Un recuadro que no está ni en `cotas_boceto` ni en `cotas_descartadas` da error: así ninguna cota queda sin leer.
- El informe resume: «COTAS DEL BOCETO COMPROBADAS: 34 (32 cumplen, 2 no)», y lista solo las que fallan.
- Opcionales: `"desp"` desplaza la línea de cota y `"dibujar": false` comprueba sin dibujar.

## Cotas explícitas (`"cotas"`)
Solo dibujan, no comprueban (es preferible usar `cotas_boceto`). Cada entrada dibuja una cota alineada entre `de` y `a` (en metros, en coordenadas de la planta). Si la diferencia en x es mayor o igual que la diferencia en y, la cota es horizontal; si no, es vertical. `desp` desplaza la línea de cota en perpendicular (+ arriba o a la derecha). Se dibujan siempre, no se descartan como duplicadas y van en la capa COTAS. Úsalas para reproducir **toda** cota del boceto que no salga sola (estrechamientos, pilares, fondos parciales). Funcionan en modo de coordenadas y en modo cadenas.

## Qué audita el motor
**Errores (E#)**: la entrega queda bloqueada hasta corregirlos.
- Estancias que se solapan.
- Estancias pegadas sin tabique y no declaradas como `abiertas`.
- Contorno que no cierra.
- Puerta entre estancias que no comparten pared.
- Hoja de puerta que no cabe al abrir en ningún sentido.
- Ventana en pared interior o en medianera.
- Estancia sin puerta, o a la que no se llega desde la entrada.
- Falta la puerta de entrada.
- Volumen suelto, no adosado al resto.
- Hueco grande rodeado de estancias pero sin estancia asignada.
- DXF con errores internos.

**Avisos (A#)**: se revisan y, si son correctos, se explican al entregar.
- Dormitorio o salón sin ventana.
- Superficie o anchura por debajo de lo razonable.
- Barridos de puertas que se cruzan; puerta que choca con un mueble o tiene el paso obstruido.
- Muebles fuera de su estancia o solapados entre sí.
- Tabiques de menos de 5 cm (descuadre) o macizos de más de 0,38 m.
- Quiebros de pocos centímetros en la fachada.
- Cotas totales de `control` que no coinciden.
- Baño que abre a la cocina.
- Elementos desplazados o invertidos automáticamente.
