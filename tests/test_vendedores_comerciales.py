import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from app import create_app
from config import Config
from models import db
from models.comercial import ComercialVendedor, ComercialVendedorAlias
from services.vendedores_comerciales import (
    resolver_nombre_vendedor,
    seed_vendedores_comerciales,
)


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_aliases_de_benjamin_resuelven_al_mismo_nombre_visible(app):
    with app.app_context():
        seed_vendedores_comerciales()
        db.session.commit()

        assert resolver_nombre_vendedor("KALJA BENJAMIN") == "Benjamín Kalja"
        assert resolver_nombre_vendedor("BENJAMIN KALJA") == "Benjamín Kalja"
        assert resolver_nombre_vendedor("  kalja   benjamin  ") == "Benjamín Kalja"


def test_aliases_de_walter_resuelven_al_mismo_nombre_visible(app):
    with app.app_context():
        seed_vendedores_comerciales()
        db.session.commit()

        assert resolver_nombre_vendedor("MEDINA WALTER") == "Walter Medina"
        assert resolver_nombre_vendedor("WALTER") == "Walter Medina"


def test_nombre_sin_alias_no_se_fusiona_con_otro(app):
    with app.app_context():
        seed_vendedores_comerciales()
        db.session.commit()

        assert resolver_nombre_vendedor("WALTER") == "Walter Medina"
        assert resolver_nombre_vendedor("  WALTER   MEDINA  ") == "WALTER MEDINA"
        assert resolver_nombre_vendedor("Vendedor Norte") == "Vendedor Norte"
        assert resolver_nombre_vendedor("Vendedor Norte 2") == "Vendedor Norte 2"


def test_seed_idempotente_no_duplica_vendedores_ni_aliases(app):
    with app.app_context():
        seed_vendedores_comerciales()
        db.session.commit()
        seed_vendedores_comerciales()
        db.session.commit()

        assert db.session.query(ComercialVendedor).count() == 2
        assert db.session.query(ComercialVendedorAlias).count() == 4


def test_migracion_idempotente_en_sqlite_desechable():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "versions"
        / "20261020_comercial_vendedores.py"
    )
    spec = importlib.util.spec_from_file_location(
        "comercial_vendedores_migration",
        migration_path,
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            with Operations.context(context):
                migration.upgrade()
                migration.upgrade()

            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM comercial_vendedores"
            ).scalar_one() == 2
            assert connection.exec_driver_sql(
                "SELECT COUNT(*) FROM comercial_vendedor_aliases"
            ).scalar_one() == 4
            assert set(
                connection.exec_driver_sql(
                    "SELECT nombre_origen FROM comercial_vendedor_aliases"
                ).scalars().all()
            ) == {
                "KALJA BENJAMIN",
                "BENJAMIN KALJA",
                "MEDINA WALTER",
                "WALTER",
            }
    finally:
        engine.dispose()
