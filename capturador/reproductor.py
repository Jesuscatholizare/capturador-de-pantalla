"""Ejecuta los eventos de la macro con pynput y recuerda qué hay pulsado,
para poder soltarlo todo si se pausa o se detiene."""
from . import teclas


class ReproductorPynput:
    def __init__(self):
        from pynput import keyboard, mouse
        self._mouse_mod = mouse
        self.raton = mouse.Controller()
        self.teclado = keyboard.Controller()
        self._teclas = {}    # clave -> objeto tecla pulsado
        self._botones = {}   # nombre -> botón pulsado

    def hay_algo_pulsado(self):
        return bool(self._teclas or self._botones)

    def ejecutar(self, ev):
        tipo = ev["tipo"]
        if tipo == "mover":
            self.raton.position = (ev["x"], ev["y"])
        elif tipo == "clic":
            self.raton.position = (ev["x"], ev["y"])
            boton = self._mouse_mod.Button[ev["boton"]]
            if ev["presionado"]:
                self.raton.press(boton)
                self._botones[ev["boton"]] = boton
            else:
                self.raton.release(boton)
                self._botones.pop(ev["boton"], None)
        elif tipo == "rueda":
            self.raton.position = (ev["x"], ev["y"])
            self.raton.scroll(ev["dx"], ev["dy"])
        elif tipo == "tecla":
            tecla = teclas.desde_dict(ev["tecla"])
            clave = repr(sorted(ev["tecla"].items()))
            if ev["presionada"]:
                self.teclado.press(tecla)
                self._teclas[clave] = tecla
            else:
                self.teclado.release(tecla)
                self._teclas.pop(clave, None)

    def soltar_todo(self):
        for tecla in list(self._teclas.values()):
            try:
                self.teclado.release(tecla)
            except Exception:
                pass
        for boton in list(self._botones.values()):
            try:
                self.raton.release(boton)
            except Exception:
                pass
        self._teclas.clear()
        self._botones.clear()
