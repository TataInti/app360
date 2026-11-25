"""E2E de navegador: criterio de clientes PRE / FAC / AMBOS y etiquetas de origen en Seguimiento.

Datos 100% sintéticos (rotulados «E2E» y con número de comprobante E2E-*), solo sobre la base local
127.0.0.1:55432 (la que indica DATABASE_URL). Idempotente: borra y vuelve a crear sus propias filas.

Desplegable de operaciones (parte 2): lista de 20 por vez con carga perezosa, interruptor «Ver todos los
comprobantes», «Ver más», filtro de período, vendedor y estado de error con reintento.

Uso (instancia local ya levantada y sembrada con seed_demo.py):
    DATABASE_URL=... E2E_BASE_URL=http://127.0.0.1:5100 E2E_CAPTURAS=/ruta \
    python scripts/dev_preview/e2e_criterio_ambos.py            # prueba completa (--modo despues)
    python scripts/dev_preview/e2e_criterio_ambos.py --modo antes   # solo capturas de la versión anterior

Sale con código 1 si algo falla.
"""
import argparse
import json
import os
import re
import sys
from datetime import date, timedelta
from urllib.parse import urlparse

from playwright.sync_api import expect, sync_playwright
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
# Clave de prueba SOLO-DEV del entorno E2E local; no es una credencial real.
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio")
CLAVE_VENTAS = os.environ.get("E2E_CLAVE_VENTAS", "e2e-ventas-ficticia")  # usuario sintético ventas.demo
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/home/hermes/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/tmp/e2e-criterio-ambos")
VIEWPORT = {"width": 1366, "height": 768}

TIVANO = "E2E TIVANO SIMULADO SRL"
SOLO_PRE = "E2E SOLO PRE SRL"
MUCHAS = "E2E MUCHAS OPERACIONES SRL"
HOY = date.today()
D = lambda dias: HOY - timedelta(days=dias)  # noqa: E731
DESDE, HASTA = D(20), HOY

# (cliente, comprobante, nro, dias atrás, producto, importe)
LINEAS = [
    (TIVANO, "PRE", "E2E-P1", 12, "E2E Queso", 1000),
    (TIVANO, "PRE", "E2E-P2", 8, "E2E Queso", 500),
    (TIVANO, "FCM", "E2E-F1", 5, "E2E Queso", 2000),
    (TIVANO, "FCM", "E2E-F1", 5, "E2E Leche", 1000),
    (TIVANO, "FCM", "E2E-F2", 3, "E2E Leche", 800),
    (TIVANO, "NPF", "E2E-N1", 2, "E2E Leche", -300),
    (SOLO_PRE, "PRE", "E2E-P3", 4, "E2E Queso", 700),
    (SOLO_PRE, "FCM", "E2E-F3", 1, "E2E Queso", 50),
    (TIVANO, None, "E2E-S1", 1, "E2E Sin tipo", 25),  # línea sin código de comprobante: solo con «todos»
]
# Cliente AMBOS con 25 operaciones PRE/FCM + 1 NPF, para probar «Ver más» (20 + 6).
LINEAS += [(MUCHAS, "PRE" if i % 2 == 0 else "FCM", f"E2E-M{i:02}", 1 + (i % 18), "E2E Queso", 10 + i) for i in range(25)]
LINEAS += [(MUCHAS, "NPF", "E2E-MN", 1, "E2E Queso", -5)]

fallas = []
resultados = []


def verificar(nombre, ok, detalle=""):
    resultados.append({"verificacion": nombre, "ok": bool(ok), "detalle": str(detalle)})
    print(("OK    " if ok else "FALLA ") + nombre + (f" — {detalle}" if detalle and not ok else ""), flush=True)
    if not ok:
        fallas.append(nombre)


def motor():
    url = os.environ.get("DATABASE_URL", "")
    parsed = make_url(url)
    if parsed.host not in {"127.0.0.1", "localhost"} or parsed.port != 55432:
        raise SystemExit("Rechazado: este E2E solo escribe en la base local 127.0.0.1:55432.")
    return create_engine(url)


