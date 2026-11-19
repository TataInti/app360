import pytest

from sesion_de_prueba import ADMIN_PRUEBA_ID, asegurar_usuario, marcar_sesion


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sin_sesion_admin: el módulo no inyecta la sesión admin (su base no tiene tabla users)",
    )


@pytest.fixture(autouse=True)
def authenticated_session_for_client(request):
    """Sesión admin para los tests que piden `client`.

    La sesión web se revalida contra la base en cada request: el usuario 1 debe existir
    y estar activo, y la sesión debe llevar su huella. Se crea el usuario sintético si
    falta y la sesión se marca con el mismo helper que usa el login.
    """
    if "client" not in request.fixturenames or request.node.get_closest_marker("sin_sesion_admin"):
        yield
        return

    client = request.getfixturevalue("client")
    asegurar_usuario(client.application, ADMIN_PRUEBA_ID, "test-admin", "admin")
    marcar_sesion(client, ADMIN_PRUEBA_ID)
    yield


@pytest.fixture
def app_seguridad(monkeypatch):
    """App con SQLite en memoria para pruebas de acceso, escrituras y scripts.

    Datos sintéticos rotulados PROBE; ninguna prueba apunta a una base real. No usa
    el fixture `client`, así que no recibe la sesión admin inyectada por el autouse.
    """
    from app import create_app
    from config import Config
    from models import db

    monkeypatch.setattr(Config, "SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "JWT_SECRET_KEY", "test-secret")
    monkeypatch.setattr(Config, "ADMIN_PASSWORD", "test-admin")
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", "sqlite:///:memory:")
    monkeypatch.setattr(Config, "WTF_CSRF_CHECK_DEFAULT", False, raising=False)
    monkeypatch.setattr(Config, "RATELIMIT_ENABLED", False)

    application = create_app()
    application.config["TESTING"] = True
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()
