from flask import Blueprint, render_template, jsonify, request
from app_pkg.models import db, Resolution

from app_pkg.auth import require_permissions, require_roles
bp = Blueprint('kanban', __name__, url_prefix='/kanban')

# Canonical Statuses matching Resolution.status
KANBAN_COLUMNS = {
    'pending': {
        'label': 'در انتظار',
        'aliases': ['pending'],
        'write_value': 'pending'
    },
    'approved': {
        'label': 'تأیید شده', 
        'aliases': ['approved'],
        'write_value': 'approved'
    },
    'in_progress': {
        'label': 'در حال اجرا',
        'aliases': ['in_progress'],
        'write_value': 'in_progress'
    },
    'completed': {
        'label': 'تکمیل شده',
        'aliases': ['completed'],
        'write_value': 'completed'
    }
}

@bp.route('/')
@require_permissions('resolutions.view', 'resolutions.manage', 'tasks.view', 'tasks.manage')
def board():
    resolutions = Resolution.query.all()
    
    # Group resolutions by column
    columns_data = {
        'pending': [],
        'approved': [],
        'in_progress': [],
        'completed': []
    }
    
    for r in resolutions:
        status_str = str(r.status) if r.status else 'pending'
        
        # Simple Logic since we control the status values for this model
        if status_str in columns_data:
            columns_data[status_str].append(r)
        else:
            columns_data['pending'].append(r)

    return render_template('kanban/board.html', columns=KANBAN_COLUMNS, data=columns_data)

@bp.route('/api/update_status', methods=['POST'])
@require_roles('manager', 'admin')
def update_status():
    data = request.json
    item_id = data.get('id')
    new_column = data.get('column') # e.g., 'completed'
    
    if not item_id or new_column not in KANBAN_COLUMNS:
        return jsonify({'error': 'Invalid data'}), 400
        
    resolution = Resolution.query.get(item_id)
    if not resolution:
        return jsonify({'error': 'Item not found'}), 404
        
    resolution.status = KANBAN_COLUMNS[new_column]['write_value']
    
    # Handle progress auto-updates
    if resolution.status == 'completed':
        resolution.progress = 100
    elif resolution.status == 'pending':
        resolution.progress = 0
        
    db.session.commit()
    
    return jsonify({'success': True, 'new_status': resolution.status})
