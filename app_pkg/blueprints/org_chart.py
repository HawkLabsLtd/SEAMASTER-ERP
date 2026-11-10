from flask import Blueprint, render_template, jsonify, current_app
from app_pkg.models import Employee

from app_pkg.auth import require_permissions
bp = Blueprint('org_chart', __name__, url_prefix='/org_chart')

@bp.route('/')
@require_permissions('org_chart.view')
def index():
    return render_template('org_chart/index.html')

@bp.route('/data')
@require_permissions('org_chart.view')
def data():
    employees = Employee.query.all()
    nodes = []
    
    print(f"DEBUG: OrgChart - Found {len(employees)} employees")

    # Define Super Root
    super_root_id = 999999
    nodes.append({
        'id': super_root_id,
        'pid': None,
        'name': current_app.config.get('ORG_NAME', ''),
        'title': "سازمان",
        'unit': "Main",
        'img': "",
        'mobile': ""
    })

    for emp in employees:
        # If no manager, attach to super root
        pid = emp.manager_id
        if pid is None:
            pid = super_root_id
            
        node = {
            'id': emp.id,
            'pid': pid,
            'name': emp.full_name,
            'title': emp.position,
            'unit': emp.unit,
            'img': emp.photo_path,
            'mobile': emp.mobile
        }
        nodes.append(node)
        
    print(f"DEBUG: OrgChart - Returning {len(nodes)} nodes")
    return jsonify(nodes)
