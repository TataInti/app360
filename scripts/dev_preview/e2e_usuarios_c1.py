#!/usr/bin/env python3
"""E2E de navegador: clave temporal y cambio de clave propia (C1 de administración de usuarios).

Recorre con Chromium en es-AR: entrada de los usuarios actuales sin cambio obligatorio;
clave temporal obligatoria en páginas y API; rechazos de la clave nueva; «Cambiar mi clave»
desde el menú; cierre de las otras sesiones del mismo usuario; reingreso con la clave nueva y
no con la vieja; y ausencia de 4xx/5xx inesperados en red y consola.

Datos sintéticos: al empezar fija las claves ficticias y la bandera de clave temporal de los
usuarios que usa, así que puede repetirse. Solo corre sobre la base app360_c1 en 127.0.0.1.
Sale con código 1 si alguna verificación falla. No imprime claves ni las guarda.

Uso (desde la raíz del repo; la instancia C1 la levanta run_local_c1.sh):
    E2E_BASE_URL=http://127.0.0.1:5063 DATABASE_URL=... SECRET_KEY=... ADMIN_PASSWORD=... \
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_usuarios_c1.py
Variables: E2E_BASE_URL, E2E_CHROMIUM, E2E_CAPTURAS (carpeta padre; las capturas van a despues/),
E2E_ADMIN_PASSWORD (clave ficticia del admin de la instancia).
"""

import json
import os
import sys
from urllib.parse import urlsplit

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5062").rstrip("/")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
CAPTURAS = os.path.join(
    os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/c1/capturas"), "despues"
)
CAMBIO = "/cambiar-clave"
TEMPORAL = "Primero cambiá tu clave temporal."
ADMIN_CLAVE = os.environ.get("E2E_ADMIN_PASSWORD", "c1-admin-ficticia-2026")

# usuario, rol, activo, clave temporal (estado inicial que fija el script)
USUARIOS = [
    ("admin", "admin", True, False),
    ("gerente", "gerente", True, False),
    ("ventas", "sales", True, False),
    ("rrhh", "hr", True, False),
    ("tesoreria", "caja", True, False),
    ("direccion", "director", True, False),
    ("anibal.lopez", "sales", True, True),
    ("test_user", "sales", False, False),
]
ANIBAL_NUEVA = "C1-anibal-nueva-2026"
VENTAS_NUEVA = "C1-ventas-nueva-2026"
RRHH_NUEVA = "C1-rrhh-nueva-2026"

# Respuestas 4xx que el recorrido provoca a propósito (rechazos y bloqueos).
ESPERADAS = {
    (400, CAMBIO),
    (401, "/api/rrhh"),
    (403, "/api/dashboard-comercial/mix"),
    (404, "/favicon.ico"),
}

VERIFICACIONES = []
RESPUESTAS = []
CONSOLA = []
ERRORES_JS = []
CONTEXTOS = []


def inicial(usuario):
    return ADMIN_CLAVE if usuario == "admin" else f"c1-{usuario}-ficticia-2026"


def verificar(nombre, condicion, detalle=""):
    VERIFICACIONES.append({"verificacion": nombre, "ok": bool(condicion), "detalle": detalle})
    marca = "OK   " if condicion else "FALLA"
    extra = f" [{detalle}]" if detalle and not condicion else ""
    print(f"{marca} {nombre}{extra}", flush=True)


def preparar_datos():
    """Fija clave, rol, activo y bandera de los usuarios sintéticos. Solo base app360_c1 local."""
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.hostname not in ("127.0.0.1", "localhost") or url.path.lstrip("/") != "app360_c1":
        raise SystemExit("El E2E C1 solo corre sobre la base app360_c1 en 127.0.0.1.")
    sys.path.insert(0, RAIZ)
    os.chdir(RAIZ)
    from app import create_app
    from models import db
    from models.core.user import User

    app = create_app()
    with app.app_context():
        for usuario, rol, activo, temporal in USUARIOS:
            cuenta = User.query.filter_by(username=usuario).one_or_none()
            if cuenta is None:
                raise SystemExit(f"Falta el usuario sintético {usuario}: correr run_local_c1.sh up.")
            cuenta.role = rol
            cuenta.active = activo
            cuenta.must_change_password = temporal
            cuenta.password_changed_at = None
            cuenta.set_password(inicial(usuario))
        db.session.commit()


