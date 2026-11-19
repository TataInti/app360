"""Migración 20261119_usuarios_c1_clave: upgrade, downgrade y upgrade con usuarios existentes.

Se prueba el módulo de la migración sobre una tabla users con la forma previa y los ocho
usuarios de la instancia (datos sintéticos). La cadena completa de Alembic no corre en una
base vacía (ver app360-e2e-objetivos-local), por eso aquí se usa la tabla mínima. La prueba
sobre PostgreSQL (migrate_db_safely.sh, downgrade y upgrade) se hace en la instancia C1.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

RAIZ = Path(__file__).resolve().parents[1]
MIGRACION = RAIZ / "migrations" / "versions" / "20261119_usuarios_c1_clave.py"
NUEVAS = {"must_change_password", "password_changed_at", "last_login_at"}
USUARIOS_PREVIOS = [
    ("admin", "admin", True, "hash-sintetico-admin"),
    ("gerente", "gerente", True, "hash-sintetico-gerente"),
    ("ventas", "sales", True, "hash-sintetico-ventas"),
    ("rrhh", "hr", True, "hash-sintetico-rrhh"),
    ("tesoreria", "caja", True, "hash-sintetico-tesoreria"),
    ("direccion", "director", True, "hash-sintetico-direccion"),
    ("anibal.lopez", "sales", True, "hash-sintetico-anibal"),
    ("test_user", "sales", False, "hash-sintetico-test"),
]


def _modulo():
    especificacion = importlib.util.spec_from_file_location("migracion_usuarios_c1", MIGRACION)
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


def _ejecutar(motor, funcion):
    with motor.begin() as conexion:
        with Operations.context(MigrationContext.configure(conexion)):
            funcion()


def _columnas(motor):
    return {columna["name"] for columna in sa.inspect(motor).get_columns("users")}


def _fotografia(motor):
    with motor.connect() as conexion:
        filas = conexion.execute(
            sa.text("SELECT username, role, active, password_hash FROM users ORDER BY id")
        ).all()
    return [tuple(fila) for fila in filas]


def test_upgrade_downgrade_upgrade_con_usuarios_existentes(tmp_path):
    motor = sa.create_engine(f"sqlite:///{tmp_path / 'usuarios.db'}")
    with motor.begin() as conexion:
        conexion.execute(
            sa.text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(80) NOT NULL UNIQUE, "
                "password_hash VARCHAR(255), role VARCHAR(40) NOT NULL, active BOOLEAN DEFAULT 1)"
            )
        )
        conexion.execute(
            sa.text(
                "INSERT INTO users (username, role, active, password_hash) "
                "VALUES (:usuario, :rol, :activo, :hash)"
            ),
            [
                {"usuario": u, "rol": r, "activo": a, "hash": h}
                for u, r, a, h in USUARIOS_PREVIOS
            ],
        )
    antes = _fotografia(motor)
    assert len(antes) == 8
    modulo = _modulo()

    _ejecutar(motor, modulo.upgrade)
    assert NUEVAS <= _columnas(motor)
    with motor.connect() as conexion:
        filas = conexion.execute(
            sa.text(
                "SELECT must_change_password, password_changed_at, last_login_at "
                "FROM users ORDER BY id"
            )
        ).all()
    assert len(filas) == 8
    assert all(fila[0] in (0, False) and fila[1] is None and fila[2] is None for fila in filas)
    assert _fotografia(motor) == antes, "claves, roles y estado activo no cambian al migrar"

    _ejecutar(motor, modulo.downgrade)
    assert not (NUEVAS & _columnas(motor))
    assert _fotografia(motor) == antes

    _ejecutar(motor, modulo.upgrade)
    assert NUEVAS <= _columnas(motor)
    assert _fotografia(motor) == antes
