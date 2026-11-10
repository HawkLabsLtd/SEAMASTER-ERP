from flask import Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
from datetime import date
from app_pkg.models import db, OperationalTask, User, Resolution
from app_pkg.audit import audit
from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.dates_fa import from_farsi_digits, jalali_to_gregorian

bp = Blueprint('tasks', __name__, url_prefix='/tasks')

@bp.route('/')
@require_permissions('tasks.view', 'tasks.manage')
def dashboard():
    # My Tasks: assigned to current user and not completed
    my_tasks = OperationalTask.query.filter_by(
        assigned_to_user_id=g.current_user.id
    ).filter(OperationalTask.status != 'completed').order_by(OperationalTask.due_date.asc()).all()
    
    # All Tasks (for admins/managers or just as a general list)
    # If admin, show all? Or just a separate list.
    # For now, let's pass all recent tasks for the "Overview" section.
    all_tasks = OperationalTask.query.order_by(OperationalTask.created_at.desc()).limit(20).all()
    
    users = User.query.order_by(User.name.asc()).all()
    
    return render_template('tasks/dashboard.html', 
                           my_tasks=my_tasks, 
                           all_tasks=all_tasks, 
                           users=users)

@bp.route('/new', methods=['GET', 'POST'])
@require_roles('manager', 'admin', 'staff')
def new():
    users = User.query.order_by(User.name.asc()).all()
    
    # Pre-fill from query params (e.g. from conversion)
    initial_title = request.args.get('title', '')
    initial_desc = request.args.get('description', '')
    
    if request.method == 'POST':
        title = (request.form.get('title') or '').strip()
        description = (request.form.get('description') or '').strip()
        assigned_to = request.form.get('assigned_to_user_id')
        due_date_str = request.form.get('due_date')
        
        if not title:
            flash('عنوان الزامی است.', 'danger')
            return redirect(url_for('tasks.new'))
            
        task = OperationalTask(title=title, description=description)
        task.assigned_to_user_id = int(assigned_to) if assigned_to else None
        
        if due_date_str:
            try:
                ascii_str = from_farsi_digits(due_date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    task.due_date = date(gy, gm, gd)
            except:
                flash('تاریخ نامعتبر است.', 'warning')
        
        db.session.add(task)
        db.session.commit()
        audit('task_create', 'operation', task.id)
        flash('وظایف جدید ایجاد شد.', 'success')
        return redirect(url_for('tasks.dashboard'))
        
    return render_template('tasks/form.html', users=users, 
                           initial_title=initial_title, 
                           initial_desc=initial_desc)

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@require_roles('manager', 'admin')
def edit(id):
    task = OperationalTask.query.get_or_404(id)
    users = User.query.order_by(User.name.asc()).all()
    
    if request.method == 'POST':
        task.title = request.form.get('title')
        task.description = request.form.get('description')
        assigned = request.form.get('assigned_to_user_id')
        task.assigned_to_user_id = int(assigned) if assigned else None
        
        due_date_str = request.form.get('due_date')
        if due_date_str:
            try:
                ascii_str = from_farsi_digits(due_date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    task.due_date = date(gy, gm, gd)
            except:
                pass
        else:
            task.due_date = None
            
        db.session.commit()
        audit('task_update', 'operation', task.id)
        flash('ویرایش انجام شد.', 'success')
        return redirect(url_for('tasks.dashboard'))
        
    return render_template('tasks/form.html', task=task, users=users)

def is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

@bp.route('/<int:id>/toggle', methods=['POST'])
def toggle(id):
    task = OperationalTask.query.get_or_404(id)
    # Allow assignee or manager/admin
    if g.current_user.role not in ['admin', 'manager'] and task.assigned_to_user_id != g.current_user.id:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'دسترسی غیرمجاز.'}), 403
        flash('دسترسی غیرمجاز', 'danger')
        return redirect(url_for('tasks.dashboard'))
        
    task.status = 'pending' if task.status == 'completed' else 'completed'
    db.session.commit()
    
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'task_id': task.id,
            'task_status': task.status,
            'is_completed': task.status == 'completed',
            'status_label': 'انجام شده' if task.status == 'completed' else 'در انتظار',
            'message': 'وضعیت وظیفه با موفقیت تغییر یافت.'
        })
    return redirect(request.referrer or url_for('tasks.dashboard'))

@bp.route('/<int:id>/delete', methods=['POST'])
@require_roles('manager', 'admin')
def delete(id):
    task = OperationalTask.query.get_or_404(id)
    task_id = task.id
    db.session.delete(task)
    db.session.commit()
    audit('task_delete', 'operation', task_id)
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'task_id': task_id,
            'message': 'وظیفه با موفقیت حذف شد.'
        })
    flash('حذف شد.', 'success')
    return redirect(url_for('tasks.dashboard'))

@bp.route('/convert/<int:res_id>')
@require_roles('manager', 'admin')
def convert_resolution(res_id):
    res = Resolution.query.get_or_404(res_id)
    # Redirect to creation form with pre-filled data
    return redirect(url_for('tasks.new', title=res.title, description=res.description))
