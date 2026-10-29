#!/usr/bin/env python3
"""
sync.py — Sincronizador SabioGo (Firebird) → App360 VPS

Consulta ventas y compras en la DB local de SabioGo y empuja ambos lotes al
endpoint /sabiogo/api/db-sync/daily del VPS vía HTTPS.

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
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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
        log.error("Creá config.ini manualmente y completá las secciones [firebird] y [vps].")
        sys.exit(1)
    cfg = configparser.ConfigParser()
    cfg.read(cfg_path, encoding='utf-8')
    _validate_config(cfg)
    return cfg


def _validate_config(cfg: configparser.ConfigParser):
    required = {
        'firebird': ['host', 'port', 'database', 'user', 'password'],
        'vps': ['url', 'api_key'],
    }
    for section, keys in required.items():
        if not cfg.has_section(section):
            log.error(f"Sección [{section}] faltante en config.ini")
            sys.exit(1)
        for key in keys:
            value = cfg.get(section, key, fallback='').strip()
            if not value or _is_placeholder(value):
                log.error(f"Valor requerido faltante: [{section}] {key}")
                sys.exit(1)

    try:
        port = int(cfg['firebird']['port'])
    except ValueError:
        log.error("[firebird] port debe ser un número entero")
        sys.exit(1)
    if not 1 <= port <= 65535:
        log.error("[firebird] port debe estar entre 1 y 65535")
        sys.exit(1)

    if not cfg['vps']['url'].lower().startswith('https://'):
        log.error("[vps] url debe usar HTTPS")
        sys.exit(1)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().upper()
    return (
        (normalized.startswith('<') and normalized.endswith('>'))
        or normalized.startswith('TU_')
        or normalized.startswith('CAMBIAR_')
        or normalized == 'NO_EJECUTAR_SYNC_AUN'
    )


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
PROCEDURES = {
    'ventas': 'P_VENTAS_GLOBALES',
    'compras': 'P_COMPRAS_GLOBALES',
}


def query_globales(
    cfg: configparser.ConfigParser,
    tipo: str,
    fecha_desde: date,
    fecha_hasta: date,
):
    """Ejecuta el procedimiento global del tipo y retorna columnas y filas."""
    procedure = PROCEDURES.get(tipo)
    if not procedure:
        raise ValueError(f'Tipo de sincronización inválido: {tipo}')

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

    host = fb_cfg['host']
    port = fb_cfg['port']
    database = fb_cfg['database']
    user = fb_cfg['user']
    fb.driver_config.server_defaults.host.value = host
    fb.driver_config.server_defaults.port.value = port
    log.info(f"Conectando a Firebird: {host}:{port}/{database} (usuario: {user})")

    with fb.connect(
        database,
        user=user,
        password=fb_cfg['password'],
        charset='UTF8',
    ) as con:
        with con.cursor() as cur:
            sql = f"SELECT * FROM {procedure}(?, ?)"
            log.info(f"Ejecutando {procedure}: {fecha_desde} → {fecha_hasta}")
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


def query_ventas(cfg: configparser.ConfigParser, fecha_desde: date, fecha_hasta: date):
    return query_globales(cfg, 'ventas', fecha_desde, fecha_hasta)


def query_compras(cfg: configparser.ConfigParser, fecha_desde: date, fecha_hasta: date):
    return query_globales(cfg, 'compras', fecha_desde, fecha_hasta)


# ── HTTP Push ─────────────────────────────────────────────────────────────────
def _build_http_session(max_retries: int, backoff_factor: float) -> requests.Session:
    retry = Retry(
        total=max_retries,
        connect=max_retries,
        read=max_retries,
        status=max_retries,
        other=0,
        allowed_methods=frozenset({'POST'}),
        status_forcelist=(429, 500, 502, 503, 504),
        backoff_factor=backoff_factor,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount('https://', adapter)
    return session


def _validate_vps_result(result: dict, *, tipo: str, fecha: date, total_filas: int):
    if not isinstance(result, dict):
        raise RuntimeError('El VPS respondió un JSON que no es un objeto')
    if result.get('success') is not True:
        detail = result.get('error') or 'success no es true'
        raise RuntimeError(f'El VPS rechazó el lote: {detail}')
    if result.get('errores'):
        raise RuntimeError(f'El VPS informó errores parciales: {result["errores"]}')
    if result.get('tipo') != tipo or result.get('fecha') != fecha.isoformat():
        raise RuntimeError('El VPS respondió tipo o fecha distintos del lote enviado')
    if result.get('total_filas') != total_filas:
        raise RuntimeError('El VPS respondió una cantidad de filas distinta de la enviada')


def _validate_daily_vps_result(
    result: dict,
    *,
    fecha: date,
    ventas_total: int,
    compras_total: int,
):
    if not isinstance(result, dict):
        raise RuntimeError('El VPS respondió un JSON que no es un objeto')
    if result.get('success') is not True:
        detail = result.get('error') or 'success no es true'
        raise RuntimeError(f'El VPS rechazó la sincronización diaria: {detail}')
    if result.get('errores'):
        raise RuntimeError(f'El VPS informó errores parciales: {result["errores"]}')
    if result.get('fecha') != fecha.isoformat():
        raise RuntimeError('El VPS respondió una fecha distinta de la enviada')

    expected_totals = {
        'ventas': ventas_total,
        'compras': compras_total,
        'total': ventas_total + compras_total,
    }
    if result.get('total_filas') != expected_totals:
        raise RuntimeError('El VPS respondió cantidades de filas distintas de las enviadas')
    resultados = result.get('resultados')
    if not isinstance(resultados, dict) or not {'ventas', 'compras'} <= set(resultados):
        raise RuntimeError('El VPS no respondió resultados para ventas y compras')


def _post_json_to_vps(cfg: configparser.ConfigParser, path: str, payload: dict) -> dict:
    vps_cfg = cfg['vps']
    url = f"{vps_cfg['url'].rstrip('/')}{path}"
    timeout = int(vps_cfg.get('timeout_seconds', '120'))
    max_retries = int(vps_cfg.get('max_retries', '3'))
    backoff_factor = float(vps_cfg.get('backoff_factor', '1'))
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    headers = {
        'X-Sync-Key': vps_cfg['api_key'],
        'Content-Type': 'application/json; charset=utf-8',
    }

    try:
        with _build_http_session(max_retries, backoff_factor) as session:
            resp = session.post(url, data=payload_bytes, headers=headers, timeout=timeout)
    except requests.exceptions.ConnectionError as exc:
        log.error(f"No se pudo conectar al VPS: {exc}")
        raise
    except requests.exceptions.Timeout:
        log.error(f"Timeout ({timeout}s) esperando respuesta del VPS")
        raise

    if not resp.ok:
        log.error(f"VPS respondió HTTP {resp.status_code}: {resp.text[:500]}")
        resp.raise_for_status()

    try:
        result = resp.json()
    except ValueError as exc:
        raise RuntimeError('El VPS no respondió JSON válido') from exc
    if not isinstance(result, dict):
        raise RuntimeError('El VPS respondió un JSON que no es un objeto')
    return result


def push_to_vps(
    cfg: configparser.ConfigParser,
    tipo: str,
    fecha: date,
    col_names: list,
    raw_rows: list,
    replace: bool = True,
) -> dict:
    """Serializa y envía los datos al VPS. Retorna la respuesta JSON."""
    rows = rows_to_dicts(col_names, raw_rows)
    origenes = [
        origen.strip().upper()
        for origen in cfg['vps'].get('origenes', 'CARNES,LACTEOS').split(',')
        if origen.strip()
    ]
    if not origenes:
        raise ValueError('[vps] origenes debe contener al menos un origen')
    payload = {
        'tipo': tipo,
        'fecha': fecha.isoformat(),
        'rows': rows,
        'origenes': origenes,
        'replace': replace,
    }
    payload_bytes = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    payload_kb = len(payload_bytes) / 1024
    log.info(f"Enviando {len(rows)} filas ({payload_kb:.1f} KB) al VPS")

    result = _post_json_to_vps(cfg, '/sabiogo/api/db-sync', payload)
    _validate_vps_result(result, tipo=tipo, fecha=fecha, total_filas=len(rows))
    log.info(f"VPS result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    return result


def push_daily_to_vps(
    cfg: configparser.ConfigParser,
    fecha: date,
    ventas_data: tuple[list, list],
    compras_data: tuple[list, list],
    replace: bool = True,
) -> dict:
    """Envía ventas y compras de la fecha para confirmarlas en una transacción."""
    ventas_columns, ventas_raw = ventas_data
    compras_columns, compras_raw = compras_data
    ventas = rows_to_dicts(ventas_columns, ventas_raw)
    compras = rows_to_dicts(compras_columns, compras_raw)
    origenes = [
        origen.strip().upper()
        for origen in cfg['vps'].get('origenes', 'CARNES,LACTEOS').split(',')
        if origen.strip()
    ]
    if not origenes:
        raise ValueError('[vps] origenes debe contener al menos un origen')

    payload = {
        'fecha': fecha.isoformat(),
        'ventas': ventas,
        'compras': compras,
        'origenes': origenes,
        'replace': replace,
    }
    payload_kb = len(json.dumps(payload, ensure_ascii=False).encode('utf-8')) / 1024
    log.info(
        f'Enviando sincronización diaria: {len(ventas)} ventas, '
        f'{len(compras)} compras ({payload_kb:.1f} KB)'
    )

    result = _post_json_to_vps(cfg, '/sabiogo/api/db-sync/daily', payload)
    _validate_daily_vps_result(
        result,
        fecha=fecha,
        ventas_total=len(ventas),
        compras_total=len(compras),
    )
    log.info(f"VPS result: {json.dumps(result, indent=2, ensure_ascii=False)}")
    return result


def finalize_sync(cfg: configparser.ConfigParser, fecha: date) -> dict:
    """Refresca derivados de staging después de completar ambos tipos."""
    log.info(f"Finalizando sincronización {fecha}: actualización de facts")
    result = _post_json_to_vps(
        cfg,
        '/sabiogo/api/db-sync/finalize',
        {'fecha': fecha.isoformat()},
    )
    if result.get('success') is not True:
        detail = result.get('error') or 'success no es true'
        raise RuntimeError(f'El VPS no pudo finalizar la sincronización: {detail}')
    if result.get('fecha') != fecha.isoformat():
        raise RuntimeError('El VPS finalizó una fecha distinta de la solicitada')
    return result


def report_sync_status(
    cfg: configparser.ConfigParser,
    execution_id: str,
    fecha: date,
    estado: str,
    *,
    mensaje: str | None = None,
    filas_ventas: int | None = None,
    filas_compras: int | None = None,
) -> dict:
    """Informa al VPS el estado operativo de una ejecución."""
    payload = {
        'execution_id': execution_id,
        'fecha': fecha.isoformat(),
        'estado': estado,
    }
    if mensaje:
        payload['mensaje'] = mensaje
    if filas_ventas is not None:
        payload['filas_ventas'] = filas_ventas
    if filas_compras is not None:
        payload['filas_compras'] = filas_compras

    result = _post_json_to_vps(cfg, '/sabiogo/api/db-sync/status', payload)
    if result.get('success') is not True:
        raise RuntimeError('El VPS rechazó el reporte de estado')
    if (
        result.get('execution_id') != execution_id
        or result.get('fecha') != fecha.isoformat()
        or result.get('estado') != estado
    ):
        raise RuntimeError('El VPS respondió datos distintos al estado informado')
    return result


def _report_sync_status_safely(*args, **kwargs):
    try:
        report_sync_status(*args, **kwargs)
        return True
    except Exception as exc:
        log.warning(f'No se pudo reportar el estado operativo al VPS: {exc}')
        return False


# ── Lógica principal ──────────────────────────────────────────────────────────
def sync_tipo(
    cfg: configparser.ConfigParser,
    tipo: str,
    fecha: date,
    replace: bool = True,
) -> bool:
    """Sincroniza un tipo de una fecha. Retorna True si fue exitoso."""
    query = query_ventas if tipo == 'ventas' else query_compras
    log.info(f"{'='*60}")
    log.info(f"Sincronizando {tipo.upper()} {fecha}")
    log.info(f"{'='*60}")

    try:
        col_names, raw_rows = query(cfg, fecha, fecha)
        if not raw_rows:
            log.info(f"Sin datos de {tipo} para {fecha}. Enviando lote vacío de control.")
        result = push_to_vps(cfg, tipo, fecha, col_names, raw_rows, replace=replace)

        total = result.get('total_filas', '?')
        resultados = result.get('resultados', {})
        log.info(f"✓ Sync {tipo} completado: {total} filas | detalle: {resultados}")
        return True

    except Exception as exc:
        log.error(f"✗ Error sincronizando {tipo} {fecha}: {exc}", exc_info=True)
        return False


def sync_fecha(cfg: configparser.ConfigParser, fecha: date, replace: bool = True) -> bool:
    """Extrae ambos tipos y los confirma juntos antes de refrescar derivados."""
    execution_id = str(uuid4())
    _report_sync_status_safely(cfg, execution_id, fecha, 'iniciada')

    datasets = {}
    extraction_errors = []
    for tipo, query in (('ventas', query_ventas), ('compras', query_compras)):
        log.info(f"{'='*60}")
        log.info(f"Extrayendo {tipo.upper()} {fecha}")
        log.info(f"{'='*60}")
        try:
            columns, rows = query(cfg, fecha, fecha)
            datasets[tipo] = (columns, rows)
            if not rows:
                log.info(f'Sin datos de {tipo} para {fecha}. Se enviará lote vacío de control.')
        except Exception as exc:
            extraction_errors.append(tipo)
            log.error(f'✗ Error extrayendo {tipo} {fecha}: {exc}', exc_info=True)

    if extraction_errors:
        _report_sync_status_safely(
            cfg,
            execution_id,
            fecha,
            'error',
            mensaje=f'Falló extracción: {", ".join(extraction_errors)}.',
        )
        return False

    ventas_total = len(datasets['ventas'][1])
    compras_total = len(datasets['compras'][1])
    try:
        result = push_daily_to_vps(
            cfg,
            fecha,
            datasets['ventas'],
            datasets['compras'],
            replace=replace,
        )
        log.info(
            f"✓ Carga diaria completada: {result['total_filas']['total']} filas | "
            f"detalle: {result.get('resultados', {})}"
        )
        finalize_sync(cfg, fecha)
    except Exception as exc:
        log.error(f'✗ Error sincronizando o finalizando {fecha}: {exc}', exc_info=True)
        _report_sync_status_safely(
            cfg,
            execution_id,
            fecha,
            'error',
            mensaje='Falló la carga o finalización en App360.',
            filas_ventas=ventas_total,
            filas_compras=compras_total,
        )
        return False

    status_reported = _report_sync_status_safely(
        cfg,
        execution_id,
        fecha,
        'exitosa',
        mensaje='Carga y finalización completadas.',
        filas_ventas=ventas_total,
        filas_compras=compras_total,
    )
    if not status_reported:
        log.error('La carga terminó bien, pero no se pudo confirmar su estado operativo.')
        return False
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Sincroniza ventas y compras de SabioGo al VPS App360',
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