def _registrar_respuesta(etiqueta, respuesta):
    if respuesta.status >= 400:
        RESPUESTAS.append(
            {
                "contexto": etiqueta,
                "metodo": respuesta.request.method,
                "status": respuesta.status,
                "ruta": urlsplit(respuesta.url).path,
            }
        )


def nuevo_contexto(navegador, etiqueta):
    contexto = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})
    contexto.on("response", lambda respuesta: _registrar_respuesta(etiqueta, respuesta))
    CONTEXTOS.append(contexto)
    return contexto


def nueva_pagina(contexto, etiqueta):
    pagina = contexto.new_page()

    def consola(mensaje):
        if mensaje.type == "error":
            CONSOLA.append(
                {"contexto": etiqueta, "texto": mensaje.text[:200], "url": mensaje.location.get("url", "")}
            )

    pagina.on("console", consola)
    pagina.on("pageerror", lambda error: ERRORES_JS.append({"contexto": etiqueta, "error": str(error)[:200]}))
    return pagina


def entrar(pagina, usuario, clave):
    """Entra por el formulario de la pantalla de login. Devuelve la ruta a la que cayó."""
    pagina.goto(BASE + "/", wait_until="load")
    pagina.fill("input[name=username]", usuario)
    pagina.fill("input[name=password]", clave)
    with pagina.expect_navigation(wait_until="load"):
        pagina.press("input[name=password]", "Enter")
    return urlsplit(pagina.url).path


def ir(pagina, ruta):
    pagina.goto(BASE + ruta, wait_until="load")
    return urlsplit(pagina.url).path


def mensajes(pagina):
    return [texto.strip() for texto in pagina.locator(".alert").all_inner_texts() if texto.strip()]


def errores_campo(pagina):
    return [texto.strip() for texto in pagina.locator(".invalid-feedback").all_inner_texts()]


def enviar_cambio(pagina, actual, nueva, repetida):
    pagina.fill("#clave_actual", actual)
    pagina.fill("#clave_nueva", nueva)
    pagina.fill("#repetir_clave", repetida)
    with pagina.expect_navigation(wait_until="load"):
        pagina.click("form[action='/cambiar-clave'] button[type=submit]")


def abrir_desde_menu(pagina):
    with pagina.expect_navigation(wait_until="load"):
        pagina.click("a.cambiar-clave-btn")


def captura(pagina, nombre):
    os.makedirs(CAPTURAS, exist_ok=True)
    pagina.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"))


def escenario_compatibilidad(navegador):
    for usuario in ("admin", "gerente", "ventas", "rrhh", "tesoreria", "direccion"):
        contexto = nuevo_contexto(navegador, f"compat-{usuario}")
        pagina = nueva_pagina(contexto, f"compat-{usuario}")
        ruta = entrar(pagina, usuario, inicial(usuario))
        verificar(
            f"compat: {usuario} entra con su clave sin pasar por el cambio",
            ruta not in (CAMBIO, "/"),
            ruta,
        )
        verificar(
            f"menú: {usuario} ve «Cambiar mi clave»",
            pagina.locator("a.cambiar-clave-btn").count() == 1,
        )
        contexto.close()

    contexto = nuevo_contexto(navegador, "compat-test_user")
    pagina = nueva_pagina(contexto, "compat-test_user")
    entrar(pagina, "test_user", inicial("test_user"))
    verificar(
        "compat: cuenta desactivada recibe el mensaje genérico",
        "Usuario o contraseña incorrectos." in mensajes(pagina),
    )
    contexto.close()


