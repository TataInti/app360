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