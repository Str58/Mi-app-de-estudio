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
3. **Todas las cotas del boceto se comprueban.** Cada recuadro C# de `mapa_cotas.jpg` va en `cotas_boceto` (con su valor y el tramo que mide) o en `cotas_descartadas` con el motivo. El motor mide cada cota en la geometría dibujada y da error si no coincide o si falta algún recuadro. Una cota que no cierra se marca `"no_cuadra": true` y se explica; no se fuerza.
4. **Ahorrar imágenes.** Cada imagen leída cuesta mucho más que el texto. Lee solo `mapa_cotas.jpg`, `hoja_cotas_*.png` y, si hace falta, `ventanas_azul.png`. Revisa los resultados con el texto del informe y mira una sola imagen al final (`superpuesto.jpg`).
5. **No se entrega con errores.** Solo se entrega cuando el informe da **0 errores** y cada aviso está revisado.

## Flujo (con tiempos objetivo)
**0. Preparar (unos 10 s).** Lee `references/lecciones.md` (reglas cortas de Ester, que prevalecen sobre todo lo demás; el detalle está en `lecciones_historial.md` y solo se consulta si hace falta). `SKILL_DIR` es la carpeta de esta skill. El motor instala solo sus dependencias si faltan.
```bash
python3 SKILL_DIR/scripts/zonas.py BOCETO.jpg TRABAJO/zonas
```
Lo que hay que leer (unas 4 imágenes en total):
- `mapa_cotas.jpg`: el boceto con un recuadro azul y su número (C1, C2…) sobre cada grupo de cotas rojas. Dice **a qué pared va cada cota** y sirve para entender las estancias.
- `hoja_cotas_1.png`, `_2`…: cada recuadro ampliado y en sus **4 giros** (0°, 90°, 180°, 270°). Cada número se lee en el giro en el que queda derecho, sin girar ni ampliar nada más. Un recuadro puede contener varias cotas.
- `ventanas_azul.png`: solo si hay dudas con las ventanas o las cristaleras.

Imágenes de reserva, solo si algo no se ve: `completo.jpg` (cuadrícula A–J / 1–10), `zona_F_C.jpg` y `cotas_rojas*.png`.

**1. Leer (unos 60 s).** Recorre los recuadros C1, C2… en orden. Para cada uno, anota el valor de cada cota y el tramo que mide (lecciones 1 a 6). **No hagas cuentas ni intentes cuadrar nada.** Si un número es dudoso, escribe las dos lecturas: `"dy": ["1'58","1'28"]`.

**2. Escribir `TRABAJO/planta.json` en modo cadenas (unos 2 min).** Formato y ejemplo completo en `references/formato_json.md` y `ejemplos/bergamin/planta_cadenas.json`:
- **Estancias** con sus cotas `dx` (ancho E-O) y `dy` (fondo N-S), sin coordenadas. Pasillos y vestíbulos llevan `"tipo":"circulacion"`, porque son los que absorben los descuadres. Una cota que no aparece en el boceto se pone como `"?"`.
- **Formas en L o en U**: se trocean en rectángulos (`"parte": true`) que se juntan con `"union"`. Un entrante que provoca otra pieza (una galería, un patinillo) se describe con `"recortes": [{"por": "galeria", "muro": 0.30}]`.
- **Cadenas**: cada fila (eje x, de oeste a este) y cada columna (eje y, de sur a norte) del boceto. Se escriben como la lista de estancias en orden, con `{"muro": 0.30}` donde el muro no es un tabique de 0,08. Se añaden `"desde":"O"` / `"hasta":"E"` cuando la cadena toca fachada. Una cota suelta que no es una estancia, como un tramo de pared o un total, va como `{"cota": 2.52}` o `"total"`.
- **Alineaciones**: caras que el boceto dibuja en la misma línea sin estar en la misma cadena, por ejemplo los dos tramos de un pasillo.

