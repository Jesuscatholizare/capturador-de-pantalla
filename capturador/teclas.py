"""Conversión entre teclas de pynput y diccionarios guardables en JSON.

Se guarda el código virtual (vk) además del carácter: en Windows, con Ctrl
pulsado, pynput entrega caracteres de control (p. ej. '\\x03' para Ctrl+C) y
solo el vk permite reproducir la combinación correctamente.
"""
import sys

# Teclas reservadas para controlar el programa: nunca se graban.
TECLA_MARCA = "f8"      # al grabar: marca de captura
TECLA_PAUSA = "f9"      # al grabar: terminar; al reproducir: pausar/continuar
TECLA_DETENER = "f10"   # al reproducir: detener de inmediato
RESERVADAS = {TECLA_MARCA, TECLA_PAUSA, TECLA_DETENER}


def nombre_especial(key):
    """Devuelve el nombre ('f8', 'enter'...) si es tecla especial, o None."""
    return getattr(key, "name", None)


def a_dict(key):
    nombre = nombre_especial(key)
    if nombre is not None:
        return {"especial": nombre}
    return {"char": getattr(key, "char", None), "vk": getattr(key, "vk", None)}


def desde_dict(d):
    from pynput import keyboard  # import tardío: pynput necesita escritorio
    if "especial" in d:
        return keyboard.Key[d["especial"]]
    vk, char = d.get("vk"), d.get("char")
    if vk is not None and sys.platform == "win32":
        return keyboard.KeyCode.from_vk(vk)
    if char is not None:
        return keyboard.KeyCode.from_char(char)
    if vk is not None:
        return keyboard.KeyCode.from_vk(vk)
    raise ValueError(f"Tecla no reproducible: {d}")
