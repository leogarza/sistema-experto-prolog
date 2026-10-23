#!/usr/bin/env python3
"""Genera src/horarios.pl a partir del volcado del SAES.

Uso:
    python3 scripts/generar_horarios.py

Produce:
    horario(Clave, Grupo, Dia, Inicio, Fin).

Las horas van como enteros HHMM (1030 = 10:30) para que se puedan comparar
con < y > directamente en Prolog. Los días son lun, mar, mie, jue, vie, sab.

Los grupos se modelan aparte: `horario/5` es la integración real; `horario/4`
(una materia, un horario) se queda como está en conocimiento.pl.
"""

import json
import re
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "datos" / "saes_horarios_2026-10-23.json"
HECHOS = RAIZ / "src" / "hechos.pl"

DIAS = ["lun", "mar", "mie", "jue", "vie", "sab"]

ALIAS = {
    "algoritmos_y_estructuras_de_datos": "algoritmos_y_estructura_de_datos",
    "tecnologias_para_el_desarrollo_de_aplicaciones_web": "tecnologias_para_desarrollo_de_aplicaciones_web",
    "intrumentacion_y_control": "instrumentacion_y_control",
}


def atomo(texto: str) -> str:
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
    limpio = re.sub(r"[^a-z0-9]+", "_", sin_acentos.lower()).strip("_")
    return ALIAS.get(limpio, limpio) or "materia"


def atomo_prolog(texto: str) -> str:
    """Los grupos como 1CM1 empiezan con dígito: hay que citarlos."""
    if re.fullmatch(r"[a-z][a-zA-Z0-9_]*", texto):
        return texto
    return "'" + texto.replace("\\", "\\\\").replace("'", "\\'") + "'"


def hhmm(texto: str) -> int:
    """'10:30' -> 1030 ; '08:00' -> 800."""
    h, m = texto.strip().split(":")
    return int(h) * 100 + int(m)


def materias_del_plan():
    if not HECHOS.exists():
        return set()
    texto = HECHOS.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"^materia\(([a-z0-9_]+),", texto, re.M))


def main():
    if not FUENTE.exists():
        print(f"no existe {FUENTE}", file=sys.stderr)
        return 1

    datos = json.loads(FUENTE.read_text(encoding="utf-8"))
    grupos = datos.get("horarios", [])
    plan = materias_del_plan()

    hechos = []
    sin_match = {}
    usados = set()

    for g in grupos:
        clave = atomo(g.get("materia", ""))
        grupo = g.get("grupo", "").strip()
        if not clave or not grupo:
            continue
        if plan and clave not in plan:
            sin_match[clave] = g.get("materia")
            continue
        for dia in DIAS:
            rango = (g.get("horarios") or {}).get(dia)
            if not rango or "-" not in rango:
                continue
            ini, fin = rango.split("-", 1)
            try:
                hechos.append((clave, grupo, dia, hhmm(ini), hhmm(fin)))
                usados.add(clave)
            except ValueError:
                continue

    print("% GENERADO por scripts/generar_horarios.py — no editar a mano.")
    print("% Fuente: horarios del SAES. Hora en formato HHMM (1030 = 10:30).")
    print()
    for clave, grupo, dia, ini, fin in sorted(hechos):
        print(f"horario({clave}, {atomo_prolog(grupo)}, {dia}, {ini}, {fin}).")

    print(
        f"% total: {len(hechos)} bloques de {len({h[1] for h in hechos})} grupos "
        f"de {len(usados)} materias",
        file=sys.stderr,
    )
    if sin_match:
        print(
            "% AVISO: materias del SAES que no están en el plan: "
            + ", ".join(sorted(sin_match.values())),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