El motor calcula todas las coordenadas y elige las alternativas que cierran las cadenas. **Las cotas escritas de las estancias no se tocan.** Los descuadres se absorben en este orden:
1. lo que no tiene cota (`"?"`);
2. los muros gruesos: fachadas, galerías y zonas de bajantes. Si una estancia no llega a la línea de fachada, la fachada engorda por dentro y por fuera sigue recta;
3. **las estancias húmedas** (baños, aseos, cocinas, lavaderos), que pueden **crecer** hasta 10 cm, porque el boceto se queda corto por el alicatado;
4. pasillos y vestíbulos;
5. **los tabiques, solo como último recurso**.

El informe dice qué ha cedido y dónde. La geometría sale exacta al centímetro y la capa COTAS reproduce todas las cotas del boceto. **Las cuentas no las hace el modelo.**

Antes de escribir el JSON, repasa:
- **Pilares y salientes**: todo cuadradito o escalón en un muro, y toda cota pequeña junto a un muro, va en `pilares`.
- **Puertas interiores de 0,80** y la de entrada de 0,90, salvo cota. No se estrechan nunca.

Si la planta es muy simple, también vale el modo de coordenadas (`rect`, `pegado`, `contorno`).

**3. Añadir `cotas_boceto` y generar (unos 5 s por vuelta, 3 vueltas como máximo).** En el JSON van `"zonas": "RUTA a TRABAJO/zonas"`, una entrada en `cotas_boceto` por cada cota leída y `cotas_descartadas` para las que no son geométricas (alturas `h=`, notas, puertas ya descritas). Formato en `references/formato_json.md`.
```bash
python3 SKILL_DIR/scripts/plano.py TRABAJO/planta.json TRABAJO/salida
```
- Los errores `C#` son de las cadenas, por ejemplo una estancia que no está en ninguna cadena de un eje. Se corrigen en las cadenas.
- Corrige en el JSON cada error `E#`. Uno de la forma «Cota C12: el boceto dice 2,89 y el plano da 3,23» significa una cota mal leída, mal asignada o una geometría equivocada. Se busca la causa; **nunca se cambia el valor para que cuadre**. Si es una discrepancia real del boceto, se marca `"no_cuadra": true`.
- Un error «Recuadro C7 sin usar» indica una cota que se ha quedado sin leer.
- Revisa cada aviso `A#`. Corrígelo si es una mala lectura; si es fiel al boceto, explícalo al entregar.
- Todo esto se revisa **con el texto del informe**, sin abrir imágenes.

**4. Una sola mirada al final (unos 20 s): `superpuesto.jpg`.** Es el plano (contornos azules de las estancias) encima del boceto. Como el boceto no está a escala, no busques desplazamientos: busca **paredes que falten o sobren, estancias inventadas, pilares o huecos sin dibujar**. Solo se abre `plano.png` si hay que revisar puertas o mobiliario.

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
- **Azul: ventanas.** Pueden venir de varias formas, todas válidas:
  - **Forma habitual:** dos rayitas azules perpendiculares a la pared que marcan el inicio y el fin del hueco.
  - **Forma rápida:** una **línea azul paralela a la pared**, dibujada sobre ella o pegada a ella. Su longitud y su posición son el hueco. Si es muy larga (casi toda la pared), es un acristalamiento corrido.
  - **Azul sobre un tabique interior** (entre dos estancias): es una **cristalera**, es decir, una puerta de vidrio o una mampara (`"tipo": "cristalera"`), no una ventana ni una puerta normal (lección 33).
  - **Cotas de la ventana:** en azul, o **en rojo rodeadas por un óvalo azul**. Lo que está dentro del óvalo es siempre de la ventana más cercana, aunque esté en rojo: el primer número es el ancho y `h=` la altura, que se ignora. Ejemplo: `0'95 h:2'25` es una ventana de 0,95 de ancho.
  - Una cota roja **fuera** de un óvalo, junto a la ventana, es su distancia a la esquina.
  - `ventanas_azul.png` (de `zonas.py`) aísla todo lo azul sobre la planta tenue: así se ven de un vistazo todas las rayitas, líneas y óvalos.
