"""Escenario de dinero para el E2E del corte D2 (liquidación, arqueo, Friar y margen).

Agrega, sobre la semilla de seed_demo.py, datos 100 % sintéticos y rotulados
«DEMO E2E»:
- usuarios de prueba: consulta.demo (sin módulos), operaciones.demo (módulo operations)
  y lectura.demo (sin módulos, con permisos individuales de solo lectura);
- una empleada sintética con salario 250.000,50, dos adelantos en efectivo de 50.000 y dos
  préstamos de 120.000 en 3 cuotas al 10 % (escenario de A-011);
- un instrumento de caja y dos movimientos del día, turno mañana, de 1.500 y 500 (A-012);
- con --con-compras, una compra de SabioGo procesada en el período (A-013).

Solo escribe en 127.0.0.1:55432/app360_fix_d2; cualquier otra URL se rechaza.

Uso (desde la raíz del repo, con el esquema ya migrado y seed_demo.py aplicado):
    python scripts/dev_preview/seed_dinero_d2.py [--con-compras]
"""

import argparse
import os
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.engine import make_url

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST_PERMITIDO = {"127.0.0.1", "localhost"}
PUERTO_PERMITIDO = 55432
NOMBRE_BASE_PERMITIDO = "app360_fix_d2"
PREFIJO = "DEMO E2E"
FUENTE = "SINTETICO_E2E_D2"

# Contraseñas ficticias de la base local. No corresponden a ningún usuario real.
CONTRASENAS = {
    "consulta.demo": "e2e-consulta-ficticia",
    "operaciones.demo": "e2e-operaciones-ficticia",
    "lectura.demo": "e2e-lectura-ficticia",
}
MODULOS_SOLO_LECTURA = ("products", "stock", "crm", "rrhh")


def verificar_base_local(url: str) -> None:
    if not url:
        raise SystemExit("DATABASE_URL no está definida.")
    parsed = make_url(url)
    if parsed.host not in HOST_PERMITIDO or parsed.port != PUERTO_PERMITIDO:
        raise SystemExit(
            "Rechazado: el seed solo escribe en 127.0.0.1:55432. "
            f"Host/puerto recibidos: {parsed.host}:{parsed.port}"
        )
    if parsed.database != NOMBRE_BASE_PERMITIDO:
        raise SystemExit(f"Rechazado: la base debe llamarse {NOMBRE_BASE_PERMITIDO}.")


def _usuarios(db):
    from models.core.user import User
    from models.core.user_permission import UserModulePermission

    for usuario, rol in (
        ("consulta.demo", "consulta"),
        ("operaciones.demo", "operations"),
        ("lectura.demo", "consulta"),
    ):
        cuenta = db.session.query(User).filter_by(username=usuario).one_or_none()
        if cuenta is None:
            cuenta = User(username=usuario, role=rol, active=True)
            db.session.add(cuenta)
        cuenta.role = rol
        cuenta.active = True
        cuenta.set_password(CONTRASENAS[usuario])
    db.session.flush()

    lectura = db.session.query(User).filter_by(username="lectura.demo").one()
    for modulo in MODULOS_SOLO_LECTURA:
        permiso = (
            db.session.query(UserModulePermission)
            .filter_by(user_id=lectura.id, module=modulo)
            .one_or_none()
        )
        if permiso is None:
            db.session.add(UserModulePermission(user_id=lectura.id, module=modulo, access_level="view"))
        else:
            permiso.access_level = "view"


