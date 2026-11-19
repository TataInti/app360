"""Blueprint para administración y análisis SabioGo."""

from flask import Blueprint, render_template, request, jsonify, current_app, session, redirect, url_for
from functools import wraps
from werkzeug.utils import secure_filename
import pandas as pd
import hashlib
import json
import gc
import os
import re
from datetime import datetime, date, timedelta
from typing import Optional
from uuid import UUID
from sqlalchemy import text, func, inspect as sa_inspect
from sqlalchemy.orm import joinedload

from models import db
from models.sabiogo import (
    StgSabiogoVentas,
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap,
    LogSabiogoCarga,
    SabiogoSyncRun,
)
from models.time_utils import now_local
from models.core.product import Product
from models.crm.client import Client
from services.sabiogo_service import SabiogoService
from dtos.sabiogo_dto import (
    RentabilidadProductoDTO,
    RentabilidadResumenDTO,
    ProductoTopMargenDTO
)
from extensions import csrf
from security import protect_blueprint
from models.core.user import User

sabiogo_bp = Blueprint("sabiogo", __name__, url_prefix="/sabiogo")
protect_blueprint(sabiogo_bp, "admin")


ALLOWED_EXTENSIONS = {'xls', 'xlsx'}


ORIGEN_LEGACY = 'LEGACY'
ORIGEN_CARNES = 'CARNES'
ORIGEN_LACTEOS = 'LACTEOS'
DEFAULT_EMPRESA_MAP = {
    'VYP': ORIGEN_CARNES,
    'CARNES': ORIGEN_CARNES,
    'VYP_LACTEOS': ORIGEN_LACTEOS,
    'LACTEOS_VP': ORIGEN_LACTEOS,
    'LACTEOS': ORIGEN_LACTEOS,
}


def _parse_sync_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {'false', '0', 'no', 'off'}


def _parse_sync_fecha(value) -> Optional[date]:
    if value in (None, ''):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _parse_sync_count(payload: dict, field_name: str) -> Optional[int]:
    value = payload.get(field_name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field_name} debe ser un entero no negativo')
    return value


def _build_empresa_map(custom_map) -> dict[str, str]:
    empresa_map = {k.upper(): v.upper() for k, v in DEFAULT_EMPRESA_MAP.items()}
    if not isinstance(custom_map, dict):
        return empresa_map

    for empresa, origen in custom_map.items():
        empresa_norm = str(empresa or '').strip().upper()
        origen_norm = str(origen or '').strip().upper()
        if origen_norm and origen_norm not in {ORIGEN_CARNES, ORIGEN_LACTEOS}:
            raise ValueError(
                f'empresa_map contiene un origen inválido para {empresa_norm or empresa}: '
                f'{origen_norm}'
            )
        if empresa_norm and origen_norm:
            empresa_map[empresa_norm] = origen_norm
    return empresa_map


def _hash_sync_payload(tipo: str, fecha_lote: date, origen: str, rows: list[dict], replace: bool) -> str:
    canonical_payload = {
        'tipo': tipo,
        'fecha': fecha_lote.isoformat(),
        'origen': origen,
        'replace': replace,
        'rows': rows,
    }
    payload_json = json.dumps(canonical_payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload_json.encode('utf-8')).hexdigest()


def _group_sync_rows(rows, *, fecha_lote: date, empresa_map: dict[str, str]) -> dict[str, list[dict]]:
    rows_por_origen: dict[str, list[dict]] = {}

    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f'Fila {idx} inválida: se esperaba un objeto JSON')

        empresa_raw = row.get('EMPRESA', row.get('empresa'))
        empresa = str(empresa_raw or '').strip().upper()
        if not empresa:
            raise ValueError(f'Fila {idx} inválida: columna EMPRESA faltante')

        origen = empresa_map.get(empresa)
        if not origen:
            raise ValueError(f'Fila {idx} inválida: EMPRESA no mapeada ({empresa})')

        normalized = {
            str(key).strip().lower(): value
            for key, value in row.items()
        }

        fecha_row = _parse_sync_fecha(normalized.get('fecha'))
        if fecha_row is None:
            normalized['fecha'] = fecha_lote
        elif fecha_row != fecha_lote:
            raise ValueError(
                f'Fila {idx} inválida: FECHA {fecha_row.isoformat()} '
                f'no coincide con el lote {fecha_lote.isoformat()}'
            )
        else:
            normalized['fecha'] = fecha_row

        rows_por_origen.setdefault(origen, []).append(normalized)

    return rows_por_origen


def infer_origen_from_filename(filename: str) -> Optional[str]:
    """Inferir origen (CARNES/LACTEOS) desde el nombre de archivo."""
    if not filename:
        return None
    name = filename.lower()
    if re.search(r"\b(carne|carnes|vyp\s*carnes)\b", name):
        return ORIGEN_CARNES
    if re.search(r"\b(lacteo|lácteo|lacteos|lácteos|vyp\s*lacteos)\b", name):
        return ORIGEN_LACTEOS
    return None


def normalize_codigo(value) -> Optional[str]:
    """Normaliza `codigo` para que sea comparable (evita .0, espacios, NaN)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    text_value = str(value).strip()
    if not text_value:
        return None

    # Excel a veces entrega números como '123.0'
    if re.fullmatch(r"\d+\.0+", text_value):
        text_value = text_value.split('.', 1)[0]

    return text_value


def login_required(f):
    """Compatibilidad con sistema de sesión propio del proyecto."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if session.get("user"):
            return f(*args, **kwargs)
        return redirect(url_for("auth.login"))

    return decorated


def allowed_file(filename):
    """Verifica si la extensión del archivo es permitida."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def calcular_hash_archivo(filepath):
    """Calcula hash SHA256 de un archivo."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()


