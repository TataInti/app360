#!/usr/bin/env python3
"""E2E de navegador: administración de usuarios (C2 de App360).

Recorre con Chromium en es-AR: pantalla Administración > Usuarios; alta con clave temporal que se
muestra una sola vez; lista con «Debe cambiar la clave»; ingreso con la temporal, cambio obligatorio
y reingreso con la clave nueva; autodesactivación bloqueada; desactivar a otro con su sesión abierta
(cae en la siguiente acción) y reactivar sin restablecer la clave; último administrador protegido;
roles sin administración (menú, pantalla y API en 403); visor de auditoría; salida por POST y GET
/logout que no cierra la sesión; y ausencia de 4xx/5xx inesperados en red y consola.

Datos sintéticos: el usuario de prueba se llama probe-c2-<hora> y las claves son ficticias. Solo corre
sobre la base app360_c2 en 127.0.0.1. Sale con código 1 si alguna verificación falla. No imprime claves
ni las guarda: la clave temporal se tapa en las capturas antes de guardarlas.

Uso (desde la raíz del repo; la instancia C2 la levanta run_local_c2.sh):
    E2E_BASE_URL=http://127.0.0.1:5066 DATABASE_URL=<url local> SECRET_KEY=<ficticia> \
        E2E_ADMIN_PASSWORD=<ficticia> /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_usuarios_c2.py
Variables: E2E_BASE_URL, E2E_CHROMIUM, E2E_CAPTURAS (carpeta padre; las capturas van a despues/).
"""

import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import urlsplit

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5066").rstrip("/")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
CAPTURAS = os.path.join(
    os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/c2/capturas"), "despues"
)
ADMIN_CLAVE = os.environ.get("E2E_ADMIN_PASSWORD", "c2-admin-ficticia-2026")
CAMBIO = "/cambiar-clave"
TEMPORAL = "Primero cambiá tu clave temporal."
CREDENCIALES_MAL = "Usuario o contraseña incorrectos."
SESION_NO_VALIDA = "Tu sesión ya no es válida"
PROBE = "probe-c2-" + datetime.now().strftime("%H%M%S")
NUEVA = "C2-probe-clave-nueva-2026"
ULTIMO_ADMIN = "No se puede: el sistema debe conservar al menos un administrador activo."
AUTODESACTIVACION = "No podés desactivar tu propia cuenta"

# usuario, rol, activo, clave temporal (estado inicial que fija el script)
USUARIOS = [
    ("admin", "admin", True, False),
    ("gerente", "gerente", True, False),
    ("ventas", "sales", True, False),
    ("rrhh", "hr", True, False),
    ("tesoreria", "caja", True, False),
    ("direccion", "director", True, False),
    ("anibal.lopez", "sales", True, False),
    ("test_user", "sales", False, False),
]

# Respuestas 4xx que el recorrido provoca a propósito (bloqueos y rechazos).
ESPERADAS = [
    (400, re.compile(r"^/cambiar-clave$")),
    (403, re.compile(r"^/admin/usuarios$")),
    (403, re.compile(r"^/api/admin/usuarios$")),
    (403, re.compile(r"^/api/admin/usuarios/\d+/desactivar$")),
    (409, re.compile(r"^/api/admin/usuarios/\d+/desactivar$")),
    (404, re.compile(r"^/favicon\.ico$")),
]

VERIFICACIONES = []
RESPUESTAS = []
CONSOLA = []
ERRORES_JS = []
CONTEXTOS = []


def inicial(usuario):
    return ADMIN_CLAVE if usuario == "admin" else f"c2-{usuario}-ficticia-2026"


def es_esperada(estado, ruta):
    return any(estado == codigo and patron.match(ruta or "") for codigo, patron in ESPERADAS)


def verificar(nombre, condicion, detalle=""):
    VERIFICACIONES.append({"verificacion": nombre, "ok": bool(condicion), "detalle": detalle})
    marca = "OK   " if condicion else "FALLA"
    extra = f" [{detalle}]" if detalle and not condicion else ""
    print(f"{marca} {nombre}{extra}", flush=True)


def preparar_datos():
    """Fija clave, rol, activo y bandera de los usuarios sintéticos. Solo base app360_c2 local."""
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.hostname not in ("127.0.0.1", "localhost") or url.path.lstrip("/") != "app360_c2":
        raise SystemExit("El E2E de C2 solo corre sobre la base app360_c2 en 127.0.0.1.")
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
                raise SystemExit(f"Falta el usuario sintético {usuario}: correr run_local_c2.sh up.")
            cuenta.role = rol
            cuenta.active = activo
            cuenta.must_change_password = temporal
            cuenta.password_changed_at = None
            cuenta.temp_password_expires_at = None
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


