"""Toma de capturas de pantalla y comprobación de que la imagen es válida."""
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

TAM_COMPARACION = (320, 180)


def tomar_captura(monitor=1, region=None):
    """Devuelve una imagen PIL RGB.

    monitor: 0 = todos los monitores juntos, 1 = principal, 2 = segundo...
    region:  (x, y, ancho, alto) en píxeles de pantalla, o None.
    """
    import mss
    with mss.mss() as sct:
        if region:
            x, y, w, h = region
            zona = {"left": int(x), "top": int(y), "width": int(w), "height": int(h)}
        else:
            if monitor >= len(sct.monitors):
                raise ValueError(f"No existe el monitor {monitor} "
                                 f"(hay {len(sct.monitors) - 1}).")
            zona = sct.monitors[monitor]
        shot = sct.grab(zona)
        return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _reducida(img):
    return img.convert("L").resize(TAM_COMPARACION)


def porcentaje_cambio(img, previa):
    """% de píxeles (en una versión reducida) que cambian de forma visible."""
    diff = ImageChops.difference(_reducida(img), _reducida(previa))
    distintos = sum(diff.point(lambda v: 255 if v > 24 else 0).histogram()[255:])
    total = TAM_COMPARACION[0] * TAM_COMPARACION[1]
    return 100.0 * distintos / total


def motivo_rechazo(img, previa=None, rechazar_vacia=True,
                   rechazar_igual=True, umbral_cambio=0.5):
    """Devuelve None si la imagen es aceptable o un texto con el motivo."""
    if rechazar_vacia:
        desviacion = ImageStat.Stat(_reducida(img)).stddev[0]
        if desviacion < 2.0:
            return "imagen vacía (toda de un color)"
    if rechazar_igual and previa is not None:
        if img.size == previa.size:
            cambio = porcentaje_cambio(img, previa)
            if cambio < umbral_cambio:
                return f"igual a la anterior (cambió {cambio:.2f} %)"
    return None


def guardar(img, ruta, calidad_jpg=92):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.stem + ".tmp" + ruta.suffix)
    if ruta.suffix.lower() in (".jpg", ".jpeg"):
        img.save(temporal, "JPEG", quality=calidad_jpg)
    else:
        img.save(temporal, "PNG", optimize=False, compress_level=3)
    temporal.replace(ruta)  # escritura atómica: no quedan imágenes a medias
