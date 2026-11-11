"""Une las imágenes de una carpeta en PDF por lotes (30 por defecto)."""
import re
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

EXTENSIONES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}


def _orden_natural(ruta):
    return [int(p) if p.isdigit() else p.lower()
            for p in re.split(r"(\d+)", ruta.name)]


def listar_imagenes(carpeta):
    carpeta = Path(carpeta)
    imagenes = [p for p in carpeta.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONES
                and ".tmp" not in p.suffixes]
    return sorted(imagenes, key=_orden_natural)


def lotes(lista, tamano):
    if tamano < 1:
        raise ValueError("El tamaño del lote debe ser 1 o más.")
    return [lista[i:i + tamano] for i in range(0, len(lista), tamano)]


def _pdf_de(imagenes, destino, dpi):
    c = canvas.Canvas(str(destino))
    for ruta in imagenes:
        with Image.open(ruta) as img:
            img = img.convert("RGB")
            ancho, alto = img.size
            w_pt, h_pt = ancho * 72.0 / dpi, alto * 72.0 / dpi
            c.setPageSize((w_pt, h_pt))
            c.drawImage(ImageReader(img), 0, 0, width=w_pt, height=h_pt)
            c.showPage()
    c.save()


def generar_pdfs(carpeta, por_pdf=30, destino=None, nombre="lote", dpi=150,
                 progreso=None):
    """Crea un PDF por cada lote de imágenes. Devuelve la lista de PDF creados.

    El último PDF lleva las imágenes que sobren aunque sean menos de `por_pdf`.
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
        _pdf_de(grupo, archivo, dpi)
        creados.append(archivo)
        if progreso:
            progreso(n, len(grupos), archivo)
        inicio = fin + 1
    return creados
