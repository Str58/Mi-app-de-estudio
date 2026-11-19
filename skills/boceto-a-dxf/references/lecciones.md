# Lecciones aprendidas de las correcciones de Ester

Se leen antes de cada boceto y prevalecen sobre el resto de la skill. Cada corrección nueva se añade aquí como regla general.

1. **Tabiques siempre de 0,08 y rectos.** Nunca se engorda un tabique ni se dobla una pared para absorber un descuadre de cotas. La diferencia la absorben los muros como saliente, nunca recortando una cota escrita (ver la 18). *(Bergamín 10, nov. 2026)*
2. **Galerías, tendederos y terrazas cerradas**: su pared hacia las estancias interiores es la antigua fachada, de **0,30**. *(Bergamín 10)*
3. **Marcas de hueco en los dos extremos de una pared**, aunque no estén en azul, indican un acristalamiento corrido casi a todo lo largo: la pared menos 0,10 a cada lado. Un ancho escrito más pequeño no lo anula. *(Bergamín 10, galería de 3,25)*
4. **Cotas giradas**: un 2 trazado deprisa puede parecer un 5 al girarlo. Si duda, se escriben las dos lecturas como alternativa y el motor elige la que cierra las cadenas. *(Bergamín 10, baño de 1,28 que parecía 1'58)*
5. **Pared hacia el rellano o la escalera**: es medianera de 0,20, aunque tenga puertas. Puede haber una puerta principal y otra de servicio. *(Bergamín 10)*
6. **Ventanas medidas deprisa**: sus cotas pueden estar en **rojo dentro de un óvalo azul** (`0'95 h:2'25` = ancho 0,95; la altura se ignora). Lo que va dentro del óvalo es de la ventana más cercana. *(Avenida 25-2, nov. 2026)*
7. **Ventana como línea azul paralela a la pared**, en lugar de dos rayitas perpendiculares: la línea marca el hueco (posición y longitud). Es poco frecuente, pero hay que reconocerla. *(Avenida 25-2)*
8. **Números boca abajo o girados**: se confirman siempre en `cotas_rojas_giro_izq/der.png` antes de escribirlos. Un 1 mal trazado leído como 7 descuadra toda la planta. *(Avenida 25-2: «4'12» leído como 4'72)*
9. **Mandan las cotas, no las alineaciones del dibujo.** En las cadenas solo se ponen las alineaciones que haga falta. Si el motor da un descuadre grande o una dimensión negativa, lo primero que se sospecha es una alineación tomada del dibujo, y se quita. *(Avenida 25-2: los dormitorios 1 y 2 quedan alineados con la cocina, no con el salón)*
10. **Ventanas con h = 2,25** son balconeras. Si dan a una galería acristalada, se describen como `puertas` de tipo balconera entre la estancia y la galería. *(Avenida 25-2)*
11. **Las medidas de las estancias son sagradas.** Una cota de estancia no se cambia nunca para cuadrar el plano. Las diferencias las absorben primero la circulación y después los **muros, engordando como salientes**, y el informe dice dónde. Una parte con cota (`dx` o `dy` numérico) nunca lleva `"flexible": true`. *(Avenida 25-2, corrección de Ester)*
12. **Puertas interiores siempre de 0,80** y la de entrada de 0,90, salvo cota escrita. No se estrechan para que quepan: si el motor dice que no caben, lo que está mal es la lectura de las cotas del tramo. *(Avenida 25-2)*
13. **Pilares y salientes**: hay que buscar todos los cuadraditos y escalones dibujados en los muros. Una cota pequeña (0,15–0,60) junto a un muro, o dos cotas de una misma estancia que difieren (1,40 / 1,59), indican un saliente de esa medida, y se dibuja en `pilares`. *(Avenida 25-2: saliente de 1,37 × 0,19 en el baño)*
14. **Cotas del DXF**: en metros (5,32, nunca 532), en la capa COTAS, con la misma medida que el boceto para cada estancia o tramo. **Las puertas no se acotan**; las ventanas sí. *(Avenida 25-2)*
15. **Más confusiones de números girados**: 1'13 leído como 1'43 y 1'17 leído como 1'41. Todo número boca abajo se lee en `cotas_rojas_giro_180.png`. *(Avenida 25-2, corrección de Ester)*
16. **Piezas pequeñas** (despensas, lavaderos) entre la cocina y una galería: sus cotas suelen estar escritas dentro o justo al lado (Avenida: despensa de 0,71 × 1,30). No se confunden con las de la galería contigua (1,65 en la galería). *(Avenida 25-2)*
17. **Geometría al centímetro**: el motor redondea las caras a 0,01 m, así que en AutoCAD se mide 4,69 y no 4,686. *(Avenida 25-2)*
18. **Ninguna cota escrita se toca**, tampoco las de pasillos y vestíbulos ni las totales. Solo absorben las piezas sin medir (`"?"` o `"flexible": true`) y los muros, como salientes. Comprobación final: todas las cotas del boceto deben aparecer en la capa COTAS, exactas al centímetro. *(Avenida 25-2, corrección de Ester)*
