"""Pruebas del motor, las capturas y los PDF sin pantalla real.

Ejecutar:  python -m pytest pruebas
"""
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from capturador import capturas, estado, pdfs  # noqa: E402
from capturador.grabador import limpiar  # noqa: E402
from capturador.motor import Config, Motor, capturas_por_repeticion  # noqa: E402


def pagina(n, size=(400, 300)):
    """Imagen distinta para cada n (simula una página nueva)."""
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    for i in range(12):
        x0 = 10 + (n * 37 + i * 29) % (size[0] - 100)
        y0 = (5 + i * 22) % (size[1] - 20)
        d.rectangle([x0, y0, x0 + 20 + (n * 53 + i * 17) % 70, y0 + 14], fill="black")
    return img


class ReproFalso:
    def __init__(self):
        self.ejecutados = []
        self.pulsado = False

    def ejecutar(self, ev):
        self.ejecutados.append(ev)

    def soltar_todo(self):
        self.pulsado = False

    def hay_algo_pulsado(self):
        return self.pulsado


class Pantalla:
    """Devuelve una página nueva por cada «clic»; puede fallar a propósito."""
    def __init__(self, repro, fallos=None):
        self.repro = repro
        self.fallos = dict(fallos or {})  # nº de llamada -> 'excepcion'|'vacia'|'igual'
        self.llamadas = 0
        self.ultima = None

    def __call__(self):
        self.llamadas += 1
        tipo = self.fallos.pop(self.llamadas, None)
        if tipo == "excepcion":
            raise OSError("pantalla bloqueada")
        if tipo == "vacia":
            return Image.new("RGB", (400, 300), "black")
        n = len(self.repro.ejecutados)
        if tipo == "igual" and self.ultima is not None:
            return self.ultima.copy()
        self.ultima = pagina(n)
        return self.ultima


def macro_simple(marcas=0):
    eventos = [{"t": 0.001, "tipo": "clic", "x": 5, "y": 5, "boton": "left", "presionado": True},
               {"t": 0.002, "tipo": "clic", "x": 5, "y": 5, "boton": "left", "presionado": False}]
    for i in range(marcas):
        eventos.append({"t": 0.003 + i * 0.001, "tipo": "captura"})
        eventos.append({"t": 0.0035 + i * 0.001, "tipo": "tecla", "presionada": True,
                        "tecla": {"especial": "right"}})
    return {"version": 1, "eventos": eventos}


def config(tmp_path, **kw):
    base = dict(carpeta=str(tmp_path), repeticiones=5, modo="final", espera_captura_ms=0,
                espera_reintento_ms=0, espera_reanudar_ms=0, reintentos=2)
    base.update(kw)
    return Config(**base)


def archivos(tmp_path):
    return sorted(p.name for p in Path(tmp_path).glob("captura_*.png"))


def test_una_captura_por_repeticion(tmp_path):
    repro = ReproFalso()
    m = Motor(macro_simple(), config(tmp_path), repro, Pantalla(repro))
    assert m.ejecutar() == "completado"
    assert archivos(tmp_path) == [f"captura_{i:05d}.png" for i in range(1, 6)]
    prog = estado.cargar_progreso(tmp_path)
    assert prog["estado"] == "completado" and prog["siguiente"] == 6


def test_modos_marcas_y_ambos(tmp_path):
    assert capturas_por_repeticion(macro_simple(2), "marcas") == 2
    assert capturas_por_repeticion(macro_simple(2), "ambos") == 3
    with pytest.raises(ValueError):
        capturas_por_repeticion(macro_simple(0), "marcas")
    repro = ReproFalso()
    m = Motor(macro_simple(2), config(tmp_path, repeticiones=3, modo="ambos"),
              repro, Pantalla(repro))
    m.ejecutar()
    assert len(archivos(tmp_path)) == 9


