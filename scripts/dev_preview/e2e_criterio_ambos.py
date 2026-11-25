"""E2E de navegador: criterio de clientes PRE / FAC / AMBOS y etiquetas de origen en Seguimiento.

Datos 100% sintéticos (rotulados «E2E» y con número de comprobante E2E-*), solo sobre la base local
127.0.0.1:55432 (la que indica DATABASE_URL). Idempotente: borra y vuelve a crear sus propias filas.

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

from playwright.sync_api import sync_playwright
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:5055").rstrip("/")
ADMIN_USER = os.environ.get("E2E_ADMIN_USER", "admin")
# Clave de prueba SOLO-DEV del entorno E2E local; no es una credencial real.
ADMIN_PASSWORD = os.environ.get("E2E_ADMIN_PASSWORD", "e2e-admin-ficticio")
CHROMIUM = os.environ.get("E2E_CHROMIUM", "/home/hermes/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome")
CAPTURAS = os.environ.get("E2E_CAPTURAS", "/tmp/e2e-criterio-ambos")
VIEWPORT = {"width": 1366, "height": 768}

TIVANO = "E2E TIVANO SIMULADO SRL"
SOLO_PRE = "E2E SOLO PRE SRL"
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
]

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


def fila(page, nombre):
    return page.locator("#com-clientes tbody tr", has=page.locator("button.com-name", has_text=nombre)).first


def abrir_criterio_y_buscar(page):
    page.goto(BASE_URL + "/ventas/criterio-clientes", wait_until="domcontentloaded")
    page.wait_for_selector("#criterio-clientes-body .criterio-row-check", timeout=20000)
    page.fill("#criterio-buscar", "E2E")
    page.wait_for_timeout(200)


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
        page.on("requestfailed", lambda r: errores_red.append(f"FALLO {r.url}"))
        try:
            verificar("login con admin", login(page))

            if args.modo == "antes":
                abrir_criterio_y_buscar(page)
                page.screenshot(path=os.path.join(CAPTURAS, "antes-criterio-clientes.png"))
                abrir_seguimiento(page)
                page.screenshot(path=os.path.join(CAPTURAS, "antes-seguimiento.png"))
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
            page.screenshot(path=os.path.join(CAPTURAS, "seguimiento-antes-modo-pre.png"))

            # 2) Criterio de clientes: pasar el cliente a AMBOS desde la pantalla.
            abrir_criterio_y_buscar(page)
            opciones = page.locator("#criterio-modo option").all_inner_texts()
            verificar("selector con tres modos", len(opciones) == 3 and any("ambos" in o.lower() for o in opciones), opciones)
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
            verificar("AMBOS: etiquetas PRE y FAC en la fila", "PRE" in etiquetas and "FAC" in etiquetas, etiquetas)
            verificar("AMBOS: PRE 2 op. $1.500", "2 op." in txt and "1.500" in txt, txt)
            verificar("AMBOS: FAC 2 op. $3.800 (la NC no suma)", "3.800" in txt and "3.500" not in txt, txt)
            ultima = tivano.locator("td").nth(3)
            verificar("AMBOS: última compra = la FCM más reciente, con etiqueta FAC",
                      "FAC" in ultima.inner_text() and D(3).strftime("%d/%m/%Y") in ultima.inner_text(), ultima.inner_text())
            solo = fila(page, SOLO_PRE)
            verificar("cliente solo PRE se ve como antes (sin etiquetas, $700)",
                      solo.locator(".com-origen").count() == 0 and "700" in solo.inner_text(), solo.inner_text())
            page.screenshot(path=os.path.join(CAPTURAS, "seguimiento-despues-ambos.png"))

            # 4) Detalle: operaciones con PRE / FAC / NC; la NC se muestra y no suma.
            tivano.locator("button.com-name").click()
            page.wait_for_selector("#com-detalle-content table")
            page.wait_for_load_state("networkidle")
            detalle = page.locator("#com-detalle-content")
            filas_ops = detalle.locator("table").first.locator("tbody tr").all_inner_texts()
            tipos = [re.search(r"\b(PRE|FAC|NC)\b", f).group(1) for f in filas_ops if re.search(r"\b(PRE|FAC|NC)\b", f)]
            verificar("detalle: operaciones PRE, FAC y NC visibles", set(tipos) == {"PRE", "FAC", "NC"} and len(tipos) == 5, filas_ops)
            nc = [f for f in filas_ops if "NC" in f]
            verificar("detalle: la NC lleva su importe negativo y su número", bool(nc) and "E2E-N1" in nc[0] and "300" in nc[0], nc)
            tabla_tipos = detalle.locator("table").nth(1).inner_text()
            verificar("detalle: totales discriminados por tipo", "1.500" in tabla_tipos and "3.800" in tabla_tipos, tabla_tipos)
            verificar("detalle: importe del período = PRE + FAC (5.300)", "5.300" in detalle.inner_text(), detalle.inner_text()[:300])
            page.screenshot(path=os.path.join(CAPTURAS, "seguimiento-detalle-ambos.png"))
            page.keyboard.press("Escape")

            # 5) Sin desborde horizontal a 1366×768 en ambas pantallas.
            desborde = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            verificar("Seguimiento sin desborde horizontal a 1366×768", desborde <= 0, desborde)
            abrir_criterio_y_buscar(page)
            desborde = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            verificar("Criterio sin desborde horizontal a 1366×768", desborde <= 0, desborde)

            verificar("consola y red sin errores", not errores_consola and not errores_red,
                      json.dumps(errores_consola + errores_red)[:600])
        finally:
            navegador.close()
            with open(os.path.join(CAPTURAS, f"informe-{args.modo}.json"), "w", encoding="utf-8") as fh:
                json.dump(resultados, fh, ensure_ascii=False, indent=1)
    print(f"\nTOTAL {len(resultados)} · FALLAS {len(fallas)} · capturas {CAPTURAS}", flush=True)
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