- **Amarillo: mobiliario y aparatos sanitarios.** Se colocan contra la pared donde estén dibujados y, si no hay cota, con las medidas por defecto.
- **Pilares y salientes** marcados en las paredes: 0,30×0,30 si no tienen cota.
- **Baños y cocinas**: si a la cadena de cotas le faltan unos centímetros, son baldosas (no hagas nada). Si faltan más, hay un **patinillo de instalaciones** entre las paredes.
- Las estancias pueden tener cualquier forma ortogonal: en L, en U, con quiebros o con remetidos.
- **Una estancia solo existe si tiene paredes dibujadas en todos sus lados** (o el nombre o el mobiliario lo indican). Una zona sin muro que la cierre es parte del espacio de al lado, aunque tenga sus propias cotas: se describe como una `parte` de esa estancia.

## Tabla de decisiones (sustituye a cualquier pregunta)
| Situación | Decisión |
|---|---|
| Cota ilegible | Deducirla de la cadena: total menos el resto de cotas y tabiques. Si no hay cadena, de la cota paralela de la estancia vecina. Si tampoco, por proporción con una cota conocida. Anotar el supuesto. |
| La cadena de cotas no cierra | Lo resuelve el motor: lo absorbe la circulación y, si no puede, ajusta la cota que no cuadra y avisa. Entre 0,10 y 0,60 junto a baño o cocina sin circulación en medio: añadir `{"cota":"?"}` como patinillo. |
| Número dudoso (girado, mal trazado) | Las dos lecturas como alternativa: `["1'58","1'28"]`. El motor elige la que cierra. |
| Estancia con una sola cota | La otra dimensión sale de la vecina alineada (misma fachada o mismo fondo). |
| Puerta sin posición | Junto a la esquina donde esté dibujada (`desde` 0,10 a 0,15). Si está a media pared, centrada. |
| Sentido de apertura dudoso | No indicarlo: el motor elige el que cabe sin chocar. |
| Ventana sin cotas | Centrada en la pared de fachada de esa estancia: 1,20 en dormitorios, 1,50 a 2,00 en el salón, 1,00 en la cocina, 0,60 en el baño. |
| Pasillo o recibidor sin cota de ancho | 1,00 (mínimo 0,90). |
| Cocina abierta al salón (sin línea entre ambos) | Estancias pegadas, declaradas en `"abiertas"`. |
| Marcas de hueco en los dos extremos de una pared (aunque no sean azules) | Acristalamiento corrido: ancho = pared − 0,10 a cada lado. Prevalece sobre un ancho escrito que no cuadre. |
| Galería, tendedero o terraza cerrada | Su pared hacia las estancias interiores es la antigua fachada: **0,30**, que se deja como hueco entre ellas. |
| Una cadena horizontal no cuadra con otra paralela | **Nunca engordar un tabique** para absorberlo: los tabiques son siempre de 0,08 y rectos. La diferencia va a la circulación (vestíbulo o pasillo). Si con eso la pieza queda con un ancho absurdo, va a la galería o al cuerpo saliente, y se anota. |
| Hueco en un tabique sin dibujo de puerta | `"tipo":"paso"`. |
| No se sabe si una pared exterior es medianera | Dejar el modo automático: si no tiene huecos, es medianera. |
| No queda claro dónde está la entrada | La puerta que da a la escalera, el rellano o la calle, normalmente en el recibidor o el pasillo, con 0,90. |
| Estancia sin puerta dibujada | Añadir una de 0,80 hacia la circulación más próxima y anotar el supuesto. |
| Elemento indescifrable que no afecta a la geometría | Omitirlo y anotarlo. |

## Lista de comprobación final (sobre `superpuesto.jpg` y el informe)
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
- Capas independientes, para poder apagarlas en AutoCAD:

