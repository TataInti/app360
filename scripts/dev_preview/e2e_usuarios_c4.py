"""E2E de navegador de Administración > Usuarios (C4): bloqueo por cuenta, desbloqueo y visor de auditoría.

Playwright con Chromium, locale es-AR. Datos sintéticos rotulados «c4e.»; solo corre sobre la base
app360_c4 en 127.0.0.1. Sale con código 1 si alguna verificación falla.

Uso (desde la raíz del worktree):
    E2E_BASE_URL=http://127.0.0.1:5082 DATABASE_URL=<url local a app360_c4> SECRET_KEY=<ficticia> \
        E2E_ADMIN_PASSWORD=<ficticia> /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_usuarios_c4.py
Variables: E2E_BASE_URL, E2E_CHROMIUM, E2E_CAPTURAS (carpeta padre; las capturas van a despues/).
Las claves de prueba se fijan en la base sintética y no se imprimen ni van a las capturas.
"""

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5082").rstrip("/")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
CAPTURAS = os.path.join(os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/c4/capturas"), "despues")
ADMIN_CLAVE = os.environ.get("E2E_ADMIN_PASSWORD", "")
BLOQUEO = "c4e.bloqueo"
CLAVE_BLOQUEO = "c4e-bloqueo-ficticia-2026"
SINTETICO = "c4e.sintetico"
MENSAJE = "Usuario o contraseña incorrectos."
ZONA = timezone(timedelta(hours=-3))
ESPERADAS = [
    (403, re.compile(r"^/admin/usuarios/auditoria$")),
    (403, re.compile(r"^/api/admin/usuarios/auditoria$")),
    (404, re.compile(r"^/favicon\.ico$")),
]
VERIFICACIONES = []
RESPUESTAS = []
CONSOLA = []


def verificar(nombre, condicion, detalle=""):
    VERIFICACIONES.append({"verificacion": nombre, "ok": bool(condicion), "detalle": detalle})
    marca = "OK   " if condicion else "FALLA"
    extra = f" [{detalle}]" if detalle and not condicion else ""
    print(f"{marca} {nombre}{extra}", flush=True)


def preparar_datos():
    """Fija los datos sintéticos de la base app360_c4 (solo local). Devuelve la app para la base."""
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.hostname not in ("127.0.0.1", "localhost") or url.path.lstrip("/") != "app360_c4":
        raise SystemExit("El E2E de C4 solo corre sobre la base app360_c4 en 127.0.0.1.")
    if not ADMIN_CLAVE:
        raise SystemExit("Falta E2E_ADMIN_PASSWORD (clave ficticia del administrador de la instancia).")
    sys.path.insert(0, RAIZ)
    os.chdir(RAIZ)
    from app import create_app
    from models import db
    from models.core.user import User
    from models.core.user_audit_log import UserAuditLog

    app = create_app()
    with app.app_context():
        for usuario, rol in (("gerente", "gerente"), ("ventas", "sales"), ("rrhh", "hr")):
            cuenta = User.query.filter_by(username=usuario).one_or_none()
            if cuenta is None:
                raise SystemExit(f"Falta el usuario sintético {usuario}: correr run_local_c4.sh up.")
            cuenta.role, cuenta.active, cuenta.must_change_password = rol, True, False
            cuenta.temp_password_expires_at = None
            cuenta.set_password(f"c4-{usuario}-ficticia-2026")
            cuenta.failed_login_count, cuenta.failed_login_window_start, cuenta.locked_until = 0, None, None
        cuenta = User.query.filter_by(username=BLOQUEO).one_or_none()
        if cuenta is None:
            cuenta = User(username=BLOQUEO, role="sales", active=True)
            db.session.add(cuenta)
        cuenta.role, cuenta.active, cuenta.must_change_password = "sales", True, False
        cuenta.temp_password_expires_at, cuenta.deactivated_at = None, None
        cuenta.set_password(CLAVE_BLOQUEO)
        cuenta.failed_login_count, cuenta.failed_login_window_start, cuenta.locked_until = 0, None, None
        UserAuditLog.query.filter_by(actor_username=SINTETICO).delete()
        ahora = datetime.now(timezone.utc)
        for minutos in range(55):
            db.session.add(
                UserAuditLog(
                    created_at=ahora - timedelta(minutes=minutos),
                    actor_username=SINTETICO,
                    accion="user_role_changed",
                    target_username="c4e.objetivo",
                    detalle={"de": "sales", "a": "hr"},
                    ip="10.0.0.5",
                )
            )
        db.session.commit()
    return app


def nuevo_contexto(navegador, etiqueta):
    contexto = navegador.new_context(locale="es-AR", viewport={"width": 1280, "height": 900})

    def registrar(respuesta):
        if respuesta.status >= 400:
            RESPUESTAS.append((etiqueta, respuesta.request.method, respuesta.status, urlsplit(respuesta.url).path))

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
    pagina.screenshot(path=os.path.join(CAPTURAS, f"{nombre}.png"))


def ingresar(pagina, usuario, clave):
    pagina.goto(BASE + "/")
    pagina.fill("#username", usuario)
    pagina.fill("#password", clave)
    with pagina.expect_navigation():
        pagina.click("button.btn-login")


def sigue_en_login(pagina):
    return pagina.locator("#password").count() > 0


def recorrido_bloqueo(navegador):
    """10 fallos → bloqueo, la clave correcta sigue rechazada con el mismo mensaje y la pantalla no lo revela."""
    pagina = nueva_pagina(nuevo_contexto(navegador, "anonimo"), "anonimo")
    mensajes = 0
    for intento in range(1, 11):
        ingresar(pagina, BLOQUEO, f"c4e-mal-{intento}-ficticia")
        mensajes += MENSAJE in pagina.content()
    verificar("10 fallos muestran el mensaje genérico de siempre", mensajes == 10, f"mensajes={mensajes}")
    captura(pagina, "01_anonimo_diez_fallos")
    ingresar(pagina, BLOQUEO, CLAVE_BLOQUEO)
    contenido = pagina.content()
    verificar("con la clave correcta sigue rechazado con el mismo mensaje", MENSAJE in contenido and sigue_en_login(pagina))
    verificar("la pantalla no revela el bloqueo", "bloque" not in contenido.lower())
    captura(pagina, "02_anonimo_clave_correcta_rechazada")
    pagina.context.close()


def recorrido_admin_desbloqueo(navegador):
    contexto = nuevo_contexto(navegador, "admin")
    pagina = nueva_pagina(contexto, "admin")
    ingresar(pagina, "admin", ADMIN_CLAVE)
    pagina.goto(BASE + "/admin/usuarios")
    pagina.wait_for_selector("#cargandoUsuarios.d-none", state="attached")
    fila = pagina.locator("#cuerpoUsuarios tr", has_text=BLOQUEO)
    verificar("la lista muestra «Bloqueada hasta hh:mm»", bool(re.search(r"Bloqueada hasta \d{2}:\d{2}", fila.inner_text())))
    captura(pagina, "03_admin_lista_bloqueada")
    with pagina.expect_response(lambda r: "estado=bloqueada" in r.url):
        pagina.select_option("#filtroEstado", "bloqueada")
    pagina.wait_for_timeout(300)
    filas = pagina.locator("#cuerpoUsuarios tr")
    nombres = [filas.nth(i).inner_text().split("\t")[0].split("\n")[0] for i in range(filas.count())]
    verificar("el filtro «Bloqueadas» deja solo las cuentas bloqueadas", filas.count() == 1 and BLOQUEO in nombres[0], f"filas={nombres}")
    captura(pagina, "04_admin_filtro_bloqueadas")
    pagina.locator("#cuerpoUsuarios button[data-accion='desbloquear']").first.click()
    pagina.wait_for_selector("#app360ConfirmAccept", state="visible")
    with pagina.expect_response(lambda r: r.url.endswith("/desbloquear") and r.request.method == "POST") as respuesta:
        pagina.click("#app360ConfirmAccept")
    verificar("desbloquear responde 200", respuesta.value.status == 200, f"status={respuesta.value.status}")
    pagina.wait_for_timeout(400)
    verificar("el aviso confirma el desbloqueo", "quedó desbloqueada" in pagina.locator("#avisoUsuarios").inner_text())
    verificar("sin cuentas bloqueadas tras el desbloqueo", pagina.locator("#estadoVacioUsuarios").is_visible())
    captura(pagina, "05_admin_desbloqueada")

    usuario = nueva_pagina(nuevo_contexto(navegador, "usuario"), "usuario")
    ingresar(usuario, BLOQUEO, CLAVE_BLOQUEO)
    verificar("tras el desbloqueo el usuario entra con su clave", not sigue_en_login(usuario))
    captura(usuario, "06_usuario_entra")
    usuario.context.close()
    return pagina


def visor_fila_textos(pagina):
    return [pagina.locator("#cuerpoAuditoriaCompleta tr").nth(i).inner_text() for i in range(pagina.locator("#cuerpoAuditoriaCompleta tr").count())]


def recorrido_visor(pagina):
    pagina.goto(BASE + "/admin/usuarios")
    pagina.click("#enlaceAuditoriaCompleta")
    pagina.wait_for_url("**/admin/usuarios/auditoria")
    pagina.wait_for_selector("#cargandoAuditoria.d-none", state="attached")
    verificar("«Ver auditoría completa» abre el visor", "Auditoría de usuarios" in pagina.content())
    with pagina.expect_response(lambda r: "q=c4e.bloqueo" in r.url):
        pagina.fill("#filtroUsuarioAuditoria", BLOQUEO)
    pagina.wait_for_timeout(300)
    textos = " | ".join(visor_fila_textos(pagina))
    verificar("el visor muestra login fallidos, cuenta bloqueada y desbloqueo", all(
        t in textos for t in ("Login fallido", "Desbloqueo", "Login correcto", "Motivo: clave incorrecta", "Motivo: cuenta bloqueada")
    ), textos[:300])
    verificar("el detalle es legible (sin JSON)", "{" not in textos)
    captura(pagina, "07_visor_por_usuario")
    with pagina.expect_response(lambda r: "accion=login_failed" in r.url):
        pagina.select_option("#filtroAccionAuditoria", "login_failed")
    pagina.wait_for_timeout(300)
    acciones = {fila.split("\t")[2] if "\t" in fila else "" for fila in visor_fila_textos(pagina)}
    filas = pagina.locator("#cuerpoAuditoriaCompleta tr")
    columnas_accion = [filas.nth(i).locator("td").nth(2).inner_text() for i in range(filas.count())]
    verificar("el filtro por acción deja solo login fallidos", filas.count() > 0 and set(columnas_accion) == {"Login fallido"}, f"acciones={set(columnas_accion)}")
    hoy = datetime.now(ZONA).date()
    with pagina.expect_response(lambda r: "desde=" in r.url):
        pagina.fill("#filtroDesdeAuditoria", hoy.isoformat())
        pagina.press("#filtroDesdeAuditoria", "Tab")
    pagina.wait_for_timeout(300)
    verificar("el rango de fechas con hoy mantiene las filas", pagina.locator("#cuerpoAuditoriaCompleta tr").count() > 0)
    manana = (hoy + timedelta(days=1)).isoformat()
    with pagina.expect_response(lambda r: "desde=" in r.url):
        pagina.fill("#filtroDesdeAuditoria", manana)
        pagina.press("#filtroDesdeAuditoria", "Tab")
    pagina.wait_for_timeout(300)
    verificar("un rango sin acciones muestra el estado vacío afirmativo", pagina.locator("#estadoVacioAuditoria").is_visible() and "Ninguna acción coincide" in pagina.locator("#tituloVacioAuditoria").inner_text())
    captura(pagina, "08_visor_estado_vacio")
    pagina.click("#btnLimpiarAuditoria")
    pagina.wait_for_timeout(300)
    with pagina.expect_response(lambda r: f"q={SINTETICO}" in r.url):
        pagina.fill("#filtroUsuarioAuditoria", SINTETICO)
    pagina.wait_for_timeout(300)
    verificar("55 acciones se paginan de 50 en 50", "Página 1 de 2" in pagina.locator("#textoPaginaAuditoria").inner_text(), pagina.locator("#textoPaginaAuditoria").inner_text())
    captura(pagina, "09_visor_pagina_1")
    with pagina.expect_response(lambda r: "pagina=2" in r.url):
        pagina.click("#btnPaginaSiguiente")
    pagina.wait_for_timeout(300)
    verificar("la página 2 trae las 5 restantes", pagina.locator("#cuerpoAuditoriaCompleta tr").count() == 5 and "Página 2 de 2" in pagina.locator("#textoPaginaAuditoria").inner_text())
    captura(pagina, "10_visor_pagina_2")
    with pagina.expect_response(lambda r: "q=c4e.nadie.inexistente" in r.url):
        pagina.fill("#filtroUsuarioAuditoria", "c4e.nadie.inexistente")
    pagina.wait_for_timeout(300)
    verificar("un usuario sin acciones muestra el estado vacío", pagina.locator("#estadoVacioAuditoria").is_visible())
    pagina.fill("#filtroUsuarioAuditoria", "<b>c4e</b>")
    pagina.wait_for_timeout(400)
    verificar("el HTML del texto de búsqueda no se interpreta", pagina.locator("#cuerpoAuditoriaCompleta b").count() == 0)


def recorrido_permisos(navegador):
    for usuario in ("ventas", "rrhh"):
        contexto = nuevo_contexto(navegador, usuario)
        pagina = nueva_pagina(contexto, usuario)
        ingresar(pagina, usuario, f"c4-{usuario}-ficticia-2026")
        respuesta = pagina.goto(BASE + "/admin/usuarios/auditoria")
        verificar(f"{usuario} recibe 403 en la pantalla del visor", respuesta.status == 403, f"status={respuesta.status}")
        api = pagina.request.get(BASE + "/api/admin/usuarios/auditoria", max_redirects=0)
        verificar(f"{usuario} recibe 403 en la API del visor", api.status == 403, f"status={api.status}")
        contexto.close()


def main():
    preparar_datos()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        recorrido_bloqueo(navegador)
        pagina_admin = recorrido_admin_desbloqueo(navegador)
        recorrido_visor(pagina_admin)
        recorrido_permisos(navegador)
        navegador.close()

    inesperadas = [r for r in RESPUESTAS if not any(r[2] == c and p.match(r[3] or "") for c, p in ESPERADAS)]
    verificar("sin respuestas 4xx/5xx inesperadas", not inesperadas, str(inesperadas[:5]))
    errores_consola = [c for c in CONSOLA if "status of 403" not in c[1] and "status of 404" not in c[1] and "status of 401" not in c[1]]
    verificar("consola sin errores inesperados", not errores_consola, str(errores_consola[:3]))
    fallas = [v for v in VERIFICACIONES if not v["ok"]]
    print(f"RESUMEN: {len(VERIFICACIONES) - len(fallas)}/{len(VERIFICACIONES)} verificaciones OK. Capturas en {CAPTURAS}")
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
