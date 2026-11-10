from flask import Blueprint, render_template, g
from app_pkg.auth import require_permissions

bp = Blueprint('admin_bp', __name__)

@bp.route('/admin')
@require_permissions('dashboard.view')
def dashboard():
    return render_template('admin_dashboard.html', user=g.current_user)
