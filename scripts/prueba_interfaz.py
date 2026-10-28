#!/usr/bin/env python3
"""Prueba de la interfaz de materias contra el servidor local (CDP + Chromium).

Cubre: carga del catalogo, arrastrar y soltar (eventos drag con DataTransfer),
el clic que rota las fichas, el filtro de busqueda, la persistencia en
localStorage y el veredicto de POST /revisar. El cliente NO juzga
prerrequisitos: las fichas no deben traer marca local y lo que dice el
prolog lo pinta solo el boton revisar.

Uso:
    PORT=8091 go run . &          # el servidor con la interfaz embebida
    python3 scripts/prueba_interfaz.py

Variables:
    CHROME   ruta al chromium/headless-shell (por default busca el de playwright)
    BASE     url del servidor (por default http://localhost:8091)
"""
import asyncio
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

import websockets

CHROME = os.environ.get("CHROME") or os.path.expanduser(
    "~/.cache/ms-playwright/chromium_headless_shell-1243/"
    "chrome-headless-shell-linux64/chrome-headless-shell"
)
BASE = os.environ.get("BASE", "http://localhost:8091")
PUERTO = 9223

# JS helpers que se inyectan en la pagina ---------------------------------

LEE_ESTADO = """
(() => ({
  catalogo: document.querySelectorAll('#lista-catalogo .materia').length,
  cursadas: [...document.querySelectorAll('#lista-cursadas .materia')].map(f => f.dataset.clave),
  deseadas: [...document.querySelectorAll('#lista-deseadas .materia')].map(f => f.dataset.clave),
  contCatalogo: document.getElementById('cont-catalogo').textContent,
  contCursadas: document.getElementById('cont-cursadas').textContent,
  contDeseadas: document.getElementById('cont-deseadas').textContent,
  // el cliente no juzga prerrequisitos: ninguna ficha puede traer clases
  // de aviso ni pie de faltante pintado a mano
  marcadas: [...document.querySelectorAll('#lista-deseadas .materia')]
    .filter(f => f.classList.length > 1 || f.querySelector('.pie-falta'))
    .map(f => f.dataset.clave),
  veredicto: document.getElementById('veredicto').hidden
    ? null : document.getElementById('veredicto').textContent,
  botonRevisar: !document.getElementById('revisar').disabled,
  botonGenerar: !document.getElementById('generar').disabled,
  semanaVisible: !document.getElementById('semana').hidden,
  navegador: document.getElementById('navegador').hidden
    ? null : document.getElementById('opcion-indice').textContent,
  flechaPrev: document.getElementById('opcion-anterior').disabled,
  flechaNext: document.getElementById('opcion-siguiente').disabled,
  gruposSemana: [...document.querySelectorAll('#semana .bloque')]
    .map(b => b.title),
  botonLimpiar: !document.getElementById('limpiar').hidden,
  guardado: localStorage.getItem('materias:seleccion-v1'),
}))()
"""

# simula el arrastre completo de una ficha hacia una caja
ARRASTRA = """
((clave, destino) => {
  const origen = document.querySelector(`.materia[data-clave="${clave}"]`);
  if (!origen) return 'no-encontrada';
  const dt = new DataTransfer();
  origen.dispatchEvent(new DragEvent('dragstart', {dataTransfer: dt, bubbles: true}));
  const caja = document.querySelector(`.caja[data-caja="${destino}"]`);
  caja.dispatchEvent(new DragEvent('dragover', {dataTransfer: dt, bubbles: true, cancelable: true}));
  const claseSobre = caja.classList.contains('sobre');
  caja.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true}));
  origen.dispatchEvent(new DragEvent('dragend', {dataTransfer: dt, bubbles: true}));
  return claseSobre ? 'ok' : 'sin-resaltar';
})($0, $1)
"""