def _autogenerar_mapeos_faltantes():
    """Autogenera mapeos faltantes de productos y clientes desde staging."""
    stats = {
        'productos_creados': 0,
        'productos_auto_mapeados': 0,
        'clientes_creados': 0,
        'clientes_auto_mapeados': 0,
    }

    # Productos: unir códigos de ventas y compras (por origen)
    codigos_ventas = db.session.query(
        StgSabiogoVentas.origen,
        StgSabiogoVentas.codigo,
        func.max(StgSabiogoVentas.producto).label('producto'),
        func.max(StgSabiogoVentas.marca).label('marca'),
        func.max(StgSabiogoVentas.modelo).label('modelo'),
    ).filter(
        StgSabiogoVentas.codigo.isnot(None),
        StgSabiogoVentas.codigo != '',
    ).group_by(StgSabiogoVentas.origen, StgSabiogoVentas.codigo).all()

    codigos_compras = db.session.query(
        StgSabiogoCompras.origen,
        StgSabiogoCompras.codigo,
        func.max(StgSabiogoCompras.producto).label('producto'),
        func.max(StgSabiogoCompras.marca).label('marca'),
        func.max(StgSabiogoCompras.modelo).label('modelo'),
    ).filter(
        StgSabiogoCompras.codigo.isnot(None),
        StgSabiogoCompras.codigo != '',
    ).group_by(StgSabiogoCompras.origen, StgSabiogoCompras.codigo).all()

    codigos_dict = {}
    for row in codigos_ventas + codigos_compras:
        origen = row.origen or ORIGEN_LEGACY
        codigo = row.codigo
        key = (origen, codigo)
        if key not in codigos_dict:
            codigos_dict[key] = {
                'producto': row.producto,
                'marca': row.marca,
                'modelo': row.modelo,
            }

    codigos_existentes = {
        (origen or ORIGEN_LEGACY, codigo)
        for origen, codigo in db.session.query(SabiogoProductMap.origen, SabiogoProductMap.codigo).all()
    }

    for (origen, codigo), info in codigos_dict.items():
        if (origen, codigo) in codigos_existentes:
            continue

        product = Product.query.filter_by(sku=codigo).first()
        nuevo_mapeo = SabiogoProductMap(
            origen=origen,
            codigo=codigo,
            product_id=product.id if product else None,
            marca=info.get('marca'),
            modelo=info.get('modelo'),
            producto_descripcion=info.get('producto'),
            activo=True if product else False,
        )
        db.session.add(nuevo_mapeo)
        stats['productos_creados'] += 1
        if product:
            stats['productos_auto_mapeados'] += 1

    # Clientes: extraer únicos desde ventas
    clientes_staging = db.session.query(
        StgSabiogoVentas.cliente,
        StgSabiogoVentas.condicion_iva,
        func.max(StgSabiogoVentas.zona).label('zona'),
        func.max(StgSabiogoVentas.localidad).label('localidad'),
    ).filter(
        StgSabiogoVentas.cliente.isnot(None),
        StgSabiogoVentas.cliente != '',
    ).group_by(
        StgSabiogoVentas.cliente,
        StgSabiogoVentas.condicion_iva,
    ).all()

    clientes_existentes = {
        (cliente, condicion_iva)
        for cliente, condicion_iva in db.session.query(
            SabiogoClientMap.cliente,
            SabiogoClientMap.condicion_iva,
        ).all()
    }

    for row in clientes_staging:
        key = (row.cliente, row.condicion_iva)
        if key in clientes_existentes:
            continue

        client = None
        if row.cliente:
            client = Client.query.filter(
                func.lower(Client.name).like(f"%{row.cliente.lower()}%")
            ).first()

        nuevo_cliente = SabiogoClientMap(
            cliente=row.cliente,
            condicion_iva=row.condicion_iva,
            client_id=client.id if client else None,
            zona=row.zona,
            localidad=row.localidad,
            activo=True if client else False,
        )
        db.session.add(nuevo_cliente)
        stats['clientes_creados'] += 1
        if client:
            stats['clientes_auto_mapeados'] += 1

    db.session.commit()
    return stats


# ============================================================================
# ENDPOINTS HTML - ADMINISTRACIÓN
# ============================================================================

@sabiogo_bp.route("/admin")
@login_required
def admin_panel():
    """Panel de administración SabioGo."""
    # Consolidar métricas en una sola ida al motor para evitar latencia en page load.
    total_productos_map_sq = db.session.query(func.count(SabiogoProductMap.id)).scalar_subquery()
    productos_mapeados_sq = db.session.query(func.count(SabiogoProductMap.id)).filter(
        SabiogoProductMap.activo == True,
        SabiogoProductMap.product_id.isnot(None),
    ).scalar_subquery()
    total_clientes_map_sq = db.session.query(func.count(SabiogoClientMap.id)).scalar_subquery()
    clientes_mapeados_sq = db.session.query(func.count(SabiogoClientMap.id)).filter(
        SabiogoClientMap.activo == True,
        SabiogoClientMap.client_id.isnot(None),
    ).scalar_subquery()

    stats_row = db.session.query(
        total_productos_map_sq.label('total_productos'),
        productos_mapeados_sq.label('productos_mapeados'),
        total_clientes_map_sq.label('total_clientes'),
        clientes_mapeados_sq.label('clientes_mapeados'),
    ).one()

    total_productos_map = int(stats_row.total_productos or 0)
    productos_mapeados = int(stats_row.productos_mapeados or 0)
    total_clientes_map = int(stats_row.total_clientes or 0)
    clientes_mapeados = int(stats_row.clientes_mapeados or 0)
    
    return render_template(
        "sabiogo_admin.html",
        stats={
            'total_productos': total_productos_map,
            'productos_mapeados': productos_mapeados,
            'productos_sin_mapear': total_productos_map - productos_mapeados,
            'total_clientes': total_clientes_map,
            'clientes_mapeados': clientes_mapeados,
            'clientes_sin_mapear': total_clientes_map - clientes_mapeados
        }
    )


# ============================================================================
# ENDPOINTS API - CARGA DE DATOS
# ============================================================================

def _prepare_sync_rows(
    rows,
    *,
    field_name: str,
    fecha_lote: date,
    empresa_map: dict[str, str],
    origenes_payload,
) -> tuple[list, dict[str, list[dict]]]:
    if not isinstance(rows, list):
        raise ValueError(f'{field_name} requerido y debe ser una lista')

    rows_por_origen = _group_sync_rows(rows, fecha_lote=fecha_lote, empresa_map=empresa_map)
    if origenes_payload is None:
        if not rows_por_origen:
            raise ValueError(f'origenes requerido cuando {field_name} está vacío')
        origenes = list(rows_por_origen)
    else:
        if not isinstance(origenes_payload, list) or not origenes_payload:
            raise ValueError('origenes debe ser una lista no vacía')
        origenes = list(dict.fromkeys(
            str(origen or '').strip().upper()
            for origen in origenes_payload
            if str(origen or '').strip()
        ))
        allowed_origins = set(empresa_map.values())
        invalid_origins = sorted(set(origenes) - allowed_origins)
        if invalid_origins:
            raise ValueError(f'origenes inválidos: {invalid_origins}')
        missing_origins = sorted(set(rows_por_origen) - set(origenes))
        if missing_origins:
            raise ValueError(
                f'origenes no incluye unidades presentes en {field_name}: {missing_origins}'
            )

    for origen in origenes:
        rows_por_origen.setdefault(origen, [])
    return rows, rows_por_origen


