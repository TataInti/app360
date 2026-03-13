"""Blueprint para administración y análisis SabioGo."""

from flask import Blueprint, render_template, request, jsonify, current_app, session, redirect, url_for
from functools import wraps
from werkzeug.utils import secure_filename
import pandas as pd
import hashlib
import os
import re
from datetime import datetime, date, timedelta
from typing import Optional
from sqlalchemy import text, func, inspect as sa_inspect

from models import db
from models.sabiogo import (
    StgSabiogoVentas,
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap
)
from models.core.product import Product
from models.crm.client import Client
from services.sabiogo_service import SabiogoService
from dtos.sabiogo_dto import (
    RentabilidadProductoDTO,
    RentabilidadResumenDTO,
    ProductoTopMargenDTO
)
from security import protect_blueprint
from models.core.user import User

sabiogo_bp = Blueprint("sabiogo", __name__, url_prefix="/sabiogo")
protect_blueprint(sabiogo_bp, "admin")


ALLOWED_EXTENSIONS = {'xls', 'xlsx'}


ORIGEN_LEGACY = 'LEGACY'
ORIGEN_CARNES = 'CARNES'
ORIGEN_LACTEOS = 'LACTEOS'


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
        # En desarrollo local permitimos bypass para poder usar la UI sin sesión.
        if current_app.config.get('LOCAL_DEV_BYPASS_AUTH'):
            return f(*args, **kwargs)
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
    if SabiogoProductMap.query.count() == 0 or SabiogoClientMap.query.count() == 0:
        try:
            auto_stats = _autogenerar_mapeos_faltantes()
            current_app.logger.info(f"Autogeneración de mapeos SabioGo: {auto_stats}")
        except Exception as e:
            current_app.logger.error(f"Error autogenerando mapeos SabioGo: {e}")

    # Estadísticas básicas
    total_productos_map = SabiogoProductMap.query.count()
    productos_mapeados = SabiogoProductMap.query.filter_by(activo=True).filter(
        SabiogoProductMap.product_id.isnot(None)
    ).count()
    
    total_clientes_map = SabiogoClientMap.query.count()
    clientes_mapeados = SabiogoClientMap.query.filter_by(activo=True).filter(
        SabiogoClientMap.client_id.isnot(None)
    ).count()
    
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


