"""E2E de navegador de Administración > Usuarios (C3): cambio de rol, restablecimiento de clave y clave
temporal vencida. Playwright con Chromium, locale es-AR. Datos sintéticos rotulados PROBE; solo corre
sobre la base app360_c3 en 127.0.0.1. Sale con código 1 si alguna verificación falla.

Uso (desde la raíz del worktree):
    E2E_BASE_URL=http://127.0.0.1:5079 DATABASE_URL=<url local a app360_c3> SECRET_KEY=<ficticia> \
        E2E_ADMIN_PASSWORD=<ficticia> /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_usuarios_c3.py
Variables: E2E_BASE_URL, E2E_CHROMIUM, E2E_CAPTURAS (carpeta padre; las capturas van a despues/).
Las claves temporales se leen del DOM y no se imprimen ni van a las capturas de la pantalla de clave.
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5079").rstrip("/")
CHROMIUM = os.environ.get(
    "E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome"
)
CAPTURAS = os.path.join(os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/c3/capturas"), "despues")
ADMIN_CLAVE = os.environ.get("E2E_ADMIN_PASSWORD", "")
NUEVA = "PROBE-clave-nueva-e2e-2026"
CAMBIO = "/cambiar-clave"
MENSAJE_LOGIN = "Usuario o contraseña incorrectos."
PATRON_CLAVE_TEMPORAL = re.compile(r"[abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789]{16}")

# usuario, rol, activo, bandera de cambio (estado inicial que fija el script)
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

# Respuestas 4xx que el recorrido provoca a propósito (bloqueos por rol, sesión y regla de negocio).
ESPERADAS = [
    (401, re.compile(r"^/api/admin/usuarios/\d+/rol$")),
    (403, re.compile(r"^/api/admin/usuarios/\d+/rol$")),
    (403, re.compile(r"^/api/admin/usuarios/\d+/restablecer-clave$")),
    (403, re.compile(r"^/api/admin/usuarios/\d+/desactivar$")),
    (403, re.compile(r"^/admin/usuarios$")),
    (409, re.compile(r"^/api/admin/usuarios/\d+/restablecer-clave$")),
    (404, re.compile(r"^/favicon\.ico$")),
]

VERIFICACIONES = []
RESPUESTAS = []
CONSOLA = []
ERRORES_JS = []
CONTEXTOS = []
APP = None


def inicial(usuario):
    return ADMIN_CLAVE if usuario == "admin" else f"c3-{usuario}-ficticia-2026"


def es_esperada(estado, ruta):
    return any(estado == codigo and patron.match(ruta or "") for codigo, patron in ESPERADAS)


def verificar(nombre, condicion, detalle=""):
    VERIFICACIONES.append({"verificacion": nombre, "ok": bool(condicion), "detalle": detalle})
    marca = "OK   " if condicion else "FALLA"
    extra = f" [{detalle}]" if detalle and not condicion else ""
    print(f"{marca} {nombre}{extra}", flush=True)


def preparar_datos():
    """Fija clave, rol, activo y bandera de los usuarios sintéticos. Solo base app360_c3 local."""
    url = urlsplit(os.environ.get("DATABASE_URL", ""))
    if url.hostname not in ("127.0.0.1", "localhost") or url.path.lstrip("/") != "app360_c3":
        raise SystemExit("El E2E de C3 solo corre sobre la base app360_c3 en 127.0.0.1.")
    if not ADMIN_CLAVE:
        raise SystemExit("Falta E2E_ADMIN_PASSWORD (clave ficticia del administrador de la instancia).")
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
                raise SystemExit(f"Falta el usuario sintético {usuario}: correr run_local_c3.sh up.")
            cuenta.role = rol
            cuenta.active = activo
            cuenta.must_change_password = temporal
            cuenta.password_changed_at = None
            cuenta.temp_password_expires_at = None
            cuenta.deactivated_at = None
            cuenta.set_password(inicial(usuario))
        db.session.commit()
    return app


def id_de(usuario):
    from models.core.user import User

    with APP.app_context():
        return User.query.filter_by(username=usuario).one().id


def vencer_clave_temporal(usuario):
    """Fuerza el vencimiento de la clave temporal al pasado (solo instancia local)."""
    from models import db
    from models.core.user import User

    with APP.app_context():
        cuenta = User.query.filter_by(username=usuario).one()
        cuenta.temp_password_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
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
    pagina.on(
        "console",
        lambda mensaje: CONSOLA.append({"contexto": etiqueta, "texto": mensaje.text})
        if mensaje.type == "error"
        else None,
    )
    pagina.on("pageerror", lambda error: ERRORES_JS.append({"contexto": etiqueta, "texto": str(error)}))
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


def captura(pagina, nombre):
    os.makedirs(CAPTURAS, exist_ok=True)
    pagina.screenshot(path=os.path.join(CAPTURAS, nombre + ".png"), full_page=False)


def token(pagina):
    return pagina.get_attribute('meta[name="csrf-token"]', "content")


def fila_de(pagina, usuario):
    return pagina.locator("#cuerpoUsuarios tr").filter(
        has=pagina.locator("td.fw-semibold", has_text=re.compile(rf"^{re.escape(usuario)}$"))
    )


def esperar_lista(pagina):
    pagina.wait_for_selector("#cuerpoUsuarios tr", timeout=20000)


def api(contexto, metodo, ruta, csrf=None, cuerpo=None):
    cabeceras = {"Accept": "application/json"}
    if csrf:
        cabeceras["X-CSRFToken"] = csrf
    datos = None
    if cuerpo is not None:
        cabeceras["Content-Type"] = "application/json"
        datos = json.dumps(cuerpo)
    respuesta = contexto.request.fetch(
        BASE + ruta, method=metodo, headers=cabeceras, data=datos, max_redirects=0
    )
    if respuesta.status >= 400:
        RESPUESTAS.append({"contexto": "api", "metodo": metodo, "status": respuesta.status, "ruta": ruta})
    return respuesta


def cuerpo_json(respuesta):
    try:
        return respuesta.json()
    except Exception:
        return {}


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
    verificar("compat: cuenta desactivada recibe el mensaje genérico", MENSAJE_LOGIN in mensajes(pagina))
    contexto.close()


def escenario_rol(navegador, admin, admin_ctx):
    """R1: admin cambia a Ventas → RRHH; ventas ve el cambio sin volver a entrar; RRHH recibe 403."""
    ventas_ctx = nuevo_contexto(navegador, "rol-ventas")
    ventas = nueva_pagina(ventas_ctx, "rol-ventas")
    entrar(ventas, "ventas", inicial("ventas"))
    verificar("(R1) antes: ventas ve el menú de Ventas", ventas.locator("a[href='/leads']").count() >= 1)
    verificar("(R1) antes: ventas no ve el menú de RRHH", ventas.locator("a[href^='/rrhh']").count() == 0)

    ir(admin, "/admin/usuarios")
    esperar_lista(admin)
    id_ventas = id_de("ventas")
    fila_de(admin, "ventas").get_by_role("button", name="Cambiar rol").click()
    admin.locator("#modalRol").wait_for(state="visible")
    verificar(
        "(R1) el título del modal dice «Cambiar rol de ventas»",
        admin.locator("#modalRolTitulo").inner_text().strip() == "Cambiar rol de ventas",
        admin.locator("#modalRolTitulo").inner_text(),
    )
    verificar(
        "(R1) la etiqueta visible del selector dice «NUEVO ROL»",
        admin.locator("label[for='modalRolSelect']").inner_text().strip() == "NUEVO ROL",
    )
    verificar(
        "(R1) el modal preselecciona el rol actual (Ventas)",
        admin.locator("#modalRolSelect").input_value() == "sales",
    )
    verificar(
        "(R1) el modal no ofrece «Administrador (manager)»",
        admin.locator("#modalRolSelect option[value='manager']").count() == 0,
    )
    captura(admin, "02_modal_cambiar_rol_ventas")
    admin.locator("#modalRolSelect").select_option("hr")
    with admin.expect_response(
        lambda r: r.url.endswith(f"/api/admin/usuarios/{id_ventas}/rol") and r.request.method == "POST"
    ) as info:
        admin.click("#btnGuardarRol")
    verificar("(R1) el servidor responde 200 al cambio de rol", info.value.status == 200, str(info.value.status))
    admin.wait_for_selector("#avisoUsuarios.alert-success", timeout=10000)
    verificar("(R1) el aviso confirma el rol RRHH", "RRHH" in admin.locator("#avisoUsuarios").inner_text())
    captura(admin, "03_admin_lista_tras_cambio_de_rol")

    ruta = ir(ventas, "/leads")
    verificar(
        "(R1) ventas, sin volver a entrar, cae en una pantalla de RRHH",
        ruta.startswith("/rrhh"),
        ruta,
    )
    verificar("(R1) ventas ya ve el menú de RRHH", ventas.locator("a[href^='/rrhh']").count() >= 1)
    verificar("(R1) ventas dejó de ver el menú de Ventas", ventas.locator("a[href='/leads']").count() == 0)
    captura(ventas, "04_ventas_menu_despues_del_cambio")
    ventas_ctx.close()

    rrhh_ctx = nuevo_contexto(navegador, "rol-rrhh")
    rrhh = nueva_pagina(rrhh_ctx, "rol-rrhh")
    entrar(rrhh, "rrhh", inicial("rrhh"))
    ir(rrhh, "/admin/usuarios")
    csrf = token(rrhh)
    cambio = api(rrhh_ctx, "POST", f"/api/admin/usuarios/{id_ventas}/rol", csrf, {"role": "sales"})
    reseteo = api(rrhh_ctx, "POST", f"/api/admin/usuarios/{id_ventas}/restablecer-clave", csrf)
    verificar(
        "(R1) RRHH: cambiar rol responde 403 en JSON",
        cambio.status == 403 and cuerpo_json(cambio).get("codigo") == "SIN_PERMISO",
        str(cambio.status),
    )
    verificar(
        "(R2) RRHH: restablecer clave responde 403 en JSON",
        reseteo.status == 403 and cuerpo_json(reseteo).get("codigo") == "SIN_PERMISO",
        str(reseteo.status),
    )
    verificar("(R1) RRHH: el rol de ventas no se tocó", _rol_de("ventas") == "hr", _rol_de("ventas"))
    rrhh_ctx.close()

    anonimo_ctx = nuevo_contexto(navegador, "anonimo")
    anonimo = api(anonimo_ctx, "POST", f"/api/admin/usuarios/{id_ventas}/rol", None, {"role": "sales"})
    verificar(
        "(R4b) sin sesión y sin token CSRF: 401 JSON «Sesión requerida»",
        anonimo.status == 401
        and cuerpo_json(anonimo).get("error") == "Sesión requerida"
        and cuerpo_json(anonimo).get("codigo") == "SESION_REQUERIDA",
        str(anonimo.status),
    )
    anonimo_ctx.close()


def _rol_de(usuario):
    from models.core.user import User

    with APP.app_context():
        return User.query.filter_by(username=usuario).one().role


def escenario_jerarquia(navegador):
    """R1/R2: el gerente no toca cuentas superiores y sí administra a ventas."""
    from models import db
    from models.core.user import User

    usuario_gerente = "probe-c3-gerente-jerarquia"
    usuario_manager = "probe-c3-manager-jerarquia"
    usuario_ventas = "probe-c3-ventas-jerarquia"
    with APP.app_context():
        for nombre, rol in ((usuario_gerente, "gerente"), (usuario_manager, "manager"), (usuario_ventas, "sales")):
            cuenta = User.query.filter_by(username=nombre).one_or_none()
            if cuenta is None:
                cuenta = User(username=nombre, role=rol, active=True)
                db.session.add(cuenta)
            cuenta.role = rol
            cuenta.active = True
            cuenta.must_change_password = False
            cuenta.temp_password_expires_at = None
            cuenta.deactivated_at = None
            cuenta.set_password(inicial(nombre))
        db.session.commit()

    contexto = nuevo_contexto(navegador, "jerarquia-gerente")
    pagina = nueva_pagina(contexto, "jerarquia-gerente")
    entrar(pagina, usuario_gerente, inicial(usuario_gerente))
    ir(pagina, "/admin/usuarios")
    esperar_lista(pagina)
    csrf = token(pagina)
    id_admin = id_de("admin")
    id_ventas = id_de(usuario_ventas)

    promover = api(contexto, "POST", f"/api/admin/usuarios/{id_ventas}/rol", csrf, {"role": "admin"})
    verificar(
        "(C3 jerarquía) gerente no puede promover ventas a admin",
        promover.status == 403 and cuerpo_json(promover).get("codigo") == "JERARQUIA_INSUFICIENTE"
        and _rol_de(usuario_ventas) == "sales",
        str(promover.status),
    )
    reset_admin = api(contexto, "POST", f"/api/admin/usuarios/{id_admin}/restablecer-clave", csrf)
    verificar(
        "(C3 jerarquía) gerente no puede restablecer la clave de admin",
        reset_admin.status == 403 and cuerpo_json(reset_admin).get("codigo") == "JERARQUIA_INSUFICIENTE",
        str(reset_admin.status),
    )
    baja_admin = api(contexto, "POST", f"/api/admin/usuarios/{id_admin}/desactivar", csrf)
    with APP.app_context():
        admin_sigue_activo = User.query.filter_by(username="admin").one().active is True
    verificar(
        "(C3 jerarquía) gerente no puede desactivar admin",
        baja_admin.status == 403 and cuerpo_json(baja_admin).get("codigo") == "JERARQUIA_INSUFICIENTE"
        and admin_sigue_activo,
        str(baja_admin.status),
    )
    pasar_a_hr = api(contexto, "POST", f"/api/admin/usuarios/{id_ventas}/rol", csrf, {"role": "hr"})
    verificar(
        "(C3 jerarquía) gerente sí puede administrar una cuenta de ventas",
        pasar_a_hr.status == 200 and _rol_de(usuario_ventas) == "hr",
        str(pasar_a_hr.status),
    )

    fila_admin = fila_de(pagina, "admin")
    fila_manager = fila_de(pagina, usuario_manager)
    botones_admin = fila_admin.locator("button[data-accion]")
    botones_manager = fila_manager.locator("button[data-accion]")
    roles = [opcion.get_attribute("value") for opcion in pagina.locator("#altaRol option").all()]
    ui_roles_ok = "admin" not in roles and "manager" not in roles
    ui_filas_ok = all(botones_admin.nth(i).is_disabled() for i in range(botones_admin.count())) and all(
        botones_manager.nth(i).is_disabled() for i in range(botones_manager.count())
    )
    explicacion = "Esta cuenta la administra un administrador. Pedile a un administrador que haga este cambio."
    ui_notas_ok = explicacion in fila_admin.inner_text() and explicacion in fila_manager.inner_text()
    verificar("(C3 jerarquía) selector del gerente oculta admin y manager", ui_roles_ok, str(roles))
    verificar(
        "(C3 jerarquía) filas admin/manager deshabilitadas con explicación",
        ui_filas_ok and ui_notas_ok,
    )

    # No dejar roles administrativos sintéticos activos para afectar la siguiente regresión.
    with APP.app_context():
        for nombre in (usuario_gerente, usuario_manager, usuario_ventas):
            cuenta = User.query.filter_by(username=nombre).one()
            cuenta.role = "sales"
            cuenta.active = False
            cuenta.deactivated_at = datetime.now(timezone.utc)
            cuenta.must_change_password = False
            cuenta.temp_password_expires_at = None
        db.session.commit()
    contexto.close()


def escenario_reseteo(navegador, admin):
    """R2: restablece la clave de anibal.lopez; la clave se muestra una vez y entra con cambio obligatorio."""
    id_anibal = id_de("anibal.lopez")
    ir(admin, "/admin/usuarios")
    esperar_lista(admin)
    fila_de(admin, "anibal.lopez").get_by_role("button", name="Restablecer clave").click()
    admin.locator("#app360ConfirmModal").wait_for(state="visible")
    confirmacion = admin.locator("#app360ConfirmModal").inner_text()
    verificar(
        "(R2) la confirmación explica el efecto en español",
        "Restablecer la clave de anibal.lopez" in confirmacion and "deberá cambiarla" in confirmacion,
    )
    captura(admin, "05_confirmar_restablecer_clave")
    with admin.expect_response(
        lambda r: r.url.endswith(f"/api/admin/usuarios/{id_anibal}/restablecer-clave") and r.request.method == "POST"
    ) as info:
        admin.click("#app360ConfirmAccept")
    respuesta = info.value
    verificar("(R2) el servidor responde 200", respuesta.status == 200, str(respuesta.status))
    verificar(
        "(R2) la respuesta no se guarda en caché (no-store)",
        respuesta.headers.get("cache-control") == "no-store",
        respuesta.headers.get("cache-control", ""),
    )
    admin.wait_for_selector("#panelClaveTemporal:not(.d-none)", timeout=10000)
    clave = admin.locator("#clave_temporal_nueva").inner_text()
    verificar("(R2) la clave temporal se muestra con 16 caracteres", bool(PATRON_CLAVE_TEMPORAL.fullmatch(clave)))
    verificar(
        "(R2) el panel dice «Clave restablecida» y avisa que no se vuelve a mostrar",
        "Clave restablecida" in admin.locator("#claveTitulo").inner_text()
        and "no se vuelve a mostrar" in admin.locator("#panelClaveTemporal").inner_text(),
    )
    verificar("(R2) la clave no aparece en la URL", clave not in admin.url)
    admin.click("#btnCerrarClave")
    verificar("(R2) al cerrar el panel, la clave sale del DOM", admin.locator("#clave_temporal_nueva").inner_text() == "")
    esperar_lista(admin)
    fila = fila_de(admin, "anibal.lopez")
    espera_texto(fila, "Debe cambiar la clave")
    verificar(
        "(R2) la lista marca «Debe cambiar la clave» con el vencimiento",
        "Debe cambiar la clave" in fila.inner_text() and "Clave temporal vence el" in fila.inner_text(),
        fila.inner_text(),
    )
    captura(admin, "06_admin_lista_tras_restablecer")

    anibal_ctx = nuevo_contexto(navegador, "reseteo-anibal")
    anibal = nueva_pagina(anibal_ctx, "reseteo-anibal")
    ruta = entrar(anibal, "anibal.lopez", clave)
    verificar("(R2) la clave temporal entra y fuerza /cambiar-clave", ruta == CAMBIO, ruta)
    ruta = ir(anibal, "/leads")
    verificar("(R2) cualquier otra pantalla vuelve a /cambiar-clave", ruta == CAMBIO, ruta)
    captura(anibal, "07_anibal_obligado_a_cambiar_clave")
    anibal.fill("#clave_actual", clave)
    anibal.fill("#clave_nueva", NUEVA)
    anibal.fill("#repetir_clave", NUEVA)
    with anibal.expect_navigation(wait_until="load"):
        anibal.press("#repetir_clave", "Enter")
    ruta = urlsplit(anibal.url).path
    verificar("(R2) cambia la clave y llega a su inicio", ruta not in (CAMBIO, "/"), ruta)
    anibal_ctx.close()

    viejo_ctx = nuevo_contexto(navegador, "reseteo-viejo")
    viejo = nueva_pagina(viejo_ctx, "reseteo-viejo")
    entrar(viejo, "anibal.lopez", clave)
    verificar("(R2) la clave temporal ya no entra después del cambio", MENSAJE_LOGIN in mensajes(viejo))
    viejo_ctx.close()


def espera_texto(localizador, texto, segundos=10):
    try:
        localizador.filter(has_text=texto).first.wait_for(timeout=segundos * 1000)
        return True
    except Exception:
        return False


def escenario_vencida(navegador, admin):
    """R3: clave temporal vencida: no entra, la lista lo muestra y el filtro lo encuentra."""
    ir(admin, "/admin/usuarios")
    esperar_lista(admin)
    fila_de(admin, "tesoreria").get_by_role("button", name="Restablecer clave").click()
    admin.locator("#app360ConfirmModal").wait_for(state="visible")
    id_tesoreria = id_de("tesoreria")
    with admin.expect_response(
        lambda r: r.url.endswith(f"/api/admin/usuarios/{id_tesoreria}/restablecer-clave") and r.request.method == "POST"
    ):
        admin.click("#app360ConfirmAccept")
    admin.wait_for_selector("#panelClaveTemporal:not(.d-none)", timeout=10000)
    clave = admin.locator("#clave_temporal_nueva").inner_text()
    admin.click("#btnCerrarClave")
    vencer_clave_temporal("tesoreria")

    tesoreria_ctx = nuevo_contexto(navegador, "vencida-tesoreria")
    tesoreria = nueva_pagina(tesoreria_ctx, "vencida-tesoreria")
    entrar(tesoreria, "tesoreria", clave)
    verificar("(R3) la clave temporal vencida no entra y responde el mensaje genérico", MENSAJE_LOGIN in mensajes(tesoreria))
    tesoreria_ctx.close()

    ir(admin, "/admin/usuarios")
    esperar_lista(admin)
    espera_texto(fila_de(admin, "tesoreria"), "Clave temporal vencida")
    verificar(
        "(R3) la lista muestra «Clave temporal vencida»",
        "Clave temporal vencida" in fila_de(admin, "tesoreria").inner_text(),
    )
    with admin.expect_response(lambda r: "/api/admin/usuarios?" in r.url and "estado=clave_vencida" in r.url):
        admin.select_option("#filtroEstado", "clave_vencida")
    espera_texto(admin.locator("#cuerpoUsuarios"), "tesoreria")
    filas = admin.locator("#cuerpoUsuarios tr")
    verificar(
        "(R3) el filtro «Clave temporal vencida» encuentra solo a tesoreria",
        filas.count() == 1 and "tesoreria" in filas.first.inner_text(),
        str(filas.count()),
    )
    captura(admin, "08_filtro_clave_temporal_vencida")
    admin.select_option("#filtroEstado", "todos")


def escenario_propia(navegador, admin, admin_ctx):
    """R4a: la fila propia del administrador tiene los botones deshabilitados; el servidor también bloquea."""
    ir(admin, "/admin/usuarios")
    esperar_lista(admin)
    id_propio = int(admin.get_attribute("#pantallaUsuarios", "data-yo"))
    fila = fila_de(admin, "admin")
    deshabilitados = [
        fila.get_by_role("button", name=nombre).is_disabled()
        for nombre in ("Cambiar rol", "Restablecer clave", "Desactivar")
    ]
    verificar("(R4a) en su fila, Cambiar rol, Restablecer clave y Desactivar están deshabilitados", all(deshabilitados), str(deshabilitados))
    verificar("(R4a) la fila propia explica por qué", "Es tu cuenta" in fila.inner_text())
    captura(admin, "09_fila_propia_deshabilitada")
    csrf = token(admin)
    cambio = api(admin_ctx, "POST", f"/api/admin/usuarios/{id_propio}/rol", csrf, {"role": "sales"})
    reseteo = api(admin_ctx, "POST", f"/api/admin/usuarios/{id_propio}/restablecer-clave", csrf)
    verificar(
        "(R4a) el servidor bloquea el autocambio de rol (403 AUTOCAMBIO_ROL)",
        cambio.status == 403 and cuerpo_json(cambio).get("codigo") == "AUTOCAMBIO_ROL",
        str(cambio.status),
    )
    verificar(
        "(R4a) el servidor bloquea el autorreseteo (403 AUTORESET)",
        reseteo.status == 403 and cuerpo_json(reseteo).get("codigo") == "AUTORESET",
        str(reseteo.status),
    )


def verificar_consola_y_red():
    verificar("consola: sin errores de JavaScript", not ERRORES_JS, json.dumps(ERRORES_JS)[:300])
    favicon_404 = [respuesta for respuesta in RESPUESTAS if respuesta["ruta"] == "/favicon.ico" and respuesta["status"] == 404]
    verificar("red: favicon.ico no devuelve 404", not favicon_404, json.dumps(favicon_404)[:200])
    no_http = [c for c in CONSOLA if "Failed to load resource" not in c["texto"]]
    verificar("consola: sin errores que no sean respuestas HTTP", not no_http, json.dumps(no_http)[:300])
    inesperadas = [r for r in RESPUESTAS if not es_esperada(r["status"], r["ruta"])]
    verificar("red: sin 4xx inesperados", not inesperadas, json.dumps(inesperadas)[:400])
    verificar("red: sin 5xx", not [r for r in RESPUESTAS if r["status"] >= 500])


def informe():
    fallas = [v for v in VERIFICACIONES if not v["ok"]]
    print(f"\nRESUMEN: {len(VERIFICACIONES) - len(fallas)} de {len(VERIFICACIONES)} verificaciones OK", flush=True)
    for v in fallas:
        print(f"FALLA: {v['verificacion']} {v['detalle']}", flush=True)
    os.makedirs(CAPTURAS, exist_ok=True)
    with open(os.path.join(CAPTURAS, "informe.json"), "w", encoding="utf-8") as archivo:
        json.dump({"verificaciones": VERIFICACIONES, "respuestas_4xx_5xx": RESPUESTAS}, archivo, ensure_ascii=False, indent=2)
    return not fallas


def main():
    from playwright.sync_api import sync_playwright

    preparar_datos()
    with sync_playwright() as pw:
        navegador = pw.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        try:
            escenario_compatibilidad(navegador)
            admin_ctx = nuevo_contexto(navegador, "admin")
            admin = nueva_pagina(admin_ctx, "admin")
            verificar("admin entra sin cambio obligatorio", entrar(admin, "admin", ADMIN_CLAVE) not in (CAMBIO, "/"))
            escenario_rol(navegador, admin, admin_ctx)
            escenario_reseteo(navegador, admin)
            escenario_vencida(navegador, admin)
            escenario_propia(navegador, admin, admin_ctx)
            escenario_jerarquia(navegador)
            verificar_consola_y_red()
        finally:
            for contexto in CONTEXTOS:
                try:
                    contexto.close()
                except Exception:
                    pass
            navegador.close()
    return 0 if informe() else 1


if __name__ == "__main__":
    APP = preparar_datos()
    sys.exit(main())
