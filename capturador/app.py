"""Interfaz gráfica (tkinter) del Capturador."""
import json
import queue
import sys
import threading
import tkinter as tk
from dataclasses import asdict, fields
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import capturas, energia, estado, macro as macros, ocr, pdfs, teclas
from .motor import Config, Motor, capturas_por_repeticion

VERSION = "1.5.0"
ARCHIVO_CONFIG = Path.home() / "capturador_config.json"
CUENTA_ATRAS = 3

MODOS = [("Capturar y luego hacer las acciones (lo normal: captura la página y pasa a la siguiente)", "inicio"),
         ("Hacer las acciones y luego capturar", "final"),
         ("En las marcas (F8) que pusiste al grabar", "marcas"),
         ("Ambos: en las marcas y al final", "ambos")]
POLITICAS = [("Preguntarme qué hacer", "preguntar"),
             ("Guardarla igual y anotarlo en el registro", "guardar"),
             ("Detener (luego se reanuda en esa captura)", "detener")]


def pitido(frecuencia=1000, ms=120):
    if sys.platform == "win32":
        try:
            import winsound
            winsound.Beep(frecuencia, ms)
        except Exception:
            pass


class App:
    def __init__(self, raiz):
        self.raiz = raiz
        raiz.title(f"Capturador {VERSION}")
        raiz.minsize(640, 600)
        self.cola = queue.Queue()
        self.macro = macros.nueva_macro()
        self.ruta_macro = None
        self.motor = None
        self.grabador = None
        self.oyente_atajos = None
        self.ultimo_progreso = 0

        self._variables()
        self._construir()
        self._cargar_config()
        self._actualizar_resumen()
        raiz.protocol("WM_DELETE_WINDOW", self._cerrar)
        raiz.after(100, self._atender_cola)

    # ------------------------------------------------------------------
    # Variables y persistencia
    # ------------------------------------------------------------------
    def _variables(self):
        S, B = tk.StringVar, tk.BooleanVar
        self.v = {
            "carpeta": S(value=str(Path.home() / "Capturas")),
            "repeticiones": S(value="10"),
            "modo": S(value="inicio"),
            "espera_captura_ms": S(value="800"),
            "velocidad": S(value="1.0"),
            "pausa_entre_reps_ms": S(value="0"),
            "inicio": S(value="1"),
            "prefijo": S(value="captura"),
            "formato": S(value="png"),
            "reintentos": S(value="3"),
            "espera_reintento_ms": S(value="1500"),
            "rechazar_vacia": B(value=True),
            "rechazar_igual": B(value=True),
            "permitir_blancas": B(value=True),
            "umbral_cambio": S(value="0.5"),
            "politica": S(value="preguntar"),
            "espera_reanudar_ms": S(value="1500"),
        }
        self.v_monitor = S(value="1")
        self.areas = []  # [[x, y, ancho, alto], ...]; vacía = pantalla completa
        self.v_por_pdf = S(value="30")
        self.v_pdf_al_final = B(value=True)
        self.v_ocr = B(value=False)
        self.v_recapturar = S(value="")

    def _cargar_config(self):
        try:
            datos = json.loads(ARCHIVO_CONFIG.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for clave, var in self.v.items():
            if clave in datos:
                var.set(datos[clave])
        for clave, var in (("monitor", self.v_monitor),
                           ("por_pdf", self.v_por_pdf), ("pdf_al_final", self.v_pdf_al_final),
                           ("ocr", self.v_ocr)):
            if clave in datos:
                var.set(datos[clave])
        areas = datos.get("areas")
        if areas is None and datos.get("region"):  # configuración de la versión 1.0
            try:
                areas = [[int(v) for v in str(datos["region"]).split(",")]]
            except ValueError:
                areas = []
        self.areas = [list(a) for a in (areas or []) if len(a) == 4]
        self._refrescar_areas()
        ruta = datos.get("ruta_macro")
        if ruta and Path(ruta).exists():
            try:
                self.macro = macros.cargar(ruta)
                self.ruta_macro = ruta
            except Exception:
                pass

    def _guardar_config(self):
        datos = {k: v.get() for k, v in self.v.items()}
        datos.update(monitor=self.v_monitor.get(), areas=self.areas,
                     por_pdf=self.v_por_pdf.get(), pdf_al_final=self.v_pdf_al_final.get(),
                     ocr=self.v_ocr.get(),
                     ruta_macro=self.ruta_macro)
        try:
            ARCHIVO_CONFIG.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
        except OSError:
            pass

    def _leer_config(self):
        """Convierte los campos en un Config; lanza ValueError con un mensaje claro."""
        tipos = {f.name: f.type for f in fields(Config)}
        valores = {}
        for clave, var in self.v.items():
            bruto = var.get()
            tipo = tipos[clave]
            try:
                if tipo in (int, "int"):
                    valores[clave] = int(str(bruto).strip())
                elif tipo in (float, "float"):
                    valores[clave] = float(str(bruto).strip().replace(",", "."))
                elif tipo in (bool, "bool"):
                    valores[clave] = bool(bruto)
                else:
                    valores[clave] = str(bruto).strip()
            except ValueError:
                raise ValueError(f"El campo «{clave}» tiene un valor no válido: {bruto!r}")
        if not valores["carpeta"]:
            raise ValueError("Elige la carpeta donde se guardarán las imágenes.")
        if valores["reintentos"] < 0:
            raise ValueError("Los reintentos no pueden ser negativos.")
        return Config(**valores)

    def _refrescar_areas(self):
        if not hasattr(self, "lista_areas"):
            return
        self.lista_areas.delete(0, "end")
        for i, (x, y, w, h) in enumerate(self.areas, start=1):
            self.lista_areas.insert("end", f"Área {i}:  x={x}  y={y}  ancho={w}  alto={h}")
        if not self.areas:
            self.lista_areas.insert("end", "(sin áreas: se captura el monitor completo)")
        self._actualizar_resumen()

    def quitar_area(self):
        sel = self.lista_areas.curselection()
        if sel and sel[0] < len(self.areas):
            del self.areas[sel[0]]
            self._refrescar_areas()

    def borrar_areas(self):
        self.areas = []
        self._refrescar_areas()

    # ------------------------------------------------------------------
    # Construcción de la ventana
    # ------------------------------------------------------------------
    def _construir(self):
        marco = ttk.Frame(self.raiz, padding=10)
        marco.pack(fill="both", expand=True)
        cuaderno = ttk.Notebook(marco)
        cuaderno.pack(fill="x")

        # 1. Grabar
        p = ttk.Frame(cuaderno, padding=10)
        cuaderno.add(p, text="1. Grabar")
        ttk.Label(p, wraplength=560, justify="left", text=(
            "Pulsa «Grabar». La ventana se minimiza, aparece arriba a la derecha un "
            "recuadro rojo «GRABANDO» y se graban tu ratón y tu teclado.\n"
            "  • Haz UNA sola vuelta: por ejemplo, el clic en «página siguiente».\n"
            "  • Para terminar: botón «Terminar» del recuadro, o F9 (en laptops, quizá Fn+F9).\n"
            "  • Marcar una captura en ese momento (solo para el modo «en las marcas»): "
            "botón «Marcar captura» o F8.\n"
            "No hace falta grabar la captura: la toma el programa.")
        ).pack(anchor="w")
        fila = ttk.Frame(p)
        fila.pack(anchor="w", pady=8)
        self.btn_grabar = ttk.Button(fila, text="● Grabar", command=self.grabar)
        self.btn_grabar.pack(side="left")
        ttk.Button(fila, text="Abrir macro…", command=self.abrir_macro).pack(side="left", padx=6)
        ttk.Button(fila, text="Guardar macro…", command=self.guardar_macro).pack(side="left")
        self.lbl_macro = ttk.Label(p, text="", foreground="#1a5")
        self.lbl_macro.pack(anchor="w")

        # 2. Repetir
        p = ttk.Frame(cuaderno, padding=10)
        cuaderno.add(p, text="2. Repetir y capturar")
        self._campo(p, 0, "Repeticiones:", self.v["repeticiones"])
        ttk.Label(p, text="¿Cuándo capturar?").grid(row=1, column=0, sticky="nw", pady=(6, 0))
        caja = ttk.Frame(p)
        caja.grid(row=1, column=1, columnspan=3, sticky="w", pady=(6, 0))
        for texto, valor in MODOS:
            ttk.Radiobutton(caja, text=texto, value=valor, variable=self.v["modo"],
                            command=self._actualizar_resumen).pack(anchor="w")
        self._campo(p, 2, "Espera antes de capturar (ms):", self.v["espera_captura_ms"])
        self._campo(p, 3, "Velocidad (1 = igual que lo grabado):", self.v["velocidad"])
        self._campo(p, 4, "Pausa entre repeticiones (ms):", self.v["pausa_entre_reps_ms"])
        self._campo(p, 5, "Empezar en la captura nº:", self.v["inicio"])
        ttk.Button(p, text="Continuar donde se quedó", command=self.continuar_donde_quedo
                   ).grid(row=5, column=2, sticky="w", padx=6)
        self.lbl_total = ttk.Label(p, text="", foreground="#1a5")
        self.lbl_total.grid(row=6, column=0, columnspan=4, sticky="w", pady=(8, 0))
        for var in (self.v["repeticiones"], self.v["inicio"]):
            var.trace_add("write", lambda *a: self._actualizar_resumen())

        # 3. Imágenes
        p = ttk.Frame(cuaderno, padding=10)
        cuaderno.add(p, text="3. Imágenes")
        ttk.Label(p, text="Carpeta:").grid(row=0, column=0, sticky="w")
        fila_carpeta = ttk.Frame(p)
        fila_carpeta.grid(row=0, column=1, columnspan=3, sticky="we")
        ttk.Button(fila_carpeta, text="Elegir…", command=self.elegir_carpeta).pack(side="right", padx=(4, 0))
        ttk.Entry(fila_carpeta, textvariable=self.v["carpeta"], width=20).pack(side="left", fill="x", expand=True)
        self._campo(p, 1, "Nombre de archivo:", self.v["prefijo"])
        ttk.Label(p, text="(captura_00001.png, captura_00002.png…)").grid(row=1, column=2, sticky="w")
        ttk.Label(p, text="Formato:").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Combobox(p, textvariable=self.v["formato"], values=["png", "jpg"], width=8,
                     state="readonly").grid(row=2, column=1, sticky="w")
        self._campo(p, 3, "Monitor (1 = principal, 0 = todos):", self.v_monitor)
        ttk.Label(p, text="Áreas a capturar:").grid(row=4, column=0, sticky="nw", pady=3)
        self.lista_areas = tk.Listbox(p, height=4, width=46, activestyle="none")
        self.lista_areas.grid(row=4, column=1, columnspan=2, sticky="we", pady=3)
        fila = ttk.Frame(p)
        fila.grid(row=5, column=1, columnspan=3, sticky="w")
        ttk.Button(fila, text="➕ Añadir área…", command=self.seleccionar_region).pack(side="left")
        ttk.Button(fila, text="Quitar la seleccionada", command=self.quitar_area).pack(side="left", padx=4)
        ttk.Button(fila, text="Borrar todas", command=self.borrar_areas).pack(side="left")
        ttk.Label(p, foreground="#555", wraplength=560, justify="left", text=(
            "Cada área se guarda como imagen separada y en orden: área 1, área 2, área 1, "
            "área 2… Las áreas pueden estar en cualquiera de los monitores. Sin áreas, se "
            "captura el monitor indicado arriba.")).grid(row=6, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Button(p, text="Probar una captura", command=self.probar_captura).grid(row=7, column=0, sticky="w", pady=8)

        # 4. Errores
        p = ttk.Frame(cuaderno, padding=10)
        cuaderno.add(p, text="4. Si algo falla")
        ttk.Checkbutton(p, text="Puede haber páginas en blanco (aceptarlas sin detenerse)",
                        variable=self.v["permitir_blancas"]).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(p, foreground="#555", text=(
            "     Antes de aceptarla espera los reintentos, por si la página aún está cargando."
        )).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(p, text="Rechazar imágenes vacías (todo negro, todo de un color…)",
                        variable=self.v["rechazar_vacia"]).grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(p, text="Rechazar si es igual a la anterior (la página no cambió)",
                        variable=self.v["rechazar_igual"]).grid(row=3, column=0, columnspan=3, sticky="w")
        self._campo(p, 4, "Mínimo que debe cambiar (% de píxeles):", self.v["umbral_cambio"])
        self._campo(p, 5, "Reintentos de cada captura:", self.v["reintentos"])
        self._campo(p, 6, "Espera entre reintentos (ms):", self.v["espera_reintento_ms"])
        self._campo(p, 7, "Margen al reanudar (ms):", self.v["espera_reanudar_ms"])
        ttk.Label(p, text="Si después de reintentar sigue fallando:").grid(row=8, column=0, sticky="nw", pady=(6, 0))
        caja = ttk.Frame(p)
        caja.grid(row=8, column=1, columnspan=2, sticky="w", pady=(6, 0))
        for texto, valor in POLITICAS:
            ttk.Radiobutton(caja, text=texto, value=valor, variable=self.v["politica"]).pack(anchor="w")
        ttk.Label(p, foreground="#555", wraplength=560, justify="left", text=(
            "Todo fallo queda en registro.csv y el avance en progreso.json, dentro de la carpeta. "
            "Si se detiene en la captura 154, «Continuar donde se quedó» empieza en la 154 sin "
            "tocar las anteriores.")).grid(row=9, column=0, columnspan=3, sticky="w", pady=(8, 0))

        # 5. PDF
        p = ttk.Frame(cuaderno, padding=10)
        cuaderno.add(p, text="5. PDF")
        self._campo(p, 0, "Imágenes por PDF:", self.v_por_pdf)
        ttk.Checkbutton(p, text="Crear los PDF automáticamente al terminar",
                        variable=self.v_pdf_al_final).grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(p, text="Añadir OCR: texto buscable y copiable (OCR de Windows)",
                        variable=self.v_ocr).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Button(p, text="Comprobar OCR", command=self.comprobar_ocr).grid(row=2, column=2, sticky="w", padx=6)
        ttk.Label(p, foreground="#555", wraplength=560, justify="left", text=(
            "Con OCR, el PDF se ve igual pero lleva el texto debajo: puedes buscar con Ctrl+F y "
            "copiar. Tarda un par de segundos más por página. «Comprobar OCR» reconoce la "
            "última captura y te muestra el texto en el registro.")).grid(row=3, column=0, columnspan=3, sticky="w")
        ttk.Button(p, text="Crear PDF ahora con la carpeta…", command=self.crear_pdfs_ahora
                   ).grid(row=4, column=0, sticky="w", pady=8)
        ttk.Label(p, foreground="#555", text="Se guardan en la subcarpeta PDF; el último lleva las que sobren."
                  ).grid(row=5, column=0, columnspan=3, sticky="w")

        # Controles de ejecución
        ctl = ttk.LabelFrame(marco, text="Ejecución", padding=8)
        ctl.pack(fill="x", pady=(10, 0))
        fila = ttk.Frame(ctl)
        fila.pack(fill="x")
        self.btn_iniciar = ttk.Button(fila, text="▶ Iniciar", command=self.iniciar)
        self.btn_iniciar.pack(side="left")
        self.btn_pausa = ttk.Button(fila, text="⏸ Pausar (F9)", command=self.alternar_pausa, state="disabled")
        self.btn_pausa.pack(side="left", padx=6)
        self.btn_detener = ttk.Button(fila, text="■ Detener (F10)", command=self.detener, state="disabled")
        self.btn_detener.pack(side="left")
        self.marco_pausa = ttk.Frame(ctl)
        ttk.Label(self.marco_pausa, text="En pausa. Rehacer la captura nº").pack(side="left")
        ttk.Entry(self.marco_pausa, textvariable=self.v_recapturar, width=7).pack(side="left", padx=4)
        ttk.Button(self.marco_pausa, text="Recapturar ahora", command=self.recapturar).pack(side="left")
        ttk.Label(self.marco_pausa, foreground="#555",
                  text="  (pon antes en pantalla lo que corresponde)").pack(side="left")
        self.barra = ttk.Progressbar(ctl, mode="determinate")
        self.barra.pack(fill="x", pady=6)
        self.lbl_estado = ttk.Label(ctl, text="Listo.")
        self.lbl_estado.pack(anchor="w")

        reg = ttk.LabelFrame(marco, text="Registro", padding=4)
        reg.pack(fill="both", expand=True, pady=(8, 0))
        self.txt = tk.Text(reg, height=9, wrap="word", state="disabled")
        barra = ttk.Scrollbar(reg, command=self.txt.yview)
        self.txt.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y")
        self.txt.pack(fill="both", expand=True)

    def _campo(self, padre, fila, etiqueta, var, ancho=10):
        ttk.Label(padre, text=etiqueta).grid(row=fila, column=0, sticky="w", pady=3)
        ttk.Entry(padre, textvariable=var, width=ancho).grid(row=fila, column=1, sticky="w", pady=3)

    # ------------------------------------------------------------------
    # Utilidades de interfaz
    # ------------------------------------------------------------------
    def log(self, texto):
        self.txt.configure(state="normal")
        self.txt.insert("end", texto + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _actualizar_resumen(self):
        hay = bool(self.macro["eventos"])
        nombre = f" — {Path(self.ruta_macro).name}" if self.ruta_macro else ""
        self.lbl_macro.configure(text=("Macro: " + macros.texto_resumen(self.macro) + nombre)
                                 if hay else "Todavía no hay macro grabada.")
        try:
            puntos = capturas_por_repeticion(self.macro, self.v["modo"].get())
            reps = int(self.v["repeticiones"].get())
            n_areas = max(1, len(self.areas))
            cpr = puntos * n_areas
            detalle = (f"{puntos} momento(s) de captura × {n_areas} áreas = {cpr} imágenes por repetición"
                       if n_areas > 1 else f"{cpr} captura(s) por repetición")
            self.lbl_total.configure(
                text=f"{detalle} × {reps} = {cpr * reps} imágenes", foreground="#1a5")
        except ValueError as e:
            self.lbl_total.configure(text=str(e), foreground="#b30")

    def _modo_ejecucion(self, activo):
        self.btn_iniciar.configure(state="disabled" if activo else "normal")
        self.btn_grabar.configure(state="disabled" if activo else "normal")
        self.btn_pausa.configure(state="normal" if activo else "disabled", text="⏸ Pausar (F9)")
        self.btn_detener.configure(state="normal" if activo else "disabled")
        if not activo:
            self.marco_pausa.pack_forget()

    def _mostrar(self):
        self.raiz.deiconify()
        self.raiz.lift()
        self.raiz.attributes("-topmost", True)
        self.raiz.after(300, lambda: self.raiz.attributes("-topmost", False))
        self.raiz.focus_force()

    def _cuenta_atras(self, segundos, accion, texto):
        if segundos <= 0:
            self.raiz.iconify()
            self.raiz.after(700, accion)
            return
        self.lbl_estado.configure(text=f"{texto} en {segundos}…")
        self.raiz.after(1000, lambda: self._cuenta_atras(segundos - 1, accion, texto))

    # ------------------------------------------------------------------
    # Grabación
    # ------------------------------------------------------------------
    def grabar(self):
        if self.macro["eventos"] and not messagebox.askyesno(
                "Grabar", "Ya hay una macro. ¿Reemplazarla por una nueva grabación?"):
            return
        self.log("Grabación: prepara la pantalla. Arriba a la derecha aparecerá el recuadro "
                 "GRABANDO con el botón Terminar (o F9).")
        self._cuenta_atras(CUENTA_ATRAS, self._empezar_grabacion, "Grabando")

    def _empezar_grabacion(self):
        from .grabador import Grabador
        self.grabador = Grabador(
            al_terminar=lambda m: self.cola.put(("grabacion_fin", m)),
            al_marcar=lambda: (pitido(1500, 80), self.cola.put(("marca", None))))
        self._crear_indicador()
        try:
            self.grabador.iniciar()
        except Exception as e:
            self._cerrar_indicador()
            self._mostrar()
            messagebox.showerror("Grabar", f"No se pudo iniciar la grabación:\n{e}")
            return
        pitido(800, 150)
        self._t_grabacion = 0
        self.raiz.after(250, self._vigilar_grabacion)

    def _crear_indicador(self):
        """Recuadro siempre visible mientras se graba: contador y botones.
        Lo que se haga dentro de él no se graba."""
        ind = tk.Toplevel(self.raiz)
        ind.overrideredirect(True)
        ind.attributes("-topmost", True)
        ind.configure(bg="#b00020")
        cuerpo = tk.Frame(ind, bg="#b00020", padx=10, pady=6)
        cuerpo.pack()
        tk.Label(cuerpo, text="● GRABANDO", fg="white", bg="#b00020",
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.lbl_conteo = tk.Label(cuerpo, text="Acciones: 0", fg="white", bg="#b00020",
                                   font=("Segoe UI", 10))
        self.lbl_conteo.pack(anchor="w")
        self.lbl_aviso_grab = tk.Label(cuerpo, text="", fg="#ffe08a", bg="#b00020",
                                       font=("Segoe UI", 9), wraplength=260, justify="left")
        self.lbl_aviso_grab.pack(anchor="w")
        botones = tk.Frame(cuerpo, bg="#b00020")
        botones.pack(anchor="w", pady=(4, 0))
        tk.Button(botones, text="Marcar captura (F8)",
                  command=lambda: self.grabador and self.grabador.marcar()).pack(side="left")
        tk.Button(botones, text="■ Terminar (F9)",
                  command=lambda: self.grabador and self.grabador.detener()).pack(side="left", padx=(6, 0))
        ind.update_idletasks()
        ancho, alto = ind.winfo_reqwidth(), ind.winfo_reqheight()
        x = self.raiz.winfo_screenwidth() - ancho - 20
        ind.geometry(f"+{x}+20")
        ind.update_idletasks()
        margen = 8  # el borde también queda fuera de la grabación
        self.grabador.zonas_excluidas = [(x - margen, 20 - margen, ancho + 2 * margen, alto + 2 * margen)]
        self.indicador = ind

    def _cerrar_indicador(self):
        ind = getattr(self, "indicador", None)
        if ind is not None:
            try:
                ind.destroy()
            except tk.TclError:
                pass
        self.indicador = None

    def _vigilar_grabacion(self):
        if not (self.grabador and getattr(self, "indicador", None)):
            return
        acciones, marcas = self.grabador.conteo()
        self.lbl_conteo.configure(text=f"Acciones: {acciones}   Marcas: {marcas}")
        self._t_grabacion += 1
        if not self.grabador.activo():
            self.lbl_aviso_grab.configure(text=(
                "Windows dejó de entregar el ratón o el teclado. Pulsa Terminar y "
                "revisa el registro."))
        elif acciones == 0 and self._t_grabacion > 16:
            self.lbl_aviso_grab.configure(text=(
                "Mueve el ratón: el número debe subir. Si se queda en 0, el equipo "
                "no deja grabar (seguridad o permisos)."))
        else:
            self.lbl_aviso_grab.configure(text="")
        self.raiz.after(250, self._vigilar_grabacion)

    # ------------------------------------------------------------------
    # Archivos de macro
    # ------------------------------------------------------------------
    def abrir_macro(self):
        ruta = filedialog.askopenfilename(filetypes=[("Macro", "*.json"), ("Todos", "*.*")])
        if not ruta:
            return
        try:
            self.macro = macros.cargar(ruta)
            self.ruta_macro = ruta
        except Exception as e:
            messagebox.showerror("Abrir macro", str(e))
            return
        self._actualizar_resumen()
        self.log(f"Macro abierta: {ruta}")

    def guardar_macro(self):
        if not self.macro["eventos"]:
            messagebox.showinfo("Guardar macro", "No hay nada grabado todavía.")
            return
        ruta = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("Macro", "*.json")])
        if not ruta:
            return
        macros.guardar(self.macro, ruta)
        self.ruta_macro = ruta
        self._actualizar_resumen()
        self.log(f"Macro guardada: {ruta}")

    # ------------------------------------------------------------------
    # Imágenes
    # ------------------------------------------------------------------
    def elegir_carpeta(self):
        ruta = filedialog.askdirectory(initialdir=self.v["carpeta"].get() or str(Path.home()))
        if ruta:
            self.v["carpeta"].set(ruta)

    def _funciones_captura(self):
        """Una función de captura por área (o una sola, del monitor completo)."""
        monitor = int(self.v_monitor.get())
        if not self.areas:
            return [lambda: capturas.tomar_captura(monitor, None)]
        return [lambda r=tuple(a): capturas.tomar_captura(monitor, r) for a in self.areas]

    def probar_captura(self):
        try:
            captura = self._funciones_captura()
            self.raiz.iconify()
            self.raiz.update()
            self.raiz.after(800, lambda: self._probar(captura))
        except Exception as e:
            messagebox.showerror("Probar captura", str(e))

    def _probar(self, funciones):
        try:
            # en una subcarpeta, para que la prueba no acabe dentro de los PDF
            carpeta = Path(self.v["carpeta"].get()) / "_prueba"
            carpeta.mkdir(parents=True, exist_ok=True)
            lineas = []
            for i, captura in enumerate(funciones, start=1):
                img = captura()
                nombre = "prueba.png" if len(funciones) == 1 else f"prueba_area{i}.png"
                ruta = carpeta / nombre
                capturas.guardar(img, ruta)
                motivo = capturas.motivo_rechazo(img)
                lineas.append(f"Prueba: {img.size[0]}×{img.size[1]} px → {ruta}"
                              + (f" (aviso: {motivo})" if motivo else ""))
            self._mostrar()
            for linea in lineas:
                self.log(linea)
        except Exception as e:
            self._mostrar()
            messagebox.showerror("Probar captura", str(e))

    def seleccionar_region(self):
        try:
            import mss
            with mss.mss() as sct:
                todo = sct.monitors[0]
        except Exception as e:
            messagebox.showerror("Región", str(e))
            return
        self.raiz.iconify()
        capa = tk.Toplevel(self.raiz)
        capa.overrideredirect(True)
        capa.geometry(f"{todo['width']}x{todo['height']}+{todo['left']}+{todo['top']}")
        capa.attributes("-alpha", 0.3)
        capa.attributes("-topmost", True)
        lienzo = tk.Canvas(capa, cursor="cross", bg="gray20", highlightthickness=0)
        lienzo.pack(fill="both", expand=True)
        n = len(self.areas) + 1
        lienzo.create_text(todo["width"] // 2, 40, fill="white", font=("Segoe UI", 18),
                           text=f"Arrastra para marcar el ÁREA {n}. Esc para cancelar.")
        for i, (x, y, w, h) in enumerate(self.areas, start=1):
            cx, cy = x - todo["left"], y - todo["top"]
            lienzo.create_rectangle(cx, cy, cx + w, cy + h, outline="yellow", width=3)
            lienzo.create_text(cx + 10, cy + 10, anchor="nw", fill="yellow",
                               font=("Segoe UI", 16, "bold"), text=f"Área {i}")
        inicio = {}

        def pulsar(e):
            inicio.update(x=e.x_root, y=e.y_root, cx=e.x, cy=e.y)
            inicio["rect"] = lienzo.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=3)

        def arrastrar(e):
            if "rect" in inicio:
                lienzo.coords(inicio["rect"], inicio["cx"], inicio["cy"], e.x, e.y)

        def soltar(e):
            if "x" not in inicio:
                return
            x0, x1 = sorted((inicio["x"], e.x_root))
            y0, y1 = sorted((inicio["y"], e.y_root))
            capa.destroy()
            self._mostrar()
            if x1 - x0 > 5 and y1 - y0 > 5:
                self.areas.append([x0, y0, x1 - x0, y1 - y0])
                self._refrescar_areas()
                self.log(f"Área {len(self.areas)}: x={x0} y={y0} ancho={x1 - x0} alto={y1 - y0}")

        def cancelar(_e=None):
            capa.destroy()
            self._mostrar()

        lienzo.bind("<ButtonPress-1>", pulsar)
        lienzo.bind("<B1-Motion>", arrastrar)
        lienzo.bind("<ButtonRelease-1>", soltar)
        capa.bind("<Escape>", cancelar)
        capa.focus_force()

    # ------------------------------------------------------------------
    # Ejecución
    # ------------------------------------------------------------------
    def continuar_donde_quedo(self):
        prog = estado.cargar_progreso(self.v["carpeta"].get())
        if not prog or not prog.get("siguiente"):
            messagebox.showinfo("Continuar", "No hay progreso guardado en esa carpeta.")
            return
        cfg = prog.get("config", {})
        for clave in ("repeticiones", "modo", "prefijo", "formato"):
            if clave in cfg:
                self.v[clave].set(cfg[clave])
        self.v["inicio"].set(str(prog["siguiente"]))
        self.log(f"Progreso encontrado ({prog.get('estado')}, {prog.get('actualizado')}): "
                 f"última guardada {prog.get('ultima_guardada')}, se seguirá en la "
                 f"{prog['siguiente']} de {prog.get('total_capturas')}.")
        areas_antes = prog.get("areas", 1)
        if areas_antes != max(1, len(self.areas)):
            self.log(f"¡Atención! Esa carpeta se hizo con {areas_antes} área(s) y ahora hay "
                     f"{max(1, len(self.areas))}. Deja las mismas áreas o la numeración no cuadrará.")
        self.log("Antes de iniciar, deja en pantalla lo que corresponde a esa captura.")

    def iniciar(self):
        if not self.macro["eventos"]:
            messagebox.showwarning("Iniciar", "Primero graba (o abre) una macro.")
            return
        try:
            cfg = self._leer_config()
            captura = self._funciones_captura()
            int(self.v_por_pdf.get())
            from .reproductor import ReproductorPynput
            motor = Motor(self.macro, cfg, ReproductorPynput(), captura,
                          notificar=lambda t, d: self.cola.put(("motor", (t, d))),
                          preguntar=self._preguntar_desde_hilo)
        except Exception as e:
            messagebox.showerror("Iniciar", str(e))
            return
        primera = ((max(1, cfg.inicio) - 1) // motor.cpr) * motor.cpr + 1
        existentes = [n for n in range(primera, motor.total + 1) if motor.ruta(n).exists()]
        if existentes and not messagebox.askyesno(
                "Iniciar", f"Ya hay {len(existentes)} imagen(es) desde la nº {existentes[0]} "
                           "que se van a reemplazar. ¿Continuar?"):
            return
        self._guardar_config()
        self.motor = motor
        self.barra.configure(maximum=motor.total, value=primera - 1)
        self._modo_ejecucion(True)
        self.log(f"Inicio: {motor.total} capturas en total, empezando en la {primera}. "
                 "F9 = pausa, F10 = detener.")
        self._cuenta_atras(CUENTA_ATRAS, self._lanzar, "Empieza")

    def _lanzar(self):
        from pynput import keyboard

        def atajo(key):
            nombre = teclas.nombre_especial(key)
            if nombre == teclas.TECLA_PAUSA:
                self.cola.put(("atajo", "pausa"))
            elif nombre == teclas.TECLA_DETENER:
                self.cola.put(("atajo", "detener"))

        self.oyente_atajos = keyboard.Listener(on_press=atajo)
        self.oyente_atajos.start()
        threading.Thread(target=self._hilo_motor, daemon=True).start()

    def _hilo_motor(self):
        try:
            with energia.mantener_despierto() as activo:
                if activo:
                    self.cola.put(("log", "Mientras trabaja, el equipo no se suspenderá ni "
                                          "apagará la pantalla. Al terminar vuelve a lo normal."))
                self.motor.ejecutar()
        except Exception as e:  # error inesperado: se informa y se libera la interfaz
            self.cola.put(("motor", ("fin", {"estado": "error", "mensaje": str(e)})))

    def alternar_pausa(self):
        if self.motor:
            self.motor.alternar_pausa()
            if not self.motor.en_pausa():
                self.marco_pausa.pack_forget()
                self.raiz.iconify()
            else:
                self.lbl_estado.configure(text="Pausando en cuanto no haya teclas pulsadas…")

    def detener(self):
        if self.motor:
            self.motor.detener()
            self.lbl_estado.configure(text="Deteniendo…")

    def recapturar(self):
        if not (self.motor and self.motor.en_pausa()):
            return
        try:
            n = int(self.v_recapturar.get())
            if n < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Recapturar", "Escribe el número de la captura a rehacer.")
            return
        area = self.motor.area_de(n) + 1
        self.log(f"Recapturando la nº {n}" + (f" (área {area})…" if self.motor.areas > 1 else "…"))
        self.raiz.iconify()
        self.motor.recapturar(n)

    def _preguntar_desde_hilo(self, datos):
        """Lo llama el hilo del motor: muestra el aviso en la interfaz y espera."""
        respuesta = {"evento": threading.Event(), "valor": "detener"}
        self.cola.put(("preguntar", (datos, respuesta)))
        respuesta["evento"].wait()
        return respuesta["valor"]

    def _dialogo_error(self, datos, respuesta):
        self._mostrar()
        pitido(400, 300)
        dlg = tk.Toplevel(self.raiz)
        dlg.title(f"Problema en la captura {datos['numero']}")
        dlg.transient(self.raiz)
        dlg.attributes("-topmost", True)
        dlg.grab_set()
        ttk.Label(dlg, padding=12, wraplength=440, justify="left", text=(
            f"La captura nº {datos['numero']} falló después de los reintentos.\n\n"
            f"Motivo: {datos['motivo']}\n\n¿Qué hago?")).pack()
        botones = ttk.Frame(dlg, padding=(12, 0, 12, 12))
        botones.pack(fill="x")

        def elegir(valor):
            respuesta["valor"] = valor
            dlg.destroy()
            if valor in ("reintentar", "guardar") and not datos.get("manual"):
                self.raiz.iconify()
            respuesta["evento"].set()

        opciones = [("Reintentar", "reintentar")]
        if not datos.get("manual"):
            opciones.append(("Pausar para arreglarlo", "pausar"))
        if datos.get("hay_imagen"):
            opciones.append(("Guardarla así", "guardar"))
        opciones.append(("Cancelar" if datos.get("manual") else "Detener",
                         "pausar" if datos.get("manual") else "detener"))
        for texto, valor in opciones:
            ttk.Button(botones, text=texto, command=lambda v=valor: elegir(v)).pack(side="left", padx=3)
        dlg.protocol("WM_DELETE_WINDOW", lambda: elegir(opciones[-1][1]))

    def _evento_motor(self, tipo, d):
        if tipo == "captura":
            if d.get("manual"):
                self.log(f"Captura {d['numero']} rehecha.")
                return
            self.barra.configure(value=d["numero"])
            extra = f" (intento {d['intento']})" if d["intento"] not in (1, "aviso") else ""
            if d.get("blanca"):
                extra = " — página en blanco"
                self.log(f"Captura {d['numero']}: página en blanco, aceptada")
            if d["intento"] == "aviso":
                extra = f" — guardada con aviso: {d.get('aviso')}"
                self.log(f"Captura {d['numero']}{extra}")
            elif extra:
                self.log(f"Captura {d['numero']} correcta{extra}")
            self.lbl_estado.configure(text=f"Captura {d['numero']} de {d['total']}{extra}")
            self.v_recapturar.set(str(d["numero"]))
        elif tipo == "fallo":
            self.log(f"Captura {d['numero']}: intento {d['intento']}/{d['maximo']} falló — {d['motivo']}")
        elif tipo == "repeticion":
            self.raiz.title(f"Capturador — repetición {d['repeticion']}/{d['repeticiones']}")
        elif tipo == "aviso":
            self.log(d["mensaje"])
        elif tipo == "pausa":
            self._mostrar()
            self.btn_pausa.configure(text="▶ Continuar (F9)")
            self.marco_pausa.pack(fill="x", pady=(6, 0), before=self.barra)
            self.lbl_estado.configure(text=f"En pausa. Última guardada: {d.get('ultima')}. "
                                           f"Al continuar sigue con la {d.get('siguiente')}.")
            self.log("En pausa.")
        elif tipo == "reanudar":
            self.btn_pausa.configure(text="⏸ Pausar (F9)")
            self.marco_pausa.pack_forget()
            self.raiz.iconify()
            self.log("Continúa.")
        elif tipo == "recapturada":
            self._mostrar()
        elif tipo == "fin":
            self._terminar(d)

    def _terminar(self, d):
        if self.oyente_atajos:
            self.oyente_atajos.stop()
            self.oyente_atajos = None
        self.raiz.title(f"Capturador {VERSION}")
        self._modo_ejecucion(False)
        self._mostrar()
        situacion = d.get("estado")
        self.log(f"Fin: {situacion}. {d.get('mensaje', '')}")
        if d.get("siguiente"):
            self.v["inicio"].set(str(d["siguiente"]))
        if situacion == "completado":
            pitido(1200, 200)
            self.lbl_estado.configure(text="Terminado.")
            if self.v_pdf_al_final.get():
                self._crear_pdfs(self.v["carpeta"].get())
        else:
            pitido(400, 400)
            self.lbl_estado.configure(text=(
                f"Detenido. Para seguir: deja en pantalla la captura {d.get('siguiente')} "
                "y pulsa Iniciar (ya está puesta como «Empezar en»)."))
        self.motor = None

    # ------------------------------------------------------------------
    # PDF
    # ------------------------------------------------------------------
    def crear_pdfs_ahora(self):
        ruta = filedialog.askdirectory(title="Carpeta con las imágenes",
                                       initialdir=self.v["carpeta"].get() or str(Path.home()))
        if ruta:
            self._crear_pdfs(ruta)

    def _crear_pdfs(self, carpeta):
        try:
            por_pdf = int(self.v_por_pdf.get())
        except ValueError:
            messagebox.showerror("PDF", "«Imágenes por PDF» debe ser un número.")
            return
        con_ocr = self.v_ocr.get()
        self.log(f"Creando PDF de {por_pdf} imágenes con {carpeta}"
                 + (" y OCR (puede tardar)…" if con_ocr else "…"))

        def trabajo():
            reconocedor = None
            if con_ocr:
                try:
                    reconocedor = ocr.Reconocedor()
                    self.cola.put(("log", ocr.comprobar()))
                except Exception as e:
                    self.cola.put(("log", f"Sin OCR: {str(e).rstrip('.')}. Los PDF se crean solo con las imágenes."))
                    reconocedor = None
            fallos = []

            def reconocer_pagina(img):
                try:
                    return reconocedor(img)
                except Exception as e:  # una página mala no detiene los PDF
                    fallos.append(str(e))
                    return []

            contador = {"n": 0}

            def al_reconocer(ruta, palabras):
                contador["n"] += 1
                if contador["n"] % 10 == 0 or palabras == 0:
                    aviso = " (sin texto)" if palabras == 0 else ""
                    self.cola.put(("log", f"OCR: {contador['n']} páginas… {ruta.name}: "
                                          f"{palabras} palabras{aviso}"))

            try:
                with energia.mantener_despierto():
                    creados = pdfs.generar_pdfs(
                        carpeta, por_pdf,
                        progreso=lambda n, t, a: self.cola.put(("log", f"PDF {n}/{t}: {a.name}")),
                        ocr=reconocer_pagina if reconocedor else None,
                        al_reconocer=al_reconocer)
                self.cola.put(("log", f"Listo: {len(creados)} PDF en {Path(creados[0]).parent}"))
                if fallos:
                    self.cola.put(("log", f"El OCR falló en {len(fallos)} página(s); esas van "
                                          f"sin texto. Primer error: {fallos[0]}"))
            except Exception as e:
                self.cola.put(("log", f"Error al crear los PDF: {e}"))

        threading.Thread(target=trabajo, daemon=True).start()

    def comprobar_ocr(self):
        carpeta = Path(self.v["carpeta"].get())
        self.log("Comprobando el OCR de Windows…")

        def trabajo():
            try:
                self.cola.put(("log", ocr.comprobar()))
                candidatas = sorted((carpeta / "_prueba").glob("prueba*.png"),
                                    key=lambda p: p.stat().st_mtime) if (carpeta / "_prueba").exists() else []
                if not candidatas and carpeta.exists():
                    candidatas = pdfs.listar_imagenes(carpeta)[-1:]
                if not candidatas:
                    self.cola.put(("log", "Haz «Probar una captura» (pestaña 3) para ver qué texto reconoce."))
                    return
                from PIL import Image
                with Image.open(candidatas[-1]) as img:
                    lineas = ocr.reconocer(img.convert("RGB"))
                texto = "\n".join(" ".join(p[0] for p in l) for l in lineas)
                palabras = sum(len(l) for l in lineas)
                self.cola.put(("log", f"Texto reconocido en {candidatas[-1].name} ({palabras} palabras):"))
                self.cola.put(("log", texto[:1500] if texto else "(no se reconoció texto)"))
            except Exception as e:
                self.cola.put(("log", f"OCR no disponible: {e}"))

        threading.Thread(target=trabajo, daemon=True).start()

    # ------------------------------------------------------------------
    # Cola de mensajes entre hilos
    # ------------------------------------------------------------------
    def _atender_cola(self):
        try:
            while True:
                tipo, dato = self.cola.get_nowait()
                if tipo == "motor":
                    self._evento_motor(*dato)
                elif tipo == "preguntar":
                    self._dialogo_error(*dato)
                elif tipo == "atajo":
                    if dato == "pausa":
                        self.alternar_pausa()
                    else:
                        self.detener()
                elif tipo == "marca":
                    self.log("  marca de captura")
                elif tipo == "grabacion_fin":
                    self._cerrar_indicador()
                    self.grabador = None
                    self._mostrar()
                    if not dato["eventos"]:
                        self.log("La grabación terminó vacía: no se registró ninguna acción. "
                                 "Si moviste el ratón y el contador se quedó en 0, tu equipo "
                                 "no permite leer el ratón y el teclado.")
                        messagebox.showwarning("Grabar", "No se grabó ninguna acción.")
                        self.lbl_estado.configure(text="Listo.")
                        continue
                    self.macro = dato
                    self.ruta_macro = None
                    self._actualizar_resumen()
                    self.log("Grabación terminada: " + macros.texto_resumen(dato)
                             + ". Guárdala con «Guardar macro…» si la quieres reutilizar.")
                    self.lbl_estado.configure(text="Listo.")
                elif tipo == "log":
                    self.log(dato)
        except queue.Empty:
            pass
        self.raiz.after(100, self._atender_cola)

    def _cerrar(self):
        if self.motor and not messagebox.askyesno("Salir", "Hay una ejecución en marcha. ¿Detenerla y salir?"):
            return
        if self.motor:
            self.motor.detener()
        if self.grabador:
            self.grabador.detener()
        self._guardar_config()
        self.raiz.destroy()


def main():
    if sys.platform == "win32":
        import ctypes
        try:  # coordenadas en píxeles reales aunque Windows tenga escala 125 %, 150 %…
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    raiz = tk.Tk()
    try:
        ttk.Style().theme_use("vista" if sys.platform == "win32" else "clam")
    except tk.TclError:
        pass
    App(raiz)
    raiz.mainloop()