def sembrar(engine, criterio):
    with engine.begin() as con:
        con.execute(text("DELETE FROM stg_sabiogo_ventas WHERE nro_comprob LIKE 'E2E-%'"))
        con.execute(text("DELETE FROM comercial_cliente_criterio WHERE cliente LIKE 'E2E %'"))
        for cliente, comp, nro, dias, producto, importe in LINEAS:
            con.execute(text(
                "INSERT INTO stg_sabiogo_ventas (fecha, origen, codigo, producto, cliente, vendedor, comprobante,"
                " nro_comprob, subtot, cajas, kilos, estado) VALUES (:f, 'CARNES', :c, :p, :cl, 'DEMO ANA', :comp,"
                " :n, :i, 1, 10, 'procesado')"),
                dict(f=D(dias), c=f"{nro}-{producto}", p=producto, cl=cliente, comp=comp, n=nro, i=importe))
        con.execute(text("INSERT INTO comercial_cliente_criterio (cliente, criterio, actualizado_por, actualizado_en)"
                         " VALUES (:c, 'AMBOS', 'E2E', now())"), dict(c=MUCHAS))
        if criterio:
            con.execute(text("INSERT INTO comercial_cliente_criterio (cliente, criterio, actualizado_por, actualizado_en)"
                             " VALUES (:c, :k, 'E2E', now())"), dict(c=TIVANO, k=criterio))


def numeros(texto):
    return re.sub(r"[^\d]", "", texto or "")