def _acquire_sync_lock(fecha_lote: date):
    """Serializa cargas técnicas de la misma fecha en PostgreSQL."""
    if db.engine.dialect.name != 'postgresql':
        return
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:lock_key))'),
        {'lock_key': f'sabiogo-db-sync:{fecha_lote.isoformat()}'},
    )


def _acquire_sync_status_lock(execution_id: str):
    """Serializa reportes del mismo intento técnico en PostgreSQL."""
    if db.engine.dialect.name != 'postgresql':
        return
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(hashtext(:lock_key))'),
        {'lock_key': f'sabiogo-db-sync-status:{execution_id}'},
    )


def _process_sync_lote(
    *,
    tipo: str,
    fecha_lote: date,
    rows_por_origen: dict[str, list[dict]],
    replace: bool,
    service: SabiogoService,
) -> dict:
    model_class = StgSabiogoVentas if tipo == 'ventas' else StgSabiogoCompras
    resultados = {}

    for origen, origen_rows in rows_por_origen.items():
        try:
            batch_filename = f'api_sync_{tipo}_{fecha_lote.isoformat()}_{origen.lower()}.json'
            batch_hash = _hash_sync_payload(tipo, fecha_lote, origen, origen_rows, replace)

            if replace:
                eliminados = db.session.query(model_class).filter(
                    model_class.origen == origen,
                    model_class.fecha == fecha_lote,
                ).delete(synchronize_session=False)
                current_app.logger.info(
                    f'[db-sync] replace: eliminados {eliminados} registros '
                    f'{model_class.__tablename__} fecha={fecha_lote} origen={origen}'
                )

            stats = _importar_df_a_staging(
                pd.DataFrame(origen_rows),
                ModelClass=model_class,
                origen=origen,
                filename=batch_filename,
                file_sha256=batch_hash,
            )
            if stats['filas_error']:
                raise ValueError(
                    f'{stats["filas_error"]} filas no pudieron procesarse para {origen}'
                )

            service.registrar_carga(
                archivo_nombre=batch_filename,
                tipo_carga=tipo,
                hash_archivo=batch_hash,
                filas_insertadas=stats['filas_insertadas'],
                filas_duplicadas=stats['filas_duplicadas'],
                filas_sin_mapeo=0,
                filas_error=stats['filas_error'],
                usuario_id=None,
                observaciones=f'api-sync fecha={fecha_lote.isoformat()} origen={origen}',
                auto_commit=False,
            )
            resultados[origen] = stats
        except Exception as exc:
            raise RuntimeError(f'falló tipo={tipo} origen={origen}: {exc}') from exc

    return resultados

@sabiogo_bp.route('/api/db-sync', methods=['POST'])
@csrf.exempt
def sabiogo_db_sync():
    """Recibe lotes diarios desde el servidor local SabioGo y los inserta en staging."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Payload JSON inválido'}), 400

    tipo = str(payload.get('tipo') or 'ventas').strip().lower()
    if tipo not in {'ventas', 'compras'}:
        return jsonify({'error': 'tipo inválido. Use ventas o compras'}), 400

    fecha_lote = _parse_sync_fecha(payload.get('fecha'))
    if not fecha_lote:
        return jsonify({'error': 'fecha requerida con formato YYYY-MM-DD'}), 400

    try:
        replace = _parse_sync_bool(payload.get('replace'), default=True)
        empresa_map = _build_empresa_map(payload.get('empresa_map'))
        rows, rows_por_origen = _prepare_sync_rows(
            payload.get('rows'),
            field_name='rows',
            fecha_lote=fecha_lote,
            empresa_map=empresa_map,
            origenes_payload=payload.get('origenes'),
        )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    service = SabiogoService()

    try:
        _acquire_sync_lock(fecha_lote)
        resultados = _process_sync_lote(
            tipo=tipo,
            fecha_lote=fecha_lote,
            rows_por_origen=rows_por_origen,
            replace=replace,
            service=service,
        )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            f'[db-sync] rollback tipo={tipo} fecha={fecha_lote}: {exc}',
            exc_info=True,
        )
        return jsonify({
            'success': False,
            'error': 'No se pudo procesar el lote.',
            'tipo': tipo,
            'fecha': fecha_lote.isoformat(),
            'total_filas': len(rows),
            'resultados': None,
            'errores': {'lote': 'Error interno al procesar el lote'},
            'replace': replace,
        }), 500
    finally:
        db.session.expire_all()
        gc.collect()

    return jsonify({
        'success': True,
        'tipo': tipo,
        'fecha': fecha_lote.isoformat(),
        'total_filas': len(rows),
        'resultados': resultados,
        'errores': None,
        'replace': replace,
    }), 200


@sabiogo_bp.route('/api/db-sync/daily', methods=['POST'])
@csrf.exempt
def sabiogo_db_sync_daily():
    """Reemplaza ventas y compras de una fecha en una sola transacción."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Payload JSON inválido'}), 400

    fecha_lote = _parse_sync_fecha(payload.get('fecha'))
    if not fecha_lote:
        return jsonify({'error': 'fecha requerida con formato YYYY-MM-DD'}), 400

    prepared = {}
    try:
        replace = _parse_sync_bool(payload.get('replace'), default=True)
        empresa_map = _build_empresa_map(payload.get('empresa_map'))
        origenes_payload = payload.get('origenes')
        for tipo in ('ventas', 'compras'):
            prepared[tipo] = _prepare_sync_rows(
                payload.get(tipo),
                field_name=tipo,
                fecha_lote=fecha_lote,
                empresa_map=empresa_map,
                origenes_payload=origenes_payload,
            )
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    service = SabiogoService()
    resultados = {}
    try:
        _acquire_sync_lock(fecha_lote)
        for tipo in ('ventas', 'compras'):
            _, rows_por_origen = prepared[tipo]
            resultados[tipo] = _process_sync_lote(
                tipo=tipo,
                fecha_lote=fecha_lote,
                rows_por_origen=rows_por_origen,
                replace=replace,
                service=service,
            )
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(
            f'[db-sync/daily] rollback fecha={fecha_lote}: {exc}',
            exc_info=True,
        )
        return jsonify({
            'success': False,
            'error': 'No se pudo procesar la sincronización diaria.',
            'fecha': fecha_lote.isoformat(),
            'total_filas': None,
            'resultados': None,
            'errores': {'lote': 'Error interno al procesar la sincronización diaria'},
            'replace': replace,
        }), 500
    finally:
        db.session.expire_all()
        gc.collect()

    ventas_rows = prepared['ventas'][0]
    compras_rows = prepared['compras'][0]
    return jsonify({
        'success': True,
        'fecha': fecha_lote.isoformat(),
        'total_filas': {
            'ventas': len(ventas_rows),
            'compras': len(compras_rows),
            'total': len(ventas_rows) + len(compras_rows),
        },
        'resultados': resultados,
        'errores': None,
        'replace': replace,
    }), 200


