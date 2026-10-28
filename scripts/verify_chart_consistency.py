#!/usr/bin/env python3
"""Verifica que todos los gráficos de APP360 compartan la misma apariencia.

Recorre los paneles con gráficos en un navegador real (Playwright) y compara
la configuración efectiva de cada instancia de Chart.js. Falla si dos gráficos
difieren en leyenda, tooltip, ejes, tipografía o animación.

Uso:
    python scripts/verify_chart_consistency.py
    python scripts/verify_chart_consistency.py --base-url http://127.0.0.1:5001

Requiere el servidor de desarrollo corriendo y Playwright instalado.
"""
from __future__ import annotations

import argparse
import json
import sys

PANELS = [
    ("/bi", "Resultado comercial"),
    ("/panel-ejecutivo", "Panel ejecutivo"),
    ("/dashboard-financiero", "Tesorería (financiero)"),
    ("/gastos", "Gastos"),
    ("/tesoreria", "Tesorería"),
    ("/compras", "Compras"),
    ("/rrhh/ausentismo", "Ausentismo"),
    ("/dashboard-comercial", "Ventas"),
    ("/comercial/performance-vendedores", "Performance de vendedores"),
]

# Propiedades que deben ser idénticas en todos los gráficos.
# `type` y `legend` se excluyen: varían por diseño (dona siempre con leyenda,
# serie única sin leyenda).
SIGNATURE_JS = """
() => {
  const charts = [...document.querySelectorAll('canvas')]
    .map(cv => window.Chart.getChart(cv))
    .filter(Boolean);
  return charts.map(c => ({
    id: c.canvas?.id || '(sin id)',
    type: c.config.type,
    legend: c.options.plugins?.legend?.display === false
      ? 'hidden'
      : (c.options.plugins?.legend?.position || 'default'),
    legendColor: c.options.plugins?.legend?.labels?.color,
    legendPointStyle: c.options.plugins?.legend?.labels?.usePointStyle,
    legendBoxWidth: c.options.plugins?.legend?.labels?.boxWidth,
    tickColor: c.options.scales?.y?.ticks?.color,
    tickSize: c.options.scales?.y?.ticks?.font?.size,
    gridColor: c.options.scales?.y?.grid?.color,
    tooltipBg: c.options.plugins?.tooltip?.backgroundColor,
    tooltipRadius: c.options.plugins?.tooltip?.cornerRadius,
    tooltipPadding: c.options.plugins?.tooltip?.padding,
    animation: c.options.animation,
    responsive: c.options.responsive,
    maintainAspectRatio: c.options.maintainAspectRatio,
    hasDataLabels: (c.config.plugins || []).some(p => p.id === 'app360DataLabels')
  }));
}
"""

COMPARED_KEYS = [
    "legendColor",
    "legendPointStyle",
    "legendBoxWidth",
    "tickColor",
    "tickSize",
    "gridColor",
    "tooltipBg",
    "tooltipRadius",
    "tooltipPadding",
    "animation",
    "responsive",
    "maintainAspectRatio",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--user", default=None, help="Usuario (default: ADMIN_USERNAME del entorno)")
    parser.add_argument("--password", default=None, help="Contraseña (default: ADMIN_PASSWORD del entorno)")
    parser.add_argument("--json", action="store_true", help="Salida JSON completa")
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: falta playwright. Instalar con: pip install playwright && playwright install chromium")
        return 2

    import os
    from pathlib import Path

    def _env_value(key: str) -> str | None:
        """Lee una clave del entorno o del .env sin ejecutar el archivo."""
        if os.getenv(key):
            return os.getenv(key)
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if not env_path.exists():
            return None
        for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
        return None

    user = args.user or _env_value("ADMIN_USERNAME") or "admin"
    password = args.password or _env_value("ADMIN_PASSWORD")
    # El servidor de desarrollo usa admin/admin por defecto (scripts/dev_backend.sh).
    candidates = [c for c in [password, "admin"] if c]
    if not candidates:
        print("ERROR: falta contraseña. Usar --password o definir ADMIN_PASSWORD.")
        return 2

    report: dict[str, list[dict]] = {}
    errors: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # Login: los paneles requieren sesión.
        logged_in = False
        for candidate in candidates:
            page.goto(args.base_url + "/", wait_until="networkidle", timeout=30000)
            page.fill('input[name="username"]', user)
            page.fill('input[name="password"]', candidate)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=30000)
            if "logout" in page.content():
                logged_in = True
                break
        if not logged_in:
            print("ERROR: no se pudo iniciar sesión. Revisar credenciales (--user/--password).")
            browser.close()
            return 2

        for path, label in PANELS:
            page_errors: list[str] = []

            def _capture(error, bucket=page_errors):
                bucket.append(str(error))

            page.on("pageerror", _capture)
            try:
                page.goto(args.base_url + path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(1800)
                charts = page.evaluate(SIGNATURE_JS)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{label} ({path}): no se pudo cargar — {exc}")
                continue
            finally:
                page.remove_listener("pageerror", _capture)

            if page_errors:
                errors.append(f"{label} ({path}): errores JS — {'; '.join(page_errors)}")

            report[path] = charts

        browser.close()

    # Comparar todas las firmas contra la primera encontrada.
    all_charts = [(path, chart) for path, charts in report.items() for chart in charts]
    if not all_charts:
        print("ERROR: no se encontró ningún gráfico. ¿Está el servidor corriendo?")
        return 1

    reference_path, reference = all_charts[0]
    mismatches: list[str] = []
    for path, chart in all_charts:
        for key in COMPARED_KEYS:
            if chart.get(key) != reference.get(key):
                mismatches.append(
                    f"{path} · {chart['id']} · {key}: {chart.get(key)!r} != {reference.get(key)!r} "
                    f"(referencia: {reference_path} · {reference['id']})"
                )

    if args.json:
        print(json.dumps({"report": report, "mismatches": mismatches, "errors": errors}, indent=2, ensure_ascii=False))
    else:
        total = len(all_charts)
        print(f"Gráficos analizados: {total} en {len(report)} paneles")
        for path, charts in report.items():
            ids = ", ".join(c["id"] for c in charts) or "(ninguno)"
            print(f"  {path}: {len(charts)} — {ids}")
        print()

        if errors:
            print("Errores de carga:")
            for err in errors:
                print(f"  ✗ {err}")
            print()

        if mismatches:
            print(f"Inconsistencias: {len(mismatches)}")
            for item in mismatches:
                print(f"  ✗ {item}")
        else:
            print("✓ Todos los gráficos comparten leyenda, tooltip, ejes, tipografía y animación.")

    return 1 if (mismatches or errors) else 0


if __name__ == "__main__":
    sys.exit(main())
