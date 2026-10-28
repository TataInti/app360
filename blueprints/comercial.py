from datetime import date, datetime, timedelta
from decimal import Decimal

from flask import Blueprint, request, jsonify, render_template, session as flask_session
from sqlalchemy.exc import IntegrityError

from models import (
    Client,
    ComercialObjetivo,
    ComercialObjetivoVinculo,
    ComercialVendedor,
    Comision,
    ComisionDetalle,
    Employee,
    Goal,
    Product,
    Promocion,
    PromocionAplicada,
    User,
    Venta,
    db,
)
from security import protect_blueprint
from services.sabiogo_service import SabiogoService

comercial_bp = Blueprint("comercial", __name__)

protect_blueprint(comercial_bp, "comercial")


# RUTAS WEB
@comercial_bp.route("/comercial/objetivos", methods=["GET"])
def objetivos_ventas():
    """Panel de Objetivos de Venta por vendedor"""
    return render_template("objetivos_ventas.html")


# Endpoints para Promociones

@comercial_bp.route("/api/comercial/promociones", methods=["GET"])
def promociones_listar():
    """Listar promociones activas"""
    fecha_actual = datetime.now().date()

    query = Promocion.query.filter(
        Promocion.activo == True,
        Promocion.fecha_inicio <= fecha_actual,
        Promocion.fecha_fin >= fecha_actual
    )

    tipo = request.args.get("tipo")
    if tipo:
        query = query.filter(Promocion.tipo == tipo)

    promociones = query.order_by(Promocion.fecha_fin).all()

    return jsonify({
        "promociones": [{
            "id": p.id,
            "nombre": p.nombre,
            "descripcion": p.descripcion,
            "tipo": p.tipo,
            "valor": float(p.valor),
            "fecha_inicio": p.fecha_inicio.isoformat(),
            "fecha_fin": p.fecha_fin.isoformat(),
            "producto": p.producto.name if p.producto else None,
            "cliente": p.cliente.name if p.cliente else None,
            "cantidad_minima": p.cantidad_minima,
            "monto_minimo": float(p.monto_minimo)
        } for p in promociones]
    })


