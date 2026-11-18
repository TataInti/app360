"""Datos 100% sintéticos para la vista previa local de App360 (E2E).

Reproduce la forma de los datos de producción (stg_sabiogo_ventas procesado,
catálogo comercial con alias, líneas de objetivo y objetivos históricos de
RRHH) sin usar ningún dato real. Solo escribe en la base local
127.0.0.1:55432/app360_e2e: cualquier otra URL se rechaza.

Uso (desde la raíz del repo, con el esquema ya migrado con `flask db upgrade`):
    python scripts/dev_preview/seed_demo.py            # siembra si está vacío
    python scripts/dev_preview/seed_demo.py --reset    # vacía y vuelve a sembrar
"""

import argparse
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
HOST_PERMITIDO = {"127.0.0.1", "localhost"}
PUERTO_PERMITIDO = 55432
NOMBRE_BASE_PERMITIDO = "app360_e2e"
FUENTE_SINTETICA = "SINTETICO_E2E_LOCAL"
SEMILLA = 18112026
ZONA_LOCAL = timezone(timedelta(hours=-3))

# Contraseñas ficticias de la base local. No corresponden a ningún usuario real.
CONTRASENAS_DEMO = {
    "ventas.demo": "e2e-ventas-ficticia",
    "rrhh.demo": "e2e-rrhh-ficticia",
    "finanzas.demo": "e2e-finanzas-ficticia",
}

TABLAS_PROPIAS = (
    "comercial_objetivo_vinculos",
    "comercial_objetivos",
    "comercial_vendedor_aliases",
    "comercial_vendedores",
    "stg_sabiogo_ventas",
    "goals",
    "employees",
)

# (nombre visible, activo, alias de origen en mayúsculas o con variantes)
VENDEDORES = (
    ("Vendedora Demo Ana", True, ["DEMO ANA", "ANA DEMO"]),
    ("Vendedor Demo Bruno", True, ["DEMO BRUNO"]),
    ("Vendedora Demo Carla", True, ["DEMO CARLA", "CARLA DEMO"]),
    ("Vendedor Demo Diego", True, ["DEMO DIEGO"]),
    ("Vendedora Demo Elena", True, ["DEMO ELENA"]),
    ("Salón", True, ["SALON"]),
    ("Vendedor Demo Inactivo", False, ["DEMO INACTIVO"]),
)
# Nombres de origen que aparecen en staging con variantes de mayúsculas y espacios.
VARIANTES_ORIGEN = {
    "Vendedora Demo Ana": ["DEMO ANA", "demo  ana", "ANA DEMO"],
    "Vendedor Demo Bruno": ["DEMO BRUNO", "Demo Bruno"],
    "Vendedora Demo Carla": ["DEMO CARLA", "CARLA DEMO"],
    "Vendedor Demo Diego": ["DEMO DIEGO"],
    "Vendedora Demo Elena": ["DEMO ELENA"],
    "Salón": ["SALON"],
    "Vendedor Demo Inactivo": ["DEMO INACTIVO"],
}
# Vendedor de staging sin alias en el catálogo (aparece como vendedor de venta).
VENDEDOR_SIN_ALIAS = "DEMO SIN ALIAS"

# (producto, rubro, subrubro, marca, origen, tiene_cajas, tiene_kilos)
PRODUCTOS = (
    ("Queso Cremoso Demo 1kg", "Lácteos", "Quesos blandos", "Marca Norte", "LACTEOS", True, True),
    ("Queso Sardo Demo 1kg", "Lácteos", "Quesos duros", "Marca Norte", "LACTEOS", True, True),
    ("Ricota  Húmeda 500 g", "Lácteos", "Ricotas", "Estancia Sur", "LACTEOS", False, False),
    ("Yogur Natural Demo 1 L", "Lácteos", "Yogures", "Campo Demo ", "LACTEOS", True, False),
    ("Manteca Demo 200 g", "Lácteos", "Mantecas", "Campo Demo", "LACTEOS", False, True),
    ("Vacío Demo por kilo", "Carnes", "Vacuno", "Frigo Demo", "CARNES", True, True),
    ("Bondiola Demo por kilo", "Carnes", "Cerdo", "Frigo Demo", "CARNES", False, False),
    ("Pollo Entero Demo", "Carnes", "Aves", "Granja Demo", "CARNES", True, False),
    ("Chorizo Parrillero Demo", "Fiambres", "Embutidos", "Sierra Demo", "CARNES", True, True),
    ("Jamón Cocido Demo", "Fiambres", "Embutidos", "Sierra Demo", "CARNES", False, True),
)
PRODUCTO_LEGACY = ("Producto Legacy Demo", "Legacy", "Legacy", "Legacy Demo", "LEGACY", True, True)
PRODUCTO_PENDIENTE = (
    "Pendiente Demo Sin Procesar",
    "Lácteos",
    "Pendientes",
    "Marca Norte",
    "CARNES",
    True,
    True,
)

