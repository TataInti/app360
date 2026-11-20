"""E2E de navegador de Administración > Usuarios (C5): correo, enlace de recuperación, revocación y canje.

Playwright con Chromium, locale es-AR. Datos sintéticos rotulados «c5e.»; solo corre sobre la base
app360_c5 en 127.0.0.1. Sale con código 1 si alguna verificación falla. Las capturas van a <E2E_CAPTURAS>/despues/.
Los enlaces y claves se leen en memoria y se enmascaran en las capturas; no se imprimen.

Uso (desde la raíz del worktree, con la instancia C5 levantada y la app reiniciada):
    E2E_BASE_URL=http://127.0.0.1:5087 DATABASE_URL=<url local a app360_c5> SECRET_KEY=<ficticia> \\
        E2E_ADMIN_PASSWORD=<ficticia> /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_usuarios_c5.py
Variables: E2E_BASE_URL, E2E_CHROMIUM, E2E_CAPTURAS (carpeta padre; las capturas van a despues/).
La cuenta «admin» es la de la instancia. El E2E reescribe claves de usuarios c5e.* y ventas, rrhh y gerente: solo contra su base.
"""

import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5087").rstrip("/")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.path.join(os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/c5/capturas"), "despues")
ADMIN = "admin"
ADMIN_CLAVE = os.environ.get("E2E_ADMIN_PASSWORD", "")
DESTINO = "c5e.destino"
ABIERTA = "c5e.abierta"
REVOCAR = "c5e.revocar"
VENCE = "c5e.vence"
CORREO = "c5e.destino@ejemplo.test"
CLAVE_SINTETICA = "c5e-ficticia-2026-clave"
CLAVE_NUEVA = "C5e-nueva-clave-2026-segura"
MENSAJE_GENERICO = "No pudimos usar este enlace"
ESPERADAS = [
    (403, re.compile(r"^/api/admin/usuarios/\d+/(correo|recuperacion|recuperacion/\d+/revocar)$")),
    (403, re.compile(r"^/admin/usuarios(/auditoria)?$")),
    (403, re.compile(r"^/api/admin/usuarios/auditoria$")),
    (400, re.compile(r"^/recuperar-clave$")),
    (429, re.compile(r"^/recuperar-clave$")),
    (404, re.compile(r"^/favicon\.ico$")),
]
VERIFICACIONES = []
RESPUESTAS = []
CONSOLA = []
LOGINS = []
APP = None


def verificar(nombre, condicion, detalle=""):
    VERIFICACIONES.append({"verificacion": nombre, "ok": bool(condicion), "detalle": detalle})
    marca = "OK   " if condicion else "FALLA"
    extra = f" [{detalle}]" if detalle and not condicion else ""
    print(f"{marca} {nombre}{extra}", flush=True)


def esperar_ventana_login():
    """El login web cuenta 10 peticiones por minuto (blueprint auth). Cada login son 2: como máximo 4 por minuto."""
    ahora = time.monotonic()
    recientes = [t for t in LOGINS if ahora - t < 62]
    if len(recientes) >= 4:
        time.sleep(max(1.0, 62 - (ahora - recientes[0])))
    LOGINS.append(time.monotonic())


def preparar_datos():
    """Fija los datos sintéticos de la base app360_c5 (solo local). Devuelve la app para la base."""
    global APP
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.hostname not in ("127.0.0.1", "localhost") or url.path.lstrip("/") != "app360_c5":
        raise SystemExit("El E2E de C5 solo corre sobre la base app360_c5 en 127.0.0.1.")
    if not ADMIN_CLAVE:
        raise SystemExit("Falta E2E_ADMIN_PASSWORD (clave ficticia del administrador de la instancia).")
    sys.path.insert(0, RAIZ)
    os.chdir(RAIZ)
    from app import create_app
    from models import db
    from models.core.user import User
    from models.core.user_recovery_token import UserRecoveryToken

    APP = create_app()
    with APP.app_context():
        for nombre, rol in (("gerente", "gerente"), ("ventas", "sales"), ("rrhh", "hr")):
            cuenta = User.query.filter_by(username=nombre).one_or_none()
            if cuenta is None:
                raise SystemExit(f"Falta el usuario sintético {nombre}: correr run_local_c5.sh up.")
            cuenta.role, cuenta.active, cuenta.must_change_password = rol, True, False
            cuenta.temp_password_expires_at = None
            cuenta.set_password(f"c5-{nombre}-ficticia-2026")
            cuenta.failed_login_count, cuenta.failed_login_window_start, cuenta.locked_until = 0, None, None
        for nombre in (DESTINO, ABIERTA, REVOCAR, VENCE):
            cuenta = User.query.filter_by(username=nombre).one_or_none()
            if cuenta is None:
                cuenta = User(username=nombre, role="sales", active=True)
                db.session.add(cuenta)
            cuenta.role, cuenta.active, cuenta.must_change_password = "sales", True, False
            cuenta.temp_password_expires_at, cuenta.deactivated_at = None, None
            cuenta.failed_login_count, cuenta.failed_login_window_start, cuenta.locked_until = 0, None, None
            cuenta.email = None
            cuenta.set_password(CLAVE_SINTETICA)
            db.session.flush()
            UserRecoveryToken.query.filter_by(user_id=cuenta.id).delete()
        db.session.commit()
    return APP