@comercial_bp.route("/api/comercial/promociones", methods=["POST"])
def promociones_crear():
    """Crear nueva promoción"""
    data = request.get_json()

    required_fields = ["nombre", "tipo", "valor", "fecha_inicio", "fecha_fin"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400

    try:
        fecha_inicio = datetime.strptime(data["fecha_inicio"], "%Y-%m-%d").date()
        fecha_fin = datetime.strptime(data["fecha_fin"], "%Y-%m-%d").date()
        valor = Decimal(str(data["valor"]))
    except:
        return jsonify({"error": "Datos de fecha o valor inválidos"}), 400

    if fecha_inicio > fecha_fin:
        return jsonify({"error": "Fecha de inicio no puede ser posterior a fecha fin"}), 400

    # Validar producto si se especifica
    producto_id = data.get("producto_id")
    if producto_id and not Product.query.get(producto_id):
        return jsonify({"error": "Producto no encontrado"}), 404

    # Validar cliente si se especifica
    cliente_id = data.get("cliente_id")
    if cliente_id and not Client.query.get(cliente_id):
        return jsonify({"error": "Cliente no encontrado"}), 404

    promocion = Promocion(
        nombre=data["nombre"],
        descripcion=data.get("descripcion", ""),
        tipo=data["tipo"],
        valor=valor,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
        producto_id=producto_id,
        cliente_id=cliente_id,
        cantidad_minima=data.get("cantidad_minima", 1),
        monto_minimo=Decimal(str(data.get("monto_minimo", 0)))
    )

    db.session.add(promocion)
    db.session.commit()

    return jsonify({
        "message": "Promoción creada",
        "promocion": {
            "id": promocion.id,
            "nombre": promocion.nombre,
            "tipo": promocion.tipo,
            "valor": float(promocion.valor)
        }
    }), 201


@comercial_bp.route("/api/comercial/promociones/<int:promocion_id>", methods=["DELETE"])
def promociones_eliminar(promocion_id):
    """Desactivar promoción"""
    promocion = Promocion.query.get_or_404(promocion_id)
    promocion.activo = False
    db.session.commit()

    return jsonify({"message": "Promoción desactivada"})


# Endpoints para Simulador de Rentabilidad

@comercial_bp.route("/api/comercial/simulador", methods=["POST"])
def simulador_rentabilidad():
    """Simular impacto de promoción en rentabilidad"""
    data = request.get_json()

    promocion_data = data.get("promocion", {})
    periodo_dias = data.get("periodo_dias", 30)

    # Crear promoción temporal para simulación
    try:
        valor = Decimal(str(promocion_data.get("valor", 0)))
        tipo = promocion_data.get("tipo", "descuento")
    except:
        return jsonify({"error": "Datos de promoción inválidos"}), 400

    # Obtener ventas del período
    fecha_fin = datetime.now().date()
    fecha_inicio = fecha_fin - timedelta(days=periodo_dias)

    query = Venta.query.filter(Venta.fecha >= fecha_inicio, Venta.fecha <= fecha_fin)

    # Aplicar filtros de promoción
    producto_id = promocion_data.get("producto_id")
    cliente_id = promocion_data.get("cliente_id")
    cantidad_minima = promocion_data.get("cantidad_minima", 1)
    monto_minimo = Decimal(str(promocion_data.get("monto_minimo", 0)))

    if producto_id:
        query = query.filter(Venta.producto_id == producto_id)
    if cliente_id:
        query = query.filter(Venta.cliente_id == cliente_id)

    ventas = query.all()

    # Simular aplicación de promoción
    ventas_afectadas = []
    descuento_total = Decimal('0')
    margen_perdido_total = Decimal('0')

    for venta in ventas:
        cantidad = venta.cantidad
        precio_contrato = venta.precio_contrato
        precio_efectivo = venta.precio_efectivo
        subtotal = precio_contrato * cantidad

        # Verificar condiciones
        if cantidad >= cantidad_minima and subtotal >= monto_minimo:
            # Calcular descuento según tipo
            if tipo == "descuento":
                descuento = subtotal * (valor / 100)
            elif tipo == "monto_fijo":
                descuento = min(valor, subtotal)
            else:
                descuento = Decimal('0')

            margen_actual = precio_efectivo - precio_contrato
            margen_perdido = min(descuento, margen_actual)

            ventas_afectadas.append({
                "venta_id": venta.id,
                "cliente": venta.cliente.name,
                "producto": venta.producto.name,
                "subtotal_original": float(subtotal),
                "descuento": float(descuento),
                "margen_perdido": float(margen_perdido)
            })

            descuento_total += descuento
            margen_perdido_total += margen_perdido

    return jsonify({
        "simulacion": {
            "periodo_dias": periodo_dias,
            "ventas_total": len(ventas),
            "ventas_afectadas": len(ventas_afectadas),
            "descuento_total": float(descuento_total),
            "margen_perdido_total": float(margen_perdido_total),
            "impacto_porcentual": float((margen_perdido_total / max(sum(v.precio_contrato * v.cantidad for v in ventas), 1)) * 100)
        },
        "detalle_ventas": ventas_afectadas[:10]  # Limitar a 10 para no sobrecargar
    })


# Endpoints para Comisiones

@comercial_bp.route("/api/comercial/comisiones", methods=["GET"])
def comisiones_listar():
    """Listar comisiones por período"""
    periodo = request.args.get("periodo")  # YYYY-MM
    usuario_id = request.args.get("usuario_id")
    pagada = request.args.get("pagada")

    query = Comision.query

    if periodo:
        query = query.filter(Comision.periodo == periodo)
    if usuario_id:
        query = query.filter(Comision.usuario_id == usuario_id)
    if pagada is not None:
        query = query.filter(Comision.pagada == (pagada.lower() == "true"))

    comisiones = query.order_by(Comision.periodo.desc(), Comision.usuario_id).all()

    return jsonify({
        "comisiones": [{
            "id": c.id,
            "usuario": c.usuario.username if c.usuario else None,
            "periodo": c.periodo,
            "tipo_periodo": c.tipo_periodo,
            "ventas_total": float(c.ventas_total),
            "comision_total": float(c.comision_total),
            "porcentaje_promedio": float(c.porcentaje_promedio),
            "pagada": c.pagada,
            "fecha_pago": c.fecha_pago.isoformat() if c.fecha_pago else None
        } for c in comisiones]
    })


@comercial_bp.route("/api/comercial/comisiones/calcular", methods=["POST"])
def comisiones_calcular():
    """Calcular comisiones para un período"""
    data = request.get_json()

    periodo = data.get("periodo")  # YYYY-MM
    tipo_periodo = data.get("tipo_periodo", "mensual")
    usuario_id = data.get("usuario_id")  # null = todos los usuarios

    if not periodo:
        return jsonify({"error": "Período requerido"}), 400

    # Determinar rango de fechas
    try:
        if tipo_periodo == "mensual":
            year, month = map(int, periodo.split("-"))
            fecha_inicio = datetime(year, month, 1).date()
            if month == 12:
                fecha_fin = datetime(year + 1, 1, 1).date() - timedelta(days=1)
            else:
                fecha_fin = datetime(year, month + 1, 1).date() - timedelta(days=1)
        else:
            return jsonify({"error": "Tipo de período no soportado"}), 400
    except:
        return jsonify({"error": "Formato de período inválido"}), 400

    # Obtener usuarios vendedores (asumiendo rol específico)
    if usuario_id:
        usuarios = User.query.filter(User.id == usuario_id).all()
    else:
        # Por ahora todos los usuarios, en producción filtrar por rol de vendedor
        usuarios = User.query.all()

    comisiones_creadas = []

    for usuario in usuarios:
        # Verificar si ya existe comisión para este período
        comision_existente = Comision.query.filter_by(
            usuario_id=usuario.id,
            periodo=periodo
        ).first()

        if comision_existente:
            continue

        # Obtener ventas del usuario en el período
        # Nota: Asumiendo que las ventas están asociadas al usuario que las registró
        # En un sistema real, podría haber una relación más compleja
        ventas = Venta.query.filter(
            Venta.fecha >= fecha_inicio,
            Venta.fecha <= fecha_fin
            # Aquí iría el filtro por usuario si existiera la relación
        ).all()

        if not ventas:
            continue

        # Calcular comisión (lógica simplificada: 5% del margen)
        ventas_total = sum(v.precio_contrato * v.cantidad for v in ventas)
        margen_total = sum((v.precio_efectivo - v.precio_contrato) * v.cantidad for v in ventas)
        comision_total = margen_total * Decimal('0.05')  # 5% del margen
        porcentaje_promedio = 5.0  # Simplificado

        # Crear comisión
        comision = Comision(
            usuario_id=usuario.id,
            periodo=periodo,
            tipo_periodo=tipo_periodo,
            ventas_total=ventas_total,
            comision_total=comision_total,
            porcentaje_promedio=porcentaje_promedio
        )

        db.session.add(comision)
        db.session.flush()  # Para obtener el ID

        # Crear detalles
        for venta in ventas:
            margen_venta = (venta.precio_efectivo - venta.precio_contrato) * venta.cantidad
            monto_comision = margen_venta * Decimal('0.05')

            detalle = ComisionDetalle(
                comision_id=comision.id,
                venta_id=venta.id,
                monto_venta=venta.precio_contrato * venta.cantidad,
                porcentaje_comision=5.0,
                monto_comision=monto_comision
            )
            db.session.add(detalle)

        comisiones_creadas.append({
            "usuario": usuario.username,
            "periodo": periodo,
            "ventas_total": float(ventas_total),
            "comision_total": float(comision_total)
        })

    db.session.commit()

    return jsonify({
        "message": f"Comisiones calculadas para {len(comisiones_creadas)} usuarios",
        "comisiones": comisiones_creadas
    })


@comercial_bp.route("/api/comercial/comisiones/<int:comision_id>/pagar", methods=["POST"])
def comisiones_pagar(comision_id):
    """Marcar comisión como pagada"""
    comision = Comision.query.get_or_404(comision_id)

    if comision.pagada:
        return jsonify({"error": "Comisión ya está pagada"}), 400

    comision.pagada = True
    comision.fecha_pago = datetime.utcnow()
    db.session.commit()

    return jsonify({"message": "Comisión marcada como pagada"})


# Endpoints para Objetivos de Venta

@comercial_bp.route("/api/comercial/objetivos", methods=["GET"])
def objetivos_listar():
    """Listar objetivos de venta con progreso calculado"""
    periodo = request.args.get("periodo")
    
    query = Goal.query.join(Employee)
    
    if periodo:
        query = query.filter(Goal.period == periodo)
    
    objetivos = query.order_by(Goal.period.desc(), Employee.first_name, Employee.last_name).all()
    
    # El avance oficial sale de Goal.current_value (sincronizado desde PRE SabioGo).
    resultado = []
    for obj in objetivos:
        ventas_empleado = float(obj.current_value or 0)
        progreso = (ventas_empleado / obj.target_value * 100) if obj.target_value else 0
        progreso_ventas = progreso
        
        resultado.append({
            "id": obj.id,
            "empleado_id": obj.employee_id,
            "empleado": obj.employee.full_name if obj.employee else "N/A",
            "descripcion": obj.description,
            "periodo": obj.period,
            "meta": float(obj.target_value),
            "valor_actual": float(obj.current_value or 0),
            "ventas_reales": ventas_empleado,
            "progreso": round(progreso, 1),
            "progreso_ventas": round(progreso_ventas, 1),
            "estado": obj.status
        })
    
    return jsonify({"objetivos": resultado})


@comercial_bp.route("/api/comercial/ventas-pre-detalle", methods=["GET"])
def ventas_pre_detalle():
    """Detalle comercial basado exclusivamente en comprobantes PRE."""
    fecha_desde_raw = request.args.get("fecha_desde")
    fecha_hasta_raw = request.args.get("fecha_hasta")
    vendedor = request.args.get("vendedor")
    cliente = request.args.get("cliente")
    producto = request.args.get("producto")
    limit = request.args.get("limit", 500, type=int)

    today = datetime.now().date()
    if not fecha_hasta_raw:
        fecha_hasta_raw = today.isoformat()
    if not fecha_desde_raw:
        fecha_desde_raw = (today - timedelta(days=30)).isoformat()

    try:
        fecha_desde = datetime.fromisoformat(fecha_desde_raw).date()
        fecha_hasta = datetime.fromisoformat(fecha_hasta_raw).date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido"}), 400

    if fecha_desde > fecha_hasta:
        return jsonify({"error": "fecha_desde no puede ser mayor a fecha_hasta"}), 400

    service = SabiogoService()
    data = service.get_detalle_ventas_pre(
        fecha_inicio=fecha_desde,
        fecha_fin=fecha_hasta,
        vendedor=vendedor,
        cliente=cliente,
        producto=producto,
        limit=max(1, min(limit, 2000)),
    )

    return jsonify(
        {
            "periodo": {
                "desde": fecha_desde.isoformat(),
                "hasta": fecha_hasta.isoformat(),
            },
            "filtros": {
                "vendedor": vendedor,
                "cliente": cliente,
                "producto": producto,
                "limit": max(1, min(limit, 2000)),
            },
            "data": data,
        }
    )


@comercial_bp.route("/api/comercial/objetivos/sincronizar-pre", methods=["POST"])
def sincronizar_objetivos_pre():
    """Sincroniza Goal.current_value con ventas PRE por vendedor y período."""
    payload = request.get_json(silent=True) or {}
    periodo = payload.get("periodo") or request.args.get("periodo")

    service = SabiogoService()
    try:
        resultado = service.sincronizar_objetivos_pre(periodo=periodo)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": f"No se pudo sincronizar objetivos PRE: {exc}"}), 500

    return jsonify({
        "success": True,
        "resultado": resultado,
    })


@comercial_bp.route("/api/comercial/objetivos", methods=["POST"])
def objetivos_crear():
    """Crear nuevo objetivo de venta"""
    data = request.get_json()
    
    required = ["employee_id", "description", "target_value"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"Campo requerido: {field}"}), 400
    
    objetivo = Goal(
        employee_id=data["employee_id"],
        description=data["description"],
        period=data.get("period", datetime.now().strftime("%Y-%m")),
        target_value=float(data["target_value"]),
        current_value=float(data.get("current_value", 0)),
        status=data.get("status", "en progreso")
    )
    
    db.session.add(objetivo)
    db.session.commit()
    
    return jsonify({
        "message": "Objetivo creado exitosamente",
        "id": objetivo.id
    }), 201