def escenario_clave_temporal(navegador):
    contexto = nuevo_contexto(navegador, "anibal")
    pagina = nueva_pagina(contexto, "anibal")
    ruta = entrar(pagina, "anibal.lopez", inicial("anibal.lopez"))
    verificar("(a) el ingreso con clave temporal cae en /cambiar-clave", ruta == CAMBIO, ruta)
    titulo = pagina.locator("h1").first.inner_text()
    verificar("(a) la pantalla dice «Cambiá tu clave temporal»", "Cambiá tu clave temporal" in titulo, titulo)
    captura(pagina, "01_ingreso_clave_temporal")

    ruta = ir(pagina, "/dashboard-comercial")
    verificar("(a) /dashboard-comercial redirige a /cambiar-clave", ruta == CAMBIO, ruta)
    verificar("(a) la redirección explica el motivo", TEMPORAL in mensajes(pagina), str(mensajes(pagina)))
    captura(pagina, "02_bloqueo_pagina")

    api = contexto.request.get(BASE + "/api/dashboard-comercial/mix", max_redirects=0)
    cuerpo = api.json() if api.status == 403 else {}
    verificar(
        "(a) la API responde 403 con el código de cambio obligatorio",
        api.status == 403 and cuerpo.get("codigo") == "cambio_clave_obligatorio",
        str(api.status),
    )
    verificar("(a) la respuesta bloqueada no trae datos", set(cuerpo) <= {"error", "codigo"}, str(sorted(cuerpo)))

    actual = inicial("anibal.lopez")
    rechazos = [
        ("clave actual incorrecta", "ERRADA-clave-123456", "C1-nueva-clave-2026", "C1-nueva-clave-2026",
         "La clave actual no es correcta."),
        ("clave corta", actual, "corta1", "corta1", "al menos 12 caracteres"),
        ("clave común", actual, "password1234", "password1234", "muy común"),
        ("igual a la actual", actual, actual, actual, "distinta de la actual"),
        ("no coincide", actual, ANIBAL_NUEVA, ANIBAL_NUEVA + "x", "Las claves no coinciden."),
        ("igual al nombre de usuario", actual, "anibal.lopez", "anibal.lopez", "nombre de usuario"),
    ]
    for etiqueta, clave_actual, nueva, repetida, esperado in rechazos:
        enviar_cambio(pagina, clave_actual, nueva, repetida)
        errores = " | ".join(errores_campo(pagina))
        verificar(
            f"(b) rechazo: {etiqueta}",
            esperado in errores and urlsplit(pagina.url).path == CAMBIO,
            errores[:160],
        )
        if etiqueta == "clave corta":
            captura(pagina, "03_rechazo_clave_corta")
        if etiqueta == "clave común":
            captura(pagina, "04_rechazo_clave_comun")

    enviar_cambio(pagina, actual, ANIBAL_NUEVA, ANIBAL_NUEVA)
    ruta = urlsplit(pagina.url).path
    verificar("(a) el cambio válido lleva al inicio de su rol", ruta == "/leads", ruta)
    verificar(
        "(a) aviso de clave actualizada y cierre de otras sesiones",
        any("Clave actualizada" in m for m in mensajes(pagina)),
        str(mensajes(pagina)),
    )
    captura(pagina, "05_cambio_ok_inicio")

    ruta = ir(pagina, "/dashboard-comercial")
    verificar("(a) queda operando: /dashboard-comercial abre", ruta == "/dashboard-comercial", ruta)
    api = contexto.request.get(BASE + "/api/dashboard-comercial/mix", max_redirects=0)
    verificar("(a) la API vuelve a aceptar la sesión", api.status not in (401, 403), str(api.status))
    contexto.close()

    contexto = nuevo_contexto(navegador, "anibal-reingreso")
    pagina = nueva_pagina(contexto, "anibal-reingreso")
    entrar(pagina, "anibal.lopez", actual)
    verificar(
        "(d) la clave vieja ya no entra",
        "Usuario o contraseña incorrectos." in mensajes(pagina),
    )
    ruta = entrar(pagina, "anibal.lopez", ANIBAL_NUEVA)
    verificar("(d) la clave nueva entra sin volver a pedir cambio", ruta == "/leads", ruta)
    contexto.close()