def vencer_enlaces_de(nombre):
    """Fuerza el vencimiento en la base de los enlaces vigentes de la cuenta (prueba de vencimiento)."""
    from models import db
    from models.core.user import User
    from models.core.user_recovery_token import UserRecoveryToken

    with APP.app_context():
        uid = User.query.filter_by(username=nombre).one().id
        for fila in UserRecoveryToken.query.filter_by(user_id=uid, used_at=None, revoked_at=None).all():
            fila.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.session.commit()


def nuevo_contexto(navegador, etiqueta):
    contexto = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})

    def registrar(respuesta):
        if respuesta.status >= 400:
            from urllib.parse import urlsplit as _partir

            RESPUESTAS.append((etiqueta, respuesta.request.method, respuesta.status, _partir(respuesta.url).path))

    contexto.on("response", registrar)
    return contexto


def nueva_pagina(contexto, etiqueta):
    pagina = contexto.new_page()

    def consola(mensaje):
        if mensaje.type == "error":
            CONSOLA.append((etiqueta, mensaje.text))

    pagina.on("console", consola)
    return pagina


def captura(pagina, nombre):
    os.makedirs(CAPTURAS, exist_ok=True)
    pagina.screenshot(path=os.path.join(CAPTURAS, f"{nombre}.png"), full_page=True)


def enmascarar_enlace(pagina):
    """Oculta el token en la pantalla antes de capturar (el enlace es sintético, pero no se publica)."""
    pagina.evaluate(
        "() => { const c = document.getElementById('enlace_recuperacion_nuevo'); if (c && c.textContent.includes('#')) c.textContent = c.textContent.split('#')[0] + '#[oculto]'; }"
    )


def ingresar(pagina, usuario, clave):
    esperar_ventana_login()
    pagina.goto(BASE + "/")
    pagina.fill("#username", usuario)
    pagina.fill("#password", clave)
    with pagina.expect_navigation():
        pagina.click("button.btn-login")
    pagina.wait_for_load_state()


def fila(pagina, usuario):
    return pagina.locator("#cuerpoUsuarios tr", has=pagina.locator("td.fw-semibold", has_text=usuario))


def esperar_aviso(pagina, texto):
    try:
        pagina.locator("#avisoUsuarios").filter(has_text=texto).wait_for(timeout=15000)
    except Exception:
        print("DIAG aviso visible:", pagina.locator("#avisoUsuarios").inner_text()[:160], flush=True)
        raise


def enlace_de_panel(pagina):
    texto = pagina.locator("#enlace_recuperacion_nuevo").inner_text()
    return texto


def esperar_en_fila(pagina, usuario, texto, segundos=15):
    """Espera a que la fila del usuario muestre el texto: la lista se recarga después del aviso."""
    try:
        fila(pagina, usuario).filter(has_text=texto).first.wait_for(timeout=segundos * 1000)
        return True
    except Exception:
        return False


def emitir_enlace(pagina, usuario, ttl=None):
    """Admin: genera el enlace por la fila, lo lee en memoria y devuelve (token, texto_del_panel)."""
    fila(pagina, usuario).locator("button[data-accion='recuperacion']").click()
    modal = pagina.locator("#modalRecuperacion")
    modal.wait_for(state="visible")
    if ttl is not None:
        pagina.fill("#modalRecuperacionTtl", str(ttl))
    with pagina.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/recuperacion")) as info:
        pagina.click("#btnGenerarRecuperacion")
    respuesta = info.value
    verificar(f"emitir enlace para {usuario} responde 201", respuesta.status == 201, str(respuesta.status))
    pagina.locator("#panelEnlaceRecuperacion").wait_for(state="visible")
    pagina.locator("#modalRecuperacion").wait_for(state="hidden", timeout=15000)
    texto = enlace_de_panel(pagina)
    token = texto.split("#", 1)[1] if "#" in texto else ""
    verificar(f"el enlace de {usuario} apunta a la dirección pública configurada", texto.startswith(BASE + "/recuperar-clave#"))
    return token, texto


