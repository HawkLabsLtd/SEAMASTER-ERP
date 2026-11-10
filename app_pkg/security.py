import os

from flask import request, g, flash, redirect, jsonify
from flask_wtf.csrf import CSRFProtect, CSRFError, generate_csrf
from werkzeug.middleware.proxy_fix import ProxyFix

csrf = CSRFProtect()


def request_is_https():
    return request.is_secure  # correct behind nginx thanks to ProxyFix(x_proto=1)


def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    csp_parts = [
        "default-src 'self';",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net;",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net;",
        "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net data:;",
        "img-src 'self' data:;",
        "object-src 'none';",
        "base-uri 'self';",
        "form-action 'self';",
        "frame-ancestors 'self';",
    ]
    if request_is_https():
        csp_parts.append("upgrade-insecure-requests;")
    response.headers['Content-Security-Policy'] = ' '.join(csp_parts)
    return response


def expose_csrf_cookie(response):
    """Mirror the page's CSRF token into a JS-readable cookie for scripts that read it from there."""
    token = g.get('csrf_token')
    if token:
        response.set_cookie('csrf_token', token, path='/', samesite='Lax', secure=request_is_https())
    return response


def handle_csrf_error(e):
    from app_pkg.auth import wants_json
    if wants_json():
        return jsonify({'status': 'error', 'error': 'csrf', 'message': 'نشست منقضی شده است. صفحه را دوباره بارگذاری کنید.'}), 400
    flash('نشست منقضی شده است. لطفاً دوباره تلاش کنید.', 'danger')
    return redirect(request.referrer or request.path)


def register_security(app):
    app.config.setdefault('WTF_CSRF_TIME_LIMIT', None)  # valid for the whole session, not 1 hour
    csrf.init_app(app)
    app.register_error_handler(CSRFError, handle_csrf_error)
    app.after_request(add_security_headers)
    app.after_request(expose_csrf_cookie)

    @app.context_processor
    def inject_csrf_token():
        return {'csrf_token': generate_csrf()}


def apply_proxy_fix(app):
    """Trust X-Forwarded-For/-Proto from TRUSTED_PROXY_COUNT reverse proxies (nginx = 1; 0 = none)."""
    hops = int(os.getenv('TRUSTED_PROXY_COUNT', '1') or 0)
    if hops > 0:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops)
