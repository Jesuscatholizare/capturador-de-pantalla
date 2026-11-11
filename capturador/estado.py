"""Progreso guardado en la carpeta de destino, para poder reanudar.

progreso.json se reescribe después de cada captura; registro.csv acumula
todos los fallos y decisiones, con fecha y número de captura.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

ARCHIVO_PROGRESO = "progreso.json"
ARCHIVO_REGISTRO = "registro.csv"


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


def guardar_progreso(carpeta, **datos):
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    datos["actualizado"] = _ahora()
    temporal = carpeta / (ARCHIVO_PROGRESO + ".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    temporal.replace(carpeta / ARCHIVO_PROGRESO)


def cargar_progreso(carpeta):
    ruta = Path(carpeta) / ARCHIVO_PROGRESO
    if not ruta.exists():
        return None
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def registrar(carpeta, captura, repeticion, intento, mensaje):
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta = carpeta / ARCHIVO_REGISTRO
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        if nuevo:
            w.writerow(["fecha", "captura", "repeticion", "intento", "detalle"])
        w.writerow([_ahora(), captura, repeticion, intento, mensaje])
