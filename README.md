# Capturador 1.1.0: graba, repite, captura y crea PDF

Este programa graba lo que haces con el ratón y el teclado, lo repite las veces que le indiques, toma una captura de pantalla en cada vuelta y al final junta las imágenes en PDF de 30 páginas.

## Instalación en Windows 10/11

### 1. Instala Python (una sola vez)
1. Entra a https://www.python.org/downloads/ y pulsa el botón amarillo **Download Python 3.12** (o la versión que aparezca).
2. Abre el instalador y, **antes de pulsar «Install Now»**, marca abajo la casilla **«Add python.exe to PATH»**. Si no la marcas, el programa no encontrará Python.
3. Deja todo lo demás como viene y pulsa **Install Now**.

### 2. Descarga el código
1. Entra a https://github.com/Jesuscatholizare/capturador-de-pantalla
2. Pulsa el botón verde **`<> Code`** y luego **Download ZIP**.
3. En tu carpeta **Descargas**, haz clic derecho sobre `capturador-de-pantalla-main.zip` y elige **Extraer todo…**. Elige una carpeta fácil, por ejemplo `C:\Capturador`.

### 3. Crea el programa (una sola vez)
1. Abre la carpeta que extrajiste. Dentro hay otra carpeta, `capturador-de-pantalla-main`.
2. Haz doble clic en **`crear_portable_windows.bat`**.
   - Si Windows dice «Windows protegió su PC», pulsa **Más información** y luego **Ejecutar de todas formas**.
3. Se abre una ventana negra que descarga e instala las librerías. Tarda unos 2 a 5 minutos.
4. Cuando diga **«Listo: dist\Capturador.exe»**, pulsa una tecla para cerrarla.

### 4. Abre el programa
- Entra a la carpeta **`dist`** y haz doble clic en **`Capturador.exe`**.
- Puedes copiar ese archivo al Escritorio o a una memoria USB: funciona solo, sin el resto de la carpeta.
- Si el antivirus lo bloquea, es porque el programa controla el teclado y el ratón y no lleva firma digital. Puedes permitirlo, o abrir el programa con **`ejecutar_sin_compilar.bat`**, que hace lo mismo sin crear el `.exe`.

### Si tu equipo no deja crear o abrir el `.exe` (Device Guard)
En equipos de una empresa o institución puede aparecer: *«…ha sido bloqueado por la directiva de Device Guard de su organización»*. Es una regla de seguridad del área de sistemas que solo deja ejecutar programas aprobados. **No intentes saltarla.**

El programa funciona igual sin `.exe`: haz doble clic en **`ejecutar_sin_compilar.bat`**. La primera vez instala lo necesario (unos minutos); después se abre directamente. Deja abierta la ventana negra mientras usas el Capturador.

Si también se bloquea así, pide al área de sistemas que autorice Python y las librerías de `requirements.txt`.

### 5. Primera prueba
1. En la pestaña **3. Imágenes**, elige la carpeta donde se guardarán las capturas y pulsa **Probar una captura**.
2. En **1. Grabar**, pulsa **● Grabar** y haz un clic en «página siguiente» de cualquier documento. Luego pulsa **F9** para terminar.
3. En **2. Repetir y capturar**, pon **5** repeticiones y pulsa **▶ Iniciar**. No toques el ratón mientras trabaja.

> Si en la ventana negra del paso 3 aparece un error, copia el texto completo: con él se puede encontrar la causa.

## Uso paso a paso

### 1. Grabar
- Deja abierto lo que quieres capturar (el visor, el libro, la web…).
- Pulsa **● Grabar**. La ventana se minimiza y tras 3 segundos empieza la grabación.
- Haz **una sola vuelta**: por ejemplo, el clic en «página siguiente».
- **F8** marca una captura en ese momento (solo si quieres varias capturas por vuelta).
- **F9** termina la grabación.
- Guarda la macro con **Guardar macro…** si la quieres reutilizar otro día.

### 2. Repetir y capturar
- **Repeticiones**: cuántas vueltas dará.
- **¿Cuándo capturar?**
  - *Al final de cada repetición*: una imagen por vuelta.
  - *En las marcas (F8)*: una imagen en cada marca que pusiste al grabar.
  - *Ambos*: en las marcas y además al final de la vuelta.
- **Espera antes de capturar**: margen para que la página cargue (800 ms por defecto). Si las páginas tardan, súbela.
- **Velocidad**: 1 reproduce al mismo ritmo en que grabaste; 2, al doble.

### 3. Imágenes
- Elige la **carpeta**. Las imágenes se llaman `captura_00001.png`, `captura_00002.png`…
- **Monitor**: `1` es la pantalla principal, `2` la segunda y `0` las dos juntas. Solo cuenta cuando no hay áreas marcadas.
- **Áreas a capturar**: pulsa **➕ Añadir área…**. Se oscurecen **las dos pantallas** y arrastras sobre la zona que quieres. Repítelo para el **área 2**: las que ya marcaste se ven en amarillo. Puedes marcar las que necesites y en cualquier pantalla.
  - Cada área se guarda como **imagen separada y en orden**: con dos áreas, `captura_00001` es el área 1, `captura_00002` el área 2, `captura_00003` otra vez el área 1… En el PDF quedan intercaladas igual, como las páginas izquierda y derecha de un libro abierto.
  - Las áreas quedan fijas para todas las vueltas, y el programa las recuerda para la próxima vez.
  - Sin áreas, se captura el monitor completo.
