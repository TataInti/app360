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