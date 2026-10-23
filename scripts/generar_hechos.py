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


def leer_seriacion():
    pares = []
    for linea in SERIACION.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or "->" not in linea:
            continue
        izq, der = [p.strip() for p in linea.split("->", 1)]
        if izq and der:
            pares.append((atomo(der), atomo(izq)))  # (dependiente, requerida)
    return pares


def escapar(texto: str) -> str:
    return texto.replace("\\", "\\\\").replace("'", "\\'")


def main():
    materias = leer_materias()
    pares = leer_seriacion()
    conocidas = {m["clave"] for m in materias}

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
        salida.append(f"nombre({m['clave']}, '{escapar(m['nombre'].title())}').")

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
    faltantes = []
    for dep, req in pares:
        salida.append(f"prerrequisito({dep}, {req}).")
        for x in (dep, req):
            if x not in conocidas and x not in faltantes:
                faltantes.append(x)

    print("\n".join(salida))

    if faltantes:
        print(
            "% AVISO: estas materias de la seriación no aparecen en el plan: "
            + ", ".join(faltantes),
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