@comercial_bp.route("/api/comercial/objetivos/<int:objetivo_id>", methods=["PUT"])
def objetivos_actualizar(objetivo_id):
    """Actualizar objetivo de venta"""
    objetivo = Goal.query.get_or_404(objetivo_id)
    data = request.get_json()
    
    if "current_value" in data:
        objetivo.current_value = float(data["current_value"])
    if "status" in data:
        objetivo.status = data["status"]
    if "target_value" in data:
        objetivo.target_value = float(data["target_value"])
    if "description" in data:
        objetivo.description = data["description"]
    
    db.session.commit()
    
    return jsonify({"message": "Objetivo actualizado"})


@comercial_bp.route("/api/comercial/objetivos/<int:objetivo_id>", methods=["DELETE"])
def objetivos_eliminar(objetivo_id):
    """Eliminar objetivo"""
    objetivo = Goal.query.get_or_404(objetivo_id)
    db.session.delete(objetivo)
    db.session.commit()
    
    return jsonify({"message": "Objetivo eliminado"})


@comercial_bp.route("/api/comercial/vendedores", methods=["GET"])
def vendedores_listar():
    """Listar empleados que son vendedores"""
    from sqlalchemy import or_
    
    # Filtrar por position o department que contenga 'venta', 'vendedor' o 'comercial'
    empleados = Employee.query.filter(
        Employee.is_active == True,
        or_(
            Employee.position.ilike('%venta%'),
            Employee.position.ilike('%vendedor%'),
            Employee.position.ilike('%comercial%'),
            Employee.department.ilike('%venta%'),
            Employee.department.ilike('%comercial%')
        )
    ).order_by(Employee.first_name, Employee.last_name).all()
    
    # Si no hay vendedores configurados, devolver lista vacía con mensaje
    if not empleados:
        return jsonify({
            "vendedores": [],
            "mensaje": "No hay empleados con rol de vendedor. Configure el rol 'Vendedor' o 'Comercial' en RRHH > Empleados."
        })
    
    return jsonify({
        "vendedores": [{
            "id": e.id,
            "nombre": e.full_name,
            "email": e.email
        } for e in empleados]
    })