def test_reintenta_y_continua(tmp_path):
    """La captura 3 falla dos veces (error y pantalla negra) y a la tercera sale."""
    repro = ReproFalso()
    pantalla = Pantalla(repro, fallos={3: "excepcion", 4: "vacia"})
    m = Motor(macro_simple(), config(tmp_path, politica="detener"), repro, pantalla)
    assert m.ejecutar() == "completado"
    assert len(archivos(tmp_path)) == 5
    registro = (Path(tmp_path) / "registro.csv").read_text(encoding="utf-8-sig")
    assert "pantalla bloqueada" in registro and "vacía" in registro
    assert "correcta tras reintento" in registro


def test_detecta_imagen_igual_a_la_anterior(tmp_path):
    repro = ReproFalso()
    pantalla = Pantalla(repro, fallos={2: "igual"})
    m = Motor(macro_simple(), config(tmp_path, politica="detener"), repro, pantalla)
    m.ejecutar()
    assert "igual a la anterior" in (Path(tmp_path) / "registro.csv").read_text(encoding="utf-8-sig")
    assert len(archivos(tmp_path)) == 5


def test_detener_y_reanudar_en_la_captura_del_fallo(tmp_path):
    """Falla la captura 4 sin remedio: se detiene, se guardan 1-3 y se reanuda en la 4."""
    repro = ReproFalso()
    fallos = {4: "excepcion", 5: "excepcion", 6: "excepcion"}
    m = Motor(macro_simple(), config(tmp_path, politica="detener"), repro,
              Pantalla(repro, fallos))
    assert m.ejecutar() == "detenido"
    assert len(archivos(tmp_path)) == 3
    prog = estado.cargar_progreso(tmp_path)
    assert prog["siguiente"] == 4 and prog["estado"] == "detenido"

    repro2 = ReproFalso()
    m2 = Motor(macro_simple(), config(tmp_path, inicio=prog["siguiente"]), repro2,
               Pantalla(repro2))
    assert m2.ejecutar() == "completado"
    assert len(archivos(tmp_path)) == 5
    assert len(repro2.ejecutados) == 2 * 2  # solo repeticiones 4 y 5


def test_preguntar_reintentar(tmp_path):
    repro = ReproFalso()
    preguntas = []

    def preguntar(datos):
        preguntas.append(datos)
        return "reintentar"

    fallos = {2: "excepcion", 3: "excepcion", 4: "excepcion"}
    m = Motor(macro_simple(), config(tmp_path), repro, Pantalla(repro, fallos),
              preguntar=preguntar)
    assert m.ejecutar() == "completado"
    assert preguntas and preguntas[0]["numero"] == 2
    assert len(archivos(tmp_path)) == 5


def test_guardar_con_aviso(tmp_path):
    repro = ReproFalso()
    fallos = {2: "vacia", 3: "vacia", 4: "vacia"}
    m = Motor(macro_simple(), config(tmp_path, politica="guardar"), repro,
              Pantalla(repro, fallos))
    assert m.ejecutar() == "completado"
    assert len(archivos(tmp_path)) == 5


def test_pausa_recaptura_y_detener(tmp_path):
    repro = ReproFalso()
    eventos = []
    m = Motor(macro_simple(), config(tmp_path, repeticiones=1000), repro, Pantalla(repro),
              notificar=lambda t, d: eventos.append((t, d)))
    hilo = threading.Thread(target=m.ejecutar)
    hilo.start()
    time.sleep(0.2)
    m.pausar()
    for _ in range(100):
        if any(t == "pausa" for t, _ in eventos):
            break
        time.sleep(0.02)
    n = m._ultima
    antes = (Path(tmp_path) / f"captura_{n:05d}.png").stat().st_mtime_ns
    time.sleep(0.05)
    m.recapturar(n)
    for _ in range(100):
        if any(t == "recapturada" for t, _ in eventos):
            break
        time.sleep(0.02)
    assert (Path(tmp_path) / f"captura_{n:05d}.png").stat().st_mtime_ns > antes
    assert m._ultima == n  # la pausa no avanzó
    m.detener()
    hilo.join(5)
    assert not hilo.is_alive()
    assert estado.cargar_progreso(tmp_path)["siguiente"] == n + 1