def captura(pagina, nombre):
    os.makedirs(CAPTURAS, exist_ok=True)
    pagina.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"))


def ocultar_clave(pagina):
    """Tapa la clave temporal en el DOM antes de una captura. La clave no llega a los archivos."""
    pagina.evaluate(
        "() => { const el = document.getElementById('clave_temporal_nueva'); "
        "if (el) { el.textContent = '[clave oculta en la captura]'; } }"
    )


def fila_de(pagina, usuario):
    return pagina.locator("#cuerpoUsuarios tr", has=pagina.locator(f"button[data-usuario='{usuario}']"))


def esperar_lista(pagina):
    pagina.wait_for_selector("#cuerpoUsuarios tr", timeout=15000)
    pagina.wait_for_timeout(300)


def accion(pagina, usuario, verbo):
    """Pulsa Desactivar o Reactivar en la fila del usuario, confirma en el modal de la app y espera la
    respuesta del POST (no el aviso anterior). Devuelve el texto del aviso que dejó la acción."""
    boton = f"#cuerpoUsuarios button[data-usuario='{usuario}'][data-accion='{verbo}']"
    pagina.wait_for_selector(boton, timeout=10000)
    pagina.evaluate("() => { const a = document.getElementById('avisoUsuarios'); if (a) { a.textContent = ''; } }")
    pagina.click(boton)
    pagina.wait_for_selector("#app360ConfirmModal.show", timeout=5000)
    with pagina.expect_response(
        lambda respuesta: respuesta.request.method == "POST" and "/api/admin/usuarios/" in respuesta.url,
        timeout=15000,
    ):
        pagina.click("#app360ConfirmAccept")
    for _ in range(80):
        texto = pagina.inner_text("#avisoUsuarios").strip()
        if texto:
            return texto
        pagina.wait_for_timeout(100)
    return ""


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
        verificar(f"menú: {usuario} ve «Cambiar mi clave»", pagina.locator("a.cambiar-clave-btn").count() == 1)
        puede = usuario in ("admin", "gerente")
        enlace = pagina.locator("a[href='/admin/usuarios']").count()
        verificar(
            f"menú: {usuario} {'ve' if puede else 'no ve'} «Usuarios» en Administración",
            enlace == (1 if puede else 0),
            str(enlace),
        )
        contexto.close()

    contexto = nuevo_contexto(navegador, "compat-test_user")
    pagina = nueva_pagina(contexto, "compat-test_user")
    entrar(pagina, "test_user", inicial("test_user"))
    verificar("compat: cuenta desactivada recibe el mensaje genérico", CREDENCIALES_MAL in mensajes(pagina))
    contexto.close()


def escenario_alta(navegador, admin):
    """Alta con clave temporal (una vez), lista, búsqueda y primer ingreso del nuevo usuario."""
    esperar_lista(admin)
    verificar("(a) la pantalla Usuarios carga la lista", admin.locator("#cuerpoUsuarios tr").count() >= 1)
    admin.click("#btnNuevoUsuario")
    admin.fill("#altaUsuario", PROBE)
    admin.select_option("#altaRol", "sales")
    captura(admin, "01_formulario_alta")
    admin.click("#btnCrearUsuario")
    admin.wait_for_selector("#panelClaveTemporal:not(.d-none)", timeout=15000)
    clave = admin.inner_text("#clave_temporal_nueva")
    verificar("(a) la clave temporal tiene 16 caracteres", len(clave) == 16)
    verificar(
        "(a) la confirmación avisa que no se vuelve a mostrar",
        "no se vuelve a mostrar" in admin.inner_text("#panelClaveTemporal"),
    )
    ocultar_clave(admin)
    captura(admin, "02_clave_temporal_una_vez")
    admin.click("#btnCerrarClave")
    verificar("(a) al cerrar, la clave deja de estar en la pantalla", clave not in admin.content())
    verificar("(a) la clave no viaja en la URL", clave not in admin.url)

    admin.reload(wait_until="load")
    esperar_lista(admin)
    fila = fila_de(admin, PROBE).inner_text()
    verificar("(a) la lista muestra «Debe cambiar la clave»", "Debe cambiar la clave" in fila)
    captura(admin, "03_lista_debe_cambiar_clave")

    admin.fill("#buscarUsuario", PROBE)
    admin.wait_for_timeout(600)
    verificar("(a) la búsqueda por nombre filtra la lista", admin.locator("#cuerpoUsuarios tr").count() == 1)
    admin.fill("#buscarUsuario", "")
    admin.wait_for_timeout(600)

    primer = nuevo_contexto(navegador, "probe-primer-ingreso")
    pagina = nueva_pagina(primer, "probe-primer-ingreso")
    ruta = entrar(pagina, PROBE, clave)
    verificar("(b) la clave temporal entra y cae en /cambiar-clave", ruta == CAMBIO, ruta)
    ruta = ir(pagina, "/leads")
    verificar("(b) cualquier pantalla redirige a /cambiar-clave", ruta == CAMBIO, ruta)
    verificar("(b) la redirección explica el motivo", TEMPORAL in mensajes(pagina))
    captura(pagina, "04_primer_ingreso_cambio_obligatorio")
    enviar_cambio(pagina, clave, NUEVA, NUEVA)
    ruta = urlsplit(pagina.url).path
    verificar("(b) el cambio obligatorio lleva al inicio de su rol", ruta == "/leads", ruta)

    sin_cambio = nuevo_contexto(navegador, "probe-clave-vieja")
    intento = nueva_pagina(sin_cambio, "probe-clave-vieja")
    entrar(intento, PROBE, clave)
    verificar("(b) la clave temporal ya no entra después del cambio", CREDENCIALES_MAL in mensajes(intento))
    sin_cambio.close()

    admin.reload(wait_until="load")
    esperar_lista(admin)
    verificar("(b) la lista pasa a «Activo» tras el cambio", "Activo" in fila_de(admin, PROBE).inner_text())
    return clave, primer, pagina


