"""Barrido de CSRF en plantillas y JavaScript (corte D1, punto D-2).

- Todo <form method="post"> de templates/ debe incluir csrf_token, salvo que la
  línea anterior tenga un comentario «csrf-exento: motivo» explícito.
- Todo fetch() que hace POST, PUT, PATCH o DELETE en templates/ o static/js debe
  enviar la cabecera X-CSRFToken, salvo exención igual.
Las rutas /api/* con JWT no usan sesión y no se exigen aquí.
"""

import pathlib
import re

RAIZ = pathlib.Path(__file__).resolve().parents[1]
PATRON_FORM = re.compile(r"<form\b([^>]*)>", re.I)
PATRON_FETCH = re.compile(r"fetch\(", re.I)
PATRON_METODO_MUTA = re.compile(r"method\s*:\s*['\"`](POST|PUT|PATCH|DELETE)['\"`]", re.I)
EXENCION = "csrf-exento"


def _formularios_sin_csrf():
    hallazgos = []
    for ruta in sorted((RAIZ / "templates").rglob("*.html")):
        texto = ruta.read_text(encoding="utf-8")
        lineas = texto.split("\n")
        for match in PATRON_FORM.finditer(texto):
            if not re.search(r"method\s*=\s*['\"]?post", match.group(1), re.I):
                continue
            cierre = re.search(r"</form\s*>", texto[match.end():], re.I)
            bloque = texto[match.end(): match.end() + (cierre.start() if cierre else 0)]
            numero = texto[: match.start()].count("\n") + 1
            anterior = lineas[numero - 2] if numero >= 2 else ""
            if "csrf_token" in bloque or EXENCION in anterior:
                continue
            hallazgos.append(f"{ruta.relative_to(RAIZ)}:{numero}")
    return hallazgos


def _fetch_que_muta_sin_cabecera():
    hallazgos = []
    archivos = list((RAIZ / "templates").rglob("*.html")) + list((RAIZ / "static" / "js").glob("*.js"))
    for ruta in sorted(archivos):
        texto = ruta.read_text(encoding="utf-8")
        lineas = texto.split("\n")
        for match in PATRON_FETCH.finditer(texto):
            ventana = texto[match.start(): match.start() + 500]
            if not PATRON_METODO_MUTA.search(ventana) or "X-CSRFToken" in ventana:
                continue
            numero = texto[: match.start()].count("\n") + 1
            anterior = lineas[numero - 2] if numero >= 2 else ""
            if EXENCION in anterior:
                continue
            hallazgos.append(f"{ruta.relative_to(RAIZ)}:{numero}")
    return hallazgos


def test_hay_plantillas_y_js_para_revisar():
    assert len(list((RAIZ / "templates").rglob("*.html"))) >= 20
    assert len(list((RAIZ / "static" / "js").glob("*.js"))) >= 5


def test_todo_formulario_post_de_plantillas_lleva_csrf_token():
    hallazgos = _formularios_sin_csrf()
    assert not hallazgos, "Formularios POST sin csrf_token: " + ", ".join(hallazgos)


def test_todo_fetch_que_muta_envia_x_csrftoken():
    hallazgos = _fetch_que_muta_sin_cabecera()
    assert not hallazgos, "fetch que muta sin X-CSRFToken: " + ", ".join(hallazgos)