@comercial_bp.route("/api/comercial/ranking", methods=["GET"])
def ranking_vendedores():
    """Ranking de vendedores por cumplimiento de objetivos"""
    periodo = request.args.get("periodo", datetime.now().strftime("%Y-%m"))
    
    objetivos = Goal.query.filter(Goal.period == periodo).all()
    
    ranking = []
    for obj in objetivos:
        if obj.target_value and obj.target_value > 0:
            cumplimiento = (obj.current_value / obj.target_value) * 100
            ranking.append({
                "empleado_id": obj.employee_id,
                "empleado": obj.employee.full_name if obj.employee else "N/A",
                "meta": float(obj.target_value),
                "actual": float(obj.current_value or 0),
                "cumplimiento": round(cumplimiento, 1)
            })
    
    # Ordenar por cumplimiento descendente
    ranking.sort(key=lambda x: x["cumplimiento"], reverse=True)
    
    return jsonify({"ranking": ranking, "periodo": periodo})


# API de objetivos comerciales nuevos, independiente del modelo Goal de RRHH.
_CAMPOS_REALIZADO = {
    "realizado",
    "current_value",
    "valor_actual",
    "ventas_reales",
    "cumplimiento",
    "avance",
}


def _usuario_comercial_actual_id():
    usuario_id = flask_session.get("user_id")
    current_user = getattr(request, "current_user", None)
    if usuario_id is None and isinstance(current_user, dict):
        usuario_id = current_user.get("user_id")
    if usuario_id is None:
        return None
    try:
        usuario_id = int(usuario_id)
    except (TypeError, ValueError):
        return None
    return usuario_id if db.session.get(User, usuario_id) else None