- **Probar una captura** guarda `prueba.png` (o `prueba_area1.png`, `prueba_area2.png`…) para comprobar las zonas.
- Con dos áreas, cada vuelta produce dos imágenes: **100 repeticiones = 200 imágenes**. La pestaña 2 muestra el total.

### 4. Si algo falla
Cada captura se comprueba antes de guardarla:
- **Imagen vacía**: toda negra o toda blanca, porque la pantalla estaba bloqueada o la página no había cargado.
- **Igual a la anterior**: la página no cambió, porque el clic no hizo efecto o el visor tardó.

Si la captura falla, el programa **espera y reintenta** (3 veces por defecto). Si sigue fallando, hace lo que hayas elegido:
- **Preguntarme**: suena un aviso, aparece la ventana y eliges:
  - *Reintentar*: vuelve a probar la captura.
  - *Pausar para arreglarlo*: corriges la pantalla a mano, pulsas **Continuar** y el programa vuelve a tomar esa misma captura.
  - *Guardarla así*: la guarda y lo anota en el registro.
  - *Detener*.
- **Guardar igual y anotarlo**: no se detiene nunca; revisas después `registro.csv`.
- **Detener**: se detiene en esa captura.

### Ejemplo: vas en la 154 de 200 y algo sale mal

**Caso A, el programa lo detecta solo.** Reintenta la 154. Si no se arregla, te pregunta. Eliges *Pausar*, pones en pantalla la página 154, pulsas **Continuar**: toma la 154 y sigue con la 155.

**Caso B, lo ves tú.** Por ejemplo, la 152 salió cortada.
1. Pulsa **F9** (pausa). La ventana aparece.
2. Pon en pantalla lo que debía salir en la 152, escribe **152** en «Rehacer la captura nº» y pulsa **Recapturar ahora**. Solo se reemplaza esa imagen.
3. Vuelve a dejar la pantalla donde estaba y pulsa **Continuar** (o F9).

**Caso C, se detuvo, se cerró o se apagó el equipo.** El avance se guarda tras cada imagen en `progreso.json`.
1. Abre el programa y elige la misma carpeta.
2. Pulsa **Continuar donde se quedó**: «Empezar en» queda, por ejemplo, en **154**.
3. Deja en pantalla la página 154 y pulsa **Iniciar**. Las imágenes 1–153 no se tocan.

**F10** detiene todo en cualquier momento y suelta las teclas que hubiera pulsadas.

### 5. PDF
- **Imágenes por PDF**: 30 por defecto.
- Al terminar se crean solos en la subcarpeta `PDF`: `lote_001_paginas_00001-00030.pdf`, `lote_002_paginas_00031-00060.pdf`… El último lleva las que sobren.
- **Crear PDF ahora con la carpeta…** sirve para cualquier carpeta de imágenes, aunque no las haya hecho este programa.

## Archivos en la carpeta de destino
| Archivo | Para qué |
|---|---|
| `captura_00001.png`… | Las imágenes |
| `progreso.json` | Dónde va: permite reanudar |
| `registro.csv` | Cada fallo, reintento y decisión, con fecha (se abre en Excel) |
| `PDF\` | Los PDF por lotes |

## Límites conocidos
- La macro repite **posiciones de pantalla**. Si mueves la ventana, cambias la resolución o la escala de Windows entre la grabación y la reproducción, los clics caen en otro sitio. Graba con la ventana maximizada.
- Mientras se ejecuta, no uses el ratón ni el teclado. Para intervenir, pulsa **F9** antes.
- Al reanudar, el programa no sabe qué hay en pantalla: tú dejas a la vista la página que corresponde.
- Con *marcas* o con varias áreas (varias capturas por vuelta), al reanudar a mitad de una vuelta se rehace la vuelta completa desde su primera captura. El programa avisa.
- Al reanudar, usa las mismas áreas que la primera vez; si no, la numeración (área 1, área 2…) no cuadra. El programa avisa si cambiaron.
- Al pausar con una tecla o un botón del ratón pulsados (un arrastre, por ejemplo), la pausa espera a que se suelten.
- Las combinaciones que Windows reserva para sí (Ctrl+Alt+Supr, Win+L) no se pueden reproducir.

## Para desarrolladores
- Código en `capturador/`: `grabador.py` (pynput), `reproductor.py`, `motor.py` (repeticiones, reintentos y progreso), `capturas.py` (mss y validación), `pdfs.py` (ReportLab), `app.py` (tkinter).
- Pruebas: `python -m pytest pruebas`.
