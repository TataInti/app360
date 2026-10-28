"""Helpers compartidos de lectura para los paneles comerciales web.

Agrupa la validación de parámetros de período y el envoltorio de errores que
usan tanto el Panel de Ventas (``dashboard_com_bp``) como la nueva pestaña de
Performance de Vendedores (``comercial_bp``).
"""

from datetime import date

from flask import jsonify, request

from models.time_utils import today_local_date


def parametros_panel():
    """Lee y valida empresa/fechas del query string, con la comparación anterior."""
    hoy = today_local_date()
    hasta = date.fromisoformat(request.args.get('fecha_hasta') or hoy.isoformat())
    desde = date.fromisoformat(request.args.get('fecha_desde') or hasta.replace(day=1).isoformat())
    if desde > hasta:
        raise ValueError('Desde no puede ser posterior a Hasta.')
    # Evita desbordes al construir la comparación anterior.
    from services.comercial_paneles import periodo_anterior
    periodo_anterior(desde, hasta)
    empresa = (request.args.get('empresa') or 'TODAS').upper()
    if empresa not in {'TODAS', 'CARNES', 'LACTEOS'}:
        raise ValueError('Empresa inválida.')
    return dict(desde=desde, hasta=hasta, empresa=empresa,
                vendedor=request.args.get('vendedor', '').strip() or None)


def lectura_panel(consulta):
    """Ejecuta una consulta y devuelve JSON, traduciendo errores a HTTP."""
    from flask import current_app
    try:
        return jsonify(consulta())
    except (ValueError, OverflowError):
        return jsonify(error='Revisá las fechas, filtros y paginación.'), 400
    except Exception:
        current_app.logger.exception('Error leyendo panel comercial')
        return jsonify(error='No se pudieron cargar los datos. Volvé a intentar.'), 500