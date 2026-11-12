"""OCR con el motor que trae Windows 10/11 (Windows.Media.Ocr).

No hace falta instalar ningún programa aparte: solo los paquetes de Python
de requirements-ocr.txt (pywinrt). Reconoce los idiomas instalados en
Windows (Configuración → Hora e idioma → Idioma).

reconocer(img) devuelve las líneas de texto con la caja de cada palabra, en
píxeles de la imagen: [[(texto, x, y, ancho, alto), ...], ...]
"""
import sys
import threading

# Por debajo de este tamaño (lado mayor, en píxeles) la imagen se amplía al
# doble antes de reconocerla: la letra pequeña de una captura de pantalla se
# reconoce mejor así. Las cajas se devuelven en el tamaño original.
LADO_PARA_AMPLIAR = 2000

_hilo = threading.local()


class OCRNoDisponible(Exception):
    """No se puede usar el OCR de Windows (falta el paquete, el idioma…)."""


def _importar():
    if sys.platform != "win32":
        raise OCRNoDisponible("El OCR de Windows solo funciona en Windows.")
    try:
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import (BitmapAlphaMode, BitmapPixelFormat,
                                                    SoftwareBitmap)
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.storage.streams import DataWriter
    except ImportError as e:
        raise OCRNoDisponible(
            "Faltan los paquetes del OCR de Windows. Cierra el programa y vuelve a abrirlo "
            f"con ejecutar_sin_compilar.bat para que se instalen. (Detalle: {e})")
    return Language, BitmapAlphaMode, BitmapPixelFormat, SoftwareBitmap, OcrEngine, DataWriter


def _preparar_hilo():
    """COM debe estar iniciado en cada hilo que usa WinRT."""
    if getattr(_hilo, "listo", False):
        return
    try:
        from winrt.runtime import ApartmentType, init_apartment
        init_apartment(ApartmentType.MULTI_THREADED)
    except Exception:
        pass  # ya estaba iniciado en este hilo
    _hilo.listo = True


def _motor(idioma=None):
    Language, *_resto, OcrEngine, _dw = _importar()
    _preparar_hilo()
    if idioma:
        motor = OcrEngine.try_create_from_language(Language(idioma))
        if motor is None:
            raise OCRNoDisponible(
                f"Windows no tiene instalado el reconocimiento de texto para «{idioma}». "
                "Añade ese idioma en Configuración → Hora e idioma → Idioma.")
        return motor
    motor = OcrEngine.try_create_from_user_profile_languages()
    if motor is None:
        raise OCRNoDisponible(
            "Windows no tiene ningún idioma con reconocimiento de texto. Añade el español "
            "en Configuración → Hora e idioma → Idioma.")
    return motor


def idiomas_disponibles():
    """Lista de (etiqueta, nombre) de los idiomas que el OCR de Windows reconoce."""
    _importar()
    _preparar_hilo()
    from winrt.windows.media.ocr import OcrEngine
    return [(l.language_tag, l.display_name) for l in OcrEngine.available_recognizer_languages]


def comprobar(idioma=None):
    """Devuelve un texto que describe el OCR disponible; lanza OCRNoDisponible si no hay."""
    motor = _motor(idioma)
    idiomas = ", ".join(nombre for _tag, nombre in idiomas_disponibles())
    return (f"OCR de Windows disponible. Idioma que se usará: "
            f"{motor.recognizer_language.display_name}. Instalados: {idiomas}.")


def _esperar(operacion):
    if hasattr(operacion, "get"):
        return operacion.get()
    import asyncio

    async def esperar():
        return await operacion
    return asyncio.run(esperar())


class Reconocedor:
    """Reutiliza el motor de OCR entre páginas (crear uno por página es lento)."""

    def __init__(self, idioma=None):
        self.idioma = idioma
        self._motores = {}

    def __call__(self, img):
        return reconocer(img, self._motor_del_hilo())

    def _motor_del_hilo(self):
        clave = threading.get_ident()
        if clave not in self._motores:
            self._motores[clave] = _motor(self.idioma)
        return self._motores[clave]


def reconocer(img, motor=None):
    (_lang, _alpha, BitmapPixelFormat, SoftwareBitmap,
     OcrEngine, DataWriter) = _importar()
    _preparar_hilo()
    motor = motor or _motor()

    escala = 1.0
    img = img.convert("RGB")
    maximo = int(OcrEngine.max_image_dimension)
    lado = max(img.size)
    if lado < LADO_PARA_AMPLIAR and lado * 2 <= maximo:
        escala = 2.0
    elif lado > maximo:
        escala = maximo / lado
    if escala != 1.0:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))))

    datos = img.convert("RGBA").tobytes("raw", "BGRA")
    escritor = DataWriter()
    escritor.write_bytes(datos)
    # Versión de 4 argumentos: existe en pywinrt 3.x y 4.x (la imagen es opaca).
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        escritor.detach_buffer(), BitmapPixelFormat.BGRA8, img.width, img.height)
    resultado = _esperar(motor.recognize_async(bitmap))

    lineas = []
    for linea in resultado.lines:
        palabras = []
        for palabra in linea.words:
            r = palabra.bounding_rect
            palabras.append((palabra.text, r.x / escala, r.y / escala,
                             r.width / escala, r.height / escala))
        if palabras:
            lineas.append(palabras)
    return lineas
