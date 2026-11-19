"""Recorrido E2E de formularios y cálculos (corte D1, puntos D-1 a D-9), con Playwright en es-AR.

Qué verifica, con captura de cada pantalla tocada:
- D-1 importes: Ventas guarda «1.234,56» como 1234.56 y rechaza «abc» sin guardar nada.
- D-2 CSRF: el cambio de estado de venta y de compra, la acción de lead y la interacción no dan 400.
- D-3 leads: las etapas se muestran con su nombre; el alta sin producto ni ubicación se guarda.
- D-4 y D-5 compras: el detalle de la orden abre; recepción parcial; sobrante bloqueado; doble clic
  con una sola recepción; la orden queda recibida y el stock es la suma de las recepciones.
- D-6 stock: el alta de un par existente avisa sin pisar la cantidad; la cantidad negativa se rechaza.
- D-7 catálogos: estados vacíos con enlace y Guardar deshabilitado; SKU duplicado con aviso;
  /rrhh/dotacion redirige a /rrhh.
- D-8 Objetivos: la barra de período muestra los meses en español.
- D-9 avisos: sin prefijo técnico «Error:» en las pantallas revisadas.

Requisitos:
- App en E2E_BASE_URL apuntando al worktree a probar (por defecto http://127.0.0.1:5058).
- Base de la semilla REINICIADA (catálogo vacío): la fase de estados vacíos lo exige.
- E2E_DATABASE_URL apunta a esa misma base: el script lee valores guardados y crea una unidad de
  negocio ficticia rotulada PROBE-E2E. E2E_ADMIN_USER y E2E_ADMIN_PASSWORD: admin de esa base.

Capturas e informe JSON en E2E_CAPTURAS/<etiqueta>/ (fuera del repo). Código de salida 0 solo si todas
las verificaciones pasan; 1 si alguna falla.

Uso:
    E2E_BASE_URL=http://127.0.0.1:5058 E2E_DATABASE_URL=... E2E_ADMIN_PASSWORD=... \
        /root/.cache/app360-e2e-venv/bin/python scripts/dev_preview/e2e_formularios.py --etiqueta despues
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime

import psycopg2
from playwright.sync_api import sync_playwright

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5058").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "")
DB_URL = os.environ.get("E2E_DATABASE_URL", "").replace("postgresql+psycopg2://", "postgresql://")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/root/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/root/.hermes/cache/scratch/d1/capturas")
SUFIJO = datetime.now().strftime("%H%M%S")
# Rechazos intencionales que responden 4xx: importe «abc», par de stock repetido, cantidad negativa y SKU repetido.
RECHAZOS_ESPERADOS = 4
RESULTADOS = []
RESPUESTAS_ERROR = []
ERRORES_CONSOLA = []


def verificar(nombre, ok, detalle=""):
    RESULTADOS.append({"nombre": nombre, "ok": bool(ok), "detalle": str(detalle)[:300]})
    marca = "OK   " if ok else "FALLA"
    print(f"{marca} {nombre}" + ("" if ok or not detalle else f" -> {detalle}"))


def consulta(sql, params=()):
    with psycopg2.connect(DB_URL) as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchall() if cursor.description else []


class Capturas:
    def __init__(self, etiqueta):
        self.carpeta = os.path.join(CAPTURAS, etiqueta)
        os.makedirs(self.carpeta, exist_ok=True)
        self.numero = 0

    def foto(self, page, nombre):
        self.numero += 1
        page.screenshot(path=os.path.join(self.carpeta, f"{self.numero:02d}_{nombre}.png"), full_page=True)


def registrar_respuesta(respuesta):
    if respuesta.status >= 400 and not respuesta.url.endswith("/favicon.ico"):
        RESPUESTAS_ERROR.append(
            {"status": respuesta.status, "metodo": respuesta.request.method, "url": respuesta.url}
        )


def registrar_consola(mensaje):
    if mensaje.type == "error" and not mensaje.text.startswith("Failed to load resource"):
        ERRORES_CONSOLA.append(mensaje.text[:200])


def paso(nombre, funcion, page, capturas):
    """Una falla no corta el recorrido: queda registrada con su captura."""
    try:
        funcion()
    except Exception as error:
        verificar(f"{nombre} (no se pudo completar)", False, f"{type(error).__name__}: {str(error)[:200]}")
        try:
            capturas.foto(page, "error_" + re.sub(r"\W+", "_", nombre)[:40])
        except Exception:
            pass


def enviar_y_esperar(page, formulario):
    with page.expect_navigation():
        formulario.locator("button[type=submit], button:not([type])").first.click()
    page.wait_for_load_state("networkidle")


def primera_opcion(select):
    return select.evaluate("(s) => Array.from(s.options).map((o) => o.value).find((v) => v)")


def valores_de(select):
    return select.evaluate("(s) => Array.from(s.options).map((o) => o.value)")


def boton_guardar_deshabilitado(page):
    return page.locator("button:has-text('Guardar')").first.is_disabled()


def recibir(page, cantidad):
    page.locator("#formRecepcion input[name=quantity]").fill(str(cantidad))
    with page.expect_navigation():
        page.click("#btnRegistrarRecepcion")
    page.wait_for_load_state("networkidle")
    return page.content()


def login(page):
    page.goto(BASE_URL + "/")
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    verificar("login de administrador", "/login" not in page.url, page.url)


def fase_vacia(page, capturas):
    page.goto(BASE_URL + "/products/new")
    html = page.content()
    verificar(
        "D-7 productos sin unidades: aviso con enlace a Administración",
        "Todavía no hay unidades de negocio" in html and 'href="/admin"' in html,
    )
    verificar("D-7 productos sin unidades: Guardar deshabilitado", boton_guardar_deshabilitado(page))
    capturas.foto(page, "d7_productos_sin_unidades")

    page.goto(BASE_URL + "/leads/new")
    verificar(
        "D-7 leads sin unidades: aviso y Guardar deshabilitado",
        "Todavía no hay unidades de negocio" in page.content() and boton_guardar_deshabilitado(page),
    )
    capturas.foto(page, "d7_leads_sin_unidades")

    page.goto(BASE_URL + "/stock/new")
    html = page.content()
    verificar(
        "D-7 stock sin productos ni ubicaciones: avisos con enlace",
        "Todavía no hay productos" in html and "Todavía no hay ubicaciones" in html,
    )
    verificar("D-7 stock sin productos ni ubicaciones: Guardar deshabilitado", boton_guardar_deshabilitado(page))
    capturas.foto(page, "d7_stock_sin_catalogo")

    page.goto(BASE_URL + "/rrhh/dotacion")
    verificar(
        "D-7 /rrhh/dotacion redirige a /rrhh con aviso, sin 500",
        page.url.rstrip("/").endswith("/rrhh") and "La dotación todavía no tiene datos" in page.content(),
        page.url,
    )
    capturas.foto(page, "d7_dotacion_redirige")


def preparar_catalogo(page, capturas, estado):
    estado["unidad"] = consulta(
        "INSERT INTO business_units (name) VALUES (%s) RETURNING id", (f"PROBE-E2E Unidad {SUFIJO}",)
    )[0][0]
    for clave, nombre in (("loc_a", "Deposito A"), ("loc_b", "Deposito B")):
        nombre_completo = f"PROBE-E2E {nombre} {SUFIJO}"
        page.goto(BASE_URL + "/locations/new")
        formulario = page.locator("form:has(input[name=name])")
        formulario.locator("input[name=name]").fill(nombre_completo)
        formulario.locator("select[name=type]").select_option(index=0)
        enviar_y_esperar(page, formulario)
        estado[clave] = consulta("SELECT id FROM locations WHERE name=%s", (nombre_completo,))[0][0]
    estado["sku"] = f"PROBE-E2E-{SUFIJO}"
    page.goto(BASE_URL + "/products/new")
    formulario = page.locator("form:has(input[name=sku])")
    formulario.locator("input[name=sku]").fill(estado["sku"])
    formulario.locator("input[name=name]").fill(f"PROBE-E2E Producto {SUFIJO}")
    formulario.locator("input[name=category]").fill("PROBE-E2E")
    formulario.locator("select[name=business_unit_id]").select_option(str(estado["unidad"]))
    enviar_y_esperar(page, formulario)
    estado["producto"] = consulta("SELECT id FROM products WHERE sku=%s", (estado["sku"],))[0][0]
    verificar("catálogo PROBE creado (unidad, dos ubicaciones, un producto)", bool(estado.get("producto")))
    capturas.foto(page, "catalogo_probe")


def ventas(page, capturas, estado):
    page.goto(BASE_URL + "/ventas/nuevo")
    formulario = page.locator("form:has(input[name=unit_price])")
    formulario.locator("select[name=product_id]").select_option(str(estado["producto"]))
    formulario.locator("select[name=location_id]").select_option(str(estado["loc_a"]))
    formulario.locator("input[name=quantity]").fill("1")
    formulario.locator("input[name=unit_price]").fill("1.234,56")
    capturas.foto(page, "d1_ventas_antes_de_guardar")
    enviar_y_esperar(page, formulario)
    fila = consulta(
        "SELECT id, unit_price FROM sales WHERE product_id=%s ORDER BY id DESC LIMIT 1", (estado["producto"],)
    )
    verificar("D-1 Ventas: «1.234,56» se guarda como 1234.56", bool(fila) and str(fila[0][1]) == "1234.56", fila)
    if fila:
        estado["venta"] = fila[0][0]
    capturas.foto(page, "d1_ventas_despues_de_guardar")

    page.goto(BASE_URL + "/ventas/nuevo")
    formulario = page.locator("form:has(input[name=unit_price])")
    formulario.locator("select[name=product_id]").select_option(str(estado["producto"]))
    formulario.locator("select[name=location_id]").select_option(str(estado["loc_a"]))
    formulario.locator("input[name=quantity]").fill("1")
    formulario.locator("input[name=unit_price]").fill("abc")
    enviar_y_esperar(page, formulario)
    verificar(
        "D-1 Ventas: «abc» se rechaza con aviso en español",
        "Ingresá un importe válido, por ejemplo 1.234,56" in page.content(),
    )
    cantidad = consulta("SELECT count(*) FROM sales WHERE product_id=%s", (estado["producto"],))[0][0]
    verificar("D-1 Ventas: «abc» no guarda ninguna venta nueva", cantidad == 1, cantidad)
    capturas.foto(page, "d1_ventas_rechazo_abc")

    if estado.get("venta"):
        page.goto(BASE_URL + f"/ventas/{estado['venta']}")
        formulario = page.locator("form:has(select[name=status])")
        formulario.locator("select[name=status]").select_option(valores_de(formulario.locator("select[name=status]"))[-1])
        enviar_y_esperar(page, formulario)
        verificar(
            "D-2 Ventas: cambio de estado guarda sin 400",
            page.url.rstrip("/").endswith(f"/ventas/{estado['venta']}"),
            page.url,
        )


def leads(page, capturas, estado):
    page.goto(BASE_URL + "/leads/new")
    etapas = page.locator("select[name=stage] option").evaluate_all("(ops) => ops.map((o) => o.value)")
    verificar(
        "D-3 Leads: las etapas se muestran por nombre (sin repr de diccionario)",
        bool(etapas) and all("{" not in valor for valor in etapas),
        etapas,
    )
    nombre = f"PROBE-E2E Lead {SUFIJO}"
    formulario = page.locator("form:has(input[name=source])")
    formulario.locator("input[name=name]").fill(nombre)
    formulario.locator("input[name=source]").fill("PROBE-E2E")
    formulario.locator("select[name=business_unit_id]").select_option(str(estado["unidad"]))
    capturas.foto(page, "d3_lead_sin_producto_ni_ubicacion")
    enviar_y_esperar(page, formulario)
    verificar(
        "D-3 Leads: alta sin producto ni ubicación se guarda, sin 500",
        "/leads" in page.url and nombre in page.content(),
        page.url,
    )
    fila = consulta("SELECT id, stage FROM leads WHERE name=%s", (nombre,))
    verificar("D-3 Leads: la etapa queda guardada con su nombre", bool(fila) and "{" not in str(fila[0][1]), fila)
    if not fila:
        raise RuntimeError("el lead no quedó guardado")
    estado["lead"] = fila[0][0]

    page.goto(BASE_URL + f"/leads/{estado['lead']}")
    formulario = page.locator("form[action*='/update']")
    formulario.locator("input[name=owner_name]").fill("PROBE-E2E responsable")
    with page.expect_response(lambda r: "/update" in r.url and r.request.method == "POST") as respuesta:
        formulario.locator("button[type=submit], button:not([type])").first.click()
    page.wait_for_load_state("networkidle")
    verificar("D-2 Leads: guardar la acción del lead sin 400", respuesta.value.status < 400, respuesta.value.status)

    formulario = page.locator("form[action*='/interactions/new']")
    formulario.locator("input[name=type]").fill("PROBE-E2E llamada")
    formulario.locator("textarea[name=notes]").fill("PROBE-E2E nota")
    with page.expect_response(lambda r: "/interactions/new" in r.url and r.request.method == "POST") as respuesta:
        formulario.locator("button[type=submit], button:not([type])").first.click()
    page.wait_for_load_state("networkidle")
    verificar("D-2 Leads: registrar una interacción sin 400", respuesta.value.status < 400, respuesta.value.status)
    capturas.foto(page, "d2_lead_acciones")


def crear_orden(page, estado, cantidad):
    page.goto(BASE_URL + "/compras/orden-nueva")
    formulario = page.locator("form:has(input[name=supplier_text])")
    formulario.locator("input[name=supplier_text]").fill("PROBE-E2E Proveedor")
    formulario.locator("select[name=location_id]").select_option(str(estado["loc_a"]))
    formulario.locator("select[name=product_id]").select_option(str(estado["producto"]))
    formulario.locator("input[name=quantity]").fill(str(cantidad))
    enviar_y_esperar(page, formulario)
    return consulta("SELECT id FROM purchase_orders ORDER BY id DESC LIMIT 1")[0][0]


def compras(page, capturas, estado):
    estado["orden"] = crear_orden(page, estado, 5)
    page.goto(BASE_URL + f"/compras/{estado['orden']}")
    verificar("D-4 Compras: el detalle de la orden abre", page.locator("#formRecepcion").count() == 1)
    capturas.foto(page, "d4_detalle_orden")

    texto = recibir(page, 2)
    verificar("D-5 recepción parcial de 2 se registra y muestra lo pendiente", "Quedan 3" in texto)
    page.goto(BASE_URL + f"/compras/{estado['orden']}")
    texto = recibir(page, 4)
    verificar("D-5 recepción sobrante (4 con 3 pendientes) se bloquea", "No se puede recibir más de lo pendiente" in texto)
    capturas.foto(page, "d5_sobrante_bloqueado")
    page.goto(BASE_URL + f"/compras/{estado['orden']}")
    recibir(page, 3)
    estado_orden = consulta("SELECT status FROM purchase_orders WHERE id=%s", (estado["orden"],))[0][0]
    verificar("D-5 la orden queda recibida al completarse", estado_orden == "recibida", estado_orden)
    capturas.foto(page, "d5_orden_recibida")

    estado["orden2"] = crear_orden(page, estado, 3)
    page.goto(BASE_URL + f"/compras/{estado['orden2']}")
    page.locator("#formRecepcion input[name=quantity]").fill("3")
    page.dblclick("#btnRegistrarRecepcion")
    page.wait_for_load_state("networkidle")
    recepciones = consulta("SELECT count(*) FROM purchase_receipts WHERE purchase_order_id=%s", (estado["orden2"],))[0][0]
    verificar("D-5 doble clic: una sola recepción", recepciones == 1, recepciones)
    capturas.foto(page, "d5_doble_clic")

    stock_actual = consulta(
        "SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s",
        (estado["producto"], estado["loc_a"]),
    )
    suma = consulta(
        "SELECT coalesce(sum(quantity_received), 0) FROM purchase_receipts WHERE product_id=%s AND location_id=%s",
        (estado["producto"], estado["loc_a"]),
    )[0][0]
    verificar(
        "D-5 stock = suma de las recepciones del par",
        bool(stock_actual) and stock_actual[0][0] == suma == 8,
        f"stock={stock_actual} recepciones={suma}",
    )

    page.goto(BASE_URL + f"/compras/{estado['orden']}")
    formulario = page.locator("form:has(select[name=status])")
    formulario.locator("select[name=status]").select_option(valores_de(formulario.locator("select[name=status]"))[-1])
    enviar_y_esperar(page, formulario)
    verificar(
        "D-2 Compras: cambio de estado guarda sin 400",
        page.url.rstrip("/").endswith(f"/compras/{estado['orden']}"),
        page.url,
    )


def stock(page, capturas, estado):
    page.goto(BASE_URL + "/stock/new")
    formulario = page.locator("form:has(select[name=product_id])")
    formulario.locator("select[name=product_id]").select_option(str(estado["producto"]))
    formulario.locator("select[name=location_id]").select_option(str(estado["loc_a"]))
    formulario.locator("input[name=quantity]").fill("25")
    enviar_y_esperar(page, formulario)
    cantidad = consulta(
        "SELECT quantity FROM stock_levels WHERE product_id=%s AND location_id=%s",
        (estado["producto"], estado["loc_a"]),
    )
    verificar(
        "D-6 alta de un par existente avisa y no pisa la cantidad",
        "Ya hay stock de este producto en esa ubicación (8). Editalo o sumá la diferencia." in page.content()
        and bool(cantidad) and cantidad[0][0] == 8,
        cantidad,
    )
    capturas.foto(page, "d6_par_existente")

    page.goto(BASE_URL + "/stock/new")
    formulario = page.locator("form:has(select[name=product_id])")
    formulario.locator("select[name=product_id]").select_option(str(estado["producto"]))
    formulario.locator("select[name=location_id]").select_option(str(estado["loc_b"]))
    formulario.locator("input[name=quantity]").fill("-3")
    formulario.evaluate("(f) => { f.noValidate = true; }")
    enviar_y_esperar(page, formulario)
    verificar("D-6 cantidad negativa se rechaza con aviso", "no puede ser negativa" in page.content())
    capturas.foto(page, "d6_cantidad_negativa")


def productos(page, capturas, estado):
    page.goto(BASE_URL + "/products/new")
    formulario = page.locator("form:has(input[name=sku])")
    formulario.locator("input[name=sku]").fill(estado["sku"])
    formulario.locator("input[name=name]").fill(f"PROBE-E2E repetido {SUFIJO}")
    formulario.locator("select[name=business_unit_id]").select_option(str(estado["unidad"]))
    enviar_y_esperar(page, formulario)
    verificar("D-7 SKU duplicado: aviso «El SKU ya existe.» en el formulario", "El SKU ya existe." in page.content())
    cantidad = consulta("SELECT count(*) FROM products WHERE sku=%s", (estado["sku"],))[0][0]
    verificar("D-7 SKU duplicado: no crea un segundo producto", cantidad == 1, cantidad)
    capturas.foto(page, "d7_sku_duplicado")
    page.goto(BASE_URL + "/products/new")
    verificar("D-7 con unidades cargadas, Guardar queda habilitado", not boton_guardar_deshabilitado(page))


def objetivos(page, capturas):
    page.goto(BASE_URL + "/comercial/objetivos")
    meses = page.locator("#periodoMes option").evaluate_all("(ops) => ops.map((o) => o.textContent.trim().toLowerCase())")
    verificar("D-8 barra de período: meses en español", "enero" in meses and "febrero" in meses, meses[:4])
    verificar("D-8 Objetivos sin campos de mes del navegador (input type=month)", page.locator("input[type=month]").count() == 0)
    capturas.foto(page, "d8_objetivos_mes_espanol")


def avisos(page, capturas):
    for ruta in ("/tesoreria", "/rrhh/adelantos", "/compras"):
        page.goto(BASE_URL + ruta)
        verificar(f"D-9 {ruta}: sin prefijo técnico «Error:» en pantalla", "Error:" not in page.inner_text("body"))
    capturas.foto(page, "d9_avisos_tesoreria_rrhh_compras")


def main():
    parser = argparse.ArgumentParser(description="Recorrido E2E de formularios (D-1 a D-9).")
    parser.add_argument("--etiqueta", default="despues", help="carpeta de capturas dentro de E2E_CAPTURAS")
    argumentos = parser.parse_args()
    if not ADMIN_PASSWORD or not DB_URL:
        print("Faltan E2E_ADMIN_PASSWORD o E2E_DATABASE_URL.")
        return 1

    capturas = Capturas(argumentos.etiqueta)
    estado = {}
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM, args=["--no-sandbox"])
        contexto = navegador.new_context(
            locale="es-AR", timezone_id="America/Argentina/Buenos_Aires", viewport={"width": 1280, "height": 900}
        )
        page = contexto.new_page()
        page.set_default_timeout(15000)
        page.on("response", registrar_respuesta)
        page.on("console", registrar_consola)
        paso("login", lambda: login(page), page, capturas)
        paso("estados vacíos (D-7)", lambda: fase_vacia(page, capturas), page, capturas)
        paso("catálogo PROBE", lambda: preparar_catalogo(page, capturas, estado), page, capturas)
        paso("ventas (D-1, D-2)", lambda: ventas(page, capturas, estado), page, capturas)
        paso("leads (D-2, D-3)", lambda: leads(page, capturas, estado), page, capturas)
        paso("compras (D-2, D-4, D-5)", lambda: compras(page, capturas, estado), page, capturas)
        paso("stock (D-6)", lambda: stock(page, capturas, estado), page, capturas)
        paso("productos (D-7)", lambda: productos(page, capturas, estado), page, capturas)
        paso("objetivos (D-8)", lambda: objetivos(page, capturas), page, capturas)
        paso("avisos (D-9)", lambda: avisos(page, capturas), page, capturas)
        navegador.close()

    quinientos = [r for r in RESPUESTAS_ERROR if r["status"] >= 500]
    cuatrocientos = [r for r in RESPUESTAS_ERROR if r["status"] < 500]
    verificar("red: ninguna respuesta 5xx", not quinientos, quinientos[:3])
    verificar(
        f"red: solo los {RECHAZOS_ESPERADOS} rechazos intencionales responden 4xx",
        len(cuatrocientos) == RECHAZOS_ESPERADOS,
        cuatrocientos,
    )
    verificar("consola: sin errores", not ERRORES_CONSOLA, ERRORES_CONSOLA[:3])
    fallas = [r for r in RESULTADOS if not r["ok"]]
    with open(os.path.join(capturas.carpeta, "informe.json"), "w", encoding="utf-8") as archivo:
        json.dump(
            {
                "etiqueta": argumentos.etiqueta,
                "resultados": RESULTADOS,
                "respuestas_error": RESPUESTAS_ERROR,
                "consola_error": ERRORES_CONSOLA,
            },
            archivo,
            ensure_ascii=False,
            indent=2,
        )
    print(f"RESUMEN: {len(RESULTADOS) - len(fallas)} OK, {len(fallas)} fallas. Capturas: {capturas.carpeta}")
    return 0 if not fallas else 1


if __name__ == "__main__":
    sys.exit(main())