def _objetivo_comercial_por_id(objetivo_id, corte):
    from services.objetivos_comerciales import obtener_objetivos_comerciales

    objetivo = db.session.get(ComercialObjetivo, objetivo_id)
    if objetivo is None:
        return None
    lista = obtener_objetivos_comerciales(
        objetivo.mes,
        empresa=objetivo.empresa,
        medida=objetivo.medida,
        corte=corte,
        criterio_clientes=True,
    )
    return next(
        (item for item in lista if item["vendedor_id"] == objetivo.vendedor_id),
        None,
    )


@comercial_bp.route("/api/objetivos-comerciales", methods=["GET"])
def objetivos_comerciales_listar():
    from models.time_utils import today_local_date
    from services.objetivos_comerciales import (
        NOTA_RITMO,
        obtener_objetivos_comerciales,
        validar_mes,
    )

    mes = request.args.get("mes")
    empresa = request.args.get("empresa", "TODAS")
    medida = request.args.get("medida")
    if not mes or not medida:
        return jsonify({"error": "mes y medida son requeridos"}), 400

    corte_raw = request.args.get("fecha_corte")
    if corte_raw:
        try:
            corte = date.fromisoformat(corte_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "fecha_corte debe tener formato YYYY-MM-DD"}), 400
    else:
        corte = today_local_date()

    try:
        validar_mes(mes)
        objetivos = obtener_objetivos_comerciales(
            mes,
            empresa=empresa,
            medida=medida,
            corte=corte,
            criterio_clientes=True,
            incluir_vendedores_venta=True,
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify(
        {
            "mes": mes,
            "empresa": empresa.strip().upper(),
            "medida": medida.strip().lower(),
            "fecha_corte": corte.isoformat(),
            "nota_ritmo": NOTA_RITMO,
            "objetivos": objetivos,
        }
    )


@comercial_bp.route("/api/objetivos-comerciales", methods=["POST"])
def objetivos_comerciales_crear():
    from models.time_utils import now_local, today_local_date
    from services.objetivos_comerciales import decimal_positivo, validar_mes

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Se esperaba un objeto JSON"}), 400
    if _CAMPOS_REALIZADO.intersection(data):
        return jsonify({"error": "El realizado se calcula al consultar y no se acepta"}), 400

    permitidos = {"vendedor_id", "vendedor_nombre", "empresa", "mes", "medida", "meta", "descripcion"}
    if set(data) - permitidos:
        return jsonify({"error": "El alta solo acepta vendedor, empresa, mes, medida, meta y descripción"}), 400
    requeridos = {"empresa", "mes", "medida", "meta"}
    faltantes = requeridos - set(data)
    if faltantes:
        return jsonify({"error": f"Campos requeridos: {', '.join(sorted(faltantes))}"}), 400

    vendedor_raw = data.get("vendedor_id")
    nombre_raw = data.get("vendedor_nombre")
    if (vendedor_raw is None) == (nombre_raw is None):
        return jsonify({"error": "Indicá vendedor_id o vendedor_nombre"}), 400
    vendedor_id = None
    if vendedor_raw is not None:
        if isinstance(vendedor_raw, bool) or not (
            isinstance(vendedor_raw, int)
            or (isinstance(vendedor_raw, str) and vendedor_raw.isdigit())
        ):
            return jsonify({"error": "vendedor_id debe ser un entero"}), 400
        vendedor_id = int(vendedor_raw)
    elif not isinstance(nombre_raw, str) or not nombre_raw.strip() or len(nombre_raw.strip()) > 200:
        return jsonify({"error": "vendedor_nombre debe tener entre 1 y 200 caracteres"}), 400

    empresa_raw = data["empresa"]
    medida_raw = data["medida"]
    mes = data["mes"]
    if not isinstance(empresa_raw, str) or not isinstance(medida_raw, str):
        return jsonify({"error": "empresa o medida inválida"}), 400
    empresa = empresa_raw.strip().upper()
    medida = medida_raw.strip().lower()
    try:
        validar_mes(mes)
        meta = decimal_positivo(data["meta"])
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    if empresa not in ("CARNES", "LACTEOS"):
        return jsonify({"error": "empresa debe ser CARNES o LACTEOS"}), 400
    if medida not in ("importe", "cajas", "kilos"):
        return jsonify({"error": "medida debe ser importe, cajas o kilos"}), 400

    descripcion = data.get("descripcion")
    if descripcion is not None and not isinstance(descripcion, str):
        return jsonify({"error": "descripcion debe ser texto o null"}), 400

    if vendedor_id is not None:
        vendedor = db.session.get(ComercialVendedor, vendedor_id)
        if vendedor is None:
            return jsonify({"error": "Vendedor comercial no encontrado"}), 404
    else:
        from services.vendedores_comerciales import colapsar_espacios, resolver_nombre_vendedor

        nombre_visible = resolver_nombre_vendedor(colapsar_espacios(nombre_raw))
        nombre_clave = colapsar_espacios(nombre_visible).casefold()
        vendedor = next(
            (
                candidato
                for candidato in ComercialVendedor.query.all()
                if colapsar_espacios(candidato.nombre_visible).casefold() == nombre_clave
            ),
            None,
        )
        if vendedor is None:
            vendedor = ComercialVendedor(nombre_visible=nombre_visible, activo=True)
            db.session.add(vendedor)
            db.session.flush()
        vendedor_id = vendedor.id
    if not vendedor.activo:
        return jsonify({"error": "El vendedor está inactivo y no admite nuevos objetivos"}), 409
    usuario_id = _usuario_comercial_actual_id()
    if usuario_id is None:
        return jsonify({"error": "Sesión de usuario inválida"}), 401

    duplicado = ComercialObjetivo.query.filter_by(
        vendedor_id=vendedor_id,
        empresa=empresa,
        mes=mes,
        medida=medida,
    ).first()
    if duplicado is not None:
        return jsonify({"error": "Ya existe una meta para el vendedor, empresa, mes y medida"}), 409

    objetivo = ComercialObjetivo(
        vendedor_id=vendedor_id,
        empresa=empresa,
        mes=mes,
        medida=medida,
        meta=meta,
        descripcion=descripcion,
        creado_en=now_local(),
        actualizado_en=now_local(),
        creado_por_id=usuario_id,
        actualizado_por_id=usuario_id,
    )
    db.session.add(objetivo)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Ya existe una meta para el vendedor, empresa, mes y medida"}), 409

    item = _objetivo_comercial_por_id(objetivo.id, today_local_date())
    return jsonify({"objetivo": item}), 201


@comercial_bp.route("/api/objetivos-comerciales/<int:objetivo_id>", methods=["PATCH"])
def objetivos_comerciales_editar(objetivo_id):
    from models.time_utils import now_local, today_local_date
    from services.objetivos_comerciales import decimal_positivo

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Se esperaba un objeto JSON"}), 400
    if _CAMPOS_REALIZADO.intersection(data):
        return jsonify({"error": "El realizado se calcula al consultar y no se acepta"}), 400
    if not data or set(data) - {"meta", "descripcion"}:
        return jsonify({"error": "PATCH solo acepta meta y descripcion"}), 400

    objetivo = db.session.get(ComercialObjetivo, objetivo_id)
    if objetivo is None:
        return jsonify({"error": "Objetivo comercial no encontrado"}), 404

    nueva_meta = None
    if "meta" in data:
        try:
            nueva_meta = decimal_positivo(data["meta"])
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
    nueva_descripcion = None
    if "descripcion" in data:
        nueva_descripcion = data["descripcion"]
        if nueva_descripcion is not None and not isinstance(nueva_descripcion, str):
            return jsonify({"error": "descripcion debe ser texto o null"}), 400

    usuario_id = _usuario_comercial_actual_id()
    if usuario_id is None:
        return jsonify({"error": "Sesión de usuario inválida"}), 401

    if "meta" in data:
        objetivo.meta = nueva_meta
    if "descripcion" in data:
        objetivo.descripcion = nueva_descripcion
    objetivo.actualizado_en = now_local()
    objetivo.actualizado_por_id = usuario_id
    db.session.commit()

    item = _objetivo_comercial_por_id(objetivo.id, today_local_date())
    return jsonify({"objetivo": item})


@comercial_bp.route("/api/objetivos-comerciales/<int:objetivo_id>", methods=["DELETE"])
def objetivos_comerciales_eliminar(objetivo_id):
    objetivo = db.session.get(ComercialObjetivo, objetivo_id)
    if objetivo is None:
        return jsonify({"error": "Objetivo comercial no encontrado"}), 404

    vinculo = ComercialObjetivoVinculo.query.filter_by(
        comercial_objetivo_id=objetivo_id
    ).first()
    if vinculo is not None:
        return jsonify(
            {"error": "Este objetivo está vinculado a un objetivo histórico y no se puede eliminar."}
        ), 409

    db.session.delete(objetivo)
    db.session.commit()
    return jsonify({"mensaje": "Objetivo comercial eliminado"})


def _mes_periodo_goal(periodo, validar_mes):
    try:
        validar_mes(periodo)
    except ValueError:
        return None
    return periodo


@comercial_bp.route("/api/objetivos-comerciales/pendientes", methods=["GET"])
def objetivos_comerciales_pendientes():
    from services.objetivos_comerciales import validar_mes

    pendientes = (
        db.session.query(Goal)
        .outerjoin(
            ComercialObjetivoVinculo,
            ComercialObjetivoVinculo.goal_id == Goal.id,
        )
        .filter(ComercialObjetivoVinculo.id.is_(None))
        .order_by(Goal.period.desc(), Goal.id.asc())
        .all()
    )
    vendedores = ComercialVendedor.query.order_by(
        ComercialVendedor.nombre_visible.asc()
    ).all()
    return jsonify(
        {
            "pendientes": [
                {
                    "goal_id": objetivo.id,
                    "empleado": (
                        objetivo.employee.full_name if objetivo.employee else "Sin empleado"
                    ),
                    "periodo": objetivo.period,
                    "mes_sugerido": _mes_periodo_goal(objetivo.period, validar_mes),
                    "descripcion": objetivo.description,
                    "meta": float(objetivo.target_value),
                }
                for objetivo in pendientes
            ],
            "vendedores_comerciales": [
                {"id": vendedor.id, "nombre_visible": vendedor.nombre_visible}
                for vendedor in vendedores
            ],
        }
    )


@comercial_bp.route("/api/objetivos-comerciales/convertir", methods=["POST"])
def objetivos_comerciales_convertir():
    from models.time_utils import now_local, today_local_date
    from services.objetivos_comerciales import decimal_positivo, validar_mes

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "Se esperaba un objeto JSON"}), 400
    permitidos = {"goal_id", "vendedor_id", "empresa", "medida", "mes"}
    if set(data) - permitidos:
        return jsonify({"error": "Solo se aceptan goal_id, vendedor_id, empresa, medida y mes"}), 400
    requeridos = {"goal_id", "vendedor_id", "empresa", "medida"}
    faltantes = requeridos - set(data)
    if faltantes:
        return jsonify({"error": f"Campos requeridos para convertir: {', '.join(sorted(faltantes))}"}), 400

    def entero_id(valor):
        if isinstance(valor, bool):
            return None
        if isinstance(valor, int):
            return valor if valor > 0 else None
        if isinstance(valor, str) and valor.isdigit():
            convertido = int(valor)
            return convertido if convertido > 0 else None
        return None

    goal_id = entero_id(data["goal_id"])
    vendedor_id = entero_id(data["vendedor_id"])
    if goal_id is None or vendedor_id is None:
        return jsonify({"error": "goal_id y vendedor_id deben ser enteros positivos"}), 400

    goal = db.session.get(Goal, goal_id)
    if goal is None:
        return jsonify({"error": "Objetivo anterior no encontrado"}), 404
    if ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).first() is not None:
        return jsonify({"error": "Este objetivo anterior ya fue convertido"}), 409

    empresa_raw = data["empresa"]
    medida_raw = data["medida"]
    if not isinstance(empresa_raw, str) or not isinstance(medida_raw, str):
        return jsonify({"error": "empresa y medida son obligatorias"}), 400
    empresa = empresa_raw.strip().upper()
    medida = medida_raw.strip().lower()
    if empresa not in ("CARNES", "LACTEOS"):
        return jsonify({"error": "empresa debe ser CARNES o LACTEOS"}), 400
    if medida not in ("importe", "cajas", "kilos"):
        return jsonify({"error": "medida debe ser importe, cajas o kilos"}), 400

    mes_periodo = _mes_periodo_goal(goal.period, validar_mes)
    if mes_periodo is not None:
        mes = mes_periodo
        if "mes" in data:
            try:
                validar_mes(data["mes"])
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
            if data["mes"] != mes:
                return jsonify({"error": "El mes debe coincidir con el período YYYY-MM del objetivo"}), 400
    else:
        if "mes" not in data:
            return jsonify({"error": "mes es requerido porque el período del objetivo no es YYYY-MM"}), 400
        mes = data["mes"]
        try:
            validar_mes(mes)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

    vendedor = db.session.get(ComercialVendedor, vendedor_id)
    if vendedor is None:
        return jsonify({"error": "Vendedor comercial no encontrado"}), 404
    usuario_id = _usuario_comercial_actual_id()
    if usuario_id is None:
        return jsonify({"error": "Sesión de usuario inválida"}), 401
    try:
        meta = decimal_positivo(goal.target_value)
    except ValueError as exc:
        return jsonify({"error": f"La meta del objetivo anterior no es válida: {exc}"}), 400

    duplicada = ComercialObjetivo.query.filter_by(
        vendedor_id=vendedor_id,
        empresa=empresa,
        mes=mes,
        medida=medida,
    ).first()
    if duplicada is not None:
        return jsonify(
            {
                "error": (
                    "Ya hay una meta para esa combinación de vendedor, empresa, mes y medida."
                )
            }
        ), 409

    ahora = now_local()
    comercial_objetivo = ComercialObjetivo(
        vendedor_id=vendedor_id,
        empresa=empresa,
        mes=mes,
        medida=medida,
        meta=meta,
        descripcion=goal.description,
        creado_en=ahora,
        actualizado_en=ahora,
        creado_por_id=usuario_id,
        actualizado_por_id=usuario_id,
    )
    db.session.add(comercial_objetivo)
    try:
        db.session.flush()
        vinculo = ComercialObjetivoVinculo(
            goal_id=goal_id,
            comercial_objetivo_id=comercial_objetivo.id,
            creado_en=ahora,
        )
        db.session.add(vinculo)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        if ComercialObjetivoVinculo.query.filter_by(goal_id=goal_id).first() is not None:
            return jsonify({"error": "Este objetivo anterior ya fue convertido"}), 409
        if ComercialObjetivo.query.filter_by(
            vendedor_id=vendedor_id,
            empresa=empresa,
            mes=mes,
            medida=medida,
        ).first() is not None:
            return jsonify(
                {
                    "error": (
                        "Ya hay una meta para esa combinación de vendedor, empresa, mes y medida."
                    )
                }
            ), 409
        return jsonify({"error": "No se pudo registrar el vínculo del objetivo"}), 409

    item = _objetivo_comercial_por_id(comercial_objetivo.id, today_local_date())
    return jsonify(
        {
            "mensaje": "Objetivo anterior convertido correctamente",
            "vinculo": {
                "goal_id": goal_id,
                "comercial_objetivo_id": comercial_objetivo.id,
            },
            "objetivo": item,
        }
    ), 201