def _liquidacion_demo(db):
    from models.hr.employee import Employee
    from models.rrhh import Adelanto

    ya_existe = (
        db.session.query(Employee)
        .filter_by(first_name="Empleada", last_name="Demo Liquidación")
        .one_or_none()
    )
    if ya_existe is not None:
        return "existente"
    empleada = Employee(
        first_name="Empleada",
        last_name="Demo Liquidación",
        email="empleada.demo@example.invalid",
        position="Administración",
        department="RRHH demo",
        hire_date=date(2025, 1, 1),
        salary=Decimal("250000.50"),
        is_active=True,
    )
    db.session.add(empleada)
    db.session.flush()
    for _ in range(2):
        db.session.add(Adelanto(
            empleado_id=empleada.id,
            tipo="adelanto_efectivo",
            monto=Decimal("50000"),
            concepto=f"{PREFIJO}: adelanto en efectivo",
            mes_aplicacion="2026-11",
            aprobado=True,
            liquidado=False,
        ))
    for _ in range(2):
        db.session.add(Adelanto(
            empleado_id=empleada.id,
            tipo="prestamo",
            monto=Decimal("120000"),
            concepto=f"{PREFIJO}: préstamo",
            cantidad_cuotas=3,
            interes_porcentaje=Decimal("10"),
            cuotas_pagadas=0,
            aprobado=True,
            liquidado=False,
        ))
    return "creada"


def _caja_demo(db):
    from models.core.user import User
    from models.tesoreria import InstrumentoPago, MovimientoCaja
    from models.time_utils import today_local_date

    instrumento = db.session.query(InstrumentoPago).filter_by(nombre="Efectivo").one_or_none()
    if instrumento is None:
        instrumento = InstrumentoPago(nombre="Efectivo", descripcion="Efectivo demo E2E", activo=True)
        db.session.add(instrumento)
        db.session.flush()
    if db.session.query(MovimientoCaja).filter(MovimientoCaja.descripcion.like(f"{PREFIJO}%")).first():
        return "existente"
    admin = db.session.query(User).filter_by(username="admin").one()
    hoy = today_local_date()
    for tipo, monto, hora, texto in (
        ("ingreso", "1500.00", time(9, 0), "cobranza del turno mañana"),
        ("egreso", "500.00", time(10, 30), "pago del turno mañana"),
    ):
        db.session.add(MovimientoCaja(
            fecha_hora=datetime.combine(hoy, hora),
            tipo=tipo,
            monto=Decimal(monto),
            descripcion=f"{PREFIJO}: {texto}",
            estado="activo",
            instrumento_id=instrumento.id,
            usuario_id=admin.id,
        ))
    return "creada"


def _compras_demo(db):
    from models.sabiogo.staging import StgSabiogoCompras
    from models.time_utils import today_local_date

    if db.session.query(StgSabiogoCompras).filter_by(fuente_archivo=FUENTE).first():
        return "existente"
    hoy = today_local_date()
    db.session.add(StgSabiogoCompras(
        fecha=hoy - timedelta(days=5),
        origen="CARNES",
        sucursal="Sucursal Demo",
        tipo="A",
        codigo="DEMO-COMPRA-1",
        producto="Compra demo E2E",
        rubro="Carnes",
        subrubro="Vacuno",
        marca="Frigo Demo",
        subtot=2500000.0,
        neto=2500000.0,
        iva=0.0,
        estado="procesado",
        fuente_archivo=FUENTE,
    ))
    return "creada"


def sembrar(app, con_compras: bool) -> dict:
    from models import db

    with app.app_context():
        _usuarios(db)
        resultado = {"liquidacion": _liquidacion_demo(db), "caja": _caja_demo(db)}
        if con_compras:
            resultado["compras"] = _compras_demo(db)
        db.session.commit()
        return resultado


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--con-compras", action="store_true", help="agrega una compra procesada del período")
    args = parser.parse_args()

    verificar_base_local(os.environ.get("DATABASE_URL", ""))
    for variable in ("SECRET_KEY", "ADMIN_PASSWORD"):
        if not os.environ.get(variable):
            raise SystemExit(f"Falta la variable {variable} (valor ficticio para la base local).")

    sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)
    from app import create_app

    resultado = sembrar(create_app(), con_compras=args.con_compras)
    print("SEED_DINERO_OK", resultado)
    return 0


if __name__ == "__main__":
    sys.exit(main())