def test_pdfs_por_lotes_de_30(tmp_path):
    for i in range(1, 71):
        pagina(i, (200, 150)).save(tmp_path / f"captura_{i:05d}.png")
    creados = pdfs.generar_pdfs(tmp_path, 30)
    assert [p.name for p in creados] == [
        "lote_001_paginas_00001-00030.pdf",
        "lote_002_paginas_00031-00060.pdf",
        "lote_003_paginas_00061-00070.pdf"]
    paginas = [p.read_bytes().count(b"/Type /Page\n") + p.read_bytes().count(b"/Type /Page ")
               for p in creados]
    assert paginas == [30, 30, 10]


def test_orden_natural():
    nombres = [Path(n) for n in ["c_10.png", "c_2.png", "c_1.png"]]
    assert [p.name for p in sorted(nombres, key=pdfs._orden_natural)] == ["c_1.png", "c_2.png", "c_10.png"]


def test_limpiar_teclas_sueltas():
    eventos = [{"t": 0.1, "tipo": "tecla", "presionada": False, "tecla": {"especial": "enter"}},
               {"t": 0.2, "tipo": "tecla", "presionada": True, "tecla": {"char": "a", "vk": 65}},
               {"t": 0.3, "tipo": "tecla", "presionada": False, "tecla": {"char": "a", "vk": 65}}]
    assert len(limpiar(eventos)) == 2


def test_rechazo():
    a, b = pagina(1), pagina(2)
    assert capturas.motivo_rechazo(a, None) is None
    assert capturas.motivo_rechazo(a, b) is None
    assert "igual" in capturas.motivo_rechazo(a, a.copy())
    assert "vacía" in capturas.motivo_rechazo(Image.new("RGB", (50, 50), "white"))


class Area:
    """Una zona de la pantalla: cambia con cada vuelta, distinta de las otras zonas."""
    def __init__(self, repro, desfase, fallos=None):
        self.repro, self.desfase = repro, desfase
        self.fallos = dict(fallos or {})
        self.llamadas = 0

    def __call__(self):
        self.llamadas += 1
        tipo = self.fallos.pop(self.llamadas, None)
        if tipo == "excepcion":
            raise OSError("zona no disponible")
        return pagina(len(self.repro.ejecutados) * 10 + self.desfase)


def test_dos_areas_imagenes_separadas_en_orden(tmp_path):
    repro = ReproFalso()
    a1, a2 = Area(repro, 0), Area(repro, 5)
    m = Motor(macro_simple(), config(tmp_path, repeticiones=4), repro, [a1, a2])
    assert m.cpr == 2 and m.total == 8
    assert m.ejecutar() == "completado"
    assert len(archivos(tmp_path)) == 8
    assert a1.llamadas == 4 and a2.llamadas == 4
    # impares = área 1, pares = área 2
    img1 = Image.open(tmp_path / "captura_00003.png").convert("RGB")
    img2 = Image.open(tmp_path / "captura_00004.png").convert("RGB")
    assert capturas.porcentaje_cambio(img1, pagina(2 * 2 * 10 + 0)) == 0
    assert capturas.porcentaje_cambio(img2, pagina(2 * 2 * 10 + 5)) == 0
    assert estado.cargar_progreso(tmp_path)["areas"] == 2


def test_dos_areas_comparan_con_su_misma_area(tmp_path):
    """El área 2 no se compara con el área 1, sino con el área 2 de la vuelta anterior."""
    repro = ReproFalso()
    fija = pagina(999)
    a1 = Area(repro, 0)
    a2 = lambda: fija.copy()  # el área 2 nunca cambia
    m = Motor(macro_simple(), config(tmp_path, repeticiones=3, politica="detener"),
              repro, [a1, a2])
    assert m.ejecutar() == "detenido"
    # 1 (área 1) y 2 (área 2) se guardan; 3 (área 1) bien; 4 (área 2) igual a la 2
    assert len(archivos(tmp_path)) == 3
    assert estado.cargar_progreso(tmp_path)["siguiente"] == 4