@sabiogo_bp.route('/api/db-sync/finalize', methods=['POST'])
@csrf.exempt
def sabiogo_db_sync_finalize():
    """Refresca derivados después de completar ventas y compras de una fecha."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Payload JSON inválido'}), 400

    fecha_lote = _parse_sync_fecha(payload.get('fecha'))
    if not fecha_lote:
        return jsonify({'error': 'fecha requerida con formato YYYY-MM-DD'}), 400

    service = SabiogoService()
    try:
        facts = service.refresh_facts()
    except Exception as exc:
        current_app.logger.error(
            f'[db-sync/finalize] error fecha={fecha_lote}: {exc}',
            exc_info=True,
        )
        return jsonify({
            'success': False,
            'error': 'No se pudo finalizar la sincronización.',
            'fecha': fecha_lote.isoformat(),
        }), 500

    return jsonify({
        'success': True,
        'fecha': fecha_lote.isoformat(),
        'facts': facts,
    }), 200


@sabiogo_bp.route('/api/db-sync/status', methods=['POST'])
@csrf.exempt
def sabiogo_db_sync_status():
    """Registra el inicio o resultado de una ejecución del cliente Windows."""
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Payload JSON inválido'}), 400

    try:
        execution_id = str(UUID(str(payload.get('execution_id') or '')))
    except (ValueError, TypeError, AttributeError):
        return jsonify({'error': 'execution_id debe ser un UUID válido'}), 400

    fecha_objetivo = _parse_sync_fecha(payload.get('fecha'))
    if not fecha_objetivo:
        return jsonify({'error': 'fecha requerida con formato YYYY-MM-DD'}), 400

    estado = str(payload.get('estado') or '').strip().lower()
    if estado not in {'iniciada', 'exitosa', 'error'}:
        return jsonify({'error': 'estado debe ser iniciada, exitosa o error'}), 400

    mensaje = str(payload.get('mensaje') or '').strip() or None
    if mensaje and len(mensaje) > 500:
        return jsonify({'error': 'mensaje no puede superar 500 caracteres'}), 400

    try:
        filas_ventas = _parse_sync_count(payload, 'filas_ventas')
        filas_compras = _parse_sync_count(payload, 'filas_compras')
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    _acquire_sync_status_lock(execution_id)
    run = SabiogoSyncRun.query.filter_by(execution_id=execution_id).first()
    if run and run.fecha_objetivo != fecha_objetivo:
        return jsonify({'error': 'execution_id ya pertenece a otra fecha'}), 409
    if run and run.estado in {'exitosa', 'error'} and run.estado != estado:
        return jsonify({'error': 'la ejecución ya tiene un estado final distinto'}), 409

    timestamp = now_local()
    if run is None:
        run = SabiogoSyncRun(
            execution_id=execution_id,
            fecha_objetivo=fecha_objetivo,
            estado=estado,
            iniciada_en=timestamp,
        )
        db.session.add(run)

    run.estado = estado
    run.mensaje = mensaje
    run.actualizada_en = timestamp
    if filas_ventas is not None:
        run.filas_ventas = filas_ventas
    if filas_compras is not None:
        run.filas_compras = filas_compras
    if estado in {'exitosa', 'error'} and run.finalizada_en is None:
        run.finalizada_en = timestamp

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        current_app.logger.error(
            f'[db-sync/status] error execution_id={execution_id}',
            exc_info=True,
        )
        return jsonify({'error': 'No se pudo registrar el estado de sincronización'}), 500

    return jsonify({
        'success': True,
        'execution_id': run.execution_id,
        'fecha': run.fecha_objetivo.isoformat(),
        'estado': run.estado,
    }), 200


@sabiogo_bp.route("/api/cargar-xls", methods=["POST"])
@login_required
def cargar_xls():
    return jsonify({
        'error': 'Endpoint deprecado. Use /sabiogo/api/cargar-globales con 4 archivos por empresa (carnes/lacteos).'
    }), 410


# ============================================================================
# HELPERS PARA CARGA GLOBAL DE 4 ARCHIVOS
# ============================================================================

COLS_REQUERIDAS_TRANS = ['fecha', 'codigo', 'producto']
COLS_SABIOGO_28 = [
    'rubro', 'fecha', 'subrubro', 'codigo', 'modelo', 'producto', 'marca', 'comprobante',
    'nro_comprob', 'cliente', 'condicion_iva', 'vendedor', 'deposito', 'uninegocio',
    'forma_pago', 'kilos', 'cajas', 'dtos', 'neto', 'localidad', 'zona', 'sucursal',
    'iva', 'moniva', 'tipo', 'subtot', 'numlispre', 'lisprec',
]


def _get_model_columns(ModelClass):
    """Devuelve el set de nombres de columna válidas para un modelo SQLAlchemy."""
    return {c.key for c in sa_inspect(ModelClass).mapper.column_attrs}


def _read_excel_robust(path: str) -> pd.DataFrame:
    """Lee un XLS/XLSX con detección automática de la fila de encabezado.

    Maneja el caso donde SabioGo exporta filas de título/metadata antes
    del encabezado real (problema común en 'carnes_ventas_globales.xls').
    Además normaliza los nombres de columnas a lowercase+strip.
    """
    ext = os.path.splitext(path)[1].lower()
    # xlrd maneja .xls (formato antiguo); openpyxl maneja .xlsx
    engines = ['xlrd'] if ext == '.xls' else ['openpyxl']
    # Añadimos None como fallback para que pandas elija automáticamente
    engines.append(None)

    last_error = None
    for engine in engines:
        for header_row in (0, 1, 2):
            try:
                kwargs = {'header': header_row}
                if engine is not None:
                    kwargs['engine'] = engine
                df = pd.read_excel(path, **kwargs)
                # Normalizar nombres de columnas
                df.columns = [str(c).lower().strip() for c in df.columns]
                # Si encontramos las columnas clave, es el encabezado correcto
                if all(col in df.columns for col in COLS_REQUERIDAS_TRANS):
                    return df
            except Exception as exc:
                last_error = exc
                continue

    for engine in engines:
        try:
            kwargs = {'header': None}
            if engine is not None:
                kwargs['engine'] = engine
            df = pd.read_excel(path, **kwargs)
            if df.shape[1] == len(COLS_SABIOGO_28):
                df.columns = COLS_SABIOGO_28
                return df
        except Exception as exc:
            last_error = exc
            continue

    raise ValueError(
        f"No se pudo detectar encabezado en '{os.path.basename(path)}'. "
        f"Columnas esperadas: {COLS_REQUERIDAS_TRANS}. "
        f"Último error: {last_error}"
    )


def _descartar_duplicados_importados(ModelClass, *, file_sha256: str) -> int:
    """Elimina filas duplicadas de un archivo recién importado."""
    return int(db.session.query(ModelClass).filter(
        ModelClass.hash_archivo == file_sha256,
        ModelClass.estado == 'duplicado',
    ).delete(synchronize_session=False) or 0)


def _purgar_duplicados_staging() -> dict:
    """Elimina filas heredadas con estado duplicado en staging."""
    ventas = int(db.session.query(StgSabiogoVentas).filter(
        StgSabiogoVentas.estado == 'duplicado'
    ).delete(synchronize_session=False) or 0)
    compras = int(db.session.query(StgSabiogoCompras).filter(
        StgSabiogoCompras.estado == 'duplicado'
    ).delete(synchronize_session=False) or 0)
    return {
        'ventas': ventas,
        'compras': compras,
        'total': ventas + compras,
    }


def _importar_df_a_staging(df: pd.DataFrame, *, ModelClass, origen: str, filename: str, file_sha256: str) -> dict:
    """Importa un DataFrame ya validado a la tabla de staging correspondiente.

    Optimizado para bajo consumo de memoria: procesa en chunks sin copiar
    el DataFrame completo.
    """
    valid_cols = _get_model_columns(ModelClass)
    filas_insertadas = 0
    filas_error = 0
    batch_size = 1000
    total_rows = len(df)

    for chunk_start in range(0, total_rows, batch_size):
        chunk = df.iloc[chunk_start:chunk_start + batch_size]
        batch_rows = []
        for row_idx, (_, row) in enumerate(chunk.iterrows(), start=chunk_start):
            try:
                data = {
                    k: (None if pd.isna(v) else v)
                    for k, v in row.items()
                    if k in valid_cols
                }

                codigo_raw = data.get('codigo')
                data['codigo_raw'] = None if codigo_raw is None else str(codigo_raw)
                data['codigo'] = normalize_codigo(codigo_raw)
                data['origen'] = origen
                data['fuente_archivo'] = filename
                data['hash_archivo'] = file_sha256
                data['estado'] = 'pendiente'

                batch_rows.append(data)
                filas_insertadas += 1
            except Exception as exc:
                filas_error += 1
                current_app.logger.debug(f"Error fila {row_idx}: {exc}")

        if batch_rows:
            db.session.bulk_insert_mappings(ModelClass, batch_rows)
            db.session.flush()
            db.session.expire_all()

    # Marcar duplicados pendientes
    duplicados = ModelClass.validar_duplicados(db.session)

    filas_descartadas = _descartar_duplicados_importados(ModelClass, file_sha256=file_sha256)

    # Promover pendientes a procesado
    filas_procesadas = db.session.query(ModelClass).filter(
        ModelClass.hash_archivo == file_sha256,
        ModelClass.estado == 'pendiente',
    ).update({'estado': 'procesado'}, synchronize_session=False)

    return {
        'filas_insertadas': filas_insertadas,
        'filas_procesadas': int(filas_procesadas or 0),
        'filas_duplicadas': int(filas_descartadas or duplicados or 0),
        'filas_error': filas_error,
    }


@sabiogo_bp.route("/api/cargar-globales", methods=["POST"])
@login_required
def cargar_globales():
    """Carga hasta 4 archivos globales de ventas/compras con reemplazo por origen.

    Form fields esperados (todos opcionales, al menos 1 requerido):
        carnes_ventas   – XLS ventas unidad Carnes
        lacteos_ventas  – XLS ventas unidad Lácteos
        carnes_compras  – XLS compras unidad Carnes
        lacteos_compras – XLS compras unidad Lácteos
        replace         – "true" (default) para borrar datos del origen antes de importar
    """
    ARCHIVOS_CONFIG = {
        'carnes_ventas':   (ORIGEN_CARNES,  'ventas',  StgSabiogoVentas),
        'lacteos_ventas':  (ORIGEN_LACTEOS, 'ventas',  StgSabiogoVentas),
        'carnes_compras':  (ORIGEN_CARNES,  'compras', StgSabiogoCompras),
        'lacteos_compras': (ORIGEN_LACTEOS, 'compras', StgSabiogoCompras),
    }

    replace = request.form.get('replace', 'true').lower() not in ('false', '0', 'no')
    upload_folder = current_app.config.get('UPLOAD_FOLDER', '/tmp')
    os.makedirs(upload_folder, exist_ok=True)

    # Determinar qué archivos fueron enviados
    archivos_recibidos = {
        key: request.files[key]
        for key in ARCHIVOS_CONFIG
        if key in request.files and request.files[key].filename
    }

    if not archivos_recibidos:
        return jsonify({'error': 'No se recibió ningún archivo. Envíe al menos uno.'}), 400

    for key, file in archivos_recibidos.items():
        if not allowed_file(file.filename):
            return jsonify({'error': f'{key}: extensión no permitida. Use .xls o .xlsx'}), 400

    resultados = {}
    errores_archivos = {}
    tmp_paths = []
    service = SabiogoService()
    usuario = User.query.filter_by(username=session.get('user')).first()

    # Guardar archivos a disco primero (no consume mucha RAM).
    for key, file in archivos_recibidos.items():
        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_folder, f"global_{key}_{filename}")
        file.save(filepath)
        tmp_paths.append(filepath)

    # Procesar cada archivo en su PROPIA transacción para:
    #  - no acumular 4 DataFrames en RAM simultáneamente
    #  - no perder datos ya importados si un archivo posterior falla
    for key in list(archivos_recibidos.keys()):
        origen, tipo_carga, ModelClass = ARCHIVOS_CONFIG[key]
        file = archivos_recibidos[key]
        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_folder, f"global_{key}_{filename}")

        try:
            if replace:
                eliminados = db.session.query(ModelClass).filter(
                    ModelClass.origen == origen
                ).delete(synchronize_session=False)
                current_app.logger.info(
                    f"[cargar-globales] replace: eliminados {eliminados} registros "
                    f"{ModelClass.__tablename__} origen={origen}"
                )

            hash_archivo = calcular_hash_archivo(filepath)
            df = _read_excel_robust(filepath)
            stats = _importar_df_a_staging(
                df,
                ModelClass=ModelClass,
                origen=origen,
                filename=filename,
                file_sha256=hash_archivo,
            )
            resultados[key] = {**stats, 'origen': origen, 'tipo': tipo_carga, 'archivo': filename}

            service.registrar_carga(
                archivo_nombre=filename,
                tipo_carga=tipo_carga,
                hash_archivo=hash_archivo,
                filas_insertadas=stats['filas_insertadas'],
                filas_duplicadas=stats['filas_duplicadas'],
                filas_sin_mapeo=0,
                filas_error=stats['filas_error'],
                usuario_id=usuario.id if usuario else None,
                auto_commit=False,
            )

            db.session.commit()
            current_app.logger.info(f"[cargar-globales] archivo {key} importado OK")
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(
                f"[cargar-globales] error en archivo {key}: {exc}", exc_info=True
            )
            errores_archivos[key] = str(exc)
        finally:
            # Liberar memoria del DataFrame y la sesión ORM inmediatamente.
            df = None  # noqa: F841
            db.session.expire_all()
            gc.collect()

    # Limpiar archivos temporales.
    for p in tmp_paths:
        try:
            os.remove(p)
        except Exception:
            pass

    if not resultados:
        return jsonify({
            'success': False,
            'error': 'Todos los archivos fallaron.',
            'replace': replace,
            'archivos': None,
            'errores': errores_archivos,
            'total_filas_insertadas': 0,
        }), 500

    total_insertadas = sum(r.get('filas_insertadas', 0) for r in resultados.values())
    return jsonify({
        'success': True,
        'replace': replace,
        'archivos': resultados,
        'errores': errores_archivos or None,
        'total_filas_insertadas': total_insertadas,
    }), 200


# ============================================================================
# ENDPOINTS API - COBERTURA Y HISTORIAL
# ============================================================================

def _dias_habiles_lun_sab(fecha_desde, fecha_hasta):
    """Genera lista de fechas hábiles lunes-sábado en el rango."""
    dias = []
    d = fecha_desde
    while d <= fecha_hasta:
        if d.weekday() < 6:  # 0=lun ... 5=sab, 6=dom
            dias.append(d)
        d += timedelta(days=1)
    return dias


def _normalizar_fecha_dia(valor):
    """Normaliza un valor de fecha/hora a `date` para comparaciones por día."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10])
    except (TypeError, ValueError):
        return valor