class Cliente:
    def __init__(self, ws):
        self.ws = ws
        self.id = 0

    async def llama(self, metodo, params=None):
        self.id += 1
        await self.ws.send(json.dumps(
            {"id": self.id, "method": metodo, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == self.id:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error']}")
                return msg.get("result", {})

    async def evalua(self, expresion):
        res = await self.llama("Runtime.evaluate", {
            "expression": expresion,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if res.get("exceptionDetails"):
            raise RuntimeError(f"excepcion: {res['exceptionDetails']}")
        return res["result"].get("value")

    async def espera(self, expresion, intentos=40):
        for _ in range(intentos):
            if await self.evalua(expresion):
                return True
            await asyncio.sleep(0.25)
        return False


CHEQUEOS = []


def chequea(nombre, condicion, detalle=""):
    CHEQUEOS.append((nombre, bool(condicion), detalle))
    marca = "ok " if condicion else "FALLO"
    print(f"[{marca}] {nombre}" + (f" — {detalle}" if detalle and not condicion else ""))


async def prueba():
    import tempfile
    t0 = time.monotonic()
    perfil = tempfile.mkdtemp(prefix="perf-prueba-materias-")
    proc = subprocess.Popen(
        [CHROME, f"--remote-debugging-port={PUERTO}", "--headless",
         "--no-sandbox", "--disable-gpu", "--window-size=1400,950",
         "--hide-scrollbars", f"--user-data-dir={perfil}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        # espera a que el navegador responda
        for _ in range(60):
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{PUERTO}/json/version", timeout=1) as r:
                    r.read()
                break
            except Exception:
                await asyncio.sleep(0.25)

        req = urllib.request.Request(
            f"http://127.0.0.1:{PUERTO}/json/new?{BASE}/", method="PUT")
        with urllib.request.urlopen(req, timeout=5) as r:
            pestana = json.load(r)

        async with websockets.connect(pestana["webSocketDebuggerUrl"],
                                      max_size=20 * 1024 * 1024) as ws:
            c = Cliente(ws)
            await c.llama("Page.enable")
            await c.llama("Runtime.enable")
            # arranca sin seleccion previa, aunque el perfil traiga basura:
            # espero a que la pagina termine de cargar (si no, localStorage
            # esta denegado en about:blank), limpio y recargo
            await c.espera("document.readyState === 'complete' && "
                           "location.pathname === '/'")
            await c.evalua("localStorage.clear()")
            await c.llama("Page.reload", {"ignoreCache": True})

            # --- 1. el catalogo carga con las 74 materias ---
            cargado = await c.espera(
                "document.querySelectorAll('#lista-catalogo .materia').length === 74")
            est = await c.evalua(LEE_ESTADO)
            chequea("catalogo con 74 materias", cargado,
                    f"hay {est['catalogo']}")
            chequea("contador del catalogo", est["contCatalogo"] == "74 materias",
                    est["contCatalogo"])

            # --- 2. arrastrar Calculo a "quieres cursar" ---
            res = await c.evalua(ARRASTRA.replace("$0", "'calculo'")
                                 .replace("$1", "'deseadas'"))
            chequea("dragstart→drop resalta la caja", res == "ok", res)
            est = await c.evalua(LEE_ESTADO)
            chequea("calculo queda en deseadas", est["deseadas"] == ["calculo"],
                    str(est["deseadas"]))
            chequea("calculo sale del catalogo",
                    est["catalogo"] == 73, str(est["catalogo"]))
            chequea("la ficha no trae marca local del cliente",
                    est["marcadas"] == [], str(est["marcadas"]))
            chequea("el veredicto esta apagado hasta que hable el prolog",
                    est["veredicto"] is None, str(est["veredicto"])[:80])

            # --- 3. falta prerrequisito: lo avisa el prolog, no el cliente ---
            await c.evalua(ARRASTRA.replace("$0", "'bases_de_datos'")
                           .replace("$1", "'deseadas'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("bases_de_datos sin faltante pintado en el navegador",
                    est["marcadas"] == [], str(est["marcadas"]))
            await c.evalua("document.getElementById('revisar').click()")
            await c.espera("!document.getElementById('veredicto').hidden",
                           intentos=40)
            est = await c.evalua(LEE_ESTADO)
            chequea("el prolog es el que dice que falta prerrequisito",
                    est["veredicto"] is not None
                    and "Matematicas Discretas" in est["veredicto"],
                    str(est["veredicto"])[:160])

            # --- 4. al cursar lo que faltaba, manda el prolog otra vez ---
            await c.evalua(ARRASTRA.replace("$0", "'matematicas_discretas'")
                           .replace("$1", "'cursadas'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("matematicas_discretas en cursadas",
                    est["cursadas"] == ["matematicas_discretas"],
                    str(est["cursadas"]))
            chequea("mover materias apaga el veredicto viejo",
                    est["veredicto"] is None, str(est["veredicto"])[:80])
            await c.evalua("document.getElementById('revisar').click()")
            await c.espera(
                "document.getElementById('veredicto').textContent"
                ".startsWith('✓')", intentos=40)
            est = await c.evalua(LEE_ESTADO)
            chequea("recursado lo que faltaba, el prolog da el visto bueno",
                    est["veredicto"] is not None
                    and est["veredicto"].startswith('✓'),
                    str(est["veredicto"])[:160])
            chequea("el cliente sigue sin marcar nada por su cuenta",
                    est["marcadas"] == [], str(est["marcadas"]))
            chequea("contador de cursadas",
                    est["contCursadas"].startswith("1 materia"),
                    est["contCursadas"])
            chequea("contador de deseadas",
                    est["contDeseadas"].startswith("2 materias"),
                    est["contDeseadas"])

            # --- 5. clic rota la ficha: deseadas -> cursadas -> catalogo ---
            await c.evalua("""
              document.querySelector('#lista-deseadas .materia[data-clave="calculo"]')
                .click()""")
            est = await c.evalua(LEE_ESTADO)
            chequea("clic mueve calculo a cursadas",
                    "calculo" in est["cursadas"] and "calculo" not in est["deseadas"],
                    f"cursadas={est['cursadas']} deseadas={est['deseadas']}")
            await c.evalua("""
              document.querySelector('#lista-cursadas .materia[data-clave="calculo"]')
                .click()""")
            est = await c.evalua(LEE_ESTADO)
            chequea("segundo clic regresa calculo al catalogo",
                    "calculo" not in est["cursadas"]
                    and "calculo" not in est["deseadas"]
                    and est["catalogo"] == 72,
                    f"catalogo={est['catalogo']} cursadas={est['cursadas']}")

            # --- 6. mover entre cajas directamente (deseadas -> catalogo) ---
            await c.evalua(ARRASTRA.replace("$0", "'bases_de_datos'")
                           .replace("$1", "'catalogo'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("soltar en catalogo la quita de deseadas",
                    est["deseadas"] == [], str(est["deseadas"]))

            # --- 7. una materia no puede vivir en las dos cajas ---
            await c.evalua(ARRASTRA.replace("$0", "'calculo'")
                           .replace("$1", "'deseadas'"))
            await c.evalua(ARRASTRA.replace("$0", "'calculo'")
                           .replace("$1", "'cursadas'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("mover a cursadas la saca de deseadas",
                    est["cursadas"].count("calculo") == 1
                    and "calculo" not in est["deseadas"],
                    f"cursadas={est['cursadas']} deseadas={est['deseadas']}")

            # --- 8. filtro de busqueda ---
            await c.evalua("""
              (() => { const b = document.getElementById('busqueda');
                       b.value = 'algoritmos';
                       b.dispatchEvent(new Event('input', {bubbles: true})); })()""")
            est = await c.evalua(LEE_ESTADO)
            chequea("filtro reduce el catalogo",
                    0 < est["catalogo"] < 74, str(est["catalogo"]))
            chequea("contador muestra el filtro", "/" in est["contCatalogo"],
                    est["contCatalogo"])
            await c.evalua("""
              (() => { const b = document.getElementById('busqueda');
                       b.value = '';
                       b.dispatchEvent(new Event('input', {bubbles: true})); })()""")

            # --- 9. persistencia: recargar y seguir igual ---
            est_antes = await c.evalua(LEE_ESTADO)
            await c.llama("Page.reload", {"ignoreCache": True})
            await c.espera(
                "document.querySelectorAll('#lista-catalogo .materia').length === 74")
            est = await c.evalua(LEE_ESTADO)
            chequea("la seleccion sobrevive a recargar",
                    est["cursadas"] == est_antes["cursadas"]
                    and est["deseadas"] == est_antes["deseadas"],
                    f"antes={est_antes['cursadas']}/{est_antes['deseadas']} "
                    f"despues={est['cursadas']}/{est['deseadas']}")

            # --- 10. estado visual para captura ---
            for clave, caja in [("matematicas_discretas", "cursadas"),
                                ("calculo", "cursadas"),
                                ("comunicacion_oral_y_escrita", "cursadas"),
                                ("analisis_vectorial", "cursadas"),
                                ("bases_de_datos", "deseadas"),
                                ("algoritmos_y_estructura_de_datos", "deseadas")]:
                actual = await c.evalua(
                    f"document.querySelector('.materia[data-clave=\"{clave}\"]')"
                    f"?.closest('.caja')?.dataset.caja || 'ninguna'")
                if actual != caja:
                    await c.evalua(ARRASTRA.replace("$0", f"'{clave}'")
                                   .replace("$1", f"'{caja}'"))

            est = await c.evalua(LEE_ESTADO)

            # --- 10b. el boton revisar le pregunta al prolog ---
            # estado del punto 10: cursadas = 1ro completo (menos fundamentos),
            # deseadas = bases_de_datos (ok) + algoritmos (le falta 1ro).
            chequea("boton revisar habilitado con deseadas",
                    await c.evalua("!document.getElementById('revisar').disabled"),
                    "el boton sigue deshabilitado")

            await c.evalua("document.getElementById('revisar').click()")
            veredicto = await c.espera(
                "!document.getElementById('veredicto').hidden", intentos=40)
            txt = await c.evalua(
                "document.getElementById('veredicto').textContent")
            chequea("revisar contesta y pinta el veredicto", veredicto, txt[:80])
            chequea("revisar avisa que NO se puede (falta prerrequisito)",
                    txt.startswith('✗'), txt[:100])
            chequea("revisar dice cual materia falta",
                    'Fundamentos de Programacion' in txt, txt[:200])

            # completo el prerrequisito y vuelvo a pedir revision
            await c.evalua(ARRASTRA.replace("$0", "'fundamentos_de_programacion'")
                           .replace("$1", "'cursadas'"))
            await c.evalua("document.getElementById('revisar').click()")
            await c.espera(
                "document.getElementById('veredicto').textContent"
                ".startsWith('✓')", intentos=40)
            txt = await c.evalua(
                "document.getElementById('veredicto').textContent")
            chequea("al cursar lo que faltaba, revisar da el visto bueno",
                    txt.startswith('✓'), txt[:200])

            # sin deseadas no hay nada que revisar: el boton se apaga
            await c.evalua(ARRASTRA.replace("$0", "'bases_de_datos'")
                           .replace("$1", "'catalogo'"))
            await c.evalua(ARRASTRA.replace("$0",
                           "'algoritmos_y_estructura_de_datos'")
                           .replace("$1", "'catalogo'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("sin deseadas el boton revisar se deshabilita",
                    await c.evalua("document.getElementById('revisar').disabled"),
                    f"deseadas={est['deseadas']}")

            # y el veredicto viejo se borra, ya no corresponde
            chequea("el veredicto viejo se apaga al vaciar deseadas",
                    await c.evalua("document.getElementById('veredicto').hidden"),
                    "se quedo un veredicto de una seleccion que ya no existe")

            # regreso al estado del punto 10 para la captura final
            for clave, caja in [("bases_de_datos", "deseadas"),
                                ("algoritmos_y_estructura_de_datos", "deseadas"),
                                ("fundamentos_de_programacion", "cursadas")]:
                await c.evalua(ARRASTRA.replace("$0", f"'{clave}'")
                               .replace("$1", f"'{caja}'"))

            # captura de la seleccion con el veredicto en pantalla
            await c.evalua("document.getElementById('revisar').click()")
            await c.espera("!document.getElementById('veredicto').hidden",
                           intentos=40)
            await asyncio.sleep(0.4)
            import base64
            captura = await c.llama("Page.captureScreenshot",
                                    {"format": "png", "fromSurface": True})
            with open("/tmp/interfaz-materias.png", "wb") as f:
                f.write(base64.b64decode(captura["data"]))
            print("captura guardada en /tmp/interfaz-materias.png")

            # --- 10c. la seccion de horarios pinta la semana del prolog ---
            # estado del 10b restaurado: 5 cursadas, 2 deseadas validas
            await c.evalua("document.getElementById('preferencia').value = 'matutino'")
            est = await c.evalua(LEE_ESTADO)
            chequea("el boton generar esta activo con deseadas",
                    est["botonGenerar"], "seguia deshabilitado")
            await c.evalua("document.getElementById('generar').click()")
            pintado = await c.espera(
                "!document.getElementById('semana').hidden && "
                "document.querySelectorAll('#semana .bloque').length >= 4",
                intentos=40)
            n_bloques = await c.evalua(
                "document.querySelectorAll('#semana .bloque').length")
            chequea("generar horario pinta los bloques de la semana",
                    pintado, f"bloques={n_bloques}")
            n_cols = await c.evalua("document.querySelectorAll('#semana .col').length")
            chequea("la rejilla trae las 5 columnas de dias",
                    n_cols == 5, str(n_cols))
            n_horas = await c.evalua(
                "document.querySelectorAll('#semana .hora-etiqueta').length")
            chequea("la columna de horas tiene sus marcas",
                    n_horas >= 4, str(n_horas))
            resumen = await c.evalua(
                "document.getElementById('resumen-horario').textContent")
            chequea("el resumen del horario se pinta",
                    'Termina' in resumen and 'Huecos' in resumen,
                    resumen[:120])
            chequea("el spinner se apaga al terminar",
                    await c.evalua(
                        "document.getElementById('esperando-horario').hidden"),
                    "se quedo girando")

            # --- 10d. el spinner con contador mientras el motor piensa ---
            # la respuesta se retrasa a proposito para poder verlo
            await c.evalua("""
              window.__fetchReal = window.fetch;
              window.fetch = (url, opts) => {
                const p = window.__fetchReal(url, opts);
                if (String(url).includes('/horario')) {
                  return new Promise(res => setTimeout(() => res(p), 1500));
                }
                return p;
              };
            """)
            await c.evalua("document.getElementById('generar').click()")
            await asyncio.sleep(1.2)
            vis = await c.evalua(
                "!document.getElementById('esperando-horario').hidden")
            cuenta = await c.evalua(
                "document.getElementById('tiempo-horario').textContent")
            chequea("el spinner 'Prolog pensando' aparece mientras espera",
                    vis, "no se mostro")
            chequea("el contador de segundos avanza",
                    cuenta.endswith('s') and cuenta != '0 s', repr(cuenta))
            chequea("el boton generar se bloquea durante la espera",
                    await c.evalua("document.getElementById('generar').disabled"),
                    "seguia activo")
            repintado = await c.espera(
                "!document.getElementById('semana').hidden && "
                "document.querySelectorAll('#semana .bloque').length >= 4",
                intentos=40)
            chequea("al llegar la respuesta se pinta la semana otra vez",
                    repintado, "no repinto")
            await c.evalua(
                "window.fetch = window.__fetchReal; delete window.__fetchReal;")

            # --- 10e. sin prerrequisitos el motor rechaza y el panel lo dice ---
            await c.evalua(ARRASTRA.replace("$0", "'fundamentos_de_programacion'")
                           .replace("$1", "'catalogo'"))
            est = await c.evalua(LEE_ESTADO)
            chequea("mover una materia apaga la semana vieja",
                    not est["semanaVisible"], "se quedo la semana anterior")
            await c.evalua("document.getElementById('generar').click()")
            visto = await c.espera(
                "!document.getElementById('error-horario').hidden", intentos=40)
            txt = await c.evalua(
                "document.getElementById('error-horario').textContent")
            chequea("el panel muestra el error de prerrequisitos del prolog",
                    visto and 'Fundamentos de Programacion' in txt, txt[:140])

            # restauro el estado para la captura del horario
            await c.evalua(ARRASTRA.replace("$0", "'fundamentos_de_programacion'")
                           .replace("$1", "'cursadas'"))
            est = await c.evalua(LEE_ESTADO)
            error_apagado = await c.evalua(
                "document.getElementById('error-horario').hidden")
            chequea("al restaurar la seleccion el error se apaga",
                    est["botonGenerar"] and error_apagado
                    and not est["semanaVisible"],
                    f"generar={est['botonGenerar']} error_apagado={error_apagado} "
                    f"semana={est['semanaVisible']}")

            # --- 10f. navegacion entre sugerencias ---
            await c.evalua("document.getElementById('preferencia').value = 'matutino'")
            await c.evalua("document.getElementById('generar').click()")
            await c.espera(
                "!document.getElementById('semana').hidden && "
                "document.querySelectorAll('#semana .bloque').length >= 4",
                intentos=40)
            est = await c.evalua(LEE_ESTADO)
            indice = est["navegador"]
            chequea("el navegador aparece con las sugerencias",
                    indice is not None and '/' in indice, str(indice))
            n_sugerencias = int(indice.split('/')[1].strip()) if indice else 0
            chequea("hay varias sugerencias para navegar",
                    n_sugerencias >= 2, f"n={n_sugerencias}")
            chequea("en la primera sugerencia la flecha izquierda esta muerta",
                    est["flechaPrev"] is True, str(est["flechaPrev"]))

            grupos_1 = est["gruposSemana"]
            await c.evalua("document.getElementById('opcion-siguiente').click()")
            est = await c.evalua(LEE_ESTADO)
            indice_2 = est["navegador"]
            chequea("la flecha derecha avanza el indice",
                    indice_2 == f'2 / {n_sugerencias}', str(indice_2))
            chequea("la sugerencia 2 pinta otros grupos en la rejilla",
                    est["gruposSemana"] != grupos_1,
                    "la rejilla no cambio")
            chequea("la flecha izquierda ya se activa en la opcion 2",
                    est["flechaPrev"] is False, str(est["flechaPrev"]))

            # hasta el final y de regreso
            for _ in range(n_sugerencias):
                await c.evalua("document.getElementById('opcion-siguiente').click()")
            est = await c.evalua(LEE_ESTADO)
            chequea("la flecha derecha se muere en la ultima sugerencia",
                    est["flechaNext"] is True
                    and est["navegador"] == f'{n_sugerencias} / {n_sugerencias}',
                    f"indice={est['navegador']} next={est['flechaNext']}")
            for _ in range(n_sugerencias):
                await c.evalua("document.getElementById('opcion-anterior').click()")
            est = await c.evalua(LEE_ESTADO)
            chequea("volver al principio restaura la mejor sugerencia",
                    est["navegador"] == f'1 / {n_sugerencias}'
                    and est["gruposSemana"] == grupos_1,
                    f"indice={est['navegador']}")

            # cambiar el turno regenera y el navegador se reinicia
            await c.evalua("document.getElementById('preferencia').value = 'vespertino'")
            await c.evalua("document.getElementById('generar').click()")
            await c.espera(
                "!document.getElementById('semana').hidden && "
                "document.getElementById('opcion-indice').textContent"
                ".startsWith('1 /')", intentos=40)
            est = await c.evalua(LEE_ESTADO)
            chequea("al regenerar se vuelve a la sugerencia 1",
                    est["navegador"] is not None
                    and est["navegador"].startswith('1 /'),
                    str(est["navegador"]))
            # de regreso a matutino para la captura
            await c.evalua("document.getElementById('preferencia').value = 'matutino'")
            await c.evalua("document.getElementById('generar').click()")
            await c.espera(
                "!document.getElementById('semana').hidden && "
                "document.querySelectorAll('#semana .bloque').length >= 4",
                intentos=40)

            # --- 10g. captura final: veredicto + semana en pantalla ---
            await c.evalua("document.getElementById('revisar').click()")
            await c.espera("!document.getElementById('veredicto').hidden",
                           intentos=40)
            await asyncio.sleep(0.4)
            captura = await c.llama("Page.captureScreenshot",
                                    {"format": "png", "fromSurface": True})
            with open("/tmp/interfaz-horario.png", "wb") as f:
                f.write(base64.b64decode(captura["data"]))
            # la seccion del horario vive mas abajo: me acerco a ella
            await c.evalua(
                "document.querySelector('.panel-horario')"
                ".scrollIntoView({block: 'start'})")
            await asyncio.sleep(0.4)
            captura = await c.llama("Page.captureScreenshot",
                                    {"format": "png", "fromSurface": True})
            with open("/tmp/captura-horario.png", "wb") as f:
                f.write(base64.b64decode(captura["data"]))
            print("capturas guardadas en /tmp/interfaz-horario.png y "
                  "/tmp/captura-horario.png")

            # --- 11. /materias sigue vivo pasados los 30 s de arranque ---
            # regresion del contexto que se creaba una sola vez en main():
            # pasado el tope, la consulta a prolog contestaba basura. El
            # servidor arranco antes que esta prueba, asi que duermo hasta
            # que tenga mas de 35 s de vida y vuelvo a preguntarle.
            tiempo_restante = 35 - (time.monotonic() - t0)
            if tiempo_restante > 0:
                await asyncio.sleep(tiempo_restante)
            await c.evalua("localStorage.clear()")
            await c.llama("Page.reload", {"ignoreCache": True})
            vivo = await c.espera(
                "document.querySelectorAll('#lista-catalogo .materia').length === 74")
            chequea("/materias sigue vivo pasados 30 s", vivo,
                    "el catalogo ya no carga: el contexto del servidor vencio")

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _post_horario(cuerpo, timeout=60):
    req = urllib.request.Request(
        BASE + "/horario", data=json.dumps(cuerpo).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {}


def _traslapes(horario):
    """Cuenta pares de bloques de materias distintas que se cruzan."""
    from collections import defaultdict
    por_dia = defaultdict(list)
    for m in horario:
        for b in m["bloques"]:
            i = int(b["inicio"].replace(":", ""))
            f = int(b["fin"].replace(":", ""))
            por_dia[b["dia"]].append((i, f, m["materia"]))
    total = 0
    for bloques in por_dia.values():
        bloques.sort()
        for a in range(len(bloques)):
            for b in range(a + 1, len(bloques)):
                (i1, f1, _), (i2, f2, _) = bloques[a], bloques[b]
                if i1 < f2 and i2 < f1:
                    total += 1
    return total


def prueba_horario():
    """POST /horario: casos rapidos del endpoint, sin navegador."""
    cursadas = ["fundamentos_de_programacion", "matematicas_discretas",
                "calculo", "analisis_vectorial", "comunicacion_oral_y_escrita"]
    deseadas6 = ["algoritmos_y_estructura_de_datos", "algebra_lineal",
                 "calculo_aplicado", "mecanica_y_electromagnetismo",
                 "ingenieria_etica_y_sociedad", "fundamentos_economicos"]

    cod, d = _post_horario({"cursadas": cursadas, "deseadas": deseadas6,
                            "preferencia": "matutino"})
    chequea("POST /horario arma las 6 materias (200)",
            cod == 200 and d.get("ok") and len(d.get("horario", [])) == 6,
            f"HTTP {cod} {d.get('error')}")
    if cod == 200:
        chequea("el horario viene sin traslapes",
                _traslapes(d["horario"]) == 0,
                f"{_traslapes(d['horario'])} cruces")
        r = d.get("resumen", {})
        chequea("el resumen trae materias, huecos y hora de fin",
                r.get("materias") == 6 and "huecos_minutos" in r
                and r.get("termina"), str(r))

        # sugerencias: alternativas ademas de la mejor
        sugs = d.get("sugerencias") or []
        chequea("la respuesta trae varias sugerencias",
                len(sugs) >= 2, f"trae {len(sugs)}")
        chequea("total_sugerencias coincide con lo que llega",
                d.get("total_sugerencias") == len(sugs),
                f"total={d.get('total_sugerencias')} llegan={len(sugs)}")
        if sugs:
            chequea("la primera sugerencia ES la mejor (coincide con horario)",
                    sugs[0]["horario"] == d["horario"]
                    and sugs[0]["resumen"] == d["resumen"],
                    "no coincide con horario/resumen de arriba")
            cruces = sum(_traslapes(s["horario"]) for s in sugs)
            chequea("ninguna sugerencia trae traslapes",
                    cruces == 0, f"{cruces} cruces")
            grupos = [tuple(m["grupo"] for m in s["horario"]) for s in sugs]
            chequea("las sugerencias son combinaciones distintas",
                    len(set(grupos)) == len(grupos),
                    f"{len(set(grupos))} distintas de {len(grupos)}")
            h1 = sugs[0]["resumen"]["huecos_minutos"]
            peores = [s["resumen"]["huecos_minutos"] for s in sugs[1:]]
            chequea("la mejor no tiene mas huecos que las demas",
                    all(h1 <= h for h in peores),
                    f"mejor={h1} otras={peores}")

    # mixto recorre mucho mas arbol: con 4 materias contesta enseguida, y
    # con 6 le toma ~10 s al motor (antes tronaba con 504 por el tope de
    # 10 s; el servidor ahora se fija en 100 s y esta es la regresion)
    cod, d = _post_horario({"cursadas": cursadas,
                            "deseadas": deseadas6[:4],
                            "preferencia": "mixto"})
    chequea("mixto responde con 4 materias",
            cod == 200 and d.get("ok") and len(d.get("horario", [])) == 4,
            f"HTTP {cod} {d.get('error')}")

    cod, d = _post_horario({"cursadas": cursadas,
                            "deseadas": deseadas6,
                            "preferencia": "mixto"})
    chequea("mixto con 6 materias no se pasa del timeout (regresion 504)",
            cod == 200 and d.get("ok") and len(d.get("horario", [])) == 6,
            f"HTTP {cod} {d.get('error')}")

    cod, d = _post_horario({"cursadas": [], "deseadas": ["bases_de_datos"]})
    chequea("falta prerrequisito -> 422 con reporte",
            cod == 422 and d.get("error") == "prerrequisitos"
            and d.get("reporte"), f"HTTP {cod} {d}")

    cod, d = _post_horario({"cursadas": cursadas, "deseadas": deseadas6,
                            "preferencia": "nocturno"})
    chequea("preferencia invalida -> 400",
            cod == 400 and d.get("error") == "preferencia_invalida",
            f"HTTP {cod} {d}")

    cod, d = _post_horario({"cursadas": [], "deseadas": []})
    chequea("listas vacias -> 400",
            cod == 400 and d.get("error") == "sin_materias",
            f"HTTP {cod} {d}")

    cod, d = _post_horario({"cursadas": ["calculo"],
                            "deseadas": ["calculo_aplicado", "calculo_aplicado"]})
    chequea("materia repetida -> 422",
            cod == 422 and d.get("error") == "materia_repetida",
            f"HTTP {cod} {d}")

    # el cliente puede pedir menos (o mas, tope 10) sugerencias
    cod, d = _post_horario({"cursadas": cursadas, "deseadas": deseadas6,
                            "preferencia": "matutino", "cantidad": 2})
    chequea("cantidad=2 limita las sugerencias a 2",
            cod == 200 and len(d.get("sugerencias") or []) == 2,
            f"llegan {len(d.get('sugerencias') or [])}")
    cod, d = _post_horario({"cursadas": cursadas, "deseadas": deseadas6,
                            "preferencia": "matutino", "cantidad": 99})
    chequea("cantidad=99 se recorta al tope de 10",
            cod == 200 and len(d.get("sugerencias") or []) <= 10,
            f"llegan {len(d.get('sugerencias') or [])}")


def prueba_codificacion():
    """GET /materias en crudo: la ñ y los acentos deben llegar en utf-8.

    regresion del bug de render: en el contenedor debian el locale era C,
    swipl leia hechos.pl como ascii y cada byte del ñ se volvia U+FFFD
    (dos "cuadritos" en la interfaz). el fix es encoding(utf8) al cargar
    + ENV LANG en el Dockerfile, y esta prueba lo vigila.
    """
    req = urllib.request.Request(BASE + "/materias")
    with urllib.request.urlopen(req, timeout=10) as r:
        crudo = r.read()
        ctype = r.headers.get("Content-Type", "")

    chequea("/materias declara charset utf-8",
            "charset=utf-8" in ctype.lower(), ctype)

    n_fffd = crudo.count(b"\xef\xbf\xbd") + crudo.lower().count(b"\\ufffd")
    chequea("ningun U+FFFD (cuadrito) en los datos",
            n_fffd == 0, f"{n_fffd} replacement chars")

    # la enye correcta: utf-8 crudo (c3 b1) o escape json (00f1)
    enye_ok = b"Se\xc3\xb1ales" in crudo or b"Se\\u00f1ales" in crudo.lower()
    chequea("la ñ de 'Señales' llega correcta", enye_ok,
            _contexto(crudo, b"Procesamiento Digital"))

    # y que el json ademas decodifique al nombre completo
    try:
        datos = json.loads(crudo)
        nombres = [m["nombre"] for m in datos.get("materias", [])]
        chequea("el nombre 'Procesamiento Digital de Señales' decodifica",
                "Procesamiento Digital de Señales" in nombres,
                [n for n in nombres if "Procesamiento" in n])
        acentos = [n for n in nombres if "Diseño" in n]
        chequea("los 'Diseño' del catalogo tambien decodifican",
                len(acentos) >= 3, f"{len(acentos)} con Diseño")
    except Exception as e:
        chequea("el json de /materias es parseable", False, str(e))


def _contexto(crudo, ancla, extra=30):
    i = crudo.find(ancla)
    return repr(crudo[i:i + len(ancla) + extra]) if i >= 0 else "ancla no encontrada"


def main():
    try:
        urllib.request.urlopen(f"{BASE}/materias", timeout=5).read()
    except Exception as e:
        print("el servidor no responde en", BASE, e, file=sys.stderr)
        return 2

    # primero los endpoints (no necesitan navegador), luego la interfaz
    prueba_codificacion()
    prueba_horario()

    if not os.path.exists(CHROME):
        print("no hay chromium:", CHROME, file=sys.stderr)
        return 2

    asyncio.run(prueba())
    fallos = [c for c in CHEQUEOS if not c[1]]
    print(f"\n{len(CHEQUEOS) - len(fallos)}/{len(CHEQUEOS)} chequeos ok")
    if fallos:
        for nombre, _, detalle in fallos:
            print(f"  FALLO: {nombre} — {detalle}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
