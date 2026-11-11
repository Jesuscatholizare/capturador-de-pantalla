"""Graba teclado y ratón con pynput.

F8 inserta una marca de captura; F9 termina la grabación.
"""
import threading
import time

from . import teclas
from .macro import nueva_macro

INTERVALO_MOVIMIENTO = 0.02  # segundos mínimos entre dos movimientos guardados


class Grabador:
    def __init__(self, al_terminar=None, al_marcar=None):
        self.al_terminar = al_terminar
        self.al_marcar = al_marcar
        self.macro = nueva_macro()
        self._t0 = None
        self._ultimo_mov = -1.0
        self._lock = threading.Lock()
        self._oyente_raton = None
        self._oyente_teclado = None
        self._terminado = False

    # -- utilidades ---------------------------------------------------
    def _t(self):
        return time.perf_counter() - self._t0

    def _agregar(self, ev):
        with self._lock:
            if not self._terminado:
                self.macro["eventos"].append(ev)

    # -- ratón ----------------------------------------------------------
    def _mover(self, x, y):
        t = self._t()
        if t - self._ultimo_mov >= INTERVALO_MOVIMIENTO:
            self._ultimo_mov = t
            self._agregar({"t": t, "tipo": "mover", "x": int(x), "y": int(y)})

    def _clic(self, x, y, boton, presionado):
        self._agregar({"t": self._t(), "tipo": "clic", "x": int(x), "y": int(y),
                       "boton": boton.name, "presionado": bool(presionado)})

    def _rueda(self, x, y, dx, dy):
        self._agregar({"t": self._t(), "tipo": "rueda", "x": int(x), "y": int(y),
                       "dx": int(dx), "dy": int(dy)})

    # -- teclado --------------------------------------------------------
    def _tecla(self, key, presionada):
        nombre = teclas.nombre_especial(key)
        if nombre in teclas.RESERVADAS:
            if presionada and nombre == teclas.TECLA_MARCA:
                self._agregar({"t": self._t(), "tipo": "captura"})
                if self.al_marcar:
                    self.al_marcar()
            elif presionada and nombre == teclas.TECLA_PAUSA:
                self.detener()
            return
        self._agregar({"t": self._t(), "tipo": "tecla", "presionada": presionada,
                       "tecla": teclas.a_dict(key)})

    # -- control --------------------------------------------------------
    def iniciar(self):
        from pynput import keyboard, mouse
        self._t0 = time.perf_counter()
        self._oyente_raton = mouse.Listener(on_move=self._mover, on_click=self._clic,
                                            on_scroll=self._rueda)
        self._oyente_teclado = keyboard.Listener(
            on_press=lambda k: self._tecla(k, True),
            on_release=lambda k: self._tecla(k, False))
        self._oyente_raton.start()
        self._oyente_teclado.start()

    def detener(self):
        with self._lock:
            if self._terminado:
                return
            self._terminado = True
        for oyente in (self._oyente_raton, self._oyente_teclado):
            if oyente:
                oyente.stop()
        self.macro["eventos"] = limpiar(self.macro["eventos"])
        if self.al_terminar:
            self.al_terminar(self.macro)


def limpiar(eventos):
    """Quita teclas soltadas sin haberse pulsado durante la grabación
    (p. ej. soltar la tecla con la que se arrancó) y ordena por tiempo."""
    eventos = sorted(eventos, key=lambda e: e["t"])
    pulsadas = set()
    resultado = []
    for ev in eventos:
        if ev["tipo"] == "tecla":
            clave = repr(sorted(ev["tecla"].items()))
            if ev["presionada"]:
                pulsadas.add(clave)
            elif clave not in pulsadas:
                continue
            else:
                pulsadas.discard(clave)
        resultado.append(ev)
    return resultado