| Capa | Contenido |
|---|---|
| MUROS | Contorno de los muros |
| MUROS_RELLENO | Sombreado de los muros |
| PUERTAS | Puertas |
| VENTANAS | Ventanas y balconeras |
| **MOBILIARIO** | Muebles y aparatos sanitarios |
| **ESTANCIAS** | Nombre y m² de cada estancia |
| **COTAS** | Medidas de cada estancia (las del boceto), ventanas y totales exteriores, en metros. Las puertas no se acotan |
| TEXTOS | Resumen de superficies y título |
| PATINILLOS | Patinillos de instalaciones |
- Textos y cotas en letra **Calibri** (estilo de texto CALIBRI, `calibri.ttf`). La geometría sale exacta al centímetro.
- **Sin sombreados**, ni en muros ni en suelos: los muros van solo con su contorno (capa MUROS).
- Puertas (como en el plano de referencia «CALLE IDOIA 16»): un **marco** de 0,04 en cada jamba, **sin salirse del muro**, de 0,08 de fondo en las puertas interiores y 0,10 en la de entrada (enrasado con la cara hacia la que abre), la hoja como rectángulo fino entre los marcos y un arco de 90°.
- Ventanas y balconeras (mismo plano de referencia): una línea en la cara exterior y la **carpintería como línea doble pegada a la cara interior**. Sin líneas en las jambas.
- **Mobiliario** (estilo del plano final de Carlos Soto, Avenida 25-2), en la capa MOBILIARIO, en trazo fino gris (color 251) y con formas limpias, sin rellenos:
  - **Cama doble**: colchón 1,50 × 2,00 y franja de cabecero con mesitas, 0,40 a cada lado y 0,40 de fondo.
  - **Cama individual**: colchón 0,90–1,05 × 1,90–2,00 con una línea de cabecera a 0,35. Suele ir en una esquina, con la cabecera contra la pared corta.
  - **Armario**: rectángulo de 0,60 de fondo con línea doble en el frente, sin aspa.
  - **Sofá**: doble contorno, respaldo de 0,22, brazos de 0,20 y cojines de unos 0,60. Variante en L con chaise longue (`sofa_chaise`). Delante, **mesa de centro** rectangular.
  - **Mueble de TV**: rectángulo de 0,27–0,45 de fondo con la pantalla dibujada encima.
  - **Mesa de comedor** con sillas: cada silla, asiento cuadrado de 0,42 y respaldo como barra fina por fuera; 2 sillas por lado cada 0,60 de mesa.
  - **Cocina**: encimera como rectángulo de 0,60 a lo largo de la pared.
  - **Inodoro**: cisterna rectangular con un círculo y taza en U.
  - **Bidé**: en U, con un círculo pequeño.
  - **Lavabo**: encimera con seno de esquinas redondeadas y grifo.
  - **Plato de ducha**: rectángulo con sumidero cuadrado con rejilla en el centro. En los baños pequeños, el plato ocupa todo un lado.
- Cada estancia lleva su nombre y su **superficie útil** («10,93 m2») en la capa ESTANCIAS.
- La capa COTAS (con `"acotar": false` no se genera) lleva, siempre en metros:
  - cada estancia, o cada tramo de las que tienen forma en L, acotada con las mismas medidas del boceto, por dentro;
  - cada ventana o balconera como cadena esquina – hueco – esquina, medida desde la cara de la estancia aunque haya un pilar en la esquina. Si a un lado queda menos de 0,30 de muro, solo se acotan la ventana y el muro completo;
  - sin cotas repetidas: si el muro completo ya está acotado como medida de la estancia, no se repite;
  - las cotas totales y los tramos sueltos de las cadenas (`total`, `{"cota": x}`);
  - el tamaño de pilares y salientes, y su distancia a la pared más próxima;
  - las dos cotas totales exteriores.

  Las puertas no se acotan.
- Al pie, la superficie útil total y la construida.
- Para pasar a DWG: en AutoCAD, `GUARDARCOMO` con formato 2018.

## Aprender de las correcciones
Cada vez que Ester corrija algo, sea una convención, un espesor o una forma de dibujar, se añade una línea a `references/lecciones.md` con la regla general, no el caso concreto. Si afecta al motor, se cambia también el motor. Así no vuelve a pasar.

## Si hace falta tocar el motor
`scripts/plano.py` (dibujo y auditoría) y `scripts/cadenas.py` (cuadre de cotas) son paramétricos: espesores en `ESP_DEF`, medidas de muebles en `MUEBLES` y mínimos de auditoría en `MINIMOS`. Si se cambia una convención de dibujo, se cambia ahí y en esta skill, no en un script improvisado.
