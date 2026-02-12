"""Blueprint para administración y análisis SabioGo."""

from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import pandas as pd
import hashlib
import os
from datetime import datetime, date, timedelta
from typing import Optional

from models import db
from models.sabiogo import (
    StgSabiogoVentas,
    StgSabiogoCompras,
    SabiogoProductMap,
    SabiogoClientMap,
    SabiogoLocationMap
)
from models.core.product import Product
from services.sabiogo_service import SabiogoService
from dtos.sabiogo_dto import (
    RentabilidadProductoDTO,
    RentabilidadResumenDTO,
    ProductoTopMargenDTO
)
from security import protect_blueprint

sabiogo_bp = Blueprint("sabiogo", __name__, url_prefix="/sabiogo")
protect_blueprint(sabiogo_bp, "admin")


ALLOWED_EXTENSIONS = {'xls', 'xlsx'}


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


# ============================================================================
# ENDPOINTS HTML - ADMINISTRACIÓN
# ============================================================================

@sabiogo_bp.route("/admin")
@login_required
def admin_panel():
    """Panel de administración SabioGo."""
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
    """
    Carga archivo XLS de ventas o compras.
    
    Form data:
        - file: archivo XLS
        - tipo: 'ventas' o 'compras'
    """
    if 'file' not in request.files:
        return jsonify({'error': 'No se envió archivo'}), 400
    
    file = request.files['file']
    tipo = request.form.get('tipo', 'ventas')
    
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': 'Extensión no permitida. Use .xls o .xlsx'}), 400
    
    if tipo not in ['ventas', 'compras']:
        return jsonify({'error': 'Tipo debe ser "ventas" o "compras"'}), 400
    
    try:
        # Guardar archivo temporal
        filename = secure_filename(file.filename)
        upload_folder = current_app.config.get('UPLOAD_FOLDER', '/tmp')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)
        
        filepath = os.path.join(upload_folder, filename)
        file.save(filepath)
        
        # Calcular hash
        hash_archivo = calcular_hash_archivo(filepath)
        
        # Leer Excel con pandas
        df = pd.read_excel(filepath)
        
        # Validar columnas requeridas
        columnas_requeridas = ['fecha', 'codigo', 'producto']
        if not all(col in df.columns for col in columnas_requeridas):
            os.remove(filepath)
            return jsonify({
                'error': f'Faltan columnas requeridas: {columnas_requeridas}'
            }), 400
        
        # Insertar en staging
        filas_insertadas = 0
        filas_error = 0
        
        ModelClass = StgSabiogoVentas if tipo == 'ventas' else StgSabiogoCompras
        
        for _, row in df.iterrows():
            try:
                # Convertir row a dict y limpiar
                data = row.to_dict()
                
                # Limpiar None y NaN
                for key, value in data.items():
                    if pd.isna(value):
                        data[key] = None
                
                # Agregar metadatos
                data['fuente_archivo'] = filename
                data['hash_archivo'] = hash_archivo
                data['estado'] = 'pendiente'
                
                # Crear registro
                registro = ModelClass(**data)
                db.session.add(registro)
                filas_insertadas += 1
                
            except Exception as e:
                filas_error += 1
                current_app.logger.error(f"Error insertando fila: {e}")
        
        db.session.commit()
        
        # Ejecutar validación de duplicados
        try:
            duplicados = ModelClass.validar_duplicados(db.session)
            current_app.logger.info(f"Validación de duplicados: {duplicados} registros marcados")
        except Exception as e:
            current_app.logger.warning(f"Error en validación de duplicados: {e}")
            duplicados = 0
        
        # Contar registros sin mapeo
        if tipo == 'ventas':
            sin_mapeo_query = db.session.query(StgSabiogoVentas).filter(
                StgSabiogoVentas.hash_archivo == hash_archivo,
                StgSabiogoVentas.codigo.notin_(
                    db.session.query(SabiogoProductMap.codigo).filter(
                        SabiogoProductMap.activo == True,
                        SabiogoProductMap.product_id.isnot(None)
                    )
                )
            ).count()
        else:
            sin_mapeo_query = db.session.query(StgSabiogoCompras).filter(
                StgSabiogoCompras.hash_archivo == hash_archivo,
                StgSabiogoCompras.codigo.notin_(
                    db.session.query(SabiogoProductMap.codigo).filter(
                        SabiogoProductMap.activo == True,
                        SabiogoProductMap.product_id.isnot(None)
                    )
                )
            ).count()
        
        # Registrar log de auditoría
        service = SabiogoService()
        service.registrar_carga(
            archivo_nombre=filename,
            tipo_carga=tipo,
            hash_archivo=hash_archivo,
            filas_insertadas=filas_insertadas,
            filas_duplicadas=duplicados,
            filas_sin_mapeo=sin_mapeo_query,
            filas_error=filas_error,
            usuario_id=current_user.id
        )
        
        # Limpiar archivo temporal
        os.remove(filepath)
        
        return jsonify({
            'success': True,
            'mensaje': f'Archivo cargado exitosamente',
            'filas_insertadas': filas_insertadas,
            'filas_duplicadas': duplicados,
            'filas_sin_mapeo': sin_mapeo_query,
            'filas_error': filas_error
        })
        
    except Exception as e:
        current_app.logger.error(f"Error cargando archivo: {e}")
        return jsonify({'error': str(e)}), 500


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
    
    query = SabiogoProductMap.query
    
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
    
    # Actualizar mapeo
    mapeo = SabiogoProductMap.query.filter_by(codigo=codigo).first()
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


@sabiogo_bp.route("/api/refresh-facts", methods=["POST"])
@login_required
def refresh_facts():
    """Ejecuta REFRESH MATERIALIZED VIEW en facts."""
    try:
        # Refrescar vistas materializadas
        db.session.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY fact_ventas_sabiogo")
        db.session.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY fact_costos_sabiogo")
        db.session.commit()
        
        return jsonify({
            'success': True,
            'mensaje': 'Vistas materializadas actualizadas'
        })
    except Exception as e:
        current_app.logger.error(f"Error refrescando facts: {e}")
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
