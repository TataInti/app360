"""Compatibilidad y manejo seguro de JWT con PyJWT actualizado."""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import jwt
import pytest

from models import db
from models.core.user import User
from security import (
    MAX_JWT_TOKEN_LENGTH,
    decode_token,
    generate_access_token,
    generate_refresh_token,
)


USUARIO = "PROBE-deps-jwt"


def _crear_usuario(app):
    app.config["JWT_SECRET_KEY"] = "PROBE-JWT-secret-for-dependency-compatibility-test-only"
    with app.app_context():
        usuario = User(username=USUARIO, role="admin", active=True)
        usuario.set_password("PROBE-clave-jwt-2026")
        # Aísla la prueba de la revocación C1: se comprueba aquí el formato del token,
        # no el momento de cambio de contraseña.
        usuario.password_changed_at = None
        db.session.add(usuario)
        db.session.commit()
        return usuario.id


def _cabecera(token):
    return {"Authorization": f"Bearer {token}"}


def _b64url(datos):
    return base64.urlsafe_b64encode(datos).rstrip(b"=").decode("ascii")


def _payload_base(user_id, **extra):
    ahora = int(time.time())
    return {
        "user_id": user_id,
        "username": USUARIO,
        "role": "admin",
        "type": "access",
        "iat": ahora,
        "exp": ahora + 300,
        **extra,
    }


def _token_crudo(header, payload, firma=b""):
    encabezado = _b64url(json.dumps(header, separators=(",", ":")).encode())
    contenido = _b64url(payload)
    return f"{encabezado}.{contenido}.{_b64url(firma)}"


def _token_hs256(app, payload):
    encabezado = _b64url(b'{"alg":"HS256","typ":"JWT"}')
    contenido = _b64url(payload)
    firmado = f"{encabezado}.{contenido}".encode("ascii")
    secreto = app.config["JWT_SECRET_KEY"]
    if isinstance(secreto, str):
        secreto = secreto.encode("utf-8")
    firma = hmac.new(secreto, firmado, hashlib.sha256).digest()
    return f"{firmado.decode('ascii')}.{_b64url(firma)}"


def test_access_y_refresh_con_iat_fraccionario_se_emiten_y_verifican(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    cliente = app.test_client()

    with app.app_context():
        access = generate_access_token(user_id, USUARIO, "admin")
        refresh = generate_refresh_token(user_id, USUARIO)
        payload_access = decode_token(access)
        payload_refresh = decode_token(refresh)

    assert payload_access is not None
    assert payload_refresh is not None
    assert payload_access["type"] == "access"
    assert payload_refresh["type"] == "refresh"
    assert isinstance(payload_access["iat"], float)
    assert isinstance(payload_refresh["iat"], float)
    assert payload_access["iat"] % 1 != 0
    assert payload_refresh["iat"] % 1 != 0
    assert cliente.get("/api/me", headers=_cabecera(access)).status_code == 200
    assert cliente.post("/api/refresh", json={"refresh_token": refresh}).status_code == 200


def test_token_legacy_con_iat_entero_sigue_verificando(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    cliente = app.test_client()
    ahora = int(datetime.now(timezone.utc).timestamp())
    token = jwt.encode(
        _payload_base(user_id, iat=ahora, exp=ahora + 300),
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    with app.app_context():
        payload = decode_token(token)

    assert payload is not None
    assert payload["iat"] == ahora
    assert type(payload["iat"]) is int
    assert cliente.get("/api/me", headers=_cabecera(token)).status_code == 200


def test_token_expirado_responde_401(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    ahora = int(time.time())
    token = jwt.encode(
        _payload_base(user_id, iat=ahora - 600, exp=ahora - 1),
        app.config["JWT_SECRET_KEY"],
        algorithm="HS256",
    )

    with app.app_context():
        assert decode_token(token) is None
    assert app.test_client().get("/api/me", headers=_cabecera(token)).status_code == 401


@pytest.mark.parametrize(
    "header,firma",
    [
        pytest.param({"alg": "none", "typ": "JWT"}, b"", id="alg-none"),
        pytest.param({"alg": "RS256", "typ": "JWT"}, b"firma-falsa", id="alg-rs256"),
    ],
)
def test_algoritmos_distintos_de_hs256_responden_401(app_seguridad, header, firma):
    app = app_seguridad
    user_id = _crear_usuario(app)
    payload = json.dumps(_payload_base(user_id), separators=(",", ":")).encode()
    token = _token_crudo(header, payload, firma)

    with app.app_context():
        assert decode_token(token) is None
    assert app.test_client().get("/api/me", headers=_cabecera(token)).status_code == 401


def test_token_manipulado_responde_401(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    with app.app_context():
        token = generate_access_token(user_id, USUARIO, "admin")
    encabezado, contenido, firma = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(contenido + "=" * (-len(contenido) % 4)))
    payload["username"] = "PROBE-alterado"
    contenido_alterado = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    manipulado = f"{encabezado}.{contenido_alterado}.{firma}"

    with app.app_context():
        assert decode_token(manipulado) is None
    assert app.test_client().get("/api/me", headers=_cabecera(manipulado)).status_code == 401


def test_jwt_con_payload_base64_gigante_responde_401_sin_500(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    payload = (
        json.dumps(_payload_base(user_id), separators=(",", ":")).encode()[:-1]
        + b',"padding":"'
        + b"x" * 40_000
        + b'"}'
    )
    token = _token_hs256(app, payload)

    assert len(token.split(".")) == 3
    assert len(token) > MAX_JWT_TOKEN_LENGTH
    respuesta = app.test_client().get("/api/me", headers=_cabecera(token))
    assert respuesta.status_code == 401


def test_jwt_con_payload_anidado_que_causa_recursion_responde_401(app_seguridad):
    app = app_seguridad
    user_id = _crear_usuario(app)
    prefijo = (
        f'{{"user_id":{user_id},"username":"{USUARIO}","role":"admin",'
        f'"type":"access","iat":{int(time.time())},"exp":{int(time.time()) + 300},'
        '"anidado":'
    ).encode()
    payload = prefijo + b"[" * 10_000 + b"0" + b"]" * 10_000 + b"}"
    token = _token_hs256(app, payload)

    assert len(token) < MAX_JWT_TOKEN_LENGTH
    with pytest.raises(RecursionError):
        json.loads(payload)
    respuesta = app.test_client().get("/api/me", headers=_cabecera(token))
    assert respuesta.status_code == 401
