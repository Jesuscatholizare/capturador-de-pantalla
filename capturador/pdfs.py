"""Une las imágenes de una carpeta en PDF por lotes (30 por defecto).

Con OCR, cada página lleva además el texto reconocido como capa invisible,
encima de la imagen y en el mismo sitio de cada palabra: el PDF se ve igual,
pero se puede buscar (Ctrl+F), seleccionar y copiar.
"""
import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image
from reportlab import rl_config
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas

# Por defecto ReportLab guarda las imágenes en ASCII85 (texto), que añade un
# 25 % de peso sin ninguna ventaja: se guardan en binario.
rl_config.useA85 = 0

# Formatos de PDF:
#   original   imagen sin pérdida (máxima calidad, pesa mucho)
#   comprimido JPEG; con max_mb se ajusta página a página hasta que el PDF quepa
#   byn        blanco y negro de 1 bit: muy ligero y nítido para libros de texto
#   texto      solo el texto reconocido por OCR, sin imágenes (más un .txt)
FORMATOS = ("original", "comprimido", "byn", "texto")

# Escalones de compresión (escala, calidad JPEG), de mejor a más ligero.
ESCALONES = [(1.0, 80), (1.0, 70), (1.0, 60), (1.0, 50), (0.85, 50), (0.75, 50),
             (0.75, 40), (0.65, 40), (0.6, 30), (0.5, 30), (0.4, 25)]

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


def _jpeg(img, escala, calidad):
    if escala != 1.0:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))),
                         Image.LANCZOS)
    b = io.BytesIO()
    img.save(b, "JPEG", quality=calidad, optimize=True)
    return b.getvalue()


def _blanco_y_negro(img):
    """1 bit: el umbral se calcula con el tono del papel de cada página."""
    gris = img.convert("L")
    hist = gris.histogram()
    total, acumulado, mediana = sum(hist), 0, 255
    for valor, n in enumerate(hist):
        acumulado += n
        if acumulado * 2 >= total:
            mediana = valor
            break
    umbral = max(60, int(mediana * 0.72))
    return gris.point(lambda v: 255 if v > umbral else 0).convert("1")


def _imagen_para_pdf(img, formato, gris, presupuesto):
    """Devuelve lo que se dibuja en la página según el formato."""
    if formato == "byn":
        return ImageReader(_blanco_y_negro(img))
    if formato == "comprimido":
        fuente = img.convert("L") if gris else img
        if presupuesto is None:
            return ImageReader(io.BytesIO(_jpeg(fuente, 1.0, 70)))
        datos = None
        for escala, calidad in ESCALONES:
            datos = _jpeg(fuente, escala, calidad)
            if len(datos) <= presupuesto:
                break
        return ImageReader(io.BytesIO(datos))
    return ImageReader(img)


def _pdf_de(imagenes, destino, dpi, lineas_por_imagen=None, formato="original",
            gris=False, presupuesto=None):
    """PDF con una imagen por página y, si hay OCR, su texto invisible encima."""
    c = canvas.Canvas(str(destino))
    escala = 72.0 / dpi
    for ruta in imagenes:
        with Image.open(ruta) as img:
            img = img.convert("RGB")
            ancho, alto = img.size
            # el tamaño de página sale de la imagen original: aunque se reduzca
            # al comprimir, la página y el texto del OCR no cambian de sitio
            w_pt, h_pt = ancho * escala, alto * escala
            c.setPageSize((w_pt, h_pt))
            c.drawImage(_imagen_para_pdf(img, formato, gris, presupuesto),
                        0, 0, width=w_pt, height=h_pt)
            if lineas_por_imagen is not None:
                _capa_de_texto(c, lineas_por_imagen[ruta], escala, h_pt)
            c.showPage()
    c.save()


