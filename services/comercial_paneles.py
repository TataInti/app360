"""Lecturas comerciales: estrategia y cartera, con el mismo criterio PRE/FAC."""
from types import SimpleNamespace
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func

from models import db
from models.sabiogo.staging import StgSabiogoVentas as Venta
from services.comercial_criterios import (CRITERIO_AMBOS, TIPO_FAC, TIPO_NC, TIPO_PRE, criterios_por_cliente,
                                          filtro_comprobante_panel_ventas, tipo_origen)
from services.comercial_pre import calcular_resumen_pre, expresion_vendedor_resuelta
from services.objetivos_comerciales import obtener_objetivos_comerciales
from services.vendedores_comerciales import resolver_nombre_vendedor


def periodo_anterior(desde, hasta):
    return desde - timedelta(days=(hasta - desde).days + 1), desde - timedelta(days=1)


def comparativo(actual, anterior):
    actual, anterior = float(actual or 0), float(anterior or 0)
    variacion = round((actual - anterior) / abs(anterior) * 100, 1) if anterior else None
    return dict(actual=actual, anterior=anterior, diferencia=actual - anterior,
                variacion_pct=variacion,
                variacion_texto=f'{variacion:+.1f}%' if variacion is not None else 'Sin base comparable')


def ranking(filas, limite=8):
    principales = filas[:limite]
    resto = filas[limite:]
    if resto:
        principales = principales + [dict(nombre='Otros', **{
            clave: sum(f.get(clave, 0) for f in resto)
            for clave in ('plata', 'cajas', 'kilos', 'pct')
        })]
    return principales


def resumen_estrategico(desde, hasta, empresa='TODAS', vendedor=None,
                        cliente=None, producto=None, medida='importe'):
    anterior_desde, anterior_hasta = periodo_anterior(desde, hasta)
    filtros = dict(empresa=empresa, vendedor=vendedor, cliente=cliente,
                   producto=producto, criterio_clientes=True, limite=100000)
    actual = calcular_resumen_pre(desde, hasta, **filtros)
    anterior = calcular_resumen_pre(anterior_desde, anterior_hasta, **filtros)
    objetivos = obtener_objetivos_comerciales(hasta.strftime('%Y-%m'), empresa=empresa,
                                             medida=medida, corte=hasta, criterio_clientes=True,
                                             incluir_vendedores_venta=True)
    mensual = calcular_resumen_pre(hasta.replace(day=1), hasta, empresa=empresa,
                                  criterio_clientes=True, limite=100000)
    nombres = {f['nombre_visible'] for f in objetivos}
    for fila in mensual['por_vendedor']:
        if fila['nombre'] not in nombres:
            objetivos.append(dict(nombre_visible=fila['nombre'],
                                  vendedor=fila['nombre'], vendedor_id=None, empresa='TODAS',
                                  medida=medida, mes=hasta.strftime('%Y-%m'), lineas=[],
                                  cantidad_lineas=0, realizado=0.0, meta=None,
                                  cumplimiento=None, faltante=None, desvio=None,
                                  estado='Sin meta', cobertura='sin_meta'))
    if vendedor:
        objetivos = [f for f in objetivos if f['nombre_visible'] == resolver_nombre_vendedor(vendedor)]
    for fila in objetivos:
        fila['diferencia_meta'] = fila['realizado'] - fila['meta'] if fila['meta'] is not None else None
    return dict(desde=desde.isoformat(), hasta=hasta.isoformat(),
                desde_anterior=anterior_desde.isoformat(), hasta_anterior=anterior_hasta.isoformat(),
                kpis={k: comparativo(actual[v], anterior[v]) for k, v in
                      {'importe': 'importe_pre', 'cajas': 'cajas', 'kilos': 'kilos',
                       'clientes': 'clientes_compradores'}.items()},
                serie=actual['por_fecha'], serie_anterior=anterior['por_fecha'],
                objetivos=objetivos, mes_objetivos=hasta.strftime('%Y-%m'),
                composicion={k: ranking(actual['por_' + k]) for k in ('vendedor', 'producto', 'cliente')},
                composicion_detalle={
                    k: actual['por_' + k][:100] for k in ('vendedor', 'producto', 'cliente')
                },
                estado_datos='disponible' if actual['lineas_pre'] else 'sin_operaciones',
                ultima_importacion=actual['ultima_importacion'], fecha_maxima=actual['fecha_maxima_pre'])


