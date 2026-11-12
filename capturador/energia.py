"""Evita que Windows se suspenda o apague la pantalla mientras se trabaja.

Usa SetThreadExecutionState. La petición vale para el hilo que la hace: al
terminar se retira y, si el hilo acaba (incluso por un error), Windows la
retira solo. Así el equipo vuelve a su configuración normal de ahorro de
energía en cuanto termina el trabajo.
"""
import sys
from contextlib import contextmanager

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002


def _fijar(estado):
    if sys.platform != "win32":
        return False
    import ctypes
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(estado))


@contextmanager
def mantener_despierto():
    """Mientras dure el bloque: ni suspensión ni pantalla apagada."""
    activo = _fijar(ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED)
    try:
        yield activo
    finally:
        _fijar(ES_CONTINUOUS)  # vuelve al comportamiento normal