CLIENTES = (
    ["CONSUMIDOR FINAL"] * 6
    + [f"Cliente Demo {n:02d}" for n in range(1, 22)]
    + [
        "Almacén Demo Ñandú",
    ]
)


def verificar_base_local(url: str) -> None:
    """Rechaza cualquier base que no sea la base E2E local."""
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


def _normalizar(nombre: str) -> str:
    return " ".join(nombre.split()).upper()


def _fechas(hoy: date, dias: int):
    for desplazamiento in range(dias, -1, -1):
        yield hoy - timedelta(days=desplazamiento)


def generar_ventas(rng: random.Random, hoy: date):
    """Filas de stg_sabiogo_ventas: PRE y FAC, con y sin nro_comprob."""
    from models.sabiogo.staging import StgSabiogoVentas

    vendedores_origen = []
    for nombre, _activo, _aliases in VENDEDORES:
        for variante in VARIANTES_ORIGEN.get(nombre, []):
            vendedores_origen.append((nombre, variante))
    vendedores_origen.append((None, VENDEDOR_SIN_ALIAS))
    # Un peso por cada nombre de origen de vendedores_origen, en el mismo orden.
    pesos_vendedor = [30, 14, 10, 8, 6, 3, 10, 8, 4, 3, 2, 2]
    assert len(pesos_vendedor) == len(vendedores_origen)
    productos_catalogo = list(PRODUCTOS)
    filas = []
    contador = 0
    for dia in _fechas(hoy, 150):
        for _ in range(rng.randint(0, 9)):
            contador += 1
            _nombre, origen_vendedor = rng.choices(vendedores_origen, weights=pesos_vendedor)[0]
            producto, rubro, subrubro, marca, origen, con_cajas, con_kilos = rng.choice(
                productos_catalogo
            )
            es_fac = rng.random() < 0.15
            comprobante = "FAC" if es_fac else "PRE"
            nro = None if rng.random() < 0.1 else f"0001-{contador:06d}"
            importe = round(rng.uniform(15000, 320000), 2)
            cajas = float(rng.randint(1, 20)) if con_cajas else 0.0
            kilos = float(rng.randint(1, 60)) if con_kilos else 0.0
            filas.append(
                StgSabiogoVentas(
                    fecha=dia,
                    origen=origen,
                    sucursal="Sucursal Demo",
                    tipo="A",
                    codigo=f"DEMO-{contador:06d}",
                    producto=producto,
                    rubro=rubro,
                    subrubro=subrubro,
                    marca=marca,
                    cliente=rng.choice(CLIENTES),
                    vendedor=origen_vendedor,
                    comprobante=comprobante,
                    nro_comprob=nro,
                    subtot=importe,
                    cajas=cajas,
                    kilos=kilos,
                    estado="procesado",
                    fuente_archivo=FUENTE_SINTETICA,
                )
            )
    # Salón: solo tickets FAC, con su alias de origen.
    for dia in _fechas(hoy, 30):
        if rng.random() < 0.5:
            contador += 1
            producto, rubro, subrubro, marca, origen, _c, _k = rng.choice(productos_catalogo)
            filas.append(
                StgSabiogoVentas(
                    fecha=dia,
                    origen=origen,
                    sucursal="Sucursal Demo",
                    tipo="A",
                    codigo=f"DEMO-{contador:06d}",
                    producto=producto,
                    rubro=rubro,
                    subrubro=subrubro,
                    marca=marca,
                    cliente="CONSUMIDOR FINAL",
                    vendedor="SALON",
                    comprobante="FAC",
                    nro_comprob=f"0002-{contador:06d}",
                    subtot=round(rng.uniform(5000, 60000), 2),
                    cajas=0.0,
                    kilos=0.0,
                    estado="procesado",
                    fuente_archivo=FUENTE_SINTETICA,
                )
            )
    # Filas que la aplicación debe ignorar: pendientes y origen no comercial.
    for dia in _fechas(hoy, 20):
        if rng.random() < 0.3:
            contador += 1
            producto, rubro, subrubro, marca, origen, _c, _k = PRODUCTO_PENDIENTE
            filas.append(
                StgSabiogoVentas(
                    fecha=dia,
                    origen=origen,
                    codigo=f"DEMO-{contador:06d}",
                    producto=producto,
                    rubro=rubro,
                    subrubro=subrubro,
                    marca=marca,
                    cliente="Cliente Demo 01",
                    vendedor="DEMO ANA",
                    comprobante="PRE",
                    nro_comprob=f"0003-{contador:06d}",
                    subtot=5000.0,
                    cajas=1.0,
                    kilos=1.0,
                    estado="pendiente",
                    fuente_archivo=FUENTE_SINTETICA,
                )
            )
    producto, rubro, subrubro, marca, origen, _c, _k = PRODUCTO_LEGACY
    for dia in _fechas(hoy, 20):
        if rng.random() < 0.3:
            contador += 1
            filas.append(
                StgSabiogoVentas(
                    fecha=dia,
                    origen=origen,
                    codigo=f"DEMO-{contador:06d}",
                    producto=producto,
                    rubro=rubro,
                    subrubro=subrubro,
                    marca=marca,
                    cliente="Cliente Demo 02",
                    vendedor="DEMO ANA",
                    comprobante="PRE",
                    nro_comprob=f"0004-{contador:06d}",
                    subtot=7000.0,
                    cajas=2.0,
                    kilos=2.0,
                    estado="procesado",
                    fuente_archivo=FUENTE_SINTETICA,
                )
            )
    return filas


