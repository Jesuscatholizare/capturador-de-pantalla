"""Formato de la macro grabada: lista de eventos con su tiempo relativo.

Cada evento es un diccionario con, al menos:
    t     -> segundos desde el inicio de la grabación
    tipo  -> 'mover' | 'clic' | 'rueda' | 'tecla' | 'captura'

'captura' es una marca (tecla F8 al grabar): en ese punto se toma una imagen.
"""
import json
from pathlib import Path

VERSION_FORMATO = 1


def nueva_macro():
    return {"version": VERSION_FORMATO, "eventos": []}


def guardar(macro, ruta):
    ruta = Path(ruta)
    ruta.write_text(json.dumps(macro, ensure_ascii=False, indent=1), encoding="utf-8")


def cargar(ruta):
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if "eventos" not in datos or not isinstance(datos["eventos"], list):
        raise ValueError("El archivo no es una macro válida (falta 'eventos').")
    datos["eventos"].sort(key=lambda e: e["t"])
    return datos


def resumen(macro):
    eventos = macro["eventos"]
    marcas = sum(1 for e in eventos if e["tipo"] == "captura")
    acciones = len(eventos) - marcas
    duracion = eventos[-1]["t"] if eventos else 0.0
    return {"acciones": acciones, "marcas": marcas, "duracion": duracion}


def texto_resumen(macro):
    r = resumen(macro)
    return (f"{r['acciones']} acciones, {r['marcas']} marcas de captura, "
            f"{r['duracion']:.1f} s por repetición")
