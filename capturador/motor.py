"""Motor de automatización: repite la macro, toma las capturas, reintenta
cuando una captura falla y guarda el progreso para poder reanudar.

Es independiente de la interfaz: recibe el reproductor y la función de
captura, así que puede probarse sin pantalla.
"""
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path

from PIL import Image

from . import capturas, estado


class Detenido(Exception):
    """La ejecución se detuvo (por el usuario o por un error sin resolver)."""


@dataclass
class Config:
    carpeta: str
    repeticiones: int = 1
    modo: str = "final"            # final | marcas | ambos
    espera_captura_ms: int = 800   # espera antes de cada captura
    velocidad: float = 1.0         # 2.0 = el doble de rápido
    pausa_entre_reps_ms: int = 0
    inicio: int = 1                # número de la primera captura a tomar
    prefijo: str = "captura"
    formato: str = "png"           # png | jpg
    reintentos: int = 3
    espera_reintento_ms: int = 1500
    rechazar_vacia: bool = True
    rechazar_igual: bool = True
    umbral_cambio: float = 0.5     # % mínimo de píxeles que deben cambiar
    politica: str = "preguntar"    # preguntar | guardar | detener
    espera_reanudar_ms: int = 1500  # margen tras cerrar un aviso o reanudar


MODOS = ("final", "marcas", "ambos")
DECISIONES = ("reintentar", "pausar", "guardar", "detener")


def capturas_por_repeticion(macro, modo):
    if modo not in MODOS:
        raise ValueError(f"Modo desconocido: {modo}")
    marcas = sum(1 for e in macro["eventos"] if e["tipo"] == "captura")
    if modo == "marcas" and marcas == 0:
        raise ValueError("El modo «en las marcas» necesita una macro con marcas "
                         "(pulsa F8 mientras grabas en el momento de capturar).")
    n = (marcas if modo in ("marcas", "ambos") else 0) + (1 if modo in ("final", "ambos") else 0)
    return n


