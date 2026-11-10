"""Mounts the Plotly Dash budget dashboard at /dash/budget behind the app's login.

The HR, email and performance dashboards are Flask blueprints now; only the budget
dashboard is still a separate Dash app.
"""
import os
import sys
import importlib.util
from http.cookies import SimpleCookie
from urllib.parse import quote

from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app_pkg.auth import user_from_auth_token

BUDGET_PREFIX = '/dash/budget'


class AuthWSGIMiddleware:
    """Only lets through requests whose seamaster_auth cookie belongs to a user with an allowed role."""

    def __init__(self, flask_app, wsgi_app, login_url='/login', allowed_roles=('admin', 'manager')):
        self.flask_app = flask_app
        self.wsgi_app = wsgi_app
        self.login_url = login_url
        self.allowed_roles = set(allowed_roles)

    def _user(self, environ):
        cookie = SimpleCookie()
        try:
            cookie.load(environ.get('HTTP_COOKIE', ''))
        except Exception:
            return None
        token = cookie['seamaster_auth'].value if 'seamaster_auth' in cookie else None
        if not token:
            return None
        try:
            with self.flask_app.app_context():
                return user_from_auth_token(token)
        except Exception:
            return None

    def __call__(self, environ, start_response):
        user = self._user(environ)
        if user is None or user.role not in self.allowed_roles:
            path = environ.get('SCRIPT_NAME', '') + environ.get('PATH_INFO', '/')
            qs = environ.get('QUERY_STRING', '')
            next_url = path if not qs else f"{path}?{qs}"
            location = f"{self.login_url}?next={quote(next_url)}"
            start_response('302 Found', [('Location', location), ('Content-Type', 'text/html; charset=utf-8')])
            return [b'']
        return self.wsgi_app(environ, start_response)


def mount_dashboards(app):
    # The budget module prints emoji; on a non-UTF-8 console (Windows service, pipes) that
    # raised UnicodeEncodeError and the dashboard silently failed to mount.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='backslashreplace')
        except Exception:
            pass
    try:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        budget_module_path = os.path.join(base_dir, 'dashboards', 'budget', 'plotly_dashboard.py')
        os.environ['BUDGET_DASH_PREFIX'] = BUDGET_PREFIX + '/'
        budget_spec = importlib.util.spec_from_file_location('budget_dash', budget_module_path)
        budget_mod = importlib.util.module_from_spec(budget_spec)
        budget_spec.loader.exec_module(budget_mod)

        app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {
            BUDGET_PREFIX: AuthWSGIMiddleware(app, budget_mod.server),
        })
        app.logger.info('Mounted budget dashboard at %s', BUDGET_PREFIX)
    except Exception as e:
        app.logger.error('Failed to mount budget dashboard: %s', e)