def escenario_menu_usuario_normal(navegador):
    contexto = nuevo_contexto(navegador, "ventas")
    pagina = nueva_pagina(contexto, "ventas")
    ruta = entrar(pagina, "ventas", inicial("ventas"))
    verificar("(e) ventas entra sin clave temporal", ruta == "/leads", ruta)
    abrir_desde_menu(pagina)
    titulo = pagina.locator("h1").first.inner_text()
    verificar(
        "(e) «Cambiar mi clave» abre el formulario normal",
        urlsplit(pagina.url).path == CAMBIO and "Cambiar mi clave" in titulo and "temporal" not in titulo,
        titulo,
    )
    captura(pagina, "06_menu_cambiar_mi_clave_ventas")
    enviar_cambio(pagina, inicial("ventas"), "password1234", "password1234")
    verificar("(e) rechaza una clave común en el cambio voluntario", "muy común" in " | ".join(errores_campo(pagina)))
    enviar_cambio(pagina, inicial("ventas"), VENTAS_NUEVA, VENTAS_NUEVA)
    verificar("(e) el cambio voluntario vuelve al inicio", urlsplit(pagina.url).path == "/leads")
    contexto.close()

    contexto = nuevo_contexto(navegador, "ventas-reingreso")
    pagina = nueva_pagina(contexto, "ventas-reingreso")
    entrar(pagina, "ventas", inicial("ventas"))
    verificar("(d) ventas: la clave vieja ya no entra", "Usuario o contraseña incorrectos." in mensajes(pagina))
    ruta = entrar(pagina, "ventas", VENTAS_NUEVA)
    verificar("(d) ventas: la clave nueva entra", ruta == "/leads", ruta)
    contexto.close()


def escenario_sesiones(navegador):
    contexto_a = nuevo_contexto(navegador, "rrhh-A")
    pagina_a = nueva_pagina(contexto_a, "rrhh-A")
    contexto_b = nuevo_contexto(navegador, "rrhh-B")
    pagina_b = nueva_pagina(contexto_b, "rrhh-B")
    verificar("(c) rrhh entra en el navegador A", entrar(pagina_a, "rrhh", inicial("rrhh")) == "/rrhh")
    verificar("(c) rrhh entra en el navegador B", entrar(pagina_b, "rrhh", inicial("rrhh")) == "/rrhh")

    abrir_desde_menu(pagina_a)
    enviar_cambio(pagina_a, inicial("rrhh"), RRHH_NUEVA, RRHH_NUEVA)
    verificar("(c) A cambia la clave y queda en su inicio", urlsplit(pagina_a.url).path == "/rrhh")

    ruta_b = ir(pagina_b, "/rrhh")
    verificar(
        "(c) B queda deslogueado en su siguiente acción",
        ruta_b == "/" and any("Tu sesión ya no es válida" in m for m in mensajes(pagina_b)),
        ruta_b,
    )
    captura(pagina_b, "07_sesion_b_cerrada")
    api_b = contexto_b.request.get(BASE + "/api/rrhh", max_redirects=0)
    verificar("(c) B: una llamada de API también responde 401", api_b.status == 401, str(api_b.status))

    ruta_a = ir(pagina_a, "/rrhh")
    verificar("(c) A sigue abierto", ruta_a == "/rrhh", ruta_a)
    api_a = contexto_a.request.get(BASE + "/api/rrhh", max_redirects=0)
    verificar("(c) A: la API sigue aceptando su sesión", api_a.status != 401, str(api_a.status))
    contexto_a.close()
    contexto_b.close()

    contexto = nuevo_contexto(navegador, "rrhh-reingreso")
    pagina = nueva_pagina(contexto, "rrhh-reingreso")
    entrar(pagina, "rrhh", inicial("rrhh"))
    verificar("(d) rrhh: la clave vieja ya no entra", "Usuario o contraseña incorrectos." in mensajes(pagina))
    ruta = entrar(pagina, "rrhh", RRHH_NUEVA)
    verificar("(d) rrhh: la clave nueva entra", ruta == "/rrhh", ruta)
    contexto.close()