@sabiogo_bp.route('/api/cobertura-fechas')
@login_required
def cobertura_fechas():
    """Resumen mensual de cobertura de fechas cargadas por origen y tipo."""
    hoy = date.today()
    try:
        fecha_desde = date.fromisoformat(request.args.get('fecha_desde', ''))
    except (ValueError, TypeError):
        fecha_desde = hoy - timedelta(days=60)
    try:
        fecha_hasta = date.fromisoformat(request.args.get('fecha_hasta', ''))
    except (ValueError, TypeError):
        fecha_hasta = hoy

    if fecha_hasta < fecha_desde:
        fecha_desde, fecha_hasta = fecha_hasta, fecha_desde

    estados_validos = ('procesado', 'cargado')

    # Fechas con datos para ventas y compras
    def _fechas_con_datos(ModelClass):
        fecha_dia_expr = func.date(ModelClass.fecha).label('fecha_dia')
        rows = db.session.query(
            ModelClass.origen,
            fecha_dia_expr,
            func.count().label('filas'),
        ).filter(
            ModelClass.fecha >= fecha_desde,
            ModelClass.fecha <= fecha_hasta,
            ModelClass.estado.in_(estados_validos),
        ).group_by(
            ModelClass.origen,
            fecha_dia_expr,
        ).all()
        result = {}
        for r in rows:
            fecha_dia = _normalizar_fecha_dia(r.fecha_dia)
            key = (r.origen or 'LEGACY', fecha_dia)
            result[key] = r.filas
        return result

    ventas_data = _fechas_con_datos(StgSabiogoVentas)
    compras_data = _fechas_con_datos(StgSabiogoCompras)

    # Generar días hábiles L-S
    dias_habiles = _dias_habiles_lun_sab(fecha_desde, fecha_hasta)

    # Agrupar por mes
    meses = {}
    for d in dias_habiles:
        mes_key = d.strftime('%Y-%m')
        if mes_key not in meses:
            meses[mes_key] = []
        meses[mes_key].append(d)

    origenes = [ORIGEN_CARNES, ORIGEN_LACTEOS]
    resumen = []

    for mes_key in sorted(meses.keys()):
        dias_del_mes = meses[mes_key]
        entry = {'mes': mes_key}

        for tipo_label, data_dict in [('ventas', ventas_data), ('compras', compras_data)]:
            for origen in origenes:
                campo = f'{tipo_label}_{origen.lower()}'
                dias_cargados = []
                dias_faltantes = []
                filas_total = 0
                for d in dias_del_mes:
                    filas = data_dict.get((origen, d), 0)
                    if filas > 0:
                        dias_cargados.append(d.isoformat())
                        filas_total += filas
                    else:
                        dias_faltantes.append(d.isoformat())
                entry[campo] = {
                    'dias_cargados': len(dias_cargados),
                    'dias_habiles': len(dias_del_mes),
                    'filas': filas_total,
                    'dias_faltantes': dias_faltantes,
                }
        resumen.append(entry)

    return jsonify({
        'rango': {'desde': fecha_desde.isoformat(), 'hasta': fecha_hasta.isoformat()},
        'resumen': resumen,
    })