def accion_api(pagina, usuario_id, verbo):
    """Llama a la acción en la API con la sesión de la pantalla. La pantalla no ofrece la propia cuenta (R4a)."""
    token = pagina.get_attribute('meta[name="csrf-token"]', "content")
    respuesta = pagina.request.post(
        BASE + f"/api/admin/usuarios/{usuario_id}/{verbo}", headers={"X-CSRFToken": token}, max_redirects=0
    )
    try:
        cuerpo = respuesta.json()
    except Exception:
        cuerpo = {}
    return respuesta.status, cuerpo.get("error", "")


def escenario_activar(navegador, admin, pagina_probe):
    """Autodesactivación, desactivar con sesión abierta, reactivar, y último administrador."""
    ir(admin, "/admin/usuarios")
    esperar_lista(admin)

    id_admin = int(admin.get_attribute("#pantallaUsuarios", "data-yo"))
    estado_api, texto = accion_api(admin, id_admin, "desactivar")
    deshabilitado = admin.locator("#cuerpoUsuarios button[data-usuario='admin'][data-accion='desactivar']").is_disabled()
    verificar(
        "(c) autodesactivación: el botón de su fila está deshabilitado y el servidor la rechaza con mensaje claro",
        deshabilitado and estado_api == 403 and AUTODESACTIVACION in texto,
        f"deshabilitado={deshabilitado} status={estado_api}",
    )
    captura(admin, "05_autodesactivacion_bloqueada")

    texto = accion(admin, PROBE, "desactivar")
    verificar("(c) el aviso confirma la desactivación de PROBE", "quedó desactivado" in texto, texto[:120])
    ruta = ir(pagina_probe, "/leads")
    cierre = " ".join(mensajes(pagina_probe))
    verificar(
        "(c) la sesión abierta de PROBE cae en su siguiente acción",
        ruta == "/" and SESION_NO_VALIDA in cierre,
        ruta,
    )
    captura(pagina_probe, "06_sesion_cortada_por_desactivacion")
    intento_ctx = nuevo_contexto(navegador, "probe-desactivado")
    intento = nueva_pagina(intento_ctx, "probe-desactivado")
    entrar(intento, PROBE, NUEVA)
    verificar("(c) con la cuenta desactivada, la clave nueva no entra", CREDENCIALES_MAL in mensajes(intento))
    intento_ctx.close()

    admin.reload(wait_until="load")
    esperar_lista(admin)
    texto = accion(admin, PROBE, "reactivar")
    verificar("(c) el aviso confirma la reactivación", "volvió a tener acceso" in texto, texto[:120])
    reactivado_ctx = nuevo_contexto(navegador, "probe-reactivado")
    reactivado = nueva_pagina(reactivado_ctx, "probe-reactivado")
    ruta = entrar(reactivado, PROBE, NUEVA)
    verificar("(c) reactivado entra con su clave, sin cambio obligatorio", ruta == "/leads", ruta)
    reactivado_ctx.close()

    admin.reload(wait_until="load")
    esperar_lista(admin)
    texto = accion(admin, "gerente", "desactivar")
    verificar("(d) con otro administrador activo, sí se puede desactivar a gerente", "quedó desactivado" in texto)
    estado_api, texto = accion_api(admin, id_admin, "desactivar")
    verificar("(d) desactivar al último administrador activo queda bloqueado en el servidor", estado_api == 409 and ULTIMO_ADMIN in texto, texto[:140])
    captura(admin, "07_ultimo_administrador_bloqueado")
    texto = accion(admin, "gerente", "reactivar")
    verificar("(d) gerente vuelve a quedar activo", "volvió a tener acceso" in texto)


