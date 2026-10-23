#!/usr/bin/env python3
"""Genera hechos Prolog a partir de los datos del SAES (retícula y seriación).

Uso:
    python3 scripts/generar_hechos.py > datos/generado.pl

Lo que produce:
    materia(Clave, Creditos).       % compatibles con las reglas existentes
    nombre(Clave, 'Nombre').
    semestre(Clave, N).
    tipo(Clave, Tipo).
    prerrequisito(Materia, Requerida).

Los datos NO se inventan: salen de datos/materias.html (plan de estudios) y de
datos/seriacion.txt. Es un convertidor de formato, no una fuente de conocimiento.
"""

import html
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MATERIAS = RAIZ / "datos" / "materias.html"
SERIACION = RAIZ / "datos" / "seriacion.txt"
CONOCIMIENTO = RAIZ / "src" / "conocimiento.pl"


def atomo(texto: str) -> str:
    """'Cálculo Aplicado' -> 'calculo_aplicado' (átomo Prolog seguro)."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_")
    return limpio or "materia"


def leer_materias():
    s = MATERIAS.read_text(encoding="utf-8", errors="replace")
    filas = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", s, re.S | re.I):
        celdas = [
            html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
            for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S | re.I)
        ]
        if len(celdas) >= 5 and celdas[1]:
            periodo, clave, nombre, tipo, creditos = celdas[:5]
            try:
                creditos_n = float(creditos.replace(",", "."))
            except ValueError:
                continue
            filas.append({
                "clave": atomo(nombre),
                "nombre": nombre,
                "semestre": int(periodo) if periodo.isdigit() else 0,
                "tipo": tipo,
                "creditos": creditos_n,
            })
    return filas


def ya_definidas():
    """Átomos de materia/2 que ya existen en conocimiento.pl: no se repiten."""
    if not CONOCIMIENTO.exists():
        return set()
    texto = CONOCIMIENTO.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"^materia\(([a-z0-9_]+)\s*,", texto, re.M))


def leer_seriacion():
    pares = []
    for linea in SERIACION.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or "->" not in linea:
            continue
        izq, der = [p.strip() for p in linea.split("->", 1)]
        if izq and der:
            dep, req = atomo(der), atomo(izq)
            pares.append((ALIAS.get(dep, dep), ALIAS.get(req, req)))  # (dependiente, requerida)
    return pares


# Nombres de la seriación escrita a mano que no coinciden letra por letra
# con el plan de estudios (plurales, typos). Se corrigen aquí, a la vista.
ALIAS = {
    "algoritmos_y_estructuras_de_datos": "algoritmos_y_estructura_de_datos",
    "tecnologias_para_el_desarrollo_de_aplicaciones_web": "tecnologias_para_desarrollo_de_aplicaciones_web",
    "intrumentacion_y_control": "instrumentacion_y_control",
}

CONECTORES = {"de", "del", "la", "las", "el", "los", "y", "en", "para", "por", "con"}


def bonito(texto: str) -> str:
    """'VISION POR COMPUTADORA|MACHINE LEARNING' -> 'Vision por Computadora / Machine learning'."""
    texto = texto.replace("|", " / ")
    palabras = texto.title().split()
    return " ".join(
        p.lower() if i and p.lower() in CONECTORES else p for i, p in enumerate(palabras)
    )


def escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("'", "\\'")


def main():
    materias = leer_materias()
    pares = leer_seriacion()
    conocidas = {m["clave"] for m in materias}
    repetidas = ya_definidas() & conocidas
    if repetidas:
        materias = [m for m in materias if m["clave"] not in repetidas]
        print(
            "% AVISO: no se repiten porque ya están en conocimiento.pl: "
            + ", ".join(sorted(repetidas)),
            file=sys.stderr,
        )

    salida = []
    salida.append("% GENERADO por scripts/generar_hechos.py — no editar a mano.")
    salida.append("% Fuente: plan de estudios y seriación del SAES.")
    salida.append("")

    salida.append("% ---- materias: clave, creditos ----")
    for m in materias:
        salida.append(f"materia({m['clave']}, {m['creditos']:g}).")

    salida.append("")
    salida.append("% ---- nombre legible para la interfaz ----")
    for m in materias:
        salida.append(f"nombre({m['clave']}, '{escapar(bonito(m['nombre']))}').")

    salida.append("")
    salida.append("% ---- semestre del plan de estudios ----")
    for m in materias:
        if m["semestre"]:
            salida.append(f"semestre({m['clave']}, {m['semestre']}).")

    salida.append("")
    salida.append("% ---- tipo de asignatura ----")
    for m in materias:
        salida.append(f"tipo({m['clave']}, {atomo(m['tipo'])}).")

    salida.append("")
    salida.append("% ---- seriacion: prerrequisito(Materia, Requerida) ----")
    # Solo se emiten seriaciones cuyas dos materias existen de verdad (las
    # "optativa_a1/a2" del texto no son materias del plan).
    validas = {m["clave"] for m in materias} | ya_definidas()
    faltantes, descartadas = [], []
    for dep, req in pares:
        if dep in validas and req in validas:
            salida.append(f"prerrequisito({dep}, {req}).")
        else:
            descartadas.append(f"{dep}<-{req}")
    if descartadas:
        print(
            "% AVISO: seriaciones descartadas por no existir en el plan: "
            + ", ".join(descartadas),
            file=sys.stderr,
        )

    print("\n".join(salida))

    if faltantes:
        print(
            "% AVISO: estas materias de la seriación no aparecen en el plan: "
            + ", ".join(faltantes),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