@sabiogo_bp.route('/api/historial-cargas')
@login_required
def historial_cargas():
    """Últimas cargas registradas en LogSabiogoCarga."""
    limit_raw = request.args.get('limit')
    try:
        limit = min(int(limit_raw) if limit_raw is not None else 10, 50)
        if limit < 1:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({'error': 'El parámetro limit debe ser un entero positivo'}), 400
    logs = LogSabiogoCarga.query.order_by(
        LogSabiogoCarga.fecha_carga.desc()
    ).limit(limit).all()

    items = []
    for log in logs:
        items.append({
            'id': log.id,
            'fecha_carga': log.fecha_carga.isoformat() if log.fecha_carga else None,
            'archivo_nombre': log.archivo_nombre,
            'tipo_carga': log.tipo_carga,
            'filas_insertadas': log.filas_insertadas,
            'filas_duplicadas': log.filas_duplicadas,
            'filas_error': log.filas_error,
            'observaciones': log.observaciones,
        })

    return jsonify({'items': items})


@sabiogo_bp.route('/api/purgar-duplicados', methods=['POST'])
@login_required
def purgar_duplicados():
    """Elimina duplicados heredados que hayan quedado en staging."""
    try:
        purgados = _purgar_duplicados_staging()
        db.session.commit()
        return jsonify({'success': True, 'purgados': purgados})
    except Exception as exc:
        db.session.rollback()
        current_app.logger.error(f"Error purgando duplicados heredados: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500


# ============================================================================
# ENDPOINTS API - MAPEOS
# ============================================================================

@sabiogo_bp.route("/api/mapeos/productos")
@login_required
def listar_mapeos_productos():
    """Lista códigos de productos con estado de mapeo."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    estado = request.args.get('estado')  # 'mapeado', 'sin_mapear'
    origen = request.args.get('origen')
    
    query = SabiogoProductMap.query.options(joinedload(SabiogoProductMap.product))

    if origen:
        query = query.filter((SabiogoProductMap.origen == origen) | (SabiogoProductMap.origen.is_(None)))
    
    if estado == 'mapeado':
        query = query.filter(
            SabiogoProductMap.product_id.isnot(None),
            SabiogoProductMap.activo == True
        )
    elif estado == 'sin_mapear':
        query = query.filter(SabiogoProductMap.product_id.is_(None))
    
    pagination = query.order_by(SabiogoProductMap.codigo).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    items = []
    for mapeo in pagination.items:
        items.append({
            'id': mapeo.id,
            'origen': mapeo.origen or ORIGEN_LEGACY,
            'codigo': mapeo.codigo,
            'producto_descripcion': mapeo.producto_descripcion,
            'marca': mapeo.marca,
            'modelo': mapeo.modelo,
            'product_id': mapeo.product_id,
            'product_name': mapeo.product.name if mapeo.product else None,
            'activo': mapeo.activo,
            'mapeado': mapeo.product_id is not None
        })
    
    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })


@sabiogo_bp.route("/api/mapeos/productos/<codigo>", methods=["PUT"])
@login_required
def actualizar_mapeo_producto(codigo):
    """
    Asigna product_id a un código SabioGo.
    
    JSON body:
        - product_id: ID del producto
    """
    data = request.get_json()
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'error': 'product_id requerido'}), 400
    
    # Verificar que el producto existe
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404
    
    origen = request.args.get('origen') or (request.get_json(silent=True) or {}).get('origen')
    if not origen:
        return jsonify({'error': 'origen requerido (query param o JSON body)'}), 400

    # Actualizar mapeo (por origen+codigo)
    mapeo = SabiogoProductMap.query.filter_by(origen=origen, codigo=codigo).first()
    if not mapeo:
        return jsonify({'error': 'Código no encontrado'}), 404
    
    mapeo.product_id = product_id
    mapeo.activo = True
    db.session.commit()
    
    return jsonify({
        'success': True,
        'mapeo': {
            'codigo': mapeo.codigo,
            'product_id': mapeo.product_id,
            'product_name': product.name
        }
    })


@sabiogo_bp.route("/api/mapeos/clientes")
@login_required
def listar_mapeos_clientes():
    """Lista clientes con estado de mapeo."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    pagination = SabiogoClientMap.query.options(joinedload(SabiogoClientMap.client)).order_by(
        SabiogoClientMap.cliente
    ).paginate(
        page=page,
        per_page=per_page,
        error_out=False
    )
    
    items = []
    for mapeo in pagination.items:
        items.append({
            'id': mapeo.id,
            'cliente': mapeo.cliente,
            'condicion_iva': mapeo.condicion_iva,
            'zona': mapeo.zona,
            'localidad': mapeo.localidad,
            'client_id': mapeo.client_id,
            'client_name': mapeo.client.name if mapeo.client else None,
            'activo': mapeo.activo,
            'mapeado': mapeo.client_id is not None
        })
    
    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages
    })