def escenario_roles(navegador):
    for usuario in ("ventas", "rrhh"):
        contexto = nuevo_contexto(navegador, f"rol-{usuario}")
        pagina = nueva_pagina(contexto, f"rol-{usuario}")
        entrar(pagina, usuario, inicial(usuario))
        verificar(
            f"(e) {usuario} no ve «Usuarios» en el menú",
            pagina.locator("a[href='/admin/usuarios']").count() == 0,
        )
        respuesta = pagina.goto(BASE + "/admin/usuarios", wait_until="load")
        verificar(f"(e) {usuario}: la pantalla responde 403", respuesta.status == 403, str(respuesta.status))
        api = contexto.request.get(BASE + "/api/admin/usuarios", max_redirects=0)
        cuerpo = api.json() if api.status == 403 else {}
        verificar(
            f"(e) {usuario}: la API responde 403 en JSON",
            api.status == 403 and cuerpo.get("codigo") == "SIN_PERMISO",
            str(api.status),
        )
        if usuario == "ventas":
            captura(pagina, "08_ventas_sin_permiso")
        contexto.close()


def escenario_visor(admin, clave):
    ir(admin, "/admin/usuarios")
    admin.wait_for_selector("#cuerpoAuditoria tr", timeout=15000)
    filas = admin.locator("#cuerpoAuditoria tr").all_inner_texts()
    verificar(
        "(f) el visor muestra las acciones en español",
        any("Alta de usuario" in fila for fila in filas) and any("Desactivación" in fila for fila in filas),
        str(len(filas)),
    )
    verificar("(f) el visor no muestra claves", all(clave not in fila for fila in filas))
    captura(admin, "09_visor_auditoria")


def escenario_salida(navegador, admin):
    ir(admin, "/admin/usuarios")
    with admin.expect_navigation(wait_until="load"):
        admin.click("button.logout-btn")
    verificar("(g) cerrar sesión por POST lleva al login", urlsplit(admin.url).path == "/")
    verificar("(g) aviso «Sesión cerrada.»", "Sesión cerrada." in mensajes(admin))
    captura(admin, "10_salida_por_post")
    verificar("(g) tras salir, la pantalla pide ingreso", ir(admin, "/admin/usuarios") == "/")

    contexto = nuevo_contexto(navegador, "get-logout")
    pagina = nueva_pagina(contexto, "get-logout")
    entrar(pagina, "ventas", inicial("ventas"))
    pagina.goto(BASE + "/logout", wait_until="load")
    ruta = ir(pagina, "/leads")
    verificar("(g) GET /logout no cierra la sesión", ruta == "/leads", ruta)
    contexto.close()


def _estado_en_texto(texto):
    partes = texto.split("status of ", 1)
    if len(partes) == 2 and partes[1][:3].isdigit():
        return int(partes[1][:3])
    return None


def informe():
    inesperadas = [r for r in RESPUESTAS if not es_esperada(r["status"], r["ruta"])]
    verificar("(h) sin 4xx/5xx inesperados en la navegación", not inesperadas, json.dumps(inesperadas)[:400])
    esperadas_consola, externas, inesperadas_consola = [], [], []
    for entrada in CONSOLA:
        ruta = urlsplit(entrada["url"]).path if entrada["url"] else ""
        estado = _estado_en_texto(entrada["texto"])
        if estado is None and not entrada["url"].startswith(BASE):
            externas.append(entrada)
        elif estado is not None and es_esperada(estado, ruta):
            esperadas_consola.append(entrada)
        else:
            inesperadas_consola.append(entrada)
    verificar(
        "(h) consola sin errores inesperados (solo los bloqueos previstos)",
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
    print(f"Mensajes de consola previstos (bloqueos): {len(esperadas_consola)}")
    print(f"Mensajes de consola externos ignorados (CDN u otros): {len(externas)}")
    return ok


def main():
    from playwright.sync_api import sync_playwright

    preparar_datos()
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            escenario_compatibilidad(navegador)
            contexto_admin = nuevo_contexto(navegador, "admin")
            admin = nueva_pagina(contexto_admin, "admin")
            ruta = entrar(admin, "admin", ADMIN_CLAVE)
            verificar("(a) admin entra sin cambio obligatorio", ruta not in (CAMBIO, "/"), ruta)
            ir(admin, "/admin/usuarios")
            clave, contexto_probe, pagina_probe = escenario_alta(navegador, admin)
            escenario_activar(navegador, admin, pagina_probe)
            escenario_roles(navegador)
            escenario_visor(admin, clave)
            escenario_salida(navegador, admin)
        finally:
            navegador.close()
    return 0 if informe() else 1


if __name__ == "__main__":
    sys.exit(main())