def login(page):
    page.goto(BASE_URL + "/", wait_until="domcontentloaded")
    page.fill("#username", ADMIN_USER)
    page.fill("#password", ADMIN_PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")
    return urlparse(page.url).path != "/"


def url_seguimiento():
    return (f"{BASE_URL}/comercial/seguimiento-clientes?fecha_desde={DESDE}&fecha_hasta={HASTA}"
            f"&empresa=TODAS&vista=todos&q=E2E")


def abrir_seguimiento(page):
    page.goto(url_seguimiento(), wait_until="domcontentloaded")
    page.wait_for_selector("#com-clientes table", timeout=20000)
    page.wait_for_load_state("networkidle")


def captura_lista(page, nombre):
    """Captura la lista de clientes centrada en el viewport (a 1366×768 queda bajo el pliegue)."""
    page.evaluate("document.getElementById('com-clientes').scrollIntoView({block: 'center'})")
    page.wait_for_timeout(200)
    page.screenshot(path=os.path.join(CAPTURAS, nombre))


def fila(page, nombre):
    return page.locator("#com-clientes tbody tr", has=page.locator("button.com-name", has_text=nombre)).first


def abrir_criterio_y_buscar(page):
    page.goto(BASE_URL + "/ventas/criterio-clientes", wait_until="domcontentloaded")
    page.wait_for_selector("#criterio-clientes-body .criterio-row-check", timeout=20000)
    page.fill("#criterio-buscar", "E2E")
    page.wait_for_timeout(200)


def abrir_detalle(page, nombre):
    """Abre el desplegable del cliente y espera a que termine de cargar su lista de operaciones."""
    page.locator("#com-clientes tbody tr", has=page.locator("button.com-name", has_text=nombre)).first \
        .locator("button.com-name").click()
    page.wait_for_selector("#com-ops-title")
    esperar_lista(page)


def esperar_lista(page):
    lista = page.locator("#com-detalle-content section[aria-labelledby=com-ops-title] [aria-live=polite]")
    expect(lista).to_have_attribute("aria-busy", "false", timeout=10000)
    expect(lista.locator("table, .com-empty").first).to_be_visible(timeout=10000)


def esperar_filas(page, cantidad):
    try:
        expect(page.locator("#com-detalle-content section[aria-labelledby=com-ops-title] tbody tr")).to_have_count(cantidad, timeout=8000)
    except AssertionError as error:
        raise AssertionError(f"se esperaban {cantidad} filas y hay {filas_lista(page)}") from error


def filas_lista(page):
    return page.locator("#com-detalle-content section[aria-labelledby=com-ops-title] tbody tr").all_inner_texts()


def cerrar_detalle(page):
    page.keyboard.press("Escape")
    page.wait_for_selector("#com-detalle", state="hidden")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--modo", choices=("antes", "despues"), default="despues")
    args = parser.parse_args()
    os.makedirs(CAPTURAS, exist_ok=True)
    engine = motor()
    sembrar(engine, None)
    errores_consola, errores_red = [], []

    with sync_playwright() as pw:
        chromium_args = ["--no-sandbox"]
        if urlparse(BASE_URL).port:
            chromium_args.append(f"--explicitly-allowed-ports={urlparse(BASE_URL).port}")
        navegador = pw.chromium.launch(executable_path=CHROMIUM, args=chromium_args)
        ctx = navegador.new_context(locale="es-AR", viewport=VIEWPORT)
        page = ctx.new_page()
        page.on("console", lambda m: errores_consola.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errores_consola.append(str(e)))
        page.on("response", lambda r: errores_red.append(f"{r.status} {r.url}") if r.status >= 400 else None)
        pedidos_ops = []
        page.on("request", lambda r: pedidos_ops.append(r.url) if "/seguimiento-clientes/operaciones" in r.url else None)
        page.on("requestfailed", lambda r: errores_red.append(f"FALLO {r.url}"))
        try:
            verificar("login con admin", login(page))

            if args.modo == "antes":
                abrir_criterio_y_buscar(page)
                page.screenshot(path=os.path.join(CAPTURAS, "antes-criterio-clientes.png"))
                abrir_seguimiento(page)
                captura_lista(page, "antes-seguimiento.png")
                verificar("consola y red sin errores", not errores_consola and not errores_red,
                          json.dumps(errores_consola + errores_red)[:500])
                return

            # 1) Cliente sin fila = PRE: Tivano solo cuenta PRE y no muestra etiquetas.
            abrir_seguimiento(page)
            tivano = fila(page, TIVANO)
            txt = tivano.inner_text()
            verificar("sin fila: el cliente se ve como PRE ($1.500, solo presupuestos)", "1.500" in txt and "3.800" not in txt, txt)
            verificar("sin fila: sin etiquetas de origen", tivano.locator(".com-origen").count() == 0)
            verificar("sin fila: última compra = último PRE", numeros(txt).find(numeros(D(8).strftime("%d/%m/%Y"))) >= 0, txt)
            captura_lista(page, "seguimiento-antes-modo-pre.png")

            # 2) Criterio de clientes: pasar el cliente a AMBOS desde la pantalla.
            abrir_criterio_y_buscar(page)
            opciones = page.locator("#criterio-modo option").all_inner_texts()
            verificar("selector con tres modos", len(opciones) == 3 and any("ambos" in o.lower() for o in opciones), str(opciones))
            page.locator(f'.criterio-row-check[data-cliente="{TIVANO}"]').check()
            page.select_option("#criterio-modo", "AMBOS")
            page.screenshot(path=os.path.join(CAPTURAS, "criterio-clientes-selector.png"))
            with page.expect_response(lambda r: r.url.endswith("/ventas/criterio-clientes/guardar")) as resp:
                page.click("#criterio-aplicar")
            verificar("guardar AMBOS responde 200", resp.value.status == 200, resp.value.status)
            page.wait_for_selector("#criterio-mensaje:has-text('actualizados')")
            celda = page.locator("#criterio-clientes-body tr", has_text=TIVANO).inner_text()
            verificar("la pantalla muestra «Ambos» para el cliente", "Ambos" in celda, celda)
            page.screenshot(path=os.path.join(CAPTURAS, "criterio-clientes-ambos-guardado.png"))
            page.reload(wait_until="networkidle")
            page.fill("#criterio-buscar", "E2E")
            page.wait_for_timeout(200)
            celda2 = page.locator("#criterio-clientes-body tr", has_text=TIVANO).inner_text()
            verificar("lectura de vuelta tras recargar: AMBOS persiste", "Ambos" in celda2, celda2)
            solo_pre_celda = page.locator("#criterio-clientes-body tr", has_text=SOLO_PRE).inner_text()
            verificar("otro cliente sigue en Presupuesto", "Presupuesto" in solo_pre_celda, solo_pre_celda)

            # 3) Seguimiento: etiquetas, totales por tipo y última compra.
            abrir_seguimiento(page)
            tivano = fila(page, TIVANO)
            txt = tivano.inner_text()
            etiquetas = tivano.locator(".com-origen").all_inner_texts()
            verificar("AMBOS: etiquetas PRE y FAC en la fila", "PRE" in etiquetas and "FAC" in etiquetas, str(etiquetas))
            verificar("AMBOS: PRE 2 op. $1.500", "2 op." in txt and "1.500" in txt, txt)
            verificar("AMBOS: FAC 2 op. $3.800 (la NC no suma)", "3.800" in txt and "3.500" not in txt, txt)
            ultima = tivano.locator("td").nth(3)
            verificar("AMBOS: última compra = la FCM más reciente, con etiqueta FAC",
                      "FAC" in ultima.inner_text() and D(3).strftime("%d/%m/%Y") in ultima.inner_text(), ultima.inner_text())
            solo = fila(page, SOLO_PRE)
            verificar("cliente solo PRE se ve como antes (sin etiquetas, $700)",
                      solo.locator(".com-origen").count() == 0 and "700" in solo.inner_text(), solo.inner_text())
            captura_lista(page, "seguimiento-despues-ambos.png")

            # 4) Detalle: operaciones con PRE / FAC / NC; la NC se muestra y no suma.
            tivano.locator("button.com-name").click()
            page.wait_for_selector("#com-detalle-content table")
            page.wait_for_load_state("networkidle")
            detalle = page.locator("#com-detalle-content")
            filas_ops = detalle.locator("table", has=page.locator("th", has_text="Comprobante")).locator("tbody tr").all_inner_texts()
            tipos = [m.group(1) for m in (re.search(r"\b(PRE|FAC|NC)\b", f) for f in filas_ops) if m]
            verificar("detalle: operaciones PRE, FAC y NC visibles", set(tipos) == {"PRE", "FAC", "NC"} and len(tipos) == 5, str(filas_ops))
            nc = [f for f in filas_ops if "NC" in f]
            verificar("detalle: la NC lleva su importe negativo y su número", bool(nc) and "E2E-N1" in nc[0] and "-$" in nc[0] and "300" in nc[0], str(nc))
            tabla_tipos = detalle.locator("table", has=page.locator("th", has_text="Operaciones")).inner_text()
            verificar("detalle: totales discriminados por tipo", "1.500" in tabla_tipos and "3.800" in tabla_tipos, tabla_tipos)
            verificar("detalle: importe del período = PRE + FAC (5.300)", "5.300" in detalle.inner_text(), detalle.inner_text()[:300])
            page.screenshot(path=os.path.join(CAPTURAS, "seguimiento-detalle-ambos.png"))
            # 4b) Desplegable (parte 2): lista perezosa de operaciones, interruptor y textos.
            verificar("operaciones: se pidieron recién al abrir el desplegable (1 pedido, solo de ese cliente)",
                      len(pedidos_ops) == 1 and "cliente=" in pedidos_ops[0] and "modo=criterio" in pedidos_ops[0], str(pedidos_ops))
            interruptor = page.locator("#com-ops-todos")
            verificar("interruptor «Ver todos los comprobantes» apagado por defecto, con ayuda",
                      not interruptor.is_checked() and "Ver todos los comprobantes" in detalle.inner_text()
                      and "tal como están en SabioGo" in detalle.inner_text(), detalle.inner_text()[:200])
            verificar("texto de totales según criterio bajo la lista",
                      "Los totales del panel cuentan según el criterio del cliente" in detalle.inner_text())
            detalle.locator("section[aria-labelledby=com-ops-title]").scroll_into_view_if_needed()
            page.evaluate("document.querySelector('#com-detalle').scrollTop = document.querySelector('#com-ops-title').offsetTop - 60")
            page.screenshot(path=os.path.join(CAPTURAS, "desplegable-abierto-sin-interruptor.png"))
            interruptor.focus()
            page.keyboard.press("Space")  # accesible por teclado
            esperar_lista(page)
            esperar_filas(page, 6)
            todas = filas_lista(page)
            verificar("interruptor activo: aparece también el comprobante sin código (OTRO) que el criterio excluye",
                      any("OTRO" in f and "E2E-S1" in f for f in todas) and len(todas) == 6, str(todas))
            verificar("interruptor activo: la NC sigue en negativo y marcada «No suma»",
                      any("NC" in f and "-$" in f and "No suma" in f for f in todas), str(todas))
            page.evaluate("document.querySelector('#com-detalle').scrollTop = document.querySelector('#com-ops-title').offsetTop - 60")
            page.screenshot(path=os.path.join(CAPTURAS, "desplegable-abierto-con-interruptor.png"))
            interruptor.uncheck()
            esperar_lista(page)
            verificar("al apagar el interruptor vuelve a las 5 del criterio (sin nuevo pedido: cache de la página)",
                      len(filas_lista(page)) == 5 and sum("modo=criterio" in u for u in pedidos_ops) == 1, str(pedidos_ops))
            cerrar_detalle(page)
            page.screenshot(path=os.path.join(CAPTURAS, "desplegable-cerrado.png"))

            # 4c) «Ver más»: 26 operaciones = 20 + 6.
            abrir_detalle(page, MUCHAS)
            verificar("«Ver más»: la primera carga trae 20 operaciones", len(filas_lista(page)) == 20, len(filas_lista(page)))
            mas = page.locator("#com-detalle-content button", has_text="Ver más")
            verificar("«Ver más» visible", mas.is_visible())
            mas.scroll_into_view_if_needed()
            page.screenshot(path=os.path.join(CAPTURAS, "desplegable-ver-mas.png"))
            mas.click()
            esperar_filas(page, 26)
            fechas = [f.split("\t")[0] for f in filas_lista(page)]
            verificar("«Ver más»: 26 en total, sin repetidos y de la más reciente a la más antigua",
                      len(set(filas_lista(page))) == 26 and fechas == sorted(fechas, key=lambda x: x.split("/")[::-1], reverse=True), str(fechas))
            verificar("«Ver más» desaparece al terminar la lista", not mas.is_visible())
            cerrar_detalle(page)

            # 4d) Cliente PRE: lo que excluye el criterio aparece solo con el interruptor; el estado se recuerda en la página.
            abrir_detalle(page, SOLO_PRE)
            verificar("cliente PRE: el interruptor sigue como se dejó (apagado) y se ve solo 1 PRE", len(filas_lista(page)) == 1, filas_lista(page))
            page.locator("#com-ops-todos").check()
            esperar_filas(page, 2)
            todas = filas_lista(page)
            verificar("cliente PRE con interruptor: aparece la FCM (FAC) marcada «No suma»",
                      any("FAC" in f and "E2E-F3" in f and "No suma" in f for f in todas), str(todas))
            cerrar_detalle(page)
            abrir_detalle(page, TIVANO)
            verificar("el interruptor encendido se recuerda al abrir otro cliente", page.locator("#com-ops-todos").is_checked()
                      and len(filas_lista(page)) == 6, filas_lista(page))
            page.locator("#com-ops-todos").uncheck()
            esperar_lista(page)
            cerrar_detalle(page)

            # 4e) Filtro de período de la pantalla: desde hace 8 días solo quedan P2, F2, F1 y N1.
            page.goto(url_seguimiento().replace(f"fecha_desde={DESDE}", f"fecha_desde={D(8)}"), wait_until="domcontentloaded")
            page.wait_for_selector("#com-clientes table")
            abrir_detalle(page, TIVANO)
            nros = [f for f in filas_lista(page)]
            verificar("filtro de período: el desplegable lo respeta (4 operaciones)", len(nros) == 4 and not any("E2E-P1" in f for f in nros), str(nros))
            cerrar_detalle(page)
            page.goto(url_seguimiento().replace(f"fecha_desde={DESDE}", f"fecha_desde={D(2)}").replace("&q=E2E", "&q=TIVANO"),
                      wait_until="domcontentloaded")
            page.wait_for_selector("#com-clientes table")
            abrir_detalle(page, TIVANO)
            verificar("filtro de período: solo la NC del último día", len(filas_lista(page)) == 1, filas_lista(page))
            cerrar_detalle(page)
            page.goto(url_seguimiento().replace(f"fecha_desde={DESDE}", f"fecha_desde={D(60)}")
                      .replace(f"fecha_hasta={HASTA}", f"fecha_hasta={D(40)}").replace("&q=E2E", "&q=SOLO PRE"),
                      wait_until="domcontentloaded")
            page.wait_for_selector("#com-clientes", state="attached")
            page.wait_for_load_state("networkidle")
            sin_filas = page.locator("#com-clientes").inner_text()
            verificar("período sin compras: la lista lo dice sin errores", "No hay clientes" in sin_filas or SOLO_PRE not in sin_filas, sin_filas[:120])

            # 4f) Vendedor: usuario de ventas sintético; el filtro de vendedor de la pantalla se respeta.
            ctx_v = navegador.new_context(locale="es-AR", viewport=VIEWPORT)
            pv = ctx_v.new_page()
            errores_v = []
            pv.on("console", lambda m: errores_v.append(m.text) if m.type == "error" else None)
            pv.on("pageerror", lambda e: errores_v.append(str(e)))
            pv.goto(BASE_URL + "/", wait_until="domcontentloaded")
            pv.fill("#username", "ventas.demo"); pv.fill("#password", CLAVE_VENTAS)
            pv.click("button[type=submit]"); pv.wait_for_load_state("networkidle")
            propio = url_seguimiento() + "&vendedor=Vendedora Demo Ana"
            pv.goto(propio, wait_until="domcontentloaded")
            pv.wait_for_selector("#com-clientes table")
            abrir_detalle(pv, TIVANO)
            verificar("vendedor propio (filtro Vendedora Demo Ana): ve las 5 operaciones del cliente", len(filas_lista(pv)) == 5, filas_lista(pv))
            ajeno = pv.request.get(f"{BASE_URL}/api/comercial/seguimiento-clientes/operaciones?cliente={TIVANO.replace(' ', '%20')}"
                                   f"&fecha_desde={DESDE}&fecha_hasta={HASTA}&vendedor=Vendedor%20Demo%20Bruno")
            verificar("con el filtro de otro vendedor el cliente no trae operaciones (200 con lista vacía)",
                      ajeno.status == 200 and ajeno.json()["operaciones"] == [], ajeno.text()[:200])
            anonimo = ctx_v.browser.new_context().request.get(f"{BASE_URL}/api/comercial/seguimiento-clientes/operaciones?cliente=x")
            verificar("sin sesión: 401 JSON", anonimo.status == 401, anonimo.status)
            verificar("usuario de ventas: sin errores de consola", not errores_v, str(errores_v))
            ctx_v.close()

            # 5) Sin desborde horizontal a 1366×768 en ambas pantallas.
            desborde = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            verificar("Seguimiento sin desborde horizontal a 1366×768", desborde <= 0, desborde)
            abrir_criterio_y_buscar(page)
            desborde = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            verificar("Criterio sin desborde horizontal a 1366×768", desborde <= 0, desborde)

            verificar("consola y red sin errores", not errores_consola and not errores_red,
                      json.dumps(errores_consola + errores_red)[:600])

            # 6) Error de red al pedir las operaciones: mensaje en español y reintento (provocado a propósito).
            abrir_seguimiento(page)
            page.route("**/seguimiento-clientes/operaciones*", lambda ruta: ruta.abort())
            page.locator("#com-clientes tbody tr", has=page.locator("button.com-name", has_text=TIVANO)).first.locator("button.com-name").click()
            page.wait_for_selector("#com-detalle-content button:has-text('Reintentar')")
            texto = page.locator("#com-detalle-content").inner_text()
            verificar("error de red: mensaje en español y botón Reintentar", "No se pudieron cargar las operaciones" in texto, texto[-200:])
            page.screenshot(path=os.path.join(CAPTURAS, "desplegable-error-reintento.png"))
            page.unroute("**/seguimiento-clientes/operaciones*")
            page.locator("#com-detalle-content button:has-text('Reintentar')").click()
            esperar_lista(page)
            verificar("reintento: carga las operaciones", len(filas_lista(page)) == 5, filas_lista(page))
        finally:
            navegador.close()
            with open(os.path.join(CAPTURAS, f"informe-{args.modo}.json"), "w", encoding="utf-8") as fh:
                json.dump(resultados, fh, ensure_ascii=False, indent=1)
    print(f"\nTOTAL {len(resultados)} · FALLAS {len(fallas)} · capturas {CAPTURAS}", flush=True)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