def _importar_df_a_staging(df: pd.DataFrame, *, ModelClass, origen: str, filename: str, file_sha256: str) -> dict:
    """Importa un DataFrame ya validado a la tabla de staging correspondiente."""
    valid_cols = _get_model_columns(ModelClass)
    filas_insertadas = 0
    filas_error = 0

    # Carga por lotes para minimizar overhead de ORM fila-a-fila.
    batch_size = 2500
    batch_rows = []
    df_clean = df.where(pd.notna(df), None)

    for row_idx, row in enumerate(df_clean.to_dict(orient='records')):
        try:
            data = {k: v for k, v in row.items() if k in valid_cols}

            codigo_raw = data.get('codigo')
            data['codigo_raw'] = None if codigo_raw is None else str(codigo_raw)
            data['codigo'] = normalize_codigo(codigo_raw)
            data['origen'] = origen
            data['fuente_archivo'] = filename
            data['hash_archivo'] = file_sha256
            data['estado'] = 'pendiente'

            batch_rows.append(data)
            filas_insertadas += 1

            if len(batch_rows) >= batch_size:
                db.session.bulk_insert_mappings(ModelClass, batch_rows)
                db.session.commit()
                batch_rows = []
        except Exception as exc:
            filas_error += 1
            current_app.logger.debug(f"Error fila {row_idx}: {exc}")

    if batch_rows:
        db.session.bulk_insert_mappings(ModelClass, batch_rows)
        db.session.commit()

    # Marcar duplicados pendientes
    try:
        duplicados = ModelClass.validar_duplicados(db.session)
    except Exception:
        duplicados = 0

    # Promover pendientes a procesado
    filas_procesadas = db.session.query(ModelClass).filter(
        ModelClass.hash_archivo == file_sha256,
        ModelClass.estado == 'pendiente',
    ).update({'estado': 'procesado'}, synchronize_session=False)
    db.session.commit()

    return {
        'filas_insertadas': filas_insertadas,
        'filas_procesadas': int(filas_procesadas or 0),
        'filas_duplicadas': int(duplicados or 0),
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
    sync_objetivos = request.form.get('sync_objetivos', 'false').lower() in ('true', '1', 'yes')
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

    # ── Reemplazo de datos ──────────────────────────────────────────────────
    if replace:
        for key, file in archivos_recibidos.items():
            origen, _, ModelClass = ARCHIVOS_CONFIG[key]
            eliminados = db.session.query(ModelClass).filter(
                ModelClass.origen == origen
            ).delete(synchronize_session=False)
            current_app.logger.info(
                f"[cargar-globales] replace: eliminados {eliminados} registros "
                f"{ModelClass.__tablename__} origen={origen}"
            )
        db.session.commit()

    # ── Importación por archivo ─────────────────────────────────────────────
    resultados = {}
    errores = {}
    tmp_paths = []

    try:
        for key, file in archivos_recibidos.items():
            origen, tipo_carga, ModelClass = ARCHIVOS_CONFIG[key]
            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_folder, f"global_{key}_{filename}")
            file.save(filepath)
            tmp_paths.append(filepath)

            try:
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

                # Log de auditoría
                service = SabiogoService()
                usuario = User.query.filter_by(username=session.get('user')).first()
                service.registrar_carga(
                    archivo_nombre=filename,
                    tipo_carga=tipo_carga,
                    hash_archivo=hash_archivo,
                    filas_insertadas=stats['filas_insertadas'],
                    filas_duplicadas=stats['filas_duplicadas'],
                    filas_sin_mapeo=0,
                    filas_error=stats['filas_error'],
                    usuario_id=usuario.id if usuario else None,
                )
            except Exception as exc:
                current_app.logger.error(f"[cargar-globales] error en {key}: {exc}", exc_info=True)
                errores[key] = str(exc)

        # Sincronización PRE desacoplada de la carga principal.
        objetivos_sync = None
        periodos_detectados = []
        ventas_keys = [k for k in archivos_recibidos if 'ventas' in k and k not in errores]
        if ventas_keys:
            try:
                periodos_q = db.session.query(StgSabiogoVentas.fecha).filter(
                    StgSabiogoVentas.origen.in_(
                        [ARCHIVOS_CONFIG[k][0] for k in ventas_keys]
                    ),
                    StgSabiogoVentas.estado == 'procesado',
                    StgSabiogoVentas.fecha.isnot(None),
                ).distinct().all()
                periodos = sorted({f"{r.fecha.year:04d}-{r.fecha.month:02d}" for r in periodos_q if r.fecha})
                periodos_detectados = periodos[:24]
                if sync_objetivos and periodos_detectados:
                    service = SabiogoService()
                    sync_runs = []
                    for periodo in periodos_detectados:
                        try:
                            sync_runs.append(service.sincronizar_objetivos_pre(periodo=periodo))
                        except Exception as se:
                            sync_runs.append({'periodo': periodo, 'error': str(se)})
                    objetivos_sync = {'ejecuciones': sync_runs}
            except Exception as se:
                current_app.logger.warning(f"[cargar-globales] sync PRE falló: {se}")

    finally:
        for p in tmp_paths:
            try:
                os.remove(p)
            except Exception:
                pass

    total_insertadas = sum(r.get('filas_insertadas', 0) for r in resultados.values())
    return jsonify({
        'success': len(errores) == 0,
        'replace': replace,
        'archivos': resultados,
        'errores': errores if errores else None,
        'total_filas_insertadas': total_insertadas,
        'sync_objetivos_ejecutado': bool(sync_objetivos),
        'periodos_detectados': periodos_detectados if 'periodos_detectados' in locals() else [],
        'objetivos_sync': objetivos_sync,
    }), (200 if not errores else 207)


