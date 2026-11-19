"""E2E del corte D2 (app360, rama fix/api-dinero-d2) sobre la base aislada app360_fix_d2.

Corre contra la app de desarrollo local en 127.0.0.1:5059 (scratch/d2/e2e/run_d2.sh). Usa solo
datos sintéticos rotulados «DEMO E2E» y nunca toca app360_e2e ni el puerto 5055.

Verificaciones:
- S1: matriz JWT (rol × ruta) por HTTP real, anónimo, Bearer inválido, permiso individual de
  solo lectura y sesión web de la API (RRHH con módulo; Ventas sin módulo -> 403 JSON).
- S2: alta de la cuenta Cta Cte Friar con saldo inicial «1000,00»: 201, sin texto técnico en la
  respuesta ni en la pantalla.
- S3: liquidación de 2026-11: la previsualización antes de liquidar y la posterior dan 62.000,50;
  el período liquidado muestra la etiqueta y Generar queda deshabilitado; 2026-12 sin liquidar da
  162.000,50.
- S4: modal de arqueo (saldo inicial 1.000, saldo real 2.025, turno mañana): la diferencia del
  modal coincide con la guardada, 25,00 (movimientos del turno: ingresos 1.500, egresos 500).
- S5: Panel ejecutivo sin compras muestra «Sin datos de costo para calcular el margen»; con una
  compra procesada del período, el porcentaje en pantalla coincide con el del servidor (±0,05).

Salida fuera del repo: informe.json, matriz_jwt.csv y capturas en la carpeta de --salida.
Código de salida: 0 si todas las verificaciones pasan; 1 si alguna falla.

Requisitos: app en E2E_BASE_URL; variables DATABASE_URL, SECRET_KEY y ADMIN_PASSWORD del mismo
entorno; Playwright con Chromium. Para --reset, RUN_LOCAL
(E2E_RUN_LOCAL) debe apuntar al script de la instancia propia.

Uso:
    python scripts/dev_preview/e2e_dinero_d2.py --fase despues --reset
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5059").rstrip("/")
RUN_LOCAL = os.environ.get("E2E_RUN_LOCAL", "")
SEED_DINERO = os.environ.get(
    "E2E_SEED_DINERO", os.path.join(ROOT_DIR, "scripts", "dev_preview", "seed_dinero_d2.py")
)
VENV_PY = os.environ.get("E2E_PYTHON", "/root/.cache/app360-e2e-venv/bin/python")
LOCK = "/root/.hermes/cache/scratch/heavy.lock"
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CARPETA_SHOTS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/d2/e2e-shots")
ZONA_LOCAL = timezone(timedelta(hours=-3))

# Claves ficticias de la base local: las mismas de seed_demo.py y seed_dinero_d2.py.
CLAVES = {
    "admin": os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio"),
    "ventas.demo": "e2e-ventas-ficticia",
    "rrhh.demo": "e2e-rrhh-ficticia",
    "finanzas.demo": "e2e-finanzas-ficticia",
    "consulta.demo": "e2e-consulta-ficticia",
    "operaciones.demo": "e2e-operaciones-ficticia",
    "lectura.demo": "e2e-lectura-ficticia",
}
TODOS = "*"
# Módulos efectivos: ACCESS_MAP de security.py por rol, y permisos individuales de
# lectura para lectura.demo (seed_dinero_d2.py).
MODULOS = {
    "admin": TODOS,
    "ventas.demo": {"crm", "ventas", "dashboard_comercial", "comercial", "objetivos"},  # sales
    "rrhh.demo": {"rrhh", "adelantos", "ausentismo", "dotacion", "empleados"},  # hr
    "finanzas.demo": {"tesoreria", "arqueos", "movimientos", "gastos", "bi", "panel"},  # finance
    "consulta.demo": set(),  # rol sin módulos
    "operaciones.demo": {"compras", "stock", "locations", "products", "dashboard"},  # operations
    "lectura.demo": {"products", "stock", "crm", "rrhh"},  # permisos individuales «view»
}
# (ruta GET de api_rest o de la API con sesión, módulo que protege su pantalla)
RUTAS_JWT = [
    ("/api/products", "products"),
    ("/api/locations", "locations"),
    ("/api/leads", "crm"),
    ("/api/stock", "stock"),
    ("/api/rrhh/dotacion", "rrhh"),
    ("/api/business-units", "stock"),
    ("/api/compras", "compras"),
    ("/api/compras/overview", "compras"),
    ("/api/rrhh", "rrhh"),
    ("/api/rrhh/empleados", "rrhh"),
]
EMPLEADA = "Empleada Demo Liquidación"
FRAGMENTOS_TECNICOS = (
    "psycopg2", "invalid input syntax", "InvalidTextRepresentation", "Traceback",
    "sqlalchemy", "ConversionSyntax",
)
PATRON_SQL = re.compile(r"\bSQL\b")
JS_NETO = """(nombre) => {
  const fila = [...document.querySelectorAll('#tabla-preview tr')]
    .find(tr => tr.cells.length >= 6 && tr.cells[0].innerText.includes(nombre));
  return fila ? fila.cells[5].innerText : null;
}"""

_TOKENS = {}
ESTADO_WEB = {"usuario": None}


class Informe:
    def __init__(self, fase):
        self.fase = fase
        self.verificaciones = []
        self.errores_pagina = []
        self.dialogos = []

    def verificar(self, nombre, ok, detalle=""):
        ok = bool(ok)
        self.verificaciones.append({"nombre": nombre, "ok": ok, "detalle": str(detalle)[:500]})
        marca = "OK   " if ok else "FALLA"
        print(f"{marca} {nombre}" + (f" -- {str(detalle)[:240]}" if detalle != "" else ""), flush=True)
        return ok

    def guardar(self, carpeta):
        fallas = [v for v in self.verificaciones if not v["ok"]]
        with open(os.path.join(carpeta, "informe.json"), "w", encoding="utf-8") as fh:
            json.dump({
                "fase": self.fase,
                "base_url": BASE_URL,
                "total": len(self.verificaciones),
                "fallas": len(fallas),
                "verificaciones": self.verificaciones,
                "dialogos_nativos": self.dialogos,
                "errores_consola_o_pagina": self.errores_pagina,
            }, fh, ensure_ascii=False, indent=2)
        return len(self.verificaciones), len(fallas)


def numero(texto):
    """«$ 62.000,50», «12,3 %» o «62000.5» a float; None si no hay cifra."""
    t = re.sub(r"[^\d,.\-]", "", str(texto or ""))
    if re.fullmatch(r"-?\d{1,3}(\.\d{3})+(,\d+)?", t):
        t = t.replace(".", "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def sin_texto_tecnico(texto):
    texto = texto or ""
    return not any(fragmento in texto for fragmento in FRAGMENTOS_TECNICOS) and not PATRON_SQL.search(texto)


def login_api(usuario):
    """Token JWT por /api/login (5 por minuto: si llega 429, se espera y se reintenta)."""
    if usuario in _TOKENS:
        return _TOKENS[usuario]
    cuerpo = json.dumps({"username": usuario, "password": CLAVES[usuario]}).encode()
    for _ in range(8):
        req = urllib.request.Request(BASE_URL + "/api/login", data=cuerpo,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                _TOKENS[usuario] = json.loads(resp.read())["access_token"]
                return _TOKENS[usuario]
        except urllib.error.HTTPError as err:
            if err.code != 429:
                raise
            time.sleep(20)
    raise RuntimeError(f"login API sin respuesta para {usuario}")


def pedir(metodo, ruta, token=None, cuerpo=None):
    cabeceras = {"Accept": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    datos = None
    if cuerpo is not None:
        datos = json.dumps(cuerpo).encode()
        cabeceras["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + ruta, data=datos, headers=cabeceras, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode("utf-8", "replace")


def error_de(cuerpo):
    """Texto del campo «error» de una respuesta JSON; vacío si no lo es."""
    try:
        return json.loads(cuerpo).get("error", "")
    except (ValueError, AttributeError):
        return ""


def matriz_jwt(informe, carpeta):
    filas = []
    tokens = {usuario: login_api(usuario) for usuario in MODULOS}
    for usuario, token in tokens.items():
        for ruta, modulo in RUTAS_JWT:
            permitido = MODULOS[usuario] == TODOS or modulo in MODULOS[usuario]
            esperado = 200 if permitido else 403
            codigo, cuerpo = pedir("GET", ruta, token)
            ok = codigo == esperado and (permitido or error_de(cuerpo) == "Sin acceso al módulo")
            filas.append({"usuario": usuario, "ruta": ruta, "modulo": modulo, "esperado": esperado,
                          "obtenido": codigo, "resultado": "OK" if ok else "FALLA"})
            informe.verificar(f"S1 JWT {usuario} GET {ruta} (módulo {modulo})", ok,
                              f"esperado {esperado}, obtenido {codigo}")
    for ruta, modulo in RUTAS_JWT:
        codigo, _ = pedir("GET", ruta)
        ok = codigo == 401
        filas.append({"usuario": "anonimo", "ruta": ruta, "modulo": modulo, "esperado": 401,
                      "obtenido": codigo, "resultado": "OK" if ok else "FALLA"})
        informe.verificar(f"S1 anónimo GET {ruta} -> 401", ok, f"obtenido {codigo}")
    codigo, _ = pedir("GET", "/api/compras", "token-invalido")
    informe.verificar("S1 Bearer inválido no cae a la sesión (GET /api/compras) -> 401", codigo == 401, codigo)

    for metodo, ruta, cuerpo in (("POST", "/api/products", {"name": "DEMO E2E lectura"}),
                                 ("PUT", "/api/products/1", {"name": "DEMO E2E lectura"}),
                                 ("DELETE", "/api/products/1", None)):
        codigo, texto = pedir(metodo, ruta, tokens["lectura.demo"], cuerpo)
        ok = codigo == 403 and "error" in texto
        filas.append({"usuario": "lectura.demo", "ruta": f"{metodo} {ruta}", "modulo": "products (view)",
                      "esperado": 403, "obtenido": codigo, "resultado": "OK" if ok else "FALLA"})
        informe.verificar(f"S1 solo lectura bloquea {metodo} {ruta} -> 403", ok, codigo)

    with open(os.path.join(carpeta, "matriz_jwt.csv"), "w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=["usuario", "ruta", "modulo", "esperado", "obtenido", "resultado"])
        escritor.writeheader()
        escritor.writerows(filas)


def instrumentar(page, informe):
    def al_dialogo(dialogo):
        # Los confirm nativos (Generar liquidaciones) se aceptan y quedan registrados.
        informe.dialogos.append(dialogo.message[:200])
        dialogo.accept()

    page.on("dialog", al_dialogo)
    page.on("response", lambda r: informe.errores_pagina.append(
        {"tipo": "http", "texto": f"{r.status} {r.url[:160]}"}) if r.status >= 400 else None)
    page.on("pageerror", lambda e: informe.errores_pagina.append({"tipo": "excepcion_js", "texto": str(e)[:300]}))
    page.on("console", lambda m: informe.errores_pagina.append({"tipo": "consola", "texto": m.text[:300]})
            if m.type == "error" else None)


def asegurar_login(page, usuario):
    """Entra con el formulario real. Cambia de usuario limpiando la sesión anterior."""
    if ESTADO_WEB["usuario"] == usuario:
        return True
    page.context.clear_cookies()
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", usuario)
    page.fill("#password", CLAVES[usuario])
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    ok = urlparse(page.url).path != "/"
    ESTADO_WEB["usuario"] = usuario if ok else None
    return ok


def captura(page, carpeta, nombre):
    page.screenshot(path=os.path.join(carpeta, nombre), full_page=True)


def sesion_web_api(page, informe):
    """S1, sesión web: RRHH (con módulo) lee la API; Ventas (sin módulo) recibe 403 JSON."""
    informe.verificar("S1 login web rrhh.demo", asegurar_login(page, "rrhh.demo"))
    r = page.request.get(BASE_URL + "/api/rrhh/empleados", max_redirects=0)
    informe.verificar("S1 sesión web RRHH GET /api/rrhh/empleados -> 200", r.status == 200, r.status)
    informe.verificar("S1 login web ventas.demo", asegurar_login(page, "ventas.demo"))
    r = page.request.get(BASE_URL + "/api/rrhh/empleados", max_redirects=0)
    informe.verificar("S1 sesión web Ventas GET /api/rrhh/empleados -> 403 JSON",
                      r.status == 403 and "error" in r.text(), r.status)


def s2_friar(page, informe, carpeta):
    informe.verificar("S2 login web admin", asegurar_login(page, "admin"))

    def abrir_alta():
        page.goto(BASE_URL + "/admin/tesoreria", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.click("#tab-cuenta_friar")
        page.click("button[data-entidad='cuenta_friar']:has-text('Nuevo')")
        page.wait_for_selector("#modalEntidad", state="visible", timeout=15000)

    def enviar(valor):
        abrir_alta()
        page.fill("#modalCampos input[name='saldo_inicial']", valor)
        with page.expect_response(
            lambda r: r.url.endswith("/api/admin/tesoreria/cuenta_friar") and r.request.method == "POST",
            timeout=20000,
        ) as espera:
            page.click("#formEntidad button[type=submit]")
        return espera.value

    resp = enviar("1000,00")
    envio = resp.request.post_data or ""
    informe.verificar("S2 el envío lleva el importe como se escribió («1000,00»)", "1000,00" in envio, envio[:160])
    informe.verificar("S2 alta Cta Cte Friar «1000,00» -> 201", resp.status == 201, f"HTTP {resp.status}")
    page.wait_for_timeout(1200)
    lista = page.request.get(BASE_URL + "/api/admin/tesoreria/cuenta_friar")
    items = lista.json().get("items", []) if lista.status == 200 else []
    saldos = [numero(i.get("saldo_inicial")) for i in items]
    informe.verificar("S2 cuenta guardada con saldo 1.000,00",
                      any(s is not None and abs(s - 1000.0) < 0.005 for s in saldos), saldos)
    captura(page, carpeta, "s2-1-alta-1000-00.png")

    # Caso de error: la respuesta no navega, así que el cuerpo se lee completo.
    resp_error = enviar("abc")
    cuerpo = resp_error.text()
    page.wait_for_timeout(800)
    mensaje = error_de(cuerpo)
    informe.verificar("S2 importe «abc»: 400 con mensaje en español",
                      resp_error.status == 400 and "Ingresá un importe válido" in mensaje,
                      f"HTTP {resp_error.status} {mensaje[:120]}")
    informe.verificar("S2 importe «abc»: respuesta sin texto técnico", sin_texto_tecnico(cuerpo), cuerpo[:160])
    informe.verificar("S2 pantalla sin texto técnico", sin_texto_tecnico(page.inner_text("body")))
    captura(page, carpeta, "s2-2-importe-invalido.png")


def previsualizar(page, periodo):
    page.fill("#periodo-liquidacion", periodo)
    with page.expect_response(lambda r: "/api/rrhh/liquidaciones/preview/" in r.url, timeout=20000):
        page.click("button:has-text('Previsualizar')")
    page.wait_for_timeout(400)
    return numero(page.evaluate(JS_NETO, EMPLEADA))


def s3_liquidacion(page, informe, carpeta):
    informe.verificar("S3 login web rrhh.demo", asegurar_login(page, "rrhh.demo"))
    page.goto(BASE_URL + "/rrhh/liquidaciones", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")

    neto_previo = previsualizar(page, "2026-11")
    informe.verificar("S3 previsualización 2026-11 antes de liquidar = 62.000,50",
                      neto_previo is not None and abs(neto_previo - 62000.50) < 0.005, neto_previo)
    captura(page, carpeta, "s3-1-2026-11-antes.png")

    page.click("#btn-generar")
    page.wait_for_selector("#app360ConfirmModal.show #app360ConfirmAccept", state="visible", timeout=15000)
    page.click("#app360ConfirmAccept")
    try:
        page.wait_for_function(
            "() => { const e = document.getElementById('etiqueta-periodo-liquidado');"
            " return !!e && e.style.display !== 'none'; }",
            timeout=20000)
    except Exception:
        pass

    neto_liquidado = previsualizar(page, "2026-11")
    etiqueta_visible = page.is_visible("#etiqueta-periodo-liquidado")
    generar_deshabilitado = page.is_disabled("#btn-generar")
    aviso = page.inner_text("#aviso-generar")
    informe.verificar("S3 previsualización 2026-11 ya liquidado = 62.000,50 (no 162.000,50)",
                      neto_liquidado is not None and abs(neto_liquidado - 62000.50) < 0.005, neto_liquidado)
    informe.verificar("S3 etiqueta «Período ya liquidado» visible", etiqueta_visible)
    informe.verificar("S3 Generar deshabilitado con motivo en pantalla",
                      generar_deshabilitado and "ya está liquidado" in aviso, aviso[:140])
    captura(page, carpeta, "s3-2-2026-11-liquidado.png")

    neto_siguiente = previsualizar(page, "2026-12")
    informe.verificar("S3 previsualización 2026-12 sin liquidar = 162.000,50 (siguiente cuota)",
                      neto_siguiente is not None and abs(neto_siguiente - 162000.50) < 0.005, neto_siguiente)
    informe.verificar("S3 2026-12 sin liquidar: sin etiqueta y Generar habilitado",
                      not page.is_visible("#etiqueta-periodo-liquidado") and not page.is_disabled("#btn-generar"))
    captura(page, carpeta, "s3-3-2026-12-sin-liquidar.png")


def s4_arqueo(page, informe, carpeta):
    informe.verificar("S4 login web admin", asegurar_login(page, "admin"))
    page.goto(BASE_URL + "/tesoreria/arqueos", wait_until="domcontentloaded")
    page.wait_for_load_state("networkidle")
    page.click("button:has-text('Nuevo Arqueo')")
    page.wait_for_selector("#modalNuevoArqueo", state="visible", timeout=15000)
    hoy = datetime.now(ZONA_LOCAL).date().isoformat()
    page.fill("#formArqueo input[name='fecha']", hoy)
    page.select_option("#formArqueo select[name='turno']", "mañana")
    campo_inicial = page.locator("#formArqueo label", has_text="Saldo Inicial").locator(
        "xpath=following::input[not(@type='hidden')][1]")
    campo_inicial.fill("1000")
    campo_inicial.press("Tab")
    page.fill("#saldoReal", "2025")
    page.press("#saldoReal", "Tab")
    if page.locator("#ingresosTurnoSistema").count():
        page.wait_for_function("() => document.getElementById('ingresosTurnoSistema').value !== ''",
                               timeout=15000)
        ingresos = page.input_value("#ingresosTurnoSistema")
        egresos = page.input_value("#egresosTurnoSistema")
        informe.verificar("S4 totales del sistema del turno: ingresos 1.500,00 y egresos 500,00",
                          numero(ingresos) == 1500.0 and numero(egresos) == 500.0, f"{ingresos} / {egresos}")
    page.wait_for_timeout(300)
    diferencia_modal = numero(page.input_value("#diferenciaCalc"))
    captura(page, carpeta, "s4-1-modal-antes-de-guardar.png")

    with page.expect_response(
        lambda r: r.url.endswith("/api/tesoreria/arqueos") and r.request.method == "POST", timeout=20000,
    ) as espera:
        page.click("#formArqueo button[type=submit]")
    resp = espera.value
    page.wait_for_timeout(1200)
    guardados = page.request.get(BASE_URL + "/api/tesoreria/arqueos").json().get("arqueos", [])
    fila = next((a for a in guardados if a.get("fecha") == hoy and a.get("turno") == "mañana"), None)
    diferencia_guardada = fila.get("diferencia") if fila else None
    informe.verificar("S4 arqueo guardado -> 201", resp.status == 201, f"HTTP {resp.status}")
    informe.verificar("S4 diferencia del modal = diferencia guardada",
                      diferencia_modal is not None and diferencia_guardada is not None
                      and abs(diferencia_modal - diferencia_guardada) < 0.005,
                      f"modal {diferencia_modal} / guardada {diferencia_guardada}")
    informe.verificar("S4 diferencia guardada = 25,00", diferencia_guardada is not None
                      and abs(diferencia_guardada - 25.0) < 0.005, diferencia_guardada)
    page.wait_for_timeout(500)
    captura(page, carpeta, "s4-2-despues-de-guardar.png")


def s5_panel(page, informe, carpeta):
    informe.verificar("S5 login web admin", asegurar_login(page, "admin"))
    with page.expect_response(lambda r: "/api/panel-ejecutivo-v2" in r.url, timeout=30000) as espera:
        page.goto(BASE_URL + "/panel-ejecutivo", wait_until="domcontentloaded")
    datos_sin = espera.value.json()
    page.wait_for_selector("#content:not(.d-none)", timeout=30000)
    texto_sin = page.inner_text("#kpi-resultado-pct")
    informe.verificar("S5 sin compras: el servidor marca datos_insuficientes",
                      datos_sin.get("kpis", {}).get("datos_insuficientes") is True,
                      datos_sin.get("kpis", {}).get("datos_insuficientes"))
    informe.verificar("S5 sin compras: «Sin datos de costo para calcular el margen» (no 100 %)",
                      "Sin datos de costo para calcular el margen" in texto_sin, texto_sin)
    captura(page, carpeta, "s5-1-sin-compras.png")

    subprocess.run([VENV_PY, SEED_DINERO, "--con-compras"], check=True, cwd=ROOT_DIR,
                   env=os.environ.copy(), stdout=subprocess.DEVNULL)
    with page.expect_response(lambda r: "/api/panel-ejecutivo-v2" in r.url, timeout=30000) as espera2:
        page.goto(BASE_URL + "/panel-ejecutivo", wait_until="domcontentloaded")
    datos_con = espera2.value.json()
    page.wait_for_selector("#content:not(.d-none)", timeout=30000)
    texto_con = page.inner_text("#kpi-resultado-pct")
    kpis_con = datos_con.get("kpis", {})
    informe.verificar("S5 con compras: sin aviso de datos insuficientes",
                      kpis_con.get("datos_insuficientes") is False and "Sin datos de costo" not in texto_con, texto_con)
    esperado = kpis_con.get("resultado_sobre_facturacion_pct")
    pantalla = numero(texto_con)
    informe.verificar("S5 con compras: porcentaje en pantalla = servidor (±0,05)",
                      esperado is not None and pantalla is not None and abs(pantalla - esperado) <= 0.05,
                      f"pantalla {texto_con!r} / servidor {esperado}")
    captura(page, carpeta, "s5-2-con-compras.png")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fase", required=True, help="etiqueta de la corrida: antes o despues")
    parser.add_argument("--salida", default=None, help="carpeta de capturas e informes (fuera del repo)")
    parser.add_argument("--reset", action="store_true", help="recrea la base y reinicia la app antes de correr")
    args = parser.parse_args()
    for variable in ("DATABASE_URL", "SECRET_KEY", "ADMIN_PASSWORD"):
        if not os.environ.get(variable):
            raise SystemExit(f"Falta {variable} en el entorno (ver scratch/d2/e2e/env_d2.sh).")

    carpeta = args.salida or os.path.join(CARPETA_SHOTS, f"{args.fase}-{datetime.now(ZONA_LOCAL):%Y%m%dT%H%M%S}")
    os.makedirs(carpeta, exist_ok=True)
    informe = Informe(args.fase)

    if args.reset:
        if not RUN_LOCAL:
            raise SystemExit("--reset necesita E2E_RUN_LOCAL: el script que recrea la base de la instancia propia.")
        subprocess.run(["flock", "-o", LOCK, RUN_LOCAL, "reset"], check=True, stdout=subprocess.DEVNULL)

    matriz_jwt(informe, carpeta)

    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        contexto = navegador.new_context(locale="es-AR", viewport={"width": 1366, "height": 900})
        page = contexto.new_page()
        instrumentar(page, informe)
        pasos = [
            ("S1-sesion", lambda: sesion_web_api(page, informe)),
            ("S2", lambda: s2_friar(page, informe, carpeta)),
            ("S3", lambda: s3_liquidacion(page, informe, carpeta)),
            ("S4", lambda: s4_arqueo(page, informe, carpeta)),
            ("S5", lambda: s5_panel(page, informe, carpeta)),
        ]
        for nombre, paso in pasos:
            try:
                paso()
            except Exception as error:  # una falla de flujo queda registrada y no corta el resto
                informe.verificar(f"{nombre}: el flujo terminó sin excepción", False, repr(error)[:300])
                try:
                    captura(page, carpeta, f"error-{nombre}.png")
                except Exception:
                    pass
        navegador.close()

    informe.verificar("consola: sin excepciones de JavaScript en las pantallas probadas",
                      not any(e["tipo"] == "excepcion_js" for e in informe.errores_pagina))
    informe.verificar("red: sin respuestas 5xx en las pantallas probadas",
                      not any(e["tipo"] == "http" and e["texto"].startswith("5")
                              for e in informe.errores_pagina))
    total, fallas = informe.guardar(carpeta)
    print(f"RESUMEN fase={args.fase} total={total} fallas={fallas} carpeta={carpeta}")
    return 0 if fallas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
