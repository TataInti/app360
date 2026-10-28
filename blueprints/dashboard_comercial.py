from datetime import timedelta

from flask import Blueprint, jsonify, render_template, request, session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from models import db
from models.comercial import ComercialClienteCriterio
from models.sabiogo.staging import StgSabiogoVentas
from models.time_utils import now_local
from security import protect_blueprint

dashboard_com_bp = Blueprint("dashboard_comercial", __name__)

protect_blueprint(dashboard_com_bp, "dashboard_comercial")


@dashboard_com_bp.route("/dashboard-comercial")
def dashboard_comercial():
    return render_template("dashboard_comercial.html")


@dashboard_com_bp.route("/ventas/criterio-clientes")
def criterio_clientes():
    return render_template("criterio_clientes.html")


def _clientes_procesados():
    cliente = func.trim(StgSabiogoVentas.cliente)
    return {
        row.cliente
        for row in db.session.query(cliente.label("cliente"))
        .filter(StgSabiogoVentas.estado == "procesado")
        .filter(cliente.isnot(None), cliente != "")
        .distinct()
        .all()
    }


@dashboard_com_bp.get("/ventas/criterio-clientes/datos")
def criterio_clientes_datos():
    clientes = sorted(_clientes_procesados(), key=str.casefold)
    criterios = {
        fila.cliente: fila
        for fila in ComercialClienteCriterio.query.all()
    }
    return jsonify(
        {
            "clientes": [
                {
                    "cliente": cliente,
                    "criterio": criterios[cliente].criterio if cliente in criterios else "PRE",
                    "actualizado_por": criterios[cliente].actualizado_por if cliente in criterios else None,
                    "actualizado_en": (
                        criterios[cliente].actualizado_en.isoformat()
                        if cliente in criterios and criterios[cliente].actualizado_en
                        else None
                    ),
                }
                for cliente in clientes
            ]
        }
    )


@dashboard_com_bp.post("/ventas/criterio-clientes/guardar")
def criterio_clientes_guardar():
    payload = request.get_json(silent=True) or {}
    raw_clientes = payload.get("clientes")
    criterio = str(payload.get("criterio") or "").strip().upper()
    if criterio not in {"PRE", "FAC"}:
        return jsonify({"error": "El criterio debe ser PRE o FAC."}), 400
    if not isinstance(raw_clientes, list):
        return jsonify({"error": "Selecciona uno o más clientes."}), 400

    clientes = sorted(
        {str(nombre).strip() for nombre in raw_clientes if str(nombre).strip()},
        key=str.casefold,
    )
    if not clientes:
        return jsonify({"error": "Selecciona uno o más clientes."}), 400

    disponibles = _clientes_procesados()
    desconocidos = sorted(set(clientes) - disponibles, key=str.casefold)
    if desconocidos:
        return jsonify({"error": "Hay clientes que no están en staging procesado."}), 400

    actor = session.get("user") or session.get("username") or session.get("user_id")
    if actor is None:
        return jsonify({"error": "No se pudo identificar al usuario."}), 401
    actor = str(actor)[:120]
    actualizado_en = now_local().replace(tzinfo=None)
    try:
        for cliente in clientes:
            fila = ComercialClienteCriterio.query.filter_by(cliente=cliente).with_for_update().first()
            if fila is None:
                fila = ComercialClienteCriterio(cliente=cliente)
                db.session.add(fila)
            fila.criterio = criterio
            fila.actualizado_por = actor
            fila.actualizado_en = actualizado_en
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "No se pudieron guardar los criterios; vuelve a intentar."}), 409
    except Exception:
        db.session.rollback()
        return jsonify({"error": "No se pudieron guardar los criterios."}), 500

    return jsonify({
        "guardados": len(clientes),
        "clientes": clientes,
        "criterio": criterio,
        "actualizado_por": actor,
        "actualizado_en": actualizado_en.isoformat(),
    })

@dashboard_com_bp.get('/comercial/seguimiento-clientes')
def seguimiento_clientes_pantalla():
    return render_template('seguimiento_clientes.html')





@dashboard_com_bp.get('/api/dashboard-comercial/resumen-estrategico')
def resumen_estrategico_datos():
    from services.comercial_paneles import resumen_estrategico
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        medida = request.args.get('medida', 'importe')
        if medida not in {'importe', 'cajas', 'kilos'}:
            raise ValueError('Medida inválida')
        return resumen_estrategico(**parametros, medida=medida,
                                  cliente=request.args.get('cliente', '').strip() or None,
                                  producto=request.args.get('producto', '').strip() or None)
    return lectura_panel(consultar)


@dashboard_com_bp.get('/api/comercial/seguimiento-clientes')
def seguimiento_clientes_datos():
    from services.comercial_paneles import seguimiento_clientes
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        vista = request.args.get('vista', 'atencion')
        orden = request.args.get('orden', 'prioridad')
        pagina = int(request.args.get('pagina', 1))
        por_pagina = int(request.args.get('por_pagina', 25))
        if vista not in {'atencion', 'activos', 'sin_compra', 'todos'} or orden not in {'prioridad', 'cliente', 'dias', 'importe'}:
            raise ValueError('Filtro inválido')
        if pagina < 1 or por_pagina not in {25, 50}:
            raise ValueError('Página inválida')
        return seguimiento_clientes(**parametros, vista=vista, orden=orden, pagina=pagina,
                                    por_pagina=por_pagina, busqueda=request.args.get('q', '').strip(),
                                    cliente=request.args.get('cliente', '').strip() or None,
                                    producto=request.args.get('producto', '').strip() or None)
    return lectura_panel(consultar)


