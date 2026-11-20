# Reglas aprendidas de Ester (leer antes de cada boceto; prevalecen sobre todo)

Resumen de las correcciones. El detalle y los ejemplos están en `lecciones_historial.md` (hN = número de la lección).

**Lectura de cotas**
1. Cada número rojo debe tener su tramo: todos van en `cotas_boceto` (con su `id` C# de `mapa_cotas.jpg`) o en `cotas_descartadas` con el motivo. El motor mide cada uno en el plano dibujado y da error si no coincide (h28, h18).
2. Una cota es de la pared junto a la que está escrita y hacia donde apunta su flecha, no de la orientación del texto. Si una cota está por fuera de un tabique y otra por dentro, cada una mide su cara (1,14 en el salón y 1,16 en la ducha) (h34).
3. Confusiones habituales al girar: 1↔7, 2↔5, 5↔9, 13↔43, 17↔41. Si hay duda, se ponen las dos lecturas como alternativa y el motor elige la que cierra (h4, h8, h15, h24).
4. Las cotas de lado a lado (por ejemplo, de la entrada a la pared de enfrente) mandan sobre los anchos deducidos. Primero se cierran las cadenas con las cotas escritas y después se deduce lo que no tiene cota (h35).
5. Una cota que no cierra no se fuerza ni se compensa con un saliente inventado: se marca `"no_cuadra": true`, se explica en `supuestos` y se le dice a Ester (h29, h34).
6. Lo que va dentro de un óvalo azul es la ventana más cercana: ancho, y `h=` es la altura, que se ignora. Si h ≈ 2,10–2,25, es una balconera (h6, h10).

**Geometría**
7. Las cotas de las estancias y de los tramos son sagradas, **también las de pasillos, vestíbulos y distribuidores**. Las diferencias las absorben las piezas sin medir y los muros, como salientes; nunca los tabiques (h1, h11, h18).
8. Espesores: tabique de 0,08; pared hacia la galería (la antigua fachada) de 0,30; pared hacia el rellano o la escalera (medianera) de 0,20. Las estancias húmedas pueden ganar hasta 0,10 por el alicatado y los tabiques no (h1, h2, h5, h19).
9. No se inventan estancias: una estancia solo existe si tiene pared negra en todos sus lados. Una zona sin muro es parte del espacio contiguo (h26).
10. Cada tramo de distinto ancho (estrechamientos, franjas hacia la fachada) es una parte propia con su cota, no un rectángulo único (h30). Una estancia en L no tiene «chichones» en la entrada (h23).
11. Se dibujan todos los pilares y salientes. Una cota pequeña (0,15–0,60) junto a un muro, o dos cotas distintas de una misma estancia, indican un saliente. Los pilares de bajantes suelen salir hacia los dos lados del tabique. Un muro grueso entre estancias suele ser una zona de bajantes (h13, h22, h31).
12. Alineaciones: solo las necesarias. Si algo descuadra, lo primero que se sospecha es una alineación tomada del dibujo. Si dos paredes casi alineadas no tienen cota que las relacione, se alinean y se indica qué cota falta (h9, h23, h37).
13. Si un baño no llega a la fachada, engorda el muro de fachada por dentro y el baño conserva sus cotas (h22).

18. Si casi todos los textos del boceto están boca abajo, el boceto se ha dibujado girado: da igual para la geometría, pero los números se leen en el giro de 180° de la hoja de cotas.

19. Unifamiliares: la escalera (recuadrada en amarillo) es una estancia de circulación abierta al pasillo y va en `escaleras` (tramos, muro central, meseta). Si una pared lleva la nota «es pared», es muro, no barandilla. Las letras rosas son las iniciales de las estancias (k cocina, b baño, d dormitorio, p pasillo, s salón). En una planta alta no hay puerta de entrada (`"sin_entrada": true`).
20. Si una nota dice que la suma de los tramos difiere del total («todo +10 cm, error en medio»), se respetan el total y los extremos, y la diferencia se deja en el tramo central, marcándolo como `no_cuadra`.

21. Los escalonados y las inclinaciones se dibujan **vértice a vértice** como `poligono`, siguiendo la secuencia de tramos (recto 0,71 → perpendicular 0,37 → 0,31 → inclinado + recto con 0,45 de bajada → 0,84). No se simplifican a un rectángulo y no se confunde un tramo de pared con una puerta (en Garmendia, el 0,83 y el 0,11 del pasillo eran tramos de pared) (h Garmendia).
22. Una cocina o un salón con «salida» a balcón: el balcón es una estancia `terraza` exterior y la salida es una `balconera` con el ancho indicado.

23. **Antes de declarar que una cota «no cuadra», se prueban otras formas de encajar las estancias.** En San Nicolás, el 2,89 era correcto: fallaba mi supuesto de que el baño empezaba encima del pasillo. En realidad, el baño baja junto al muro del pasillo (con la pared de la ventana de 1,12 abajo) y el salón medía 7,30, no 8,00. Una cota que no cierra suele indicar una mala colocación de las piezas, no un error del boceto. Solo se marca `no_cuadra` cuando ninguna colocación razonable la cumple.
24. **Las estancias de un lado no tienen por qué empezar donde acaba la pared del otro lado.** Un baño o un cuarto puede solaparse a lo largo de la pared de un pasillo o salón. Se colocan por sus propias cotas de cadena (por ejemplo, desde el pilar: pilar 0,53, encima 2,89 hasta el norte), no por la alineación del dibujo.
25. **Las cristaleras (líneas azules entre estancias) son cierres finos de unos 2 cm, no tabiques de 8 cm.** Por eso el paso de la balconera mide 1,07 (1,00 de hueco y 3,5 cm a cada lado), y la ducha 1,12.
26. **Una cota pequeña junto a un pilar con una marca «I» delante** (por ejemplo, «I0'28») mide el pilar (0,28 de saliente). Una línea discontinua negra delante de una balconera, con dos cotas cortas (0,20 y 0,50), es un balconcillo exterior.

**Huecos**
14. Puertas interiores de 0,80 y la de entrada de 0,90, salvo cota. No se estrechan: si no caben, la lectura está mal. Deben caber en un tramo de pared continuo (h12, h32). Si dos estancias comparten más de una pared, se indica el `lado` (h27).
15. Azul sobre un tabique interior = cristalera (`"tipo": "cristalera"`). Un cuarto pequeño cerrado con cristalera junto al baño es la ducha (h33).
16. Ventanas: dos rayitas, una línea azul paralela a la pared o marcas en los dos extremos de una pared (acristalamiento corrido, la pared menos 0,10 a cada lado) (h3, h7).
17. Piezas pequeñas (despensas, lavaderos): sus cotas están dentro o al lado; no se confunden con las de la pieza contigua (h16).

**Lo aplica el motor (no hay que hacer nada):** cotas en metros, sin acotar puertas y sin duplicados; muro completo + ventana cuando queda poco muro al lado; geometría al centímetro; sin sombreados; puertas con marcos dentro del muro (0,08 / 0,10); ventanas al estilo de «Idoia 16»; mobiliario al estilo de Carlos; letra Calibri (h14, h17, h20, h21, h25, h36).