def escenario_admin(navegador):
    contexto = nuevo_contexto(navegador, "admin-menu")
    pagina = nueva_pagina(contexto, "admin-menu")
    ruta = entrar(pagina, "admin", ADMIN_CLAVE)
    verificar("(f) admin entra", ruta not in (CAMBIO, "/"), ruta)
    verificar("(f) admin ve «Cambiar mi clave» en el menú", pagina.locator("a.cambiar-clave-btn").count() == 1)
    abrir_desde_menu(pagina)
    verificar("(f) admin llega al formulario sin cambiar su clave", pagina.locator("#clave_actual").count() == 1)
    captura(pagina, "08_admin_cambiar_mi_clave")
    contexto.close()


def _estado_en_texto(texto):
    """Extrae el estado HTTP de un mensaje de consola («... status of 400 (BAD REQUEST)»)."""
    partes = texto.split("status of ", 1)
    if len(partes) == 2 and partes[1][:3].isdigit():
        return int(partes[1][:3])
    return None


def informe():
    inesperadas = [r for r in RESPUESTAS if (r["status"], r["ruta"]) not in ESPERADAS]
    verificar("(g) sin 4xx/5xx inesperados en la navegación", not inesperadas, json.dumps(inesperadas)[:400])
    esperadas_consola, externas, inesperadas_consola = [], [], []
    for entrada in CONSOLA:
        ruta = urlsplit(entrada["url"]).path if entrada["url"] else ""
        estado = _estado_en_texto(entrada["texto"])
        if estado is None and not entrada["url"].startswith(BASE):
            externas.append(entrada)
        elif (estado, ruta) in ESPERADAS:
            esperadas_consola.append(entrada)
        else:
            inesperadas_consola.append(entrada)
    verificar(
        "(g) consola sin errores inesperados (solo los rechazos y bloqueos previstos)",
        not inesperadas_consola and not ERRORES_JS,
        json.dumps(inesperadas_consola + ERRORES_JS)[:400],
    )
    ok = all(v["ok"] for v in VERIFICACIONES)
    resumen = {
        "base_url": BASE,
        "verificaciones": VERIFICACIONES,
        "respuestas_4xx_5xx": RESPUESTAS,
        "consola_esperada": esperadas_consola,
        "consola_externa_ignorada": externas,
        "consola_inesperada": inesperadas_consola + ERRORES_JS,
        "resultado": "OK" if ok else "FALLA",
    }
    os.makedirs(CAPTURAS, exist_ok=True)
    with open(os.path.join(CAPTURAS, "resumen_e2e.json"), "w", encoding="utf-8") as archivo:
        json.dump(resumen, archivo, ensure_ascii=False, indent=2)
    print(f"\nRESULTADO {'OK' if ok else 'FALLA'}: {sum(v['ok'] for v in VERIFICACIONES)}/{len(VERIFICACIONES)} verificaciones")
    print(f"Mensajes de consola previstos (rechazos y bloqueos): {len(esperadas_consola)}")
    print(f"Mensajes de consola externos ignorados (CDN u otros): {len(externas)}")
    return ok


def main():
    from playwright.sync_api import sync_playwright

    preparar_datos()
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            escenario_compatibilidad(navegador)
            escenario_clave_temporal(navegador)
            escenario_menu_usuario_normal(navegador)
            escenario_sesiones(navegador)
            escenario_admin(navegador)
        finally:
            navegador.close()
    return 0 if informe() else 1


if __name__ == "__main__":
    sys.exit(main())