def sembrar(app, reset: bool) -> None:
    from models import db
    from models.comercial import ComercialObjetivo, ComercialVendedor, ComercialVendedorAlias
    from models.core.user import User
    from models.hr.employee import Employee
    from models.hr.goal import Goal
    from models.sabiogo.staging import StgSabiogoVentas
    from models.time_utils import now_local

    with app.app_context():
        insp = inspect(db.engine)
        faltan = [t for t in TABLAS_PROPIAS + ("users",) if not insp.has_table(t)]
        if faltan:
            raise SystemExit(f"Faltan tablas {faltan}. Ejecutá `flask db upgrade` antes del seed.")

        ya_hay_datos = db.session.query(StgSabiogoVentas.id).first() is not None
        if ya_hay_datos and not reset:
            print("La base ya tiene datos sintéticos. Usá --reset para volver a sembrar.")
            return
        # Las migraciones del repo cargan un catálogo comercial inicial con nombres
        # reales. La base E2E debe contener solo datos sintéticos: se vacían las
        # tablas propias antes de sembrar.
        db.session.execute(text(f"TRUNCATE {', '.join(TABLAS_PROPIAS)} RESTART IDENTITY CASCADE"))
        db.session.commit()

        rng = random.Random(SEMILLA)
        hoy = datetime.now(ZONA_LOCAL).date()

        admin_user = (
            db.session.query(User)
            .filter_by(username=os.environ.get("ADMIN_USERNAME", "admin"))
            .one_or_none()
        )
        if admin_user is None:
            admin_user = User(
                username=os.environ.get("ADMIN_USERNAME", "admin"), role="admin", active=True
            )
            db.session.add(admin_user)
        admin_user.role = "admin"
        admin_user.active = True
        admin_user.set_password(os.environ["ADMIN_PASSWORD"])

        for usuario, rol in (
            ("ventas.demo", "sales"),
            ("rrhh.demo", "hr"),
            ("finanzas.demo", "finance"),
        ):
            cuenta = db.session.query(User).filter_by(username=usuario).one_or_none()
            if cuenta is None:
                cuenta = User(username=usuario, role=rol, active=True)
                db.session.add(cuenta)
            cuenta.role = rol
            cuenta.active = True
            cuenta.set_password(CONTRASENAS_DEMO[usuario])
        db.session.flush()

        vendedores = {}
        for nombre, activo, aliases in VENDEDORES:
            vendedor = ComercialVendedor(nombre_visible=nombre, activo=activo)
            db.session.add(vendedor)
            db.session.flush()
            vendedores[nombre] = vendedor
            for origen in aliases:
                db.session.add(
                    ComercialVendedorAlias(
                        vendedor_id=vendedor.id,
                        nombre_origen=origen,
                        nombre_normalizado=_normalizar(origen),
                    )
                )
        db.session.flush()

        db.session.add_all(generar_ventas(rng, hoy))

        ahora = now_local()
        mes_actual = hoy.strftime("%Y-%m")
        lineas = [
            ("Vendedora Demo Ana", "empresa", "CARNES", 1500000, 0, 0, "Meta demo empresa CARNES"),
            (
                "Vendedor Demo Bruno",
                "producto",
                "Queso Sardo Demo 1kg",
                400000,
                50,
                0,
                "Meta demo producto",
            ),
            ("Vendedora Demo Carla", "rubro", "Lácteos", 900000, 0, 300, "Meta demo rubro"),
        ]
        for nombre, tipo, valor, m_imp, m_caj, m_kg, descripcion in lineas:
            db.session.add(
                ComercialObjetivo(
                    vendedor_id=vendedores[nombre].id,
                    empresa=valor if tipo == "empresa" else None,
                    mes=mes_actual,
                    medida=None,
                    meta=None,
                    dimension_tipo=tipo,
                    dimension_valor=valor,
                    meta_importe=Decimal(str(m_imp)),
                    meta_cajas=Decimal(str(m_caj)),
                    meta_kilos=Decimal(str(m_kg)),
                    descripcion=descripcion,
                    creado_en=ahora,
                    actualizado_en=ahora,
                    creado_por_id=admin_user.id,
                    actualizado_por_id=admin_user.id,
                )
            )

        empleados = [
            Employee(
                first_name="Empleado",
                last_name="Demo Uno",
                position="Vendedor",
                department="Comercial",
            ),
            Employee(
                first_name="Empleado",
                last_name="Demo Dos",
                position="Vendedor",
                department="Comercial",
            ),
            Employee(
                first_name="Empleado",
                last_name="Demo Tres",
                position="Vendedor",
                department="Comercial",
            ),
        ]
        db.session.add_all(empleados)
        db.session.flush()
        historicos = [
            (empleados[0], "Objetivo histórico demo CARNES", "2026-10", 800000.0),
            (empleados[1], "Objetivo histórico demo LACTEOS kilos", "2026-09", 1200.0),
            (empleados[2], "Objetivo histórico demo trimestral", "2026-Q4", 50000.0),
        ]
        for empleado, descripcion, periodo, meta in historicos:
            db.session.add(
                Goal(
                    employee_id=empleado.id,
                    description=descripcion,
                    period=periodo,
                    target_value=meta,
                    current_value=0.0,
                    status="en progreso",
                )
            )
        db.session.commit()

        resumen = {
            "stg_sabiogo_ventas": db.session.query(StgSabiogoVentas.id).count(),
            "comercial_vendedores": db.session.query(ComercialVendedor.id).count(),
            "comercial_vendedor_aliases": db.session.query(ComercialVendedorAlias.id).count(),
            "comercial_objetivos": db.session.query(ComercialObjetivo.id).count(),
            "goals": db.session.query(Goal.id).count(),
            "users": db.session.query(User.id).count(),
        }
        print("SEED_OK", resumen)
        print("USUARIOS", sorted(CONTRASENAS_DEMO) + [os.environ.get("ADMIN_USERNAME", "admin")])


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--reset", action="store_true", help="vacía las tablas sintéticas y vuelve a sembrar"
    )
    args = parser.parse_args()

    verificar_base_local(os.environ.get("DATABASE_URL", ""))
    for variable in ("SECRET_KEY", "ADMIN_PASSWORD"):
        if not os.environ.get(variable):
            raise SystemExit(f"Falta la variable {variable} (valor ficticio para la base local).")

    sys.path.insert(0, REPO_ROOT)
    os.chdir(REPO_ROOT)
    from app import create_app

    app = create_app()
    sembrar(app, reset=args.reset)
    return 0


if __name__ == "__main__":
    sys.exit(main())