@sabiogo_bp.route('/api/ventas')
@login_required
def listar_ventas_staging():
    """Lista ventas de staging con paginación server-side y filtros."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = max(10, min(per_page, 200))

    estado = request.args.get('estado', 'procesado')
    fecha_desde = request.args.get('fecha_desde')
    fecha_hasta = request.args.get('fecha_hasta')
    codigo = request.args.get('codigo')
    cliente = request.args.get('cliente')
    producto = request.args.get('producto')

    query = StgSabiogoVentas.query

    if estado and estado != 'todos':
        query = query.filter(StgSabiogoVentas.estado == estado)

    if fecha_desde:
        try:
            fecha_desde_dt = date.fromisoformat(fecha_desde)
            query = query.filter(StgSabiogoVentas.fecha >= fecha_desde_dt)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_desde inválido'}), 400

    if fecha_hasta:
        try:
            fecha_hasta_dt = date.fromisoformat(fecha_hasta)
            query = query.filter(StgSabiogoVentas.fecha <= fecha_hasta_dt)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_hasta inválido'}), 400

    if codigo:
        query = query.filter(StgSabiogoVentas.codigo.ilike(f'%{codigo}%'))
    if cliente:
        query = query.filter(StgSabiogoVentas.cliente.ilike(f'%{cliente}%'))
    if producto:
        query = query.filter(StgSabiogoVentas.producto.ilike(f'%{producto}%'))

    pagination = query.order_by(
        StgSabiogoVentas.fecha.desc(),
        StgSabiogoVentas.id.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for venta in pagination.items:
        subtot = float(venta.subtot or 0)
        moniva = float(getattr(venta, 'moniva', 0) or 0)
        items.append({
            'id': venta.id,
            'fecha': venta.fecha.isoformat() if venta.fecha else None,
            'codigo': venta.codigo,
            'producto': venta.producto,
            'cliente': venta.cliente,
            'sucursal': venta.sucursal,
            'kilos': float(venta.kilos or 0),
            'cajas': float(venta.cajas or 0),
            'subtot': subtot,
            # En el staging real no siempre existe columna `total`; derivamos por fallback.
            'total': subtot + moniva,
            'estado': venta.estado,
        })

    return jsonify({
        'items': items,
        'total': pagination.total,
        'page': page,
        'per_page': per_page,
        'pages': pagination.pages,
    })


@sabiogo_bp.route("/api/refresh-facts", methods=["POST"])
@login_required
def refresh_facts():
    """Ejecuta REFRESH MATERIALIZED VIEW en facts."""
    service = SabiogoService()
    try:
        result = service.refresh_facts()
        return jsonify({'success': True, **result})
    except Exception as e:
        current_app.logger.error(f"Error refrescando facts: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


@sabiogo_bp.route("/api/autogenerar-mapeos", methods=["POST"])
@login_required
def autogenerar_mapeos():
    """Autogenera mapeos faltantes (productos/clientes) desde staging."""
    try:
        stats = _autogenerar_mapeos_faltantes()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        current_app.logger.error(f"Error autogenerando mapeos SabioGo: {e}", exc_info=True)
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


# ============================================================================
# ENDPOINTS API - CONSULTAS DE RENTABILIDAD
# ============================================================================

@sabiogo_bp.route("/api/rentabilidad/producto/<int:product_id>")
@login_required
def rentabilidad_producto(product_id):
    """
    Obtiene rentabilidad de un producto específico.
    
    Query params:
        - fecha_inicio: YYYY-MM-DD
        - fecha_fin: YYYY-MM-DD
    """
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Defaults: último mes
    if not fecha_fin:
        fecha_fin = date.today()
    else:
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_fin inválido'}), 400
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_inicio inválido'}), 400
    
    # Verificar que el producto existe
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'error': 'Producto no encontrado'}), 404
    
    # Obtener rentabilidad
    service = SabiogoService()
    try:
        rentabilidad = service.get_rentabilidad_producto(product_id, fecha_inicio, fecha_fin)
        
        # Crear DTO
        from dtos.sabiogo_dto import RentabilidadProductoDTO
        dto = RentabilidadProductoDTO.from_service_result(
            rentabilidad,
            product.name,
            product.sku
        )
        
        return jsonify(dto.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error obteniendo rentabilidad: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


@sabiogo_bp.route("/api/rentabilidad/categoria/<categoria>")
@login_required
def rentabilidad_categoria(categoria):
    """
    Obtiene rentabilidad de todos los productos de una categoría.
    
    Query params:
        - fecha_inicio: YYYY-MM-DD
        - fecha_fin: YYYY-MM-DD
    """
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Defaults: último mes
    if not fecha_fin:
        fecha_fin = date.today()
    else:
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_fin inválido'}), 400
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_inicio inválido'}), 400
    
    service = SabiogoService()
    try:
        productos = service.get_rentabilidad_por_categoria(categoria, fecha_inicio, fecha_fin)
        
        from dtos.sabiogo_dto import RentabilidadCategoriaDTO
        dto = RentabilidadCategoriaDTO(categoria=categoria)
        
        for producto_data in productos:
            dto.agregar_producto(producto_data)
        
        return jsonify(dto.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error obteniendo rentabilidad por categoría: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


@sabiogo_bp.route("/api/rentabilidad/top")
@login_required
def rentabilidad_top():
    """
    Obtiene top de productos por margen.
    
    Query params:
        - limit: número de productos (default: 10)
        - fecha_inicio: YYYY-MM-DD
        - fecha_fin: YYYY-MM-DD
    """
    limit = request.args.get('limit', 10, type=int)
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Defaults: último mes
    if not fecha_fin:
        fecha_fin = date.today()
    else:
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_fin inválido'}), 400
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_inicio inválido'}), 400
    
    service = SabiogoService()
    try:
        productos = service.get_top_productos_margen(limit, fecha_inicio, fecha_fin)
        
        # Convertir a DTOs
        from dtos.sabiogo_dto import ProductoTopMargenDTO
        dtos = [ProductoTopMargenDTO.from_query_result(p) for p in productos]
        
        return jsonify({
            'periodo': {
                'inicio': fecha_inicio.isoformat(),
                'fin': fecha_fin.isoformat()
            },
            'limit': limit,
            'productos': [dto.to_dict() for dto in dtos]
        })
    except Exception as e:
        current_app.logger.error(f"Error obteniendo top productos: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


@sabiogo_bp.route("/api/rentabilidad/resumen")
@login_required
def rentabilidad_resumen():
    """
    Obtiene resumen global de rentabilidad.
    
    Query params:
        - fecha_inicio: YYYY-MM-DD
        - fecha_fin: YYYY-MM-DD
    """
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Defaults: último mes
    if not fecha_fin:
        fecha_fin = date.today()
    else:
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_fin inválido'}), 400
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_inicio inválido'}), 400
    
    service = SabiogoService()
    try:
        resumen = service.get_rentabilidad_resumen(fecha_inicio, fecha_fin)
        
        from dtos.sabiogo_dto import RentabilidadResumenDTO
        dto = RentabilidadResumenDTO.from_service_result(resumen, fecha_inicio, fecha_fin)
        
        return jsonify(dto.to_dict())
    except Exception as e:
        current_app.logger.error(f"Error obteniendo resumen: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500


@sabiogo_bp.route("/api/rentabilidad/exportar")
@login_required
def exportar_rentabilidad():
    """
    Exporta análisis de rentabilidad a Excel.
    
    Query params:
        - fecha_inicio: YYYY-MM-DD
        - fecha_fin: YYYY-MM-DD
    """
    fecha_inicio = request.args.get('fecha_inicio')
    fecha_fin = request.args.get('fecha_fin')
    
    # Defaults: último mes
    if not fecha_fin:
        fecha_fin = date.today()
    else:
        try:
            fecha_fin = date.fromisoformat(fecha_fin)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_fin inválido'}), 400
    
    if not fecha_inicio:
        fecha_inicio = fecha_fin - timedelta(days=30)
    else:
        try:
            fecha_inicio = date.fromisoformat(fecha_inicio)
        except ValueError:
            return jsonify({'error': 'Formato de fecha_inicio inválido'}), 400
    
    try:
        import pandas as pd
        from io import BytesIO
        
        service = SabiogoService()
        
        # Obtener datos
        resumen = service.get_rentabilidad_resumen(fecha_inicio, fecha_fin)
        top_productos = service.get_top_productos_margen(limit=50, fecha_inicio=fecha_inicio, fecha_fin=fecha_fin)
        
        # Crear Excel con múltiples sheets
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Sheet 1: Resumen
            df_resumen = pd.DataFrame([{
                'Total Ingresos': resumen.get('total_ingresos', 0),
                'Total Costos': resumen.get('total_costos', 0),
                'Margen Bruto': resumen.get('margen_bruto', 0),
                'Margen %': resumen.get('margen_porcentual', 0),
                'Productos Activos': resumen.get('productos_activos', 0)
            }])
            df_resumen.to_excel(writer, sheet_name='Resumen', index=False)
            
            # Sheet 2: Top Productos
            df_productos = pd.DataFrame(top_productos)
            df_productos.to_excel(writer, sheet_name='Top Productos', index=False)
            
            # Sheet 3: Por Categoría (obtener categorías únicas)
            categorias = db.session.query(Product.category).distinct().all()
            categorias_data = []
            
            for (categoria,) in categorias:
                if categoria:
                    cat_data = service.get_rentabilidad_por_categoria(categoria, fecha_inicio, fecha_fin)
                    for producto in cat_data:
                        producto['categoria'] = categoria
                        categorias_data.append(producto)
            
            if categorias_data:
                df_categorias = pd.DataFrame(categorias_data)
                df_categorias.to_excel(writer, sheet_name='Por Categoria', index=False)
        
        output.seek(0)
        
        filename = f"rentabilidad_{fecha_inicio}_{fecha_fin}.xlsx"
        
        from flask import send_file
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        current_app.logger.error(f"Error exportando rentabilidad: {e}")
        return jsonify({'error': 'No se pudo completar la operación. Intentá de nuevo.'}), 500