@dashboard_com_bp.get('/api/comercial/seguimiento-clientes/detalle')
def seguimiento_cliente_detalle():
    from services.comercial_paneles import seguimiento_clientes
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        cliente = request.args.get('cliente', '').strip()
        if not cliente:
            raise ValueError('Falta cliente')
        datos = seguimiento_clientes(**parametros, cliente=cliente, vista='todos',
                                     producto=request.args.get('producto', '').strip() or None)
        return dict(**{k: v for k, v in datos.items() if k != 'clientes'},
                    cliente=datos['clientes'][0] if datos['clientes'] else None)
    return lectura_panel(consultar)


@dashboard_com_bp.get('/api/comercial/paneles/opciones')
def paneles_opciones():
    from services.comercial_criterios import filtro_comprobante_panel_ventas
    from services.comercial_pre import expresion_vendedor_resuelta
    from services.vendedores_comerciales import resolver_nombre_vendedor
    from models.comercial import ComercialVendedor
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        hasta = parametros['hasta']
        vendedor_expr = expresion_vendedor_resuelta()
        filtros_dimensiones = [StgSabiogoVentas.estado == 'procesado']
        if parametros['empresa'] != 'TODAS':
            filtro_empresa = func.upper(func.coalesce(StgSabiogoVentas.origen, '')) == parametros['empresa']
            filtros_dimensiones.append(filtro_empresa)
        cliente = func.trim(StgSabiogoVentas.cliente)
        producto = func.trim(StgSabiogoVentas.producto)
        filtros_cliente = [*filtros_dimensiones, cliente.isnot(None), cliente != '']
        filtros_producto = [*filtros_dimensiones, producto.isnot(None), producto != '']
        clientes = db.session.query(cliente.label('cliente')).filter(*filtros_cliente).distinct().all()
        productos = db.session.query(producto.label('producto')).filter(*filtros_producto).distinct().all()

        # Las dimensiones mantienen el catálogo completo por empresa, como en
        # los filtros anteriores; fechas y vendedor limitan los datos, no el catálogo.
        filtros_vendedor = [StgSabiogoVentas.estado == 'procesado', filtro_comprobante_panel_ventas(),
                            StgSabiogoVentas.fecha < hasta + timedelta(days=1)]
        if parametros['empresa'] != 'TODAS':
            filtros_vendedor.append(func.upper(func.coalesce(StgSabiogoVentas.origen, '')) == parametros['empresa'])
        vendedores = {resolver_nombre_vendedor(f[0]) for f in
                      db.session.query(StgSabiogoVentas.vendedor).filter(*filtros_vendedor).distinct().all() if f[0]}
        vendedores.update(f.nombre_visible for f in ComercialVendedor.query.filter_by(activo=True).all())
        return dict(vendedores=sorted(vendedores, key=str.casefold),
                    clientes=sorted({row.cliente for row in clientes}, key=str.casefold),
                    productos=sorted({row.producto for row in productos}, key=str.casefold))
    return lectura_panel(consultar)


@dashboard_com_bp.route("/comercial/performance-vendedores")
def performance_vendedores_pantalla():
    return render_template("performance_vendedores.html")


@dashboard_com_bp.get("/api/comercial/performance")
def performance_vendedores_datos():
    from services.comercial_performance import performance_vendedores
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        medida = request.args.get('medida', 'importe')
        if medida not in {'importe', 'cajas', 'kilos'}:
            raise ValueError('Medida inválida')
        granularidad = request.args.get('granularidad', 'dia')
        if granularidad not in {'dia', 'semana', 'mes'}:
            raise ValueError('Granularidad inválida')
        return performance_vendedores(
            **parametros,
            medida=medida,
            granularidad=granularidad,
            cliente=request.args.get('cliente', '').strip() or None,
            producto=request.args.get('producto', '').strip() or None,
        )
    return lectura_panel(consultar)


@dashboard_com_bp.get('/api/comercial/performance-vendedores', endpoint='performance_vendedores_datos_compat')
def performance_vendedores_datos():
    from services.comercial_performance import performance_vendedores
    from services.comercial_web import lectura_panel, parametros_panel

    def consultar():
        parametros = parametros_panel()
        medida = request.args.get('medida', 'importe')
        granularidad = request.args.get('granularidad', 'dia')
        if medida not in {'importe', 'cajas', 'kilos'}:
            raise ValueError('Medida inválida')
        if granularidad not in {'dia', 'semana', 'mes'}:
            raise ValueError('Granularidad inválida')
        return performance_vendedores(
            **parametros,
            medida=medida,
            granularidad=granularidad,
            cliente=request.args.get('cliente', '').strip() or None,
            producto=request.args.get('producto', '').strip() or None,
        )
    return lectura_panel(consultar)