def test_dos_areas_reanudar(tmp_path):
    repro = ReproFalso()
    a1, a2 = Area(repro, 0), Area(repro, 5, fallos={3: "excepcion", 4: "excepcion", 5: "excepcion"})
    m = Motor(macro_simple(), config(tmp_path, repeticiones=5, politica="detener"),
              repro, [a1, a2])
    assert m.ejecutar() == "detenido"
    prog = estado.cargar_progreso(tmp_path)
    assert prog["siguiente"] == 6  # falló el área 2 de la vuelta 3
    repro2 = ReproFalso()
    m2 = Motor(macro_simple(), config(tmp_path, repeticiones=5, inicio=6), repro2,
               [Area(repro2, 0), Area(repro2, 5)])
    assert m2.ejecutar() == "completado"
    assert len(archivos(tmp_path)) == 10
    assert len(repro2.ejecutados) == 3 * 2  # rehace la vuelta 3 completa, luego 4 y 5


def test_modo_inicio_captura_antes_de_las_acciones(tmp_path):
    """Captura la página que ya está en pantalla y después pasa a la siguiente."""
    repro = ReproFalso()
    vistos = []

    def captura():
        vistos.append(len(repro.ejecutados))  # acciones hechas antes de esta captura
        return pagina(len(repro.ejecutados))

    m = Motor(macro_simple(), config(tmp_path, repeticiones=3, modo="inicio"), repro, captura)
    assert m.ejecutar() == "completado"
    assert vistos == [0, 2, 4]          # la primera, sin haber pulsado nada
    assert len(repro.ejecutados) == 4   # la última vuelta no pasa de página
    assert len(archivos(tmp_path)) == 3


def pagina_blanca(numero_de_pagina=False):
    img = Image.new("RGB", (400, 300), (250, 248, 240))
    if numero_de_pagina:
        ImageDraw.Draw(img).rectangle([190, 280, 205, 290], fill="black")
    return img


def test_paginas_en_blanco_se_aceptan_sin_detenerse(tmp_path):
    """Entre capítulos: una página en blanco y luego otra (con número de página)."""
    repro = ReproFalso()
    llamadas = []

    def captura():
        llamadas.append(len(repro.ejecutados))
        vuelta = len(repro.ejecutados) // 2
        if vuelta == 1:
            return pagina_blanca()
        if vuelta == 2:
            return pagina_blanca(numero_de_pagina=True)
        return pagina(vuelta)

    preguntas = []
    m = Motor(macro_simple(), config(tmp_path, repeticiones=4, modo="inicio"),
              repro, captura, preguntar=lambda d: preguntas.append(d) or "detener")
    assert m.ejecutar() == "completado"
    assert preguntas == []
    assert len(archivos(tmp_path)) == 4
    registro = (Path(tmp_path) / "registro.csv").read_text(encoding="utf-8-sig")
    assert registro.count("página en blanco aceptada") == 2
    # cada blanca se reintentó antes de aceptarla (por si estaba cargando)
    assert len(llamadas) == 1 + 3 + 3 + 1


def test_pantalla_negra_sigue_siendo_error(tmp_path):
    repro = ReproFalso()
    m = Motor(macro_simple(), config(tmp_path, repeticiones=2, politica="detener"), repro,
              lambda: Image.new("RGB", (400, 300), "black"))
    assert m.ejecutar() == "detenido"
    assert capturas.es_pagina_en_blanco(pagina_blanca(True))
    assert not capturas.es_pagina_en_blanco(Image.new("RGB", (400, 300), "black"))
    assert not capturas.es_pagina_en_blanco(pagina(3))


def test_sin_la_opcion_la_blanca_detiene(tmp_path):
    repro = ReproFalso()
    m = Motor(macro_simple(), config(tmp_path, repeticiones=2, politica="detener",
                                     permitir_blancas=False), repro, lambda: pagina_blanca())
    assert m.ejecutar() == "detenido"


