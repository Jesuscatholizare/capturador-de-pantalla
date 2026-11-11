# Capturador 1.0.0: graba, repite, captura y crea PDF

Este programa graba lo que haces con el ratón y el teclado, lo repite las veces que le indiques, toma una captura de pantalla en cada vuelta y al final junta las imágenes en PDF de 30 páginas.

## Instalación (Windows 10/11), una sola vez

1. Instala **Python 3.11 o 3.12** desde https://www.python.org/downloads/ y marca la casilla **«Add python.exe to PATH»**.
2. Descarga el proyecto (en GitHub: botón verde **Code → Download ZIP**) y descomprímelo en una carpeta, por ejemplo `C:\Capturador`.
3. Haz doble clic en **`crear_portable_windows.bat`**. Tarda unos minutos.
4. El programa queda en **`dist\Capturador.exe`**. Puedes copiarlo donde quieras: no necesita instalación.

> Si Windows SmartScreen o el antivirus avisan del `.exe`, es normal en programas que controlan el teclado y el ratón y que no llevan firma digital. Puedes permitirlo, o usar `ejecutar_sin_compilar.bat`, que abre el programa sin crear el `.exe`.

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
- **Región**: pulsa *Seleccionar con el ratón* y arrastra sobre la zona (por ejemplo, solo la página, sin la barra de tareas). Si la dejas vacía, se captura toda la pantalla.
- **Probar una captura** guarda `prueba.png` para comprobar la zona.

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
- Con *marcas* (varias capturas por vuelta), al reanudar a mitad de una vuelta se rehace la vuelta completa desde su primera captura. El programa avisa.
- Al pausar con una tecla o un botón del ratón pulsados (un arrastre, por ejemplo), la pausa espera a que se suelten.
- Las combinaciones que Windows reserva para sí (Ctrl+Alt+Supr, Win+L) no se pueden reproducir.

## Para desarrolladores
- Código en `capturador/`: `grabador.py` (pynput), `reproductor.py`, `motor.py` (repeticiones, reintentos y progreso), `capturas.py` (mss y validación), `pdfs.py` (ReportLab), `app.py` (tkinter).
- Pruebas: `python -m pytest pruebas`.