def canjear(contexto, etiqueta, token, clave):
    """Anónimo: abre el enlace (en el fragmento), define la clave y envía el formulario."""
    pagina = nueva_pagina(contexto, etiqueta)
    pagina.goto(BASE + "/recuperar-clave#" + token)
    pagina.locator("#formRecuperar").wait_for(state="visible", timeout=15000)
    sin_fragmento = "#" not in pagina.url
    pagina.fill("#new_password", clave)
    pagina.fill("#confirm", clave)
    with pagina.expect_response(lambda r: r.request.method == "POST" and "/recuperar-clave" in r.url) as info:
        pagina.click("#formRecuperar button[type=submit]")
    pagina.wait_for_load_state()
    return pagina, info.value.status, sin_fragmento


def main():
    preparar_datos()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            admin_ctx = nuevo_contexto(navegador, "admin")
            pa = nueva_pagina(admin_ctx, "admin")
            ingresar(pa, ADMIN, ADMIN_CLAVE)
            pa.goto(BASE + "/admin/usuarios")
            pa.locator("#cuerpoUsuarios tr").first.wait_for(timeout=15000)
            captura(pa, "01_pantalla_usuarios")
            verificar("la pantalla de usuarios carga para el administrador", "/admin/usuarios" in pa.url)

            # 1. Correo de contacto cargado por el administrador
            fila(pa, DESTINO).locator("button[data-accion='correo']").click()
            pa.locator("#modalCorreo").wait_for(state="visible")
            pa.fill("#modalCorreoInput", CORREO)
            with pa.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/correo")) as info:
                pa.click("#btnGuardarCorreo")
            verificar("guardar correo responde 200", info.value.status == 200, str(info.value.status))
            esperar_aviso(pa, "No se envió ningún correo")
            listo = esperar_en_fila(pa, DESTINO, CORREO)
            verificar("el correo se ve en la lista", listo and fila(pa, DESTINO).locator("td").nth(1).inner_text() == CORREO)
            captura(pa, "02_correo_en_lista")

            # 2. Enlace de recuperación, una sola vez, con botón Copiar y aviso
            token, _texto = emitir_enlace(pa, DESTINO)
            verificar("el panel avisa que el enlace no se vuelve a mostrar", pa.locator("#panelEnlaceRecuperacion").get_by_text("no se vuelve a mostrar").first.is_visible())
            verificar("el panel ofrece el botón Copiar", pa.locator("#btnCopiarEnlace").is_visible())
            verificar("la fila muestra el enlace vigente", "Enlace de recuperación vigente hasta" in fila(pa, DESTINO).inner_text())
            enmascarar_enlace(pa)
            captura(pa, "03_enlace_emitido_mascarado")

            # 3. Anónimo en otro contexto: define su clave y entra sin pasar por el cambio de clave temporal
            anonimo = nuevo_contexto(navegador, "anonimo")
            pc, estado, sin_fragmento = canjear(anonimo, "anonimo", token, CLAVE_NUEVA)
            verificar("el enlace se abre sin el token en la barra (fragmento borrado)", sin_fragmento)
            verificar("el canje responde 302 (redirección al ingreso)", estado == 302, str(estado))
            verificar("aviso afirmativo tras el canje", pc.locator(".alert-success").filter(has_text="Listo").count() == 1)
            captura(pc, "04_canje_ok_aviso_ingreso")
            entrante = nueva_pagina(anonimo, "anonimo")
            ingresar(entrante, DESTINO, CLAVE_NUEVA)
            verificar("entra con la clave nueva sin caer en cambiar-clave", "cambiar-clave" not in entrante.url and "/" != urlsplit(entrante.url).path)
            captura(entrante, "05_ingreso_con_clave_nueva")

            # 4. El mismo enlace por segunda vez: mensaje genérico
            segundo, estado2, _ = canjear(nuevo_contexto(navegador, "anonimo2"), "anonimo2", token, CLAVE_NUEVA)
            verificar("el mismo enlace otra vez responde 400", estado2 == 400, str(estado2))
            verificar("muestra el mensaje genérico", MENSAJE_GENERICO in segundo.locator("#mensajeRecuperacion").inner_text())
            captura(segundo, "06_segundo_uso_generico")

            # 5. Revocado por el administrador: ya no sirve
            token_r, _ = emitir_enlace(pa, REVOCAR)
            fila(pa, REVOCAR).locator("button[data-accion='revocar']").click()
            pa.locator("#app360ConfirmAccept").wait_for(state="visible")
            with pa.expect_response(lambda r: r.request.method == "POST" and r.url.endswith("/revocar")) as info_rev:
                pa.locator("#app360ConfirmAccept").click()
            print("DIAG revocar HTTP", info_rev.value.status, flush=True)
            esperar_aviso(pa, "Se revocó el enlace")
            verificar("tras revocar, la cuenta queda sin clave utilizable (estado pendiente)", esperar_en_fila(pa, REVOCAR, "Recuperación pendiente"))
            captura(pa, "07_revocado_pendiente")
            revocado, estado3, _ = canjear(nuevo_contexto(navegador, "anonimo3"), "anonimo3", token_r, CLAVE_NUEVA)
            verificar("un enlace revocado responde 400 genérico", estado3 == 400 and MENSAJE_GENERICO in revocado.locator("#mensajeRecuperacion").inner_text(), str(estado3))

            # 6. Vencido con el vencimiento forzado en la base: mismo mensaje
            token_v, _ = emitir_enlace(pa, VENCE, ttl=5)
            vencer_enlaces_de(VENCE)
            vencido, estado4, _ = canjear(nuevo_contexto(navegador, "anonimo4"), "anonimo4", token_v, CLAVE_NUEVA)
            verificar("un enlace vencido responde 400 con el mismo mensaje", estado4 == 400 and MENSAJE_GENERICO in vencido.locator("#mensajeRecuperacion").inner_text(), str(estado4))
            captura(vencido, "08_vencido_generico")

            # 7. Sesión abierta antes de la emisión: se cierra en la siguiente acción
            ctx_abierta = nuevo_contexto(navegador, "abierta")
            pab = nueva_pagina(ctx_abierta, "abierta")
            ingresar(pab, ABIERTA, CLAVE_SINTETICA)
            pab.goto(BASE + "/")
            verificar("la sesión de ABIERTA está activa antes de la emisión", "/" != urlsplit(pab.url).path or "#username" not in pab.content())
            emitir_enlace(pa, ABIERTA)
            pab.goto(BASE + "/")
            verificar("la sesión abierta antes de la emisión queda cerrada (vuelve el ingreso)", pab.locator("#username").count() == 1)
            captura(pab, "09_sesion_cerrada_por_emision")

            # 8. Ventas y RRHH reciben 403 en las acciones nuevas
            for usuario in ("ventas", "rrhh"):
                ctx_rol = nuevo_contexto(navegador, usuario)
                pr = nueva_pagina(ctx_rol, usuario)
                ingresar(pr, usuario, f"c5-{usuario}-ficticia-2026")
                pr.goto(BASE + "/")
                token_csrf = pr.evaluate("() => document.querySelector('meta[name=\"csrf-token\"]')?.content || ''")
                cabecera = {"X-CSRFToken": token_csrf, "Content-Type": "application/json", "Accept": "application/json"}
                destino_id = fila_id = None
                for accion, ruta, cuerpo in (
                    ("correo", "/api/admin/usuarios/1/correo", {"email": "x@ejemplo.test"}),
                    ("recuperacion", "/api/admin/usuarios/1/recuperacion", {"ttl": 30}),
                ):
                    r = ctx_rol.request.post(BASE + ruta, data=cuerpo, headers=cabecera, max_redirects=0)
                    verificar(f"{usuario} recibe 403 en {accion}", r.status == 403, str(r.status))
                r = ctx_rol.request.post(BASE + "/api/admin/usuarios/1/recuperacion/1/revocar", headers=cabecera, max_redirects=0)
                verificar(f"{usuario} recibe 403 al revocar", r.status == 403, str(r.status))

            # 9. Humo de las pantallas del menú con administrador, sin errores de consola
            for ruta in ("/admin/usuarios", "/admin/usuarios/auditoria", "/admin/accesos", "/cambiar-clave"):
                r = pa.request.get(BASE + ruta, max_redirects=0)
                verificar(f"pantalla {ruta} responde 200 al administrador", r.status == 200, str(r.status))
            captura(pa, "10_humo_admin_usuarios")
        finally:
            navegador.close()

    errores_consola = [
        (etiqueta, texto)
        for etiqueta, texto in CONSOLA
        if not texto.startswith("Failed to load resource")
    ]
    verificar("sin errores de consola de JavaScript", not errores_consola, str(errores_consola[:3]))
    inesperadas = [
        (etiqueta, metodo, estado, ruta)
        for etiqueta, metodo, estado, ruta in RESPUESTAS
        if not any(estado == e and rx.match(ruta) for e, rx in ESPERADAS)
    ]
    verificar("sin 4xx/5xx inesperados (solo los 400/403/429 de las pruebas negativas)", not inesperadas, str(inesperadas[:5]))
    fallas = [v for v in VERIFICACIONES if not v["ok"]]
    print(f"RESUMEN: {len(VERIFICACIONES) - len(fallas)} de {len(VERIFICACIONES)} verificaciones OK")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