@sabiogo_bp.route('/api/sync-objetivos-pre', methods=['POST'])
@login_required
def sync_objetivos_pre():
    """Endpoint para sincronización manual/nocturna de objetivos desde ventas PRE."""
    payload = request.get_json(silent=True) or {}
    periodo = payload.get('periodo') or request.args.get('periodo')

    service = SabiogoService()
    try:
        resultado = service.sincronizar_objetivos_pre(periodo=periodo)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"Error sincronizando objetivos PRE: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'success': True, 'resultado': resultado})


@sabiogo_bp.route('/api/sync-objetivos-pre-cron', methods=['POST'])
def sync_objetivos_pre_cron():
    """Endpoint para cron nocturno protegido por token en header."""
    configured_token = current_app.config.get('SABIOGO_CRON_TOKEN') or os.getenv('SABIOGO_CRON_TOKEN')
    if not configured_token:
        return jsonify({'error': 'SABIOGO_CRON_TOKEN no configurado'}), 503

    received_token = request.headers.get('X-App360-Cron-Token', '')
    if received_token != configured_token:
        return jsonify({'error': 'Token de cron inválido'}), 401

    payload = request.get_json(silent=True) or {}
    periodo = payload.get('periodo') or request.args.get('periodo')

    service = SabiogoService()
    try:
        resultado = service.sincronizar_objetivos_pre(periodo=periodo)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    except Exception as exc:
        current_app.logger.error(f"Error en sync_objetivos_pre_cron: {exc}", exc_info=True)
        return jsonify({'error': str(exc)}), 500

    return jsonify({'success': True, 'resultado': resultado})


# ============================================================================
# ENDPOINTS API - MAPEOS
# ============================================================================

@sabiogo_bp.route("/api/mapeos/productos")
@login_required
def listar_mapeos_productos():
    """Lista códigos de productos con estado de mapeo."""
    if SabiogoProductMap.query.count() == 0:
        _autogenerar_mapeos_faltantes()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    estado = request.args.get('estado')  # 'mapeado', 'sin_mapear'
    origen = request.args.get('origen')
    
    query = SabiogoProductMap.query

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
    if SabiogoClientMap.query.count() == 0:
        _autogenerar_mapeos_faltantes()

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    
    pagination = SabiogoClientMap.query.order_by(
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
    try:
        # Si hay datos cargados pero no procesados, promover estado a 'procesado'
        # para que las facts (que filtran por estado) muestren datos.
        promoted_ventas = db.session.execute(
            text(
                """
                UPDATE stg_sabiogo_ventas
                SET estado = 'procesado'
                WHERE estado IN ('cargado', 'pendiente')
                """
            )
        ).rowcount

        promoted_compras = db.session.execute(
            text(
                """
                UPDATE stg_sabiogo_compras
                SET estado = 'procesado'
                WHERE estado IN ('cargado', 'pendiente')
                """
            )
        ).rowcount

        # Refrescar vistas materializadas
        db.session.execute(text("REFRESH MATERIALIZED VIEW fact_ventas_sabiogo"))
        db.session.execute(text("REFRESH MATERIALIZED VIEW fact_costos_sabiogo"))
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mensaje': 'Vistas materializadas actualizadas',
            'staging_promovidos': {
                'ventas': int(promoted_ventas or 0),
                'compras': int(promoted_compras or 0),
            },
        })
    except Exception as e:
        current_app.logger.error(f"Error refrescando facts: {e}")
        return jsonify({'error': str(e)}), 500


@sabiogo_bp.route("/api/autogenerar-mapeos", methods=["POST"])
@login_required
def autogenerar_mapeos():
    """Autogenera mapeos faltantes (productos/clientes) desde staging."""
    try:
        stats = _autogenerar_mapeos_faltantes()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        current_app.logger.error(f"Error autogenerando mapeos SabioGo: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500


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
        return jsonify({'error': str(e)}), 500
