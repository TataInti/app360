import pytest


@pytest.fixture(autouse=True)
def authenticated_session_for_client(request):
    if "client" not in request.fixturenames:
        yield
        return

    client = request.getfixturevalue("client")
    with client.session_transaction() as session:
        session.setdefault("user", "test-admin")
        session.setdefault("role", "admin")
        session.setdefault("user_id", 1)

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
