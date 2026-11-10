import os
import sqlite3

import pytest
import sqlalchemy as sa

from conftest import TEST_PASSWORD, post_login


@pytest.fixture
def make_app(app, monkeypatch):
    """Build a second app on its own SQLite file (the session `app` must exist first)."""
    from app_pkg import create_app

    def _make(db_path):
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + db_path.as_posix())
        a = create_app()
        a.config['TESTING'] = True
        return a
    return _make


def test_schema_is_current_after_init(app):
    from app_pkg.db_setup import schema_is_current
    with app.app_context():
        assert schema_is_current()


def test_init_db_is_idempotent(app):
    from app_pkg.db_setup import init_db, schema_is_current
    with app.app_context():
        init_db()
        assert schema_is_current()


def test_startup_does_not_touch_the_database(make_app, tmp_path):
    db_file = tmp_path / 'untouched.db'
    make_app(db_file)
    if db_file.exists():
        tables = sqlite3.connect(db_file).execute("select name from sqlite_master where type='table'").fetchall()
        assert tables == []


def test_legacy_database_is_patched_and_stamped(make_app, tmp_path):
    """A pre-migration DB (old user table, no alembic_version) keeps its rows and gains the new columns."""
    from app_pkg.db_setup import init_db, schema_is_current
    db_file = tmp_path / 'legacy.db'
    con = sqlite3.connect(db_file)
    con.execute('CREATE TABLE user (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(120) UNIQUE)')
    con.execute("INSERT INTO user (name, email) VALUES ('old-user', 'old@example.test')")
    con.commit()
    con.close()

    legacy = make_app(db_file)
    with legacy.app_context():
        init_db()
        assert schema_is_current()
        from app_pkg.models import db
        tables = sa.inspect(db.engine).get_table_names()
        cols = {c['name'] for c in sa.inspect(db.engine).get_columns('user')}
        assert {'password_hash', 'role', 'username', 'is_login_enabled', 'permissions'} <= cols
        assert 'project_task' in tables and 'login_attempt' in tables
        row = db.session.execute(sa.text("select name, role from user")).one()
        assert tuple(row) == ('old-user', 'staff')


def test_permission_migration_preserves_access(make_app, tmp_path):
    """Upgrading from the deny-nothing era keeps every user's effective access."""
    import json
    from flask_migrate import upgrade
    from app_pkg.auth import PERMISSIONS
    from app_pkg.db_setup import MIGRATIONS_DIR
    from app_pkg.models import db
    a = make_app(tmp_path / 'perm.db')
    with a.app_context():
        upgrade(directory=MIGRATIONS_DIR, revision='login_attempt')
        db.session.execute(sa.text(
            "INSERT INTO user (name, role, is_active, is_login_enabled, permissions) VALUES "
            "('empty', 'staff', 1, 1, NULL), ('blank', 'staff', 1, 1, '{}'), "
            "('custom', 'staff', 1, 1, '{\"meetings.view\": true}'), "
            "('dash', 'manager', 1, 1, '{\"dashboard.view\": true}'), ('boss', 'admin', 1, 1, NULL)"))
        db.session.commit()
        upgrade(directory=MIGRATIONS_DIR)
        perms = {name: json.loads(p) if p else None for name, p in
                 db.session.execute(sa.text('select name, permissions from user')).all()}
    everything = {k: True for k in PERMISSIONS}
    assert perms['empty'] == everything
    assert perms['blank'] == everything
    assert perms['custom'] == {'meetings.view': True, 'energy.view': True}
    assert perms['dash'] == {'dashboard.view': True, 'energy.view': True, 'hr.view': True,
                             'email.view': True, 'performance.view': True}
    assert perms['boss'] is None  # admins bypass permission checks


def test_secret_key_is_generated_once_and_persisted(tmp_path, monkeypatch):
    from app_pkg.config import load_secret_key
    monkeypatch.delenv('SECRET_KEY', raising=False)
    first = load_secret_key(str(tmp_path))
    assert len(first) >= 32
    assert load_secret_key(str(tmp_path)) == first
    assert (tmp_path / '.secret_key').read_text().strip() == first


def test_secret_key_prefers_environment(tmp_path, monkeypatch):
    from app_pkg.config import load_secret_key
    monkeypatch.setenv('SECRET_KEY', 'from-env')
    assert load_secret_key(str(tmp_path)) == 'from-env'
    assert not (tmp_path / '.secret_key').exists()


def test_default_config_is_production(app):
    assert app.config['DEBUG'] is False


def test_create_admin_command(app):
    runner = app.test_cli_runner()
    result = runner.invoke(args=['create-admin', 'cli-admin'], env={'SEAMASTER_ADMIN_PASSWORD': TEST_PASSWORD})
    assert result.exit_code == 0, result.output
    c = app.test_client()
    post_login(c, 'cli-admin', TEST_PASSWORD)
    assert c.get_cookie('seamaster_auth') is not None
    with app.app_context():
        from app_pkg.models import User
        assert User.query.filter_by(name='cli-admin').one().role == 'admin'


def test_create_admin_rejects_short_password(app):
    result = app.test_cli_runner().invoke(args=['create-admin', 'weak'], env={'SEAMASTER_ADMIN_PASSWORD': 'short'})
    assert result.exit_code != 0