def _pdf_solo_texto(imagenes, destino, lineas_por_imagen, numero_inicial):
    """PDF sin imágenes: el texto de cada captura en su propia página, y un .txt."""
    from reportlab.lib.colors import grey
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

    fuente = _fuente_texto()
    normal = ParagraphStyle("normal", fontName=fuente, fontSize=11, leading=15)
    cabecera = ParagraphStyle("cabecera", fontName=fuente, fontSize=8, leading=10,
                              textColor=grey, spaceAfter=8)
    historia, txt = [], []
    for k, ruta in enumerate(imagenes):
        n = numero_inicial + k
        lineas = [" ".join(_texto_seguro(p[0], fuente) for p in l) for l in lineas_por_imagen[ruta]]
        historia.append(Paragraph(escape(f"Página {n} · {ruta.name}"), cabecera))
        txt.append(f"===== Página {n} ({ruta.name}) =====")
        if not lineas:
            historia.append(Paragraph("<i>(sin texto reconocido: página en blanco o imagen)</i>",
                                      normal))
        for linea in lineas:
            historia.append(Paragraph(escape(linea), normal))
            txt.append(linea)
        txt.append("")
        if k < len(imagenes) - 1:
            historia.append(PageBreak())
    SimpleDocTemplate(str(destino), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                      topMargin=2 * cm, bottomMargin=2 * cm).build(historia)
    return "\n".join(txt)


def generar_pdfs(carpeta, por_pdf=30, destino=None, nombre="lote", dpi=150,
                 progreso=None, ocr=None, al_reconocer=None, formato="original",
                 max_mb=None, gris=False, aviso=None):
    """Crea un PDF por cada lote de imágenes. Devuelve la lista de PDF creados.

    El último PDF lleva las imágenes que sobren aunque sean menos de `por_pdf`.
    Con `ocr`, cada página lleva el texto reconocido (buscable y copiable).
    formato: ver FORMATOS. max_mb: peso máximo de cada PDF (formato «comprimido»
    ajusta la compresión para cumplirlo; en los demás solo se avisa).
    aviso(texto): se llama si un PDF no cabe en max_mb.
    """
    if formato not in FORMATOS:
        raise ValueError(f"Formato de PDF desconocido: {formato}")
    if formato == "texto" and ocr is None:
        raise ValueError("El formato «solo texto» necesita el OCR.")
    imagenes = listar_imagenes(carpeta)
    if not imagenes:
        raise ValueError(f"No hay imágenes en {carpeta}")
    limite = int(max_mb * 1024 * 1024) if max_mb else None
    destino = Path(destino) if destino else Path(carpeta) / "PDF"
    destino.mkdir(parents=True, exist_ok=True)
    creados = []
    grupos = lotes(imagenes, por_pdf)
    inicio = 1
    for n, grupo in enumerate(grupos, start=1):
        fin = inicio + len(grupo) - 1
        archivo = destino / f"{nombre}_{n:03d}_paginas_{inicio:05d}-{fin:05d}.pdf"
        temporal = archivo.with_name(archivo.stem + ".tmp.pdf")
        lineas = None
        if ocr is not None:  # se reconoce una sola vez, sobre la imagen original
            lineas = {}
            for ruta in grupo:
                with Image.open(ruta) as img:
                    lineas[ruta] = ocr(img.convert("RGB"))
                if al_reconocer:
                    al_reconocer(ruta, sum(len(l) for l in lineas[ruta]))
        if formato == "texto":
            texto = _pdf_solo_texto(grupo, temporal, lineas, inicio)
            txt = archivo.with_suffix(".txt")
            txt.with_name(txt.name + ".tmp").write_text(texto, encoding="utf-8")
            txt.with_name(txt.name + ".tmp").replace(txt)
        elif formato == "comprimido" and limite:
            presupuesto = limite * 0.95 / len(grupo)
            for _ in range(5):
                _pdf_de(grupo, temporal, dpi, lineas, formato, gris, presupuesto)
                peso = temporal.stat().st_size
                if peso <= limite:
                    break
                presupuesto *= limite / peso * 0.9  # el texto del OCR también ocupa
        else:
            _pdf_de(grupo, temporal, dpi, lineas, formato, gris)
        temporal.replace(archivo)  # no quedan PDF a medias si algo falla
        peso = archivo.stat().st_size
        if limite and peso > limite and aviso:
            consejo = ("escala de grises, «Blanco y negro» o menos imágenes por PDF"
                       if formato != "byn" else "menos imágenes por PDF")
            aviso(f"{archivo.name} pesa {peso / 1048576:.1f} MB y no cabe en {max_mb:g} MB. "
                  f"Prueba con {consejo}.")
        creados.append(archivo)
        if progreso:
            progreso(n, len(grupos), archivo)
        inicio = fin + 1
    return creados
