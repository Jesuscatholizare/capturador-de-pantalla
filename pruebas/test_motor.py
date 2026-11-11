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
    base = dict(carpeta=str(tmp_path), repeticiones=5, espera_captura_ms=0,
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
