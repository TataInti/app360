#!/usr/bin/env python3
"""
sync.py — Sincronizador SabioGo (Firebird) → App360 VPS

Consulta p_ventas_globales en la DB local de SabioGo y empuja los datos
al endpoint /sabiogo/api/db-sync del VPS vía HTTPS.

Uso:
  python sync.py                              # sincroniza ayer (modo normal diario)
  python sync.py --fecha 2026-06-01           # fecha específica
  python sync.py --desde 2026-05-01 --hasta 2026-05-31   # rango (catch-up)
  python sync.py --fecha 2026-06-01 --no-replace          # sin borrar previos
"""

import argparse
import configparser
import decimal
import hashlib
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

# ── Setup ─────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR / 'sync.log'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)-8s %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


# ── Config ────────────────────────────────────────────────────────────────────
def load_config() -> configparser.ConfigParser:
    cfg_path = BASE_DIR / 'config.ini'
    if not cfg_path.exists():
        log.error(f"Archivo de configuración no encontrado: {cfg_path}")
        log.error("Copiá config.ini.example → config.ini y completá los valores.")
        sys.exit(1)
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding='utf-8')
    _validate_config(cfg)
    return cfg


def _validate_config(cfg: configparser.ConfigParser):
    required = {
        'firebird': ['database', 'user', 'password'],
        'vps': ['url', 'api_key'],
    }
    for section, keys in required.items():
        if not cfg.has_section(section):
            log.error(f"Sección [{section}] faltante en config.ini")
            sys.exit(1)
        for key in keys:
            if not cfg.get(section, key, fallback='').strip():
                log.error(f"Valor requerido faltante: [{section}] {key}")
                sys.exit(1)


# ── Serialización JSON ────────────────────────────────────────────────────────
def _serialize(val):
    """Convierte tipos de Firebird a tipos JSON-seguros."""
    if val is None:
        return None
    if isinstance(val, decimal.Decimal):
        return float(val)
    if isinstance(val, (datetime, date)):
        return val.isoformat()
    if isinstance(val, bytes):
        return val.decode('utf-8', errors='replace')
    return val


def rows_to_dicts(col_names: list, raw_rows: list) -> list:
    return [
        {col: _serialize(val) for col, val in zip(col_names, row)}
        for row in raw_rows
    ]


# ── Firebird ──────────────────────────────────────────────────────────────────
def query_ventas(cfg: configparser.ConfigParser, fecha_desde: date, fecha_hasta: date):
    """Ejecuta p_ventas_globales y retorna (col_names, rows_as_dicts)."""
    try:
        import firebird.driver as fb
    except ImportError:
        log.error("Librería 'firebird-driver' no instalada. Ejecutá: pip install firebird-driver")
        sys.exit(1)

    fb_cfg = cfg['firebird']

    # Apuntar al cliente Firebird si se especificó explícitamente
    client_lib = fb_cfg.get('client_library', '').strip()
    if client_lib:
        fb.driver_config.fb_client_library.value = client_lib
        log.debug(f"Usando Firebird client: {client_lib}")

    db_conn = fb_cfg['database']
    user = fb_cfg['user']
    log.info(f"Conectando a Firebird: {db_conn} (usuario: {user})")

    with fb.connect(
        database=db_conn,
        user=user,
        password=fb_cfg['password'],
        charset='UTF8',
    ) as con:
        with con.cursor() as cur:
            sql = "SELECT * FROM p_ventas_globales(?, ?)"
            log.info(f"Ejecutando query: {fecha_desde} → {fecha_hasta}")
            cur.execute(sql, (fecha_desde, fecha_hasta))
            col_names = [desc[0].upper() for desc in cur.description]
            raw_rows = cur.fetchall()

    log.info(f"Firebird devolvió {len(raw_rows)} filas ({len(col_names)} columnas)")
    if raw_rows:
        empresas = set()
        emp_idx = col_names.index('EMPRESA') if 'EMPRESA' in col_names else None
        if emp_idx is not None:
            empresas = {row[emp_idx] for row in raw_rows}
        log.info(f"Empresas en el resultado: {empresas}")

    return col_names, raw_rows


