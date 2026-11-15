import pytest

from app import auth, main

# Tests written before accounts existed act as one signed-in organizer/admin.
# Authentication and role behaviour is covered with real sessions in test_auth.py.
TEST_USER = auth.User('test-user', 'tester@example.com', 'Test Organizer', 'organizer', True)


@pytest.fixture(autouse=True)
def signed_in(request):
    if 'real_auth' in request.keywords:
        yield
        return
    main.app.dependency_overrides[auth.principal] = lambda: TEST_USER
    yield
    main.app.dependency_overrides.pop(auth.principal, None)


def pytest_configure(config):
    config.addinivalue_line('markers', 'real_auth: use real sessions instead of the default test user')
