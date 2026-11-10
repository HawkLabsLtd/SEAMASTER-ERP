import os
import sqlite3
from flask import Flask
from datetime import datetime
from app_pkg.models import db
from app_pkg.auth import register_auth
from app_pkg.security import register_security, apply_proxy_fix
from app_pkg.blueprints.main import bp as main_bp
from app_pkg.blueprints.meetings import bp as meetings_bp
from app_pkg.blueprints.resolutions import bp as resolutions_bp
from app_pkg.blueprints.users import bp as users_bp
from app_pkg.blueprints.auth import bp as auth_bp
from app_pkg.blueprints.seed import bp as seed_bp
from app_pkg.db_setup import register_cli, schema_is_current
from app_pkg.dash_mount import mount_dashboards
from app_pkg.utils.dates_fa import (
    to_farsi_digits,
    format_jalali_datetime,
    format_jalali_date_any,
    format_jalali_weekday_dm,
    format_jalali_dmy,
    format_jalali_ymd,
)
from app_pkg.utils.status import status_label_fa
from app_pkg.services.notifications import get_user_notifications

def create_app():
    from dotenv import load_dotenv
    load_dotenv()  # Load .env before any config
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    templates_dir = os.path.join(base_dir, 'templates')
    static_dir = os.path.join(base_dir, 'static')
    instance_dir = os.path.join(base_dir, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    from app_pkg.paths import ensure_data_dirs
    ensure_data_dirs()
    app = Flask(__name__, template_folder=templates_dir, static_folder=static_dir)
    # Load Config
    from app_pkg.config import config, load_secret_key
    conf = config.get(os.getenv('FLASK_ENV') or 'default', config['default'])
    app.config.from_object(conf)
    app.config['SECRET_KEY'] = load_secret_key(instance_dir)

    # Database Setup
    base_dir = os.path.dirname(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = conf.get_db_uri(base_dir)

    # app.config['SQLALCHEMY_BINDS'] removed for PostgreSQL migration

    app.config['ALLOW_SELF_REGISTRATION'] = (os.getenv('ALLOW_SELF_REGISTRATION') or '0') == '1'
    app.jinja_env.autoescape = True

    # Configure SQLite PRAGMAs for high concurrency (WAL mode, busy timeout)
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, sqlite3.Connection):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.execute("PRAGMA busy_timeout=5000")
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()
            except Exception:
                pass

    db.init_app(app)
    register_cli(app)
    if not app.config.get('TESTING'):
        with app.app_context():
            if not schema_is_current():
                app.logger.warning('Database schema is missing or out of date; run `flask --app app init-db`.')
    register_auth(app)
    register_security(app)
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(meetings_bp)
    app.register_blueprint(resolutions_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(seed_bp)
    from app_pkg.blueprints.admin import bp as admin_bp
    app.register_blueprint(admin_bp)
    from app_pkg.blueprints.agreements import bp as agreements_bp
    app.register_blueprint(agreements_bp)
    from app_pkg.blueprints.members import bp as members_bp
    app.register_blueprint(members_bp)
    from app_pkg.blueprints.timeline import bp as timeline_bp
    app.register_blueprint(timeline_bp)
    from app_pkg.blueprints.ai import bp as ai_bp
    app.register_blueprint(ai_bp)

    from app_pkg.blueprints.kanban import bp as kanban_bp
    app.register_blueprint(kanban_bp)

    from app_pkg.blueprints.tasks import bp as tasks_bp
    app.register_blueprint(tasks_bp)

    from app_pkg.blueprints.org_chart import bp as org_chart_bp
    app.register_blueprint(org_chart_bp)

    from app_pkg.blueprints.performance import bp as performance_bp
    app.register_blueprint(performance_bp)

    from app_pkg.blueprints.email_dashboard import bp as email_dashboard_bp
    app.register_blueprint(email_dashboard_bp)

    from app_pkg.blueprints.hr_dashboard import bp as hr_dashboard_bp
    app.register_blueprint(hr_dashboard_bp)

    from app_pkg.blueprints.projects import bp as projects_bp
    app.register_blueprint(projects_bp)

    from app_pkg.blueprints.energy_dashboard import bp as energy_dashboard_bp
    app.register_blueprint(energy_dashboard_bp)



    mount_dashboards(app)
    apply_proxy_fix(app)  # outermost WSGI layer, so mounted dashboards see real client info too
    @app.context_processor
    def inject_context():
        from flask import g
        from app_pkg.auth import has_permission, parse_permissions
        u = getattr(g, 'current_user', None)
        return {
            'now': datetime.utcnow(),
            'org_name': app.config.get('ORG_NAME', ''),
            'app_title': app.config.get('APP_TITLE', ''),
            'to_farsi_digits': to_farsi_digits,
            'format_jalali_datetime': format_jalali_datetime,
            'format_jalali_date_any': format_jalali_date_any,
            'format_jalali_weekday_dm': format_jalali_weekday_dm,
            'format_jalali_dmy': format_jalali_dmy,
            'format_jalali_ymd': format_jalali_ymd,
            'current_user': u,
            'has_perm': lambda *perms: has_permission(u, *perms) if u else False,
            'user_perms': parse_permissions(u) if u else {},
            'status_label_fa': status_label_fa,
            # Notifications
            'notifications': get_user_notifications(u),
        }
    
    # Support for subdirectory deployment (e.g., /new)
    # Set APPLICATION_ROOT environment variable to deploy under a prefix
    application_root = os.getenv('APPLICATION_ROOT', '')
    if application_root:
        app.config['APPLICATION_ROOT'] = application_root
        # Update session cookie path to work with the prefix
        app.config['SESSION_COOKIE_PATH'] = application_root
    
    return app