def _historial(hasta, empresa, vendedor, cliente=None, producto=None):
    nombre = func.trim(Venta.cliente)
    vendedor_expr = expresion_vendedor_resuelta()
    filtros = [Venta.estado == 'procesado', Venta.fecha < hasta + timedelta(days=1),
               nombre.isnot(None), nombre != '']
    # Primera compra global: nunca depende de empresa o vendedor seleccionados ni cuenta notas de crédito.
    primeras = db.session.query(nombre.label('cliente'), func.min(Venta.fecha).label('primera')).filter(
        *filtros, filtro_comprobante_panel_ventas())
    if cliente:
        primeras = primeras.filter(nombre == cliente)
    primeras = {nombre: primera.date() if isinstance(primera, datetime) else primera
                for nombre, primera in primeras.group_by(nombre).all()}
    filtros.append(filtro_comprobante_panel_ventas())
    if empresa != 'TODAS':
        filtros.append(func.upper(func.coalesce(Venta.origen, '')) == empresa)
    if vendedor:
        filtros.append(vendedor_expr == resolver_nombre_vendedor(vendedor))
    if cliente:
        filtros.append(nombre == cliente)
    if producto:
        filtros.append(func.trim(Venta.producto) == producto)
    comprobante = func.coalesce(func.upper(func.trim(Venta.comprobante)), '')
    nro = func.coalesce(func.trim(Venta.nro_comprob), '')
    # Agregar en SQL antes de construir estados; no cargar objetos de ventas.
    filas = db.session.query(
        nombre.label('cliente'), vendedor_expr.label('vendedor'), Venta.fecha,
        func.trim(Venta.producto).label('producto'), comprobante.label('comprobante'),
        nro.label('nro_comprob'), func.sum(Venta.subtot).label('importe'),
        func.max(Venta.fecha_import).label('importacion'),
    ).filter(*filtros).group_by(nombre, vendedor_expr, Venta.fecha, func.trim(Venta.producto),
                                comprobante, nro).all()
    nombres = {f.cliente for f in filas}
    criterios = {c: v for c, v in criterios_por_cliente().items() if c in nombres}
    return filas, primeras, criterios


