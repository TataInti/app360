"""Período sin liquidaciones: el endpoint responde 200 con lista vacía.

Un 404 queda registrado como error en la consola del navegador aunque el JS lo
maneje; por eso el período vacío responde 200. El campo ``error`` se mantiene
porque las pantallas de liquidaciones lo leen para mostrar su estado vacío.
"""


import pytest

from app import create_app
from config import Config
from models import db


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_ENABLED", False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)
    monkeypatch.setattr(Config, "FLASK_ENV", "development")
    monkeypatch.setattr(Config, "DEBUG", False)

    app = create_app()
    app.config["TESTING"] = True

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def test_periodo_sin_liquidaciones_responde_200_con_lista_vacia(client):
    respuesta = client.get("/api/rrhh/liquidaciones/2030-01")

    assert respuesta.status_code == 200
    datos = respuesta.get_json()
    assert datos["periodo"] == "2030-01"
    assert datos["liquidaciones"] == []
    assert datos["error"] == "No se encontraron liquidaciones para 2030-01"


def test_panel_muestra_estado_vacio_en_espanol(app):
    from pathlib import Path

    plantilla = (Path(app.root_path) / "templates" / "rrhh_panel.html").read_text(encoding="utf-8")

    assert "Todavía no hay liquidaciones para ${escapeHtml(periodo)}" in plantilla
    assert "Sin liquidaciones para ${escapeHtml(periodo)}" not in plantilla
