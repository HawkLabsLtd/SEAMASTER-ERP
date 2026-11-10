"""Authentication and authorization.

- Every request outside PUBLIC_PATHS needs a logged-in user (`login_gate`, a before_request hook).
- Views narrow access further with `require_access(roles=..., perms=...)`, or the shorthands
  `require_roles(...)` / `require_permissions(...)`. Admins always pass.
- Permissions are deny-by-default: a user only has the keys stored in `user.permissions`.
"""
import json
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import request, g, redirect, url_for, flash, jsonify, abort
from app_pkg.models import AuthToken, User, db

# Every permission key the app understands, with its label on the user form.
PERMISSIONS = {
    'dashboard.view': 'مشاهده داشبورد',
    'today.view': 'دستورکار روزانه',
    'meetings.view': 'مشاهده جلسات',
    'meetings.manage': 'مدیریت جلسات',
    'resolutions.view': 'مشاهده مصوبات',
    'resolutions.manage': 'مدیریت مصوبات',
    'tasks.view': 'مشاهده وظایف',
    'tasks.manage': 'مدیریت وظایف',
    'projects.view': 'مشاهده پروژه‌ها',
    'projects.manage': 'مدیریت پروژه‌ها',
    'timeline.view': 'خط زمانی',
    'events.view': 'رویدادها',
    'agreements.view': 'تفاهم‌نامه‌ها',
    'org_chart.view': 'چارت سازمانی',
    'users.manage': 'مدیریت کاربران',
    'hr.view': 'داشبورد منابع انسانی',
    'email.view': 'داشبورد ایمیل',
    'performance.view': 'داشبورد عملکرد وب‌سایت',
    'energy.view': 'داشبورد انرژی',
}

# Where a user lands after login, in priority order: first permission they hold wins.
HOME_PAGES = [
    (('dashboard.view',), 'main_bp.index'),
    (('projects.view', 'projects.manage'), 'projects.index'),
    (('tasks.view', 'tasks.manage'), 'tasks.dashboard'),
    (('meetings.view', 'meetings.manage'), 'meetings_bp.meeting_list'),
    (('resolutions.view', 'resolutions.manage'), 'resolutions_bp.resolutions_list'),
    (('today.view',), 'main_bp.today_view'),
    (('timeline.view',), 'timeline.timeline_page'),
    (('org_chart.view',), 'org_chart.index'),
    (('agreements.view',), 'agreements.index'),
    (('events.view',), 'main_bp.events_calendar'),
    (('performance.view',), 'performance_bp.index'),
    (('email.view',), 'email_dashboard.index'),
    (('hr.view',), 'hr_dashboard.index'),
    (('energy.view',), 'energy_dashboard.index'),
]

PUBLIC_PATHS = {'/login', '/register'}
PUBLIC_PREFIXES = ('/static/', '/favicon.ico')

DENIED_MSG = 'شما اجازه به صفحه مورد نظر را ندارید!'


def safe_next_url(next_url: str):
    try:
        if not next_url:
            return url_for('main_bp.index')
        next_url = next_url.strip()
        p = urlparse(next_url)
        if p.scheme or p.netloc:
            return url_for('main_bp.index')
        if not next_url.startswith('/') or next_url.startswith('//'):
            return url_for('main_bp.index')
        return next_url
    except Exception:
        return url_for('main_bp.index')


def user_from_auth_token(token):
    """Active, login-enabled user for an `seamaster_auth` token, or None. Needs an app context."""
    if not token:
        return None
    at = AuthToken.query.filter_by(token=token).first()
    if not at:
        return None
    if at.expires_at < datetime.utcnow():
        db.session.delete(at)
        db.session.commit()
        return None
    user = db.session.get(User, at.user_id)
    if user and user.is_active and user.is_login_enabled:
        return user
    return None


def get_current_user():
    try:
        user = user_from_auth_token(request.cookies.get('seamaster_auth'))
        if user:
            return user
    except Exception:
        db.session.rollback()

    from flask import session
    uid = session.get('user_id')
    if uid:
        user = db.session.get(User, uid)
        if user and user.is_active and user.is_login_enabled:
            return user
    return None


def parse_permissions(user):
    try:
        if not getattr(user, 'permissions', None):
            return {}
        if isinstance(user.permissions, dict):
            return user.permissions
        return json.loads(user.permissions or '{}')
    except Exception:
        return {}


def has_permission(user, *perms):
    """True if the user is an admin or holds any of `perms`. No stored permissions means none."""
    if not user:
        return False
    if user.role == 'admin':
        return True
    data = parse_permissions(user)
    return any(data.get(p) is True for p in perms)


def get_user_home_url(user):
    if not user:
        return url_for('auth_bp.login')
    for perms, endpoint in HOME_PAGES:
        if has_permission(user, *perms):
            return url_for(endpoint)
    # No page permissions at all: the profile page only needs a login.
    return url_for('auth_bp.profile')


def wants_json():
    return (request.is_json
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            or 'application/json' in request.headers.get('Accept', ''))


def deny(user):
    if wants_json():
        return jsonify({'status': 'error', 'error': 'forbidden', 'message': DENIED_MSG}), 403
    home = get_user_home_url(user)
    if home == request.path:
        abort(403)
    flash(DENIED_MSG, 'danger')
    return redirect(home)


def require_access(roles=(), perms=()):
    """Allow admins, users whose role is in `roles`, and users holding any of `perms`."""
    roles, perms = set(roles), tuple(perms)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = getattr(g, 'current_user', None)
            if user is None:
                return redirect(url_for('auth_bp.login'))
            if user.role == 'admin' or user.role in roles or (perms and has_permission(user, *perms)):
                return fn(*args, **kwargs)
            return deny(user)
        return wrapper
    return decorator


def require_roles(*roles):
    return require_access(roles=roles)


def require_permissions(*perms):
    return require_access(perms=perms)


def login_gate():
    path = request.path or '/'
    if path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES):
        return None
    user = get_current_user()
    g.current_user = user
    if user is None:
        if wants_json():
            return jsonify({'status': 'error', 'error': 'unauthenticated'}), 401
        nxt = safe_next_url(request.full_path if request.query_string else request.path)
        return redirect(url_for('auth_bp.login', next=nxt))
    return None


def register_auth(app):
    app.before_request(login_gate)
