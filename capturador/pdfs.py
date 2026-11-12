"""Une las imágenes de una carpeta en PDF por lotes (30 por defecto).

Con OCR, cada página lleva además el texto reconocido como capa invisible,
encima de la imagen y en el mismo sitio de cada palabra: el PDF se ve igual,
pero se puede buscar (Ctrl+F), seleccionar y copiar.
"""
import re
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

FUENTES_UNICODE = [  # para acentos, ñ, comillas… en la capa de texto
    Path(r"C:\Windows\Fonts\arial.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
]
_fuente = None


def _fuente_texto():
    """Una fuente TrueType con Unicode completo si existe; si no, Helvetica."""
    global _fuente
    if _fuente is None:
        _fuente = "Helvetica"
        for ruta in FUENTES_UNICODE:
            if ruta.exists():
                try:
                    from reportlab.pdfbase.ttfonts import TTFont
                    pdfmetrics.registerFont(TTFont("TextoOCR", str(ruta)))
                    _fuente = "TextoOCR"
                    break
                except Exception:
                    pass
    return _fuente


def _texto_seguro(texto, fuente):
    if fuente == "Helvetica":  # solo admite el juego de caracteres de Windows
        return texto.encode("cp1252", "replace").decode("cp1252")
    return texto


def _capa_de_texto(c, lineas, escala, alto_pt):
    """Dibuja el texto reconocido, invisible, sobre la página actual."""
    fuente = _fuente_texto()
    for palabras in lineas:
        for i, (texto, x, y, w, h) in enumerate(palabras):
            texto = _texto_seguro(texto, fuente)
            if not texto.strip() or w <= 0 or h <= 0:
                continue
            ultima = i == len(palabras) - 1
            # cada palabra lleva su espacio, para que al copiar salga «una frase», no «unafrase»
            contenido = texto if ultima else texto + " "
            hasta = x + w if ultima else max(x + w, palabras[i + 1][1])
            tam = max(1.0, h * escala)
            natural = pdfmetrics.stringWidth(contenido, fuente, tam)
            if natural <= 0:
                continue
            t = c.beginText()
            t.setTextRenderMode(3)  # invisible
            t.setFont(fuente, tam)
            t.setHorizScale(100.0 * (hasta - x) * escala / natural)
            t.setTextOrigin(x * escala, alto_pt - (y + h) * escala + 0.2 * tam)
            t.textOut(contenido)
            c.drawText(t)

EXTENSIONES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def _orden_natural(ruta):
    return [int(p) if p.isdigit() else p.lower()
            for p in re.split(r"(\d+)", ruta.name)]


def listar_imagenes(carpeta):
    """Imágenes de la carpeta (no de sus subcarpetas), en orden natural."""
    carpeta = Path(carpeta)
    imagenes = [p for p in carpeta.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONES
                and ".tmp" not in p.suffixes]
    return sorted(imagenes, key=_orden_natural)


def lotes(lista, tamano):
    if tamano < 1:
        raise ValueError("El tamaño del lote debe ser 1 o más.")
    return [lista[i:i + tamano] for i in range(0, len(lista), tamano)]


def _pdf_de(imagenes, destino, dpi, ocr=None, al_reconocer=None):
    """Crea un PDF. `ocr(img)` devuelve las líneas reconocidas (ver ocr.py)."""
    c = canvas.Canvas(str(destino))
    escala = 72.0 / dpi
    for ruta in imagenes:
        with Image.open(ruta) as img:
            img = img.convert("RGB")
            ancho, alto = img.size
            w_pt, h_pt = ancho * escala, alto * escala
            c.setPageSize((w_pt, h_pt))
            c.drawImage(ImageReader(img), 0, 0, width=w_pt, height=h_pt)
            if ocr is not None:
                lineas = ocr(img)
                _capa_de_texto(c, lineas, escala, h_pt)
                if al_reconocer:
                    al_reconocer(ruta, sum(len(l) for l in lineas))
            c.showPage()
    c.save()


def generar_pdfs(carpeta, por_pdf=30, destino=None, nombre="lote", dpi=150,
                 progreso=None, ocr=None, al_reconocer=None):
    """Crea un PDF por cada lote de imágenes. Devuelve la lista de PDF creados.

    El último PDF lleva las imágenes que sobren aunque sean menos de `por_pdf`.
    Con `ocr`, cada página lleva el texto reconocido (buscable y copiable).
    """
    imagenes = listar_imagenes(carpeta)
    if not imagenes:
        raise ValueError(f"No hay imágenes en {carpeta}")
    destino = Path(destino) if destino else Path(carpeta) / "PDF"
    destino.mkdir(parents=True, exist_ok=True)
    creados = []
    grupos = lotes(imagenes, por_pdf)
    inicio = 1
    for n, grupo in enumerate(grupos, start=1):
        fin = inicio + len(grupo) - 1
        archivo = destino / f"{nombre}_{n:03d}_paginas_{inicio:05d}-{fin:05d}.pdf"
        temporal = archivo.with_name(archivo.stem + ".tmp.pdf")
        _pdf_de(grupo, temporal, dpi, ocr, al_reconocer)
        temporal.replace(archivo)  # no quedan PDF a medias si algo falla
        creados.append(archivo)
        if progreso:
            progreso(n, len(grupos), archivo)
        inicio = fin + 1
    return creados
