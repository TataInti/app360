"""Avisos de Tesorería, RRHH y Compras sin prefijo técnico (corte D1, punto D-9).

Recorre las plantillas de esas áreas y falla si aparece un aviso con prefijo
«Error:» o un texto genérico «Error…» como mensaje al usuario. console.error no
cuenta: no lo ve el usuario.
"""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1] / "templates"
AREAS = ("tesoreria_*.html", "rrhh_*.html", "compras_*.html")
PATRONES = [
    re.compile(r"alert\(\s*['\"]Error"),
    re.compile(r"['\"]Error:\s*['\"]?\s*\+"),
    re.compile(r"['\"]Error:\s*\$\{"),
    re.compile(r"\|\|\s*['\"]Error['\"]\)"),
    re.compile(r">Error al "),
    re.compile(r"['\"]Error de conexi"),
]


def _plantillas_del_area():
    archivos = []
    for patron in AREAS:
        archivos.extend(sorted(RAIZ.glob(patron)))
    return archivos


def test_hay_plantillas_del_area_para_revisar():
    assert len(_plantillas_del_area()) >= 10


def test_avisos_de_tesoreria_rrhh_compras_sin_prefijo_tecnico():
    hallazgos = []
    for ruta in _plantillas_del_area():
        for numero, linea in enumerate(ruta.read_text(encoding="utf-8").splitlines(), 1):
            if "console.error" in linea:
                continue
            if any(patron.search(linea) for patron in PATRONES):
                hallazgos.append(f"{ruta.name}:{numero}")
    assert not hallazgos, "Avisos con prefijo técnico o genérico: " + ", ".join(hallazgos)