def test_pdf_con_capa_de_texto_ocr(tmp_path):
    """El texto «reconocido» se puede extraer del PDF y la página se ve igual."""
    import shutil
    import subprocess
    if not shutil.which("pdftotext"):
        pytest.skip("falta pdftotext")
    for i in (1, 2, 3):
        pagina(i, (600, 400)).save(tmp_path / f"captura_{i:05d}.png")

    def ocr_falso(img):
        return [[("Capítulo", 40, 30, 120, 24), ("primero:", 170, 30, 110, 24)],
                [("la", 40, 80, 30, 24), ("niñez", 80, 80, 80, 24), ("«feliz»", 170, 80, 100, 24)]]

    reconocidas = []
    creados = pdfs.generar_pdfs(tmp_path, 2, ocr=ocr_falso,
                                al_reconocer=lambda r, n: reconocidas.append((r.name, n)))
    assert [p.name for p in creados] == ["lote_001_paginas_00001-00002.pdf",
                                         "lote_002_paginas_00003-00003.pdf"]
    assert reconocidas[0] == ("captura_00001.png", 5) and len(reconocidas) == 3
    texto = subprocess.run(["pdftotext", "-layout", str(creados[0]), "-"],
                           capture_output=True, text=True).stdout
    assert "Capítulo primero:" in texto
    assert "la niñez «feliz»" in texto
    assert texto.count("Capítulo") == 2  # una vez por página
    assert not list((tmp_path / "PDF").glob("*.tmp.pdf"))


def test_listar_imagenes_ignora_subcarpetas(tmp_path):
    pagina(1).save(tmp_path / "captura_00001.png")
    (tmp_path / "_prueba").mkdir()
    pagina(2).save(tmp_path / "_prueba" / "prueba.png")
    assert [p.name for p in pdfs.listar_imagenes(tmp_path)] == ["captura_00001.png"]


def test_ocr_de_windows_simulado(monkeypatch):
    """Simula winrt: comprueba la ampliación ×2 y que las cajas vuelven al tamaño original."""
    import types
    from capturador import ocr

    recibido = {}

    class Rect:
        def __init__(self, x, y, w, h):
            self.x, self.y, self.width, self.height = x, y, w, h

    class Palabra:
        def __init__(self, t, r):
            self.text, self.bounding_rect = t, r

    class Linea:
        def __init__(self, palabras):
            self.words = palabras

    class Operacion:
        def __init__(self, r):
            self.r = r

        def get(self):
            return self.r

    class Motor:
        recognizer_language = types.SimpleNamespace(display_name="Español (México)")

        def recognize_async(self, bitmap):
            recibido["tam"] = bitmap
            return Operacion(types.SimpleNamespace(lines=[
                Linea([Palabra("Hola", Rect(20, 40, 80, 30)), Palabra("mundo", Rect(110, 40, 100, 30))])]))

    class OcrEngine:
        max_image_dimension = 10000

        @staticmethod
        def try_create_from_user_profile_languages():
            return Motor()

    class DataWriter:
        def write_bytes(self, b):
            self.b = b

        def detach_buffer(self):
            return self.b

    class SoftwareBitmap:
        @staticmethod
        def create_copy_from_buffer(buf, fmt, w, h):
            assert len(buf) == w * h * 4 and fmt == "BGRA8"
            return (w, h)

    mods = {
        "winrt": types.ModuleType("winrt"),
        "winrt.runtime": types.SimpleNamespace(ApartmentType=types.SimpleNamespace(MULTI_THREADED=0),
                                               init_apartment=lambda t: None),
        "winrt.windows.globalization": types.SimpleNamespace(Language=lambda t: t),
        "winrt.windows.graphics.imaging": types.SimpleNamespace(
            BitmapAlphaMode=None, BitmapPixelFormat=types.SimpleNamespace(BGRA8="BGRA8"),
            SoftwareBitmap=SoftwareBitmap),
        "winrt.windows.media.ocr": types.SimpleNamespace(OcrEngine=OcrEngine),
        "winrt.windows.storage.streams": types.SimpleNamespace(DataWriter=DataWriter),
    }
    for nombre, m in mods.items():
        monkeypatch.setitem(sys.modules, nombre, m)
    monkeypatch.setattr(ocr.sys, "platform", "win32")

    lineas = ocr.Reconocedor()(Image.new("RGB", (800, 600), "white"))
    assert recibido["tam"] == (1600, 1200)  # imagen pequeña: se amplía al doble
    assert lineas == [[("Hola", 10, 20, 40, 15), ("mundo", 55, 20, 50, 15)]]


