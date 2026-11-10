"""Shared fixtures. Every test session runs against a throwaway SQLite file,
never the real instance/seamaster.db."""
import json
import os
import re
import sys

import pytest
from werkzeug.security import generate_password_hash

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TEST_PASSWORD = 'test-pass-123'


@pytest.fixture(scope='session')
def app(tmp_path_factory):
    db_path = tmp_path_factory.mktemp('db') / 'test.db'
    # Set before create_app(); load_dotenv() does not override existing env vars.
    os.environ['DATABASE_URL'] = 'sqlite:///' + db_path.as_posix()
    os.environ['SECRET_KEY'] = 'test-secret'
    os.environ['GEMINI_API_KEY'] = ''
    os.environ.pop('SEAMASTER_ADMIN_PASSWORD', None)

    from app_pkg import create_app
    from app_pkg.db_setup import init_db
    application = create_app()
    application.config['TESTING'] = True
    assert str(db_path.as_posix()) in application.config['SQLALCHEMY_DATABASE_URI']
    with application.app_context():
        init_db()  # schema comes from the migrations, exactly as in deployment
    yield application


@pytest.fixture(scope='session')
def users(app):
    """Test accounts, all with TEST_PASSWORD:
    admin, manager, staff -> every permission (like existing accounts after the upgrade)
    limited               -> staff with only org_chart.view
    noperm                -> staff with no permissions at all
    """
    from app_pkg.auth import PERMISSIONS
    from app_pkg.models import db, User
    everything = json.dumps({k: True for k in PERMISSIONS})
    specs = {
        'admin': ('admin', None),
        'manager': ('manager', everything),
        'staff': ('staff', everything),
        'limited': ('staff', json.dumps({'org_chart.view': True})),
        'noperm': ('staff', None),
    }
    created = {}
    with app.app_context():
        for key, (role, perms) in specs.items():
            u = User(
                name=f'test-{key}',
                email=f'test-{key}@example.test',
                username=f'test-{key}',
                role=role,
                permissions=perms,
                password_hash=generate_password_hash(TEST_PASSWORD),
                is_active=True,
                is_login_enabled=True,
            )
            db.session.add(u)
            db.session.commit()
            created[key] = u.id
    return created


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(app, client, users):
    """login('admin') -> client authenticated as that user via the auth-token cookie."""
    from app_pkg.blueprints.auth import create_auth_token

    def _login(key):
        with app.app_context():
            token, _ = create_auth_token(users[key])
        client.set_cookie('seamaster_auth', token)
        return client
    return _login


def csrf_token(client):
    """A valid CSRF token for this client's session, read from the login page."""
    html = client.get('/login').get_data(as_text=True)
    return re.search(r'<meta name="csrf-token" content="([^"]+)"', html).group(1)


def csrf_headers(client):
    return {'X-CSRFToken': csrf_token(client)}


def post_login(client, ident, password):
    return client.post('/login', data={'email': ident, 'password': password, 'csrf_token': csrf_token(client)})
