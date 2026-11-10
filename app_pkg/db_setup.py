"""Database setup and maintenance, exposed as `flask` CLI commands.

None of this runs at app startup any more; deploy scripts call `flask init-db`.

    flask init-db         create / migrate the schema (safe to run repeatedly)
    flask create-admin    create or reset an admin account
    flask ingest-pm       (re)import data/projects/current_pm.xlsx into projects
"""
import os
from getpass import getpass

import click
import sqlalchemy as sa
from flask import current_app
from flask_migrate import Migrate, stamp, upgrade
from werkzeug.security import generate_password_hash

from app_pkg.models import db, User

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'migrations')
migrate = Migrate(directory=MIGRATIONS_DIR, render_as_batch=True)


# --- Pre-Alembic databases -------------------------------------------------
# Databases created before migrations existed were patched in place by these
# ALTERs on every startup. They now run once, before such a DB is stamped at
# the baseline revision.

LEGACY_COLUMNS = {
    'user': {
        'password_hash': 'VARCHAR(255)',
        'role': "VARCHAR(20) DEFAULT 'staff' NOT NULL",
        'is_active': 'BOOLEAN DEFAULT 1 NOT NULL',
        'username': 'VARCHAR(100)',
        'is_login_enabled': 'BOOLEAN DEFAULT 1 NOT NULL',
        'permissions': 'TEXT',
    },
    'employee': {
        'first_name': 'VARCHAR(100)',
        'last_name': 'VARCHAR(100)',
        'location': 'VARCHAR(100)',
        'marital_status': 'VARCHAR(20)',
        'education': 'VARCHAR(50)',
        'birth_date': 'VARCHAR(20)',
        'employment_type': 'VARCHAR(50)',
        'consultant_type': 'VARCHAR(100)',
        'gender': 'VARCHAR(10)',
        'department': 'VARCHAR(200)',
        'contract_type': 'VARCHAR(50)',
        'contract_duration': 'VARCHAR(50)',
    },
}


# Tables that exist at the 'baseline' revision. Tables added by later migrations must NOT be
# created here, or those migrations would fail with "table already exists".
BASELINE_TABLES = (
    'council_meeting', 'employee', 'meeting', 'member_birthday', 'mo_u', 'project', 'user',
    'audit_log', 'auth_token', 'council_resolution', 'operational_task', 'project_members',
    'project_task', 'resolution',
)


def patch_legacy_schema():
    inspector = sa.inspect(db.engine)
    tables = set(inspector.get_table_names())
    with db.engine.begin() as conn:
        for table, columns in LEGACY_COLUMNS.items():
            if table not in tables:
                continue
            existing = {c['name'] for c in inspector.get_columns(table)}
            for col, col_type in columns.items():
                if col not in existing:
                    conn.execute(sa.text(f'ALTER TABLE "{table}" ADD COLUMN {col} {col_type}'))
    baseline = [t for t in db.metadata.sorted_tables if t.name in BASELINE_TABLES]
    db.metadata.create_all(db.engine, tables=baseline)  # baseline tables the old DB never got
    # Indexes declared in models but never created on old DBs (create_all skips existing tables).
    with db.engine.begin() as conn:
        for table in baseline:
            for index in table.indexes:
                index.create(conn, checkfirst=True)
        conn.execute(sa.text('CREATE UNIQUE INDEX IF NOT EXISTS uq_user_username ON "user" (username)'))


def init_db():
    tables = set(sa.inspect(db.engine).get_table_names())
    if 'alembic_version' not in tables and 'user' in tables:
        click.echo('Existing database without migration history: patching and stamping baseline.')
        patch_legacy_schema()
        stamp(directory=MIGRATIONS_DIR, revision='baseline')
    upgrade(directory=MIGRATIONS_DIR)


def schema_is_current():
    """True when the DB is at the latest migration. Used for a startup warning only."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    try:
        with db.engine.connect() as conn:
            if not sa.inspect(conn).has_table('alembic_version'):
                return False
            current = set(conn.execute(sa.text('SELECT version_num FROM alembic_version')).scalars())
        cfg = Config()
        cfg.set_main_option('script_location', MIGRATIONS_DIR)
        return current == set(ScriptDirectory.from_config(cfg).get_heads())
    except Exception:
        return False


def create_admin(name, password, email=None):
    user = User.query.filter((User.name == name) | (User.username == name)).first()
    if user is None:
        user = User(name=name, username=name, email=email)
        db.session.add(user)
    user.password_hash = generate_password_hash(password)
    user.role = 'admin'
    user.is_active = True
    user.is_login_enabled = True
    db.session.commit()
    return user


def register_cli(app):
    migrate.init_app(app, db)

    @app.cli.command('init-db')
    def init_db_command():
        """Create or migrate the database schema."""
        init_db()
        click.echo(f"Database ready: {current_app.config['SQLALCHEMY_DATABASE_URI']}")

    @app.cli.command('create-admin')
    @click.argument('name')
    @click.option('--email', default=None)
    def create_admin_command(name, email):
        """Create NAME as an admin, or reset its password. Reads SEAMASTER_ADMIN_PASSWORD or prompts."""
        password = os.getenv('SEAMASTER_ADMIN_PASSWORD') or getpass(f'Password for {name}: ')
        if len(password) < 8:
            raise click.ClickException('Password must be at least 8 characters.')
        user = create_admin(name, password, email)
        click.echo(f'Admin "{user.name}" (id {user.id}) is ready.')

    @app.cli.command('ingest-pm')
    @click.argument('path', required=False)
    @click.option('--code', help='Project code')
    @click.option('--title', help='Project title')
    @click.option('--manager', help='Project manager / owner')
    def ingest_pm_command(path, code, title, manager):
        """Import or refresh the project plan from an Excel file."""
        from app_pkg.services.pm_ingest import ingest_current_pm
        _, msg = ingest_current_pm(path, code=code, title=title, manager=manager)
        click.echo(msg)