# ── HTTP Push ─────────────────────────────────────────────────────────────────
def push_to_vps(
    cfg: configparser.ConfigParser,
    tipo: str,
    fecha: date,
    col_names: list,
    raw_rows: list,
    replace: bool = True,
) -> dict:
    """Serializa y envía los datos al VPS. Retorna la respuesta JSON."""
    vps_cfg = cfg['vps']
    base_url = vps_cfg['url'].rstrip('/')
    api_key = vps_cfg['api_key']
    timeout = int(vps_cfg.get('timeout_seconds', '120'))

    rows = rows_to_dicts(col_names, raw_rows)

    payload = {
        'tipo': tipo,
        'fecha': fecha.isoformat(),
        'rows': rows,
        'replace': replace,
    }

    # Serializar con encoder seguro antes de enviar para evitar errores de tipos
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    payload_kb = len(payload_bytes) / 1024

    url = f"{base_url}/sabiogo/api/db-sync"
    headers = {
        'X-Sync-Key': api_key,
        'Content-Type': 'application/json; charset=utf-8',
    }

    log.info(f"Enviando {len(rows)} filas ({payload_kb:.1f} KB) → {url}")

    try:
        resp = requests.post(url, data=payload_bytes, headers=headers, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        log.error(f"No se pudo conectar al VPS: {exc}")
        raise
    except requests.exceptions.Timeout:
        log.error(f"Timeout ({timeout}s) esperando respuesta del VPS")
        raise

    if not resp.ok:
        log.error(f"VPS respondió HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()

    result = resp.json()
    log.info(f"VPS result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    return result


# ── Lógica principal ──────────────────────────────────────────────────────────
def sync_fecha(cfg: configparser.ConfigParser, fecha: date, replace: bool = True) -> bool:
    """Sincroniza ventas de una fecha. Retorna True si exitoso."""
    log.info(f"{'='*60}")
    log.info(f"Sincronizando VENTAS {fecha}")
    log.info(f"{'='*60}")

    try:
        col_names, raw_rows = query_ventas(cfg, fecha, fecha)

        if not raw_rows:
            log.info(f"Sin datos de ventas para {fecha}. Nada que enviar.")
            return True

        result = push_to_vps(cfg, 'ventas', fecha, col_names, raw_rows, replace=replace)

        total = result.get('total_filas', '?')
        resultados = result.get('resultados', {})
        log.info(f"✓ Sync completado: {total} filas | detalle: {resultados}")
        return True

    except Exception as exc:
        log.error(f"✗ Error sincronizando {fecha}: {exc}", exc_info=True)
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Sincroniza ventas de SabioGo al VPS App360',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--fecha',
        metavar='YYYY-MM-DD',
        help='Sincronizar una fecha específica (default: ayer)',
    )
    parser.add_argument(
        '--desde',
        metavar='YYYY-MM-DD',
        help='Inicio del rango de fechas (catch-up)',
    )
    parser.add_argument(
        '--hasta',
        metavar='YYYY-MM-DD',
        help='Fin del rango de fechas (catch-up)',
    )
    parser.add_argument(
        '--no-replace',
        action='store_true',
        help='No borrar datos pendientes previos antes de insertar',
    )
    args = parser.parse_args()

    cfg = load_config()
    replace = not args.no_replace

    errores = []

    if args.desde or args.hasta:
        # Modo rango (catch-up histórico)
        if not args.desde or not args.hasta:
            parser.error("--desde y --hasta deben usarse juntos")
        desde = date.fromisoformat(args.desde)
        hasta = date.fromisoformat(args.hasta)
        if desde > hasta:
            parser.error("--desde debe ser anterior o igual a --hasta")

        log.info(f"Modo rango: {desde} → {hasta} ({(hasta - desde).days + 1} días)")
        current = desde
        while current <= hasta:
            ok = sync_fecha(cfg, current, replace=replace)
            if not ok:
                errores.append(current)
            current += timedelta(days=1)

    elif args.fecha:
        ok = sync_fecha(cfg, date.fromisoformat(args.fecha), replace=replace)
        if not ok:
            errores.append(args.fecha)
    else:
        # Default: ayer
        ayer = date.today() - timedelta(days=1)
        ok = sync_fecha(cfg, ayer, replace=replace)
        if not ok:
            errores.append(ayer)

    if errores:
        log.error(f"Sync finalizado con errores en: {errores}")
        sys.exit(1)

    log.info("Sync finalizado correctamente.")


if __name__ == '__main__':
    main()