def seguimiento_clientes(desde, hasta, empresa='TODAS', vendedor=None, busqueda='',
                         vista='atencion', orden='prioridad', pagina=1, por_pagina=25,
                         cliente=None, producto=None):
    anterior_desde, anterior_hasta = periodo_anterior(desde, hasta)
    inicio_actividad = hasta - timedelta(days=29)
    filas, primeras, criterios = _historial(hasta, empresa, vendedor, cliente, producto)
    clientes = {}
    ultima_importacion = fecha_maxima = None
    for fila in filas:
        if isinstance(fila.fecha, datetime):
            fila = SimpleNamespace(**{**fila._mapping, 'fecha': fila.fecha.date()})
        tipo = tipo_origen(fila.comprobante)
        nombre = fila.cliente
        importe = Decimal(str(fila.importe or 0))
        item = clientes.setdefault(nombre, dict(cliente=nombre, vendedores=set(), ultima_compra=fila.fecha,
            ultima_tipos=set(), actual=Decimal(0), anterior=Decimal(0), productos_actual=set(), productos_anterior=set(),
            compras_actual=False, compras_anterior=False, serie=defaultdict(Decimal), productos=defaultdict(Decimal),
            por_tipo={t: dict(importe=Decimal(0), ops=set()) for t in (TIPO_PRE, TIPO_FAC)}))
        periodo = 'actual' if desde <= fila.fecha <= hasta else 'anterior' if anterior_desde <= fila.fecha <= anterior_hasta else None
        item['vendedores'].add(fila.vendedor or 'Sin vendedor')
        if fila.fecha > item['ultima_compra']:
            item['ultima_compra'], item['ultima_tipos'] = fila.fecha, set()
        if fila.fecha == item['ultima_compra']:
            item['ultima_tipos'].add(tipo)
        fecha_maxima = max(fecha_maxima, fila.fecha) if fecha_maxima else fila.fecha
        if fila.importacion:
            ultima_importacion = max(ultima_importacion, fila.importacion) if ultima_importacion else fila.importacion
        if periodo:
            item[periodo] += importe
            item['compras_' + periodo] = True
            if fila.producto:
                item['productos_' + periodo].add(fila.producto)
        if periodo == 'actual':
            item['serie'][fila.fecha.isoformat()] += importe
            item['productos'][fila.producto or 'Sin producto'] += importe
            if tipo in item['por_tipo']:
                item['por_tipo'][tipo]['importe'] += importe
                item['por_tipo'][tipo]['ops'].add((fila.fecha, fila.comprobante, fila.nro_comprob))
    resultado = []
    for nombre, item in clientes.items():
        senales = []
        if item['compras_anterior'] and not item['compras_actual']:
            senales.append('Sin recompra')
        if item['compras_anterior'] and item['compras_actual']:
            if item['anterior'] > 0 and item['actual'] <= item['anterior'] * Decimal('.8'):
                senales.append('Compra en baja')
            if len(item['productos_anterior']) >= 2 and len(item['productos_actual']) * 2 <= len(item['productos_anterior']):
                senales.append('Menor variedad')
        activo = item['ultima_compra'] >= inicio_actividad
        row = dict(cliente=nombre, vendedores=sorted(item['vendedores'], key=str.casefold),
                   ultima_compra=item['ultima_compra'].isoformat(), dias=(hasta - item['ultima_compra']).days,
                   activo=activo, nuevo=primeras[nombre] >= inicio_actividad,
                   importe=float(item['actual']), comparacion=comparativo(item['actual'], item['anterior']),
                   senales=senales, criterio=criterios.get(nombre) or TIPO_PRE,
                   mostrar_origen=criterios.get(nombre) == CRITERIO_AMBOS,
                   ultima_compra_tipos=sorted(item['ultima_tipos'], key=lambda t: (t != TIPO_PRE, t)),
                   por_tipo={t: dict(n=len(v['ops']), importe=float(v['importe'])) for t, v in item['por_tipo'].items()})
        if cliente:
            row['serie'] = [dict(fecha=f, importe=float(v)) for f, v in sorted(item['serie'].items())]
            row['productos'] = [dict(nombre=p, importe=float(v)) for p, v in
                                sorted(item['productos'].items(), key=lambda p: (-p[1], p[0]))]
            row['variedad'] = dict(actual=len(item['productos_actual']), anterior=len(item['productos_anterior']))
        resultado.append(row)
    # Búsqueda cambia el universo visible; vista y paginación no alteran sus métricas.
    resultado = [f for f in resultado if busqueda.casefold() in f['cliente'].casefold()]
    total = len(resultado)
    activos = sum(f['activo'] for f in resultado)
    resumen = dict(total=total, activos=activos, sin_compra=total - activos,
                   tasa_actividad=activos / total * 100 if total else None,
                   nuevos=sum(f['nuevo'] for f in resultado),
                   atencion=sum(bool(f['senales']) for f in resultado),
                   sin_recompra=sum('Sin recompra' in f['senales'] for f in resultado),
                   baja=sum('Compra en baja' in f['senales'] for f in resultado),
                   variedad=sum('Menor variedad' in f['senales'] for f in resultado))
    if vista == 'atencion':
        resultado = [f for f in resultado if f['senales']]
    elif vista == 'activos':
        resultado = [f for f in resultado if f['activo']]
    elif vista == 'sin_compra':
        resultado = [f for f in resultado if not f['activo']]
    claves = dict(prioridad=lambda f: (f['comparacion']['diferencia'], -f['dias'], f['cliente'].casefold(), f['cliente']),
                  cliente=lambda f: (f['cliente'].casefold(), f['cliente']),
                  dias=lambda f: (-f['dias'], f['cliente'].casefold(), f['cliente']),
                  importe=lambda f: (-f['importe'], f['cliente'].casefold(), f['cliente']))
    resultado.sort(key=claves[orden])
    total_resultados = len(resultado)
    paginas = max(1, (total_resultados + por_pagina - 1) // por_pagina)
    pagina = min(pagina, paginas)
    return dict(desde=desde.isoformat(), hasta=hasta.isoformat(), desde_30d=inicio_actividad.isoformat(),
                desde_anterior=anterior_desde.isoformat(), hasta_anterior=anterior_hasta.isoformat(),
                resumen=resumen, clientes=resultado[(pagina - 1) * por_pagina:pagina * por_pagina],
                total=total_resultados, pagina=pagina, por_pagina=por_pagina, paginas=paginas,
                ultima_importacion=ultima_importacion.isoformat() if ultima_importacion else None,
                fecha_maxima=fecha_maxima.isoformat() if fecha_maxima else None)