def test_ocr_fuera_de_windows():
    from capturador import ocr
    if sys.platform == "win32":
        pytest.skip("solo fuera de Windows")
    with pytest.raises(ocr.OCRNoDisponible):
        ocr.comprobar()


def pagina_realista(n, size=(1000, 1400)):
    """Página de libro con textura de papel (como un escaneo): pesa mucho en PNG."""
    from PIL import ImageFilter
    w, h = size
    base = Image.effect_noise(size, 10).convert("L").point(lambda v: 236 + (v - 128) // 8)
    img = Image.merge("RGB", (base, base, base.point(lambda v: v - 10)))
    d = ImageDraw.Draw(img)
    for i in range(28):
        y = 90 + i * 44
        x = 80 + (n * 13 + i * 7) % 40
        d.rectangle([x, y, x + 600 + (n * 31 + i * 17) % 220, y + 14], fill=(30, 28, 26))
    return img.filter(ImageFilter.GaussianBlur(0.6))


def _carpeta_realista(tmp_path, n=30):
    for i in range(1, n + 1):
        pagina_realista(i).save(tmp_path / f"captura_{i:05d}.png")


def test_pdf_comprimido_cabe_en_el_limite(tmp_path):
    _carpeta_realista(tmp_path)
    original = pdfs.generar_pdfs(tmp_path, 30, destino=tmp_path / "orig")[0].stat().st_size
    avisos = []
    pdf = pdfs.generar_pdfs(tmp_path, 30, destino=tmp_path / "comp", formato="comprimido",
                            max_mb=2, aviso=avisos.append)[0]
    assert original > 10 * 1024 * 1024        # sin comprimir, más de 10 MB
    assert pdf.stat().st_size <= 2 * 1024 * 1024
    assert avisos == []


def test_pdf_comprimido_con_ocr_conserva_el_texto(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("pdftotext"):
        pytest.skip("falta pdftotext")
    _carpeta_realista(tmp_path, 6)
    pdf = pdfs.generar_pdfs(tmp_path, 30, formato="comprimido", max_mb=0.5, gris=True,
                            ocr=lambda img: [[("Capítulo", 80, 90, 200, 30)]])[0]
    assert pdf.stat().st_size <= 0.5 * 1024 * 1024
    texto = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout
    assert texto.count("Capítulo") == 6


def test_pdf_blanco_y_negro_es_ligero(tmp_path):
    _carpeta_realista(tmp_path, 10)
    byn = pdfs.generar_pdfs(tmp_path, 30, formato="byn")[0].stat().st_size
    assert byn < 10 * 150 * 1024  # menos de 150 KB por página


def test_pdf_solo_texto_y_txt(tmp_path):
    import shutil
    import subprocess
    _carpeta_realista(tmp_path, 3)
    ocr = lambda img: [[("La", 0, 0, 10, 10), ("niñez", 12, 0, 30, 10)], [("«feliz»", 0, 20, 40, 10)]]
    with pytest.raises(ValueError):
        pdfs.generar_pdfs(tmp_path, 30, formato="texto")  # sin OCR no se puede
    pdf = pdfs.generar_pdfs(tmp_path, 2, formato="texto", ocr=ocr)
    assert [p.name for p in pdf] == ["lote_001_paginas_00001-00002.pdf",
                                     "lote_002_paginas_00003-00003.pdf"]
    assert pdf[0].stat().st_size < 60 * 1024
    txt = pdf[1].with_suffix(".txt").read_text(encoding="utf-8")
    assert "===== Página 3 (captura_00003.png) =====" in txt and "La niñez\n«feliz»" in txt
    if shutil.which("pdftotext"):
        t = subprocess.run(["pdftotext", str(pdf[0]), "-"], capture_output=True, text=True).stdout
        assert t.count("La niñez") == 2 and "Página 2" in t


def test_aviso_si_no_cabe(tmp_path):
    _carpeta_realista(tmp_path, 5)
    avisos = []
    pdfs.generar_pdfs(tmp_path, 30, formato="original", max_mb=0.1, aviso=avisos.append)
    assert avisos and "no cabe en 0.1 MB" in avisos[0]