class Motor:
    def __init__(self, macro, config, reproductor, capturar,
                 notificar=None, preguntar=None):
        """
        reproductor: objeto con ejecutar(ev), soltar_todo(), hay_algo_pulsado()
        capturar:    función sin argumentos que devuelve una imagen PIL
        notificar:   función(tipo, datos: dict) para informar a la interfaz
        preguntar:   función(datos: dict) -> una de DECISIONES (bloqueante)
        """
        self.macro = macro
        self.cfg = config
        self.repro = reproductor
        self.capturar = capturar
        self._notificar = notificar or (lambda tipo, datos: None)
        self.preguntar = preguntar
        self.cpr = capturas_por_repeticion(macro, config.modo)
        self.total = self.cpr * config.repeticiones
        self._detener = threading.Event()
        self._pausa = threading.Event()
        self._recaptura = None
        self._lock = threading.Lock()
        self._previa = None
        self._ultima = None
        self._siguiente = None
        self._rep = 0
        self._reps_completas = 0

    # -- órdenes desde la interfaz (cualquier hilo) ---------------------
    def pausar(self):
        self._pausa.set()

    def continuar(self):
        self._pausa.clear()

    def alternar_pausa(self):
        if self._pausa.is_set():
            self.continuar()
        else:
            self.pausar()

    def en_pausa(self):
        return self._pausa.is_set()

    def detener(self):
        self._detener.set()

    def recapturar(self, numero):
        """Solo durante la pausa: vuelve a tomar la captura `numero`."""
        with self._lock:
            self._recaptura = int(numero)

    # -- utilidades -----------------------------------------------------
    def ruta(self, numero):
        return Path(self.cfg.carpeta) / f"{self.cfg.prefijo}_{numero:05d}.{self.cfg.formato}"

    def notificar(self, tipo, **datos):
        datos.setdefault("total", self.total)
        self._notificar(tipo, datos)

    def _guardar_progreso(self, situacion):
        estado.guardar_progreso(
            self.cfg.carpeta, estado=situacion, siguiente=self._siguiente,
            ultima_guardada=self._ultima, total_capturas=self.total,
            capturas_por_repeticion=self.cpr,
            repeticiones_completadas=self._reps_completas,
            total_repeticiones=self.cfg.repeticiones, config=asdict(self.cfg))

    def _registrar(self, numero, intento, mensaje):
        estado.registrar(self.cfg.carpeta, numero, self._rep + 1, intento, mensaje)

    def _esperar(self, segundos, pausable=True):
        fin = time.monotonic() + max(0.0, segundos)
        while True:
            if self._detener.is_set():
                raise Detenido("Detenido por el usuario.")
            if pausable and self._pausa.is_set() and not self.repro.hay_algo_pulsado():
                fin += self._atender_pausa()
            resto = fin - time.monotonic()
            if resto <= 0:
                return
            time.sleep(min(0.02, resto))

    def _atender_pausa(self):
        inicio = time.monotonic()
        self.notificar("pausa", siguiente=self._siguiente, ultima=self._ultima)
        while self._pausa.is_set():
            if self._detener.is_set():
                raise Detenido("Detenido por el usuario.")
            with self._lock:
                pedido, self._recaptura = self._recaptura, None
            if pedido is not None:
                self._esperar(self.cfg.espera_reanudar_ms / 1000, pausable=False)
                self._capturar(pedido, manual=True)
                self.notificar("recapturada", numero=pedido)
            time.sleep(0.05)
        self.notificar("reanudar", siguiente=self._siguiente)
        self._esperar(self.cfg.espera_reanudar_ms / 1000, pausable=False)
        return time.monotonic() - inicio

    # -- captura con reintentos ---------------------------------------------
    def _capturar(self, numero, manual=False):
        cfg = self.cfg
        previa = None if manual else self._previa
        while True:
            ultima_img, motivo = None, None
            for intento in range(1, cfg.reintentos + 2):
                try:
                    img = self.capturar()
                except Exception as e:  # noqa: BLE001 - cualquier fallo de captura
                    img, motivo = None, f"error al capturar: {e}"
                else:
                    ultima_img = img
                    motivo = capturas.motivo_rechazo(
                        img, previa, cfg.rechazar_vacia,
                        cfg.rechazar_igual and not manual, cfg.umbral_cambio)
                if motivo is None:
                    self._guardar_imagen(numero, img, manual)
                    if intento > 1:
                        self._registrar(numero, intento, "correcta tras reintento")
                    self.notificar("captura", numero=numero, intento=intento,
                                   manual=manual)
                    return
                self._registrar(numero, intento, motivo)
                self.notificar("fallo", numero=numero, intento=intento,
                               maximo=cfg.reintentos + 1, motivo=motivo)
                if intento <= cfg.reintentos:
                    self._esperar(cfg.espera_reintento_ms / 1000, pausable=False)

            decision = cfg.politica
            if decision == "preguntar":
                decision = (self.preguntar(dict(numero=numero, motivo=motivo,
                                                hay_imagen=ultima_img is not None,
                                                manual=manual))
                            if self.preguntar else "detener")
            self._registrar(numero, "-", f"decisión: {decision}")

            if decision == "reintentar":
                self._esperar(cfg.espera_reanudar_ms / 1000, pausable=False)
                continue
            if decision == "pausar":
                if manual:  # ya estamos en pausa: se deja como estaba
                    return
                self._pausa.set()
                self._atender_pausa()
                continue
            if decision == "guardar" and ultima_img is not None:
                self._guardar_imagen(numero, ultima_img, manual)
                self.notificar("captura", numero=numero, intento="aviso", manual=manual,
                               aviso=motivo)
                return
            raise Detenido(f"Detenido en la captura {numero}: {motivo}")

    def _guardar_imagen(self, numero, img, manual):
        capturas.guardar(img, self.ruta(numero))
        if not manual:
            self._previa = img
            self._ultima = numero
            self._siguiente = numero + 1
            self._guardar_progreso("en curso")

    # -- ejecución principal -----------------------------------------------
    def ejecutar(self):
        cfg = self.cfg
        if cfg.repeticiones < 1:
            raise ValueError("Las repeticiones deben ser 1 o más.")
        if cfg.velocidad <= 0:
            raise ValueError("La velocidad debe ser mayor que 0.")
        inicio = max(1, int(cfg.inicio))
        rep0 = (inicio - 1) // self.cpr
        if rep0 >= cfg.repeticiones:
            raise ValueError(f"La captura {inicio} está fuera del total ({self.total}).")
        numero = rep0 * self.cpr + 1
        if numero != inicio:
            self.notificar("aviso", mensaje=(
                f"Cada repetición toma {self.cpr} capturas: se empieza en la "
                f"{numero}, al principio de la repetición {rep0 + 1}."))
        anterior = self.ruta(numero - 1)
        if numero > 1 and anterior.exists():
            with Image.open(anterior) as im:
                self._previa = im.convert("RGB")
        self._siguiente = numero
        self._reps_completas = rep0
        usa_marcas = cfg.modo in ("marcas", "ambos")
        usa_final = cfg.modo in ("final", "ambos")
        espera = cfg.espera_captura_ms / 1000
        situacion, mensaje = "detenido", ""
        self.notificar("inicio", desde=numero, repeticion=rep0 + 1)
        try:
            for rep in range(rep0, cfg.repeticiones):
                self._rep = rep
                self.notificar("repeticion", repeticion=rep + 1,
                               repeticiones=cfg.repeticiones)
                t_prev = 0.0
                for ev in self.macro["eventos"]:
                    self._esperar((ev["t"] - t_prev) / cfg.velocidad)
                    t_prev = ev["t"]
                    if ev["tipo"] == "captura":
                        if usa_marcas:
                            self._esperar(espera)
                            self._capturar(numero)
                            numero += 1
                    else:
                        self.repro.ejecutar(ev)
                if usa_final:
                    self._esperar(espera)
                    self._capturar(numero)
                    numero += 1
                self._reps_completas = rep + 1
                self._guardar_progreso("en curso")
                if rep < cfg.repeticiones - 1:
                    self._esperar(cfg.pausa_entre_reps_ms / 1000)
            situacion, mensaje = "completado", "Terminado."
        except Detenido as e:
            mensaje = str(e)
        finally:
            self.repro.soltar_todo()
            self._guardar_progreso(situacion)
        self.notificar("fin", estado=situacion, mensaje=mensaje,
                       siguiente=self._siguiente, ultima=self._ultima)
        return situacion
