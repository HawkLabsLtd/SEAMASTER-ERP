from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from app_pkg.models import db, User, Resolution, AuthToken, OperationalTask, Project, ProjectTask, AuditLog
from app_pkg.audit import audit
from app_pkg.auth import require_roles, PERMISSIONS

bp = Blueprint('users_bp', __name__)

VALID_ROLES = ('staff', 'manager', 'admin')
ADMIN_ONLY_MSG = 'فقط مدیر سیستم می‌تواند کاربران با نقش ادمین را ایجاد یا ویرایش کند.'

def actor_may_assign(role):
    """Managers may manage staff and managers; only admins may create or edit admins."""
    actor = getattr(g, 'current_user', None)
    return role in VALID_ROLES and (role != 'admin' or (actor is not None and actor.role == 'admin'))

@bp.route('/users')
@require_roles('manager','admin')
def user_list():
    page = 1
    try:
        page = int(request.args.get('page', '1'))
    except Exception:
        page = 1
    per_page = 10
    q = (request.args.get('q') or '').strip()
    query = User.query
    if q:
        query = query.filter(User.name.like(f"%{q}%"))
    users = query.order_by(User.name.asc()).offset((page-1)*per_page).limit(per_page).all()
    return render_template('users/list.html', users=users)

@bp.route('/users/new', methods=['GET', 'POST'])
@require_roles('manager','admin')
def user_new():
    all_projects = Project.query.order_by(Project.id.asc()).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        username = (request.form.get('username') or '').strip().lower() or None
        role = request.form.get('role', 'staff')
        login_enabled = bool(request.form.get('login_enabled'))
        password = (request.form.get('password') or '').strip()

        if not name:
            flash('نام مسئول الزامی است.', 'danger')
            return redirect(url_for('users_bp.user_new'))
        if not actor_may_assign(role):
            flash(ADMIN_ONLY_MSG, 'danger')
            return redirect(url_for('users_bp.user_new'))
        if email and User.query.filter_by(email=email).first():
            flash('این ایمیل قبلاً ثبت شده است.', 'danger')
            return redirect(url_for('users_bp.user_new'))
        if login_enabled and not password:
            flash('برای فعال‌سازی ورود، رمز عبور را وارد کنید.', 'danger')
            return redirect(url_for('users_bp.user_new'))
        if login_enabled and not username:
            flash('برای فعال‌سازی ورود، نام کاربری را وارد کنید.', 'danger')
            return redirect(url_for('users_bp.user_new'))
        if username and User.query.filter_by(username=username).first():
            flash('این نام کاربری قبلاً ثبت شده است.', 'danger')
            return redirect(url_for('users_bp.user_new'))

        perms_list = request.form.getlist('permissions[]')
        perms_dict = {p: True for p in perms_list if p in PERMISSIONS}

        user = User(
            name=name,
            email=email,
            username=username,
            role=role,
            is_active=True,
            is_login_enabled=login_enabled,
            permissions=(__import__('json').dumps(perms_dict) if perms_dict else None)
        )
        db.session.add(user)
        db.session.commit()

        # Handle project assignments
        allowed_proj_ids = [int(x) for x in request.form.getlist('allowed_projects[]') if x.isdigit()]
        if allowed_proj_ids:
            selected_projects = Project.query.filter(Project.id.in_(allowed_proj_ids)).all()
            user.assigned_projects = selected_projects
            db.session.commit()

        if login_enabled and password:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(password)
            db.session.commit()
        audit('user_create', 'user', user.id, f'name={name},email={email or ""},login_enabled={int(login_enabled)}')
        flash(f'مسئول «{user.name}» با موفقیت افزوده شد.', 'success')
        return redirect(url_for('users_bp.user_list'))
    return render_template('users/form.html', user=None, user_perms={}, all_projects=all_projects, user_project_ids=[])

@bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@require_roles('manager', 'admin')
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    if not actor_may_assign(user.role):
        flash(ADMIN_ONLY_MSG, 'danger')
        return redirect(url_for('users_bp.user_list'))
    all_projects = Project.query.order_by(Project.id.asc()).all()
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip() or None
        username = (request.form.get('username') or '').strip().lower() or None
        role = request.form.get('role', user.role or 'staff')
        login_enabled = bool(request.form.get('login_enabled'))
        password = (request.form.get('password') or '').strip()

        if not name:
            flash('نام مسئول الزامی است.', 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))
        if not actor_may_assign(role):
            flash(ADMIN_ONLY_MSG, 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))

        if email and User.query.filter(User.email == email, User.id != user.id).first():
            flash('این ایمیل قبلاً برای کاربر دیگری ثبت شده است.', 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))

        if username and User.query.filter(User.username == username, User.id != user.id).first():
            flash('این نام کاربری قبلاً برای کاربر دیگری ثبت شده است.', 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))

        if login_enabled and not username:
            flash('برای فعال‌سازی ورود، تعیین نام کاربری الزامی است.', 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))

        if login_enabled and not user.password_hash and not password:
            flash('برای فعال‌سازی ورود، تعیین رمز عبور الزامی است.', 'danger')
            return redirect(url_for('users_bp.user_edit', user_id=user.id))

        perms_list = request.form.getlist('permissions[]')
        perms_dict = {p: True for p in perms_list if p in PERMISSIONS}

        user.name = name
        user.email = email
        user.username = username
        user.role = role
        user.is_login_enabled = login_enabled
        user.permissions = __import__('json').dumps(perms_dict) if perms_dict else None

        # Handle project assignments
        allowed_proj_ids = [int(x) for x in request.form.getlist('allowed_projects[]') if x.isdigit()]
        selected_projects = Project.query.filter(Project.id.in_(allowed_proj_ids)).all() if allowed_proj_ids else []
        user.assigned_projects = selected_projects

        if password:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(password)

        db.session.commit()
        audit('user_update', 'user', user.id, f'name={name},username={username},login_enabled={int(login_enabled)}')
        flash(f'اطلاعات و مجوزهای دسترسی «{user.name}» با موفقیت بروزرسانی شد.', 'success')
        return redirect(url_for('users_bp.user_list'))

    user_perms = {}
    if user.permissions:
        try:
            user_perms = __import__('json').loads(user.permissions)
        except Exception:
            user_perms = {}

    user_project_ids = [p.id for p in user.assigned_projects]

    return render_template('users/form.html', user=user, user_perms=user_perms, all_projects=all_projects, user_project_ids=user_project_ids)

def is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

@bp.route('/users/<int:user_id>/delete', methods=['POST'])
@require_roles('admin')
def user_delete(user_id):
    user = User.query.get_or_404(user_id)
    Resolution.query.filter_by(approved_by_user_id=user.id).update({'approved_by_user_id': None}, synchronize_session=False)
    Resolution.query.filter_by(assigned_to_user_id=user.id).update({'assigned_to_user_id': None}, synchronize_session=False)
    OperationalTask.query.filter_by(assigned_to_user_id=user.id).update({'assigned_to_user_id': None}, synchronize_session=False)
    ProjectTask.query.filter_by(assignee_user_id=user.id).update({'assignee_user_id': None}, synchronize_session=False)
    AuditLog.query.filter_by(actor_user_id=user.id).update({'actor_user_id': None}, synchronize_session=False)
    user.assigned_projects = []
    AuthToken.query.filter_by(user_id=user.id).delete()
    db.session.commit()
    db.session.delete(user)
    db.session.commit()
    audit('user_delete', 'user', user_id)
    if is_ajax():
        return jsonify({'status': 'ok', 'user_id': user_id, 'message': 'مسئول با موفقیت حذف شد.'})
    flash('مسئول حذف شد.', 'success')
    return redirect(url_for('users_bp.user_list'))

@bp.route('/users/quick_create', methods=['POST'])
@require_roles('manager', 'admin')
def user_quick_create():
    name = (request.form.get('name') or (request.json.get('name') if request.is_json else '')).strip()
    if not name:
        return jsonify({'status': 'error', 'message': 'نام مسئول الزامی است.'}), 400
    
    # Check if user with this name already exists
    existing = User.query.filter_by(name=name).first()
    if existing:
        return jsonify({
            'status': 'ok',
            'user': {'id': existing.id, 'name': existing.name},
            'message': 'این مسئول از قبل در سامانه موجود بود و انتخاب شد.'
        })
    
    new_user = User(
        name=name,
        role='staff',
        is_active=True,
        is_login_enabled=False
    )
    db.session.add(new_user)
    db.session.commit()
    audit('user_quick_create', 'user', new_user.id, f'name={name}')
    
    return jsonify({
        'status': 'ok',
        'user': {'id': new_user.id, 'name': new_user.name},
        'message': f'مسئول «{new_user.name}» با موفقیت اضافه شد.'
    })
