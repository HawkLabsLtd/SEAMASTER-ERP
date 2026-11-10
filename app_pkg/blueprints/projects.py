from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g
from app_pkg.models import db, Project, ProjectTask, User
from app_pkg.audit import audit
from app_pkg.auth import require_roles, require_permissions, wants_json
from app_pkg.services.pm_ingest import ingest_current_pm
from app_pkg.services.projects import (
    GANTT_WEEKS, STATUSES, STATUS_LABELS, AllProjectsView, accessible_projects, assignee_name_for,
    assignee_workload, can_access_project, ensure_default_project, kpi_payload, next_wbs,
    reconcile_progress_and_status, refresh_project_progress, set_progress, set_status,
    task_counts, to_int, unique_project_code, wbs_sort_key,
)

bp = Blueprint('projects', __name__, url_prefix='/projects')

NO_PROJECT_ACCESS_MSG = 'شما به این پروژه دسترسی ندارید.'


def request_data():
    """The submitted fields, whether the client sent JSON or a form."""
    return (request.get_json(silent=True) or {}) if request.is_json else request.form


def text(data, key, default=''):
    """Stripped string field; `default` when missing or null."""
    value = data.get(key)
    if value is None:
        value = default if default is not None else ''
    return str(value).strip()


def no_project_access():
    if wants_json():
        return jsonify({'status': 'error', 'message': NO_PROJECT_ACCESS_MSG}), 403
    flash(NO_PROJECT_ACCESS_MSG, 'danger')
    return redirect(url_for('projects.index'))


def accessible_task_or_deny(task_id):
    """(task, None) if the current user may work on the task, else (None, error response)."""
    task = ProjectTask.query.get_or_404(task_id)
    if not can_access_project(g.current_user, task.project):
        return None, no_project_access()
    return task, None


# -------------------------------------------------------------------------
# Dashboard
# -------------------------------------------------------------------------

@bp.route('/')
@require_permissions('projects.view', 'projects.manage')
def index():
    user = g.current_user
    all_projects = accessible_projects(user)

    if not all_projects and user.role != 'admin':
        return render_template('projects/dashboard.html', project=None, all_projects=[], tasks=[], kpis=None,
                               users=[], is_all_projects=False, no_access=True, project_member_ids=[])
    if not all_projects:
        all_projects = [ensure_default_project()]

    project_id_raw = request.args.get('project_id')
    is_all_projects = project_id_raw == 'all'
    if is_all_projects:
        ids = [p.id for p in all_projects]
        tasks = ProjectTask.query.filter(ProjectTask.project_id.in_(ids)).all()
        project = AllProjectsView(all_projects, tasks)
    else:
        project = all_projects[0]
        requested = db.session.get(Project, to_int(project_id_raw)) if project_id_raw else None
        if project_id_raw:
            if requested and can_access_project(user, requested):
                project = requested
            else:
                flash('شما اجازه دسترسی به این پروژه را ندارید یا پروژه یافت نشد.', 'warning')
        tasks = project.tasks

    tasks = sorted(tasks, key=wbs_sort_key)
    counts = task_counts(tasks)
    kpis = {
        'total_tasks': counts['total'],
        'completed_tasks': counts['completed'],
        'in_progress_tasks': counts['in_progress'],
        'pending_tasks': counts['pending'],
        'delayed_tasks': counts['delayed'],
        'project_progress': project.progress or 0,
        'assignee_counts': assignee_workload(tasks),
        'weeks': GANTT_WEEKS,
        'is_all_projects': is_all_projects,
    }
    return render_template(
        'projects/dashboard.html',
        project=project,
        all_projects=all_projects,
        tasks=tasks,
        kpis=kpis,
        users=User.query.filter_by(is_active=True).order_by(User.name.asc()).all(),
        project_member_ids=[u.id for u in project.members],
        is_all_projects=is_all_projects,
        no_access=False,
    )


# -------------------------------------------------------------------------
# Project CRUD & Access Management
# -------------------------------------------------------------------------

@bp.route('/new', methods=['POST'])
@require_permissions('projects.manage')
def project_new():
    user = g.current_user
    title = request.form.get('title', '').strip()
    if not title:
        flash('عنوان پروژه الزامی است.', 'danger')
        return redirect(url_for('projects.index'))

    proj = Project(
        title=title,
        code=unique_project_code(request.form.get('code', '').strip()),
        manager_name=request.form.get('manager_name', '').strip() or None,
        start_date_shamsi=request.form.get('start_date_shamsi', '').strip() or '1404/01/01',
        end_date_shamsi=request.form.get('end_date_shamsi', '').strip() or '1404/12/29',
        description=request.form.get('description', '').strip() or None,
        status='in_progress',
        progress=0,
    )
    if user.role != 'admin':
        proj.members.append(user)  # creators can see what they made
    db.session.add(proj)
    db.session.commit()
    audit('project_create', 'project', proj.id, f'title={proj.title}')
    flash(f'پروژه جدید «{proj.title}» با موفقیت ایجاد شد.', 'success')
    return redirect(url_for('projects.index', project_id=proj.id))


@bp.route('/<int:project_id>/edit', methods=['POST'])
@require_permissions('projects.manage')
def project_edit(project_id):
    user = g.current_user
    proj = Project.query.get_or_404(project_id)
    if not can_access_project(user, proj):
        flash('شما دسترسی لازم برای ویرایش این پروژه را ندارید.', 'danger')
        return redirect(url_for('projects.index'))

    form = request.form
    proj.title = text(form, 'title', proj.title) or proj.title
    new_code = text(form, 'code', proj.code or '')
    if new_code and new_code != proj.code:
        if Project.query.filter(Project.code == new_code, Project.id != proj.id).first():
            flash(f'کد پروژه «{new_code}» قبلاً برای پروژه دیگری استفاده شده است.', 'warning')
        else:
            proj.code = new_code
    proj.manager_name = text(form, 'manager_name', proj.manager_name or '')
    proj.start_date_shamsi = text(form, 'start_date_shamsi', proj.start_date_shamsi or '')
    proj.end_date_shamsi = text(form, 'end_date_shamsi', proj.end_date_shamsi or '')
    proj.description = text(form, 'description', proj.description or '')
    proj.status = text(form, 'status', proj.status) or proj.status

    if user.role == 'admin' and 'member_ids_submitted' in form:
        member_ids = [int(x) for x in form.getlist('member_ids[]') if x.isdigit()]
        proj.members = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []

    db.session.commit()
    audit('project_edit', 'project', proj.id, f'title={proj.title}')
    flash('مشخصات پروژه با موفقیت ویرایش شد.', 'success')
    return redirect(url_for('projects.index', project_id=proj.id))


@bp.route('/<int:project_id>/access', methods=['POST'])
@require_roles('admin')
def project_access_update(project_id):
    proj = Project.query.get_or_404(project_id)
    if request.is_json:
        member_ids = [to_int(x) for x in (request.get_json(silent=True) or {}).get('member_ids', [])]
    else:
        member_ids = [int(x) for x in request.form.getlist('member_ids[]') if str(x).isdigit()]
    proj.members = User.query.filter(User.id.in_(member_ids)).all() if member_ids else []
    db.session.commit()
    audit('project_access_update', 'project', proj.id, f'members_count={len(proj.members)}')

    message = 'دسترسی اعضای پروژه با موفقیت بروزرسانی شد.'
    if wants_json():
        return jsonify({'status': 'ok', 'message': message, 'members_count': len(proj.members)})
    flash(message, 'success')
    return redirect(url_for('projects.index', project_id=proj.id))


@bp.route('/<int:project_id>/delete', methods=['POST'])
@require_roles('admin')
def project_delete(project_id):
    proj = Project.query.get_or_404(project_id)
    title = proj.title
    next_proj = Project.query.filter(Project.id != project_id).order_by(Project.id.desc()).first()
    db.session.delete(proj)
    db.session.commit()
    audit('project_delete', 'project', project_id, f'title={title}')
    flash(f'پروژه «{title}» و کلیه فعالیت‌های آن با موفقیت حذف شدند.', 'success')
    return redirect(url_for('projects.index', project_id=next_proj.id) if next_proj else url_for('projects.index'))


@bp.route('/reimport', methods=['POST'])
@require_permissions('projects.manage')
def reimport():
    project, msg = ingest_current_pm()
    if project:
        flash(f'همگام‌سازی اکسل با موفقیت انجام شد ({msg}).', 'success')
        return redirect(url_for('projects.index', project_id=project.id))
    flash(f'خطا در همگام‌سازی: {msg}', 'danger')
    return redirect(url_for('projects.index'))


# -------------------------------------------------------------------------
# Task CRUD & AJAX APIs (access is per project: admins, members, managers, assignees)
# -------------------------------------------------------------------------

@bp.route('/tasks/new', methods=['POST'])
@require_permissions('projects.view', 'projects.manage')
def task_new():
    data = request_data()
    project = Project.query.get_or_404(to_int(data.get('project_id'), 1))
    if not can_access_project(g.current_user, project):
        return no_project_access()

    title = text(data, 'title')
    if not title:
        if wants_json():
            return jsonify({'status': 'error', 'message': 'عنوان فعالیت الزامی است.'}), 400
        flash('عنوان فعالیت الزامی است.', 'danger')
        return redirect(url_for('projects.index', project_id=project.id))

    assignee_user_id = to_int(data.get('assignee_user_id'), None) or None
    task = ProjectTask(
        project_id=project.id,
        wbs=text(data, 'wbs') or next_wbs(project),
        title=title,
        assignee_name=text(data, 'assignee_name') or assignee_name_for(assignee_user_id),
        assignee_user_id=assignee_user_id,
        start_date_shamsi=text(data, 'start_date_shamsi') or project.start_date_shamsi,
        end_date_shamsi=text(data, 'end_date_shamsi') or project.end_date_shamsi,
        duration_days=to_int(data.get('duration_days'), 1) or 1,
        predecessor=text(data, 'predecessor') or None,
        notes=text(data, 'notes') or None,
        progress=0,
        status='pending',
    )
    db.session.add(task)
    db.session.flush()
    db.session.expire(project, ['tasks'])
    refresh_project_progress(project)
    db.session.commit()
    audit('project_task_create', 'project_task', task.id, f'wbs={task.wbs},title={task.title}')

    message = f'فعالیت جدید «{task.title}» با کد WBS {task.wbs} افزوده شد.'
    if wants_json():
        return jsonify({
            'status': 'ok',
            'message': message,
            'task_id': task.id,
            'wbs': task.wbs,
            'title': task.title,
            'assignee_name': task.assignee_name or 'تعیین نشده',
            'start_date_shamsi': task.start_date_shamsi,
            'end_date_shamsi': task.end_date_shamsi,
            'duration_days': task.duration_days,
            'progress': task.progress,
            'status_code': task.status,
            'project_progress': project.progress,
            'kpis': kpi_payload(project),
        })
    flash(message, 'success')
    return redirect(url_for('projects.index', project_id=project.id))


@bp.route('/tasks/<int:task_id>/json', methods=['GET'])
@require_permissions('projects.view', 'projects.manage')
def task_json(task_id):
    task, denied = accessible_task_or_deny(task_id)
    if denied:
        return denied
    return jsonify({
        'status': 'ok',
        'id': task.id,
        'project_id': task.project_id,
        'wbs': task.wbs,
        'title': task.title,
        'assignee_name': task.assignee_name or '',
        'assignee_user_id': task.assignee_user_id,
        'start_date_shamsi': task.start_date_shamsi or '',
        'end_date_shamsi': task.end_date_shamsi or '',
        'duration_days': task.duration_days or 1,
        'progress': task.progress,
        'task_status': task.status,
        'predecessor': task.predecessor or '',
        'notes': task.notes or '',
    })


@bp.route('/tasks/<int:task_id>/edit', methods=['POST'])
@require_permissions('projects.view', 'projects.manage')
def task_edit(task_id):
    task, denied = accessible_task_or_deny(task_id)
    if denied:
        return denied

    data = request_data()
    task.title = text(data, 'title', task.title) or task.title
    task.wbs = text(data, 'wbs', task.wbs) or task.wbs
    task.assignee_name = text(data, 'assignee_name', task.assignee_name or '') or None
    task.start_date_shamsi = text(data, 'start_date_shamsi', task.start_date_shamsi or '')
    task.end_date_shamsi = text(data, 'end_date_shamsi', task.end_date_shamsi or '')
    task.duration_days = to_int(data.get('duration_days', task.duration_days), 1) or 1
    task.predecessor = text(data, 'predecessor', task.predecessor or '') or None
    task.notes = text(data, 'notes', task.notes or '') or None
    if 'progress' in data:
        task.progress = max(0, min(100, to_int(data.get('progress'))))
    if data.get('status') in STATUSES:
        task.status = data.get('status')
    reconcile_progress_and_status(task)
    refresh_project_progress(task.project)
    db.session.commit()
    audit('project_task_edit', 'project_task', task.id, f'wbs={task.wbs},title={task.title}')

    if wants_json():
        return jsonify({
            'status': 'ok',
            'message': 'اطلاعات فعالیت با موفقیت ویرایش شد.',
            'task_id': task.id,
            'wbs': task.wbs,
            'title': task.title,
            'assignee_name': task.assignee_name or 'تعیین نشده',
            'start_date_shamsi': task.start_date_shamsi,
            'end_date_shamsi': task.end_date_shamsi,
            'duration_days': task.duration_days,
            'progress': task.progress,
            'task_status': task.status,
            'notes': task.notes or '',
            'predecessor': task.predecessor or '',
            'project_progress': task.project.progress,
            'kpis': kpi_payload(task.project),
        })
    flash('اطلاعات فعالیت با موفقیت به‌روزرسانی شد.', 'success')
    return redirect(url_for('projects.index', project_id=task.project_id))


@bp.route('/tasks/<int:task_id>/delete', methods=['POST'])
@require_permissions('projects.view', 'projects.manage')
def task_delete(task_id):
    task, denied = accessible_task_or_deny(task_id)
    if denied:
        return denied
    project, title, wbs = task.project, task.title, task.wbs
    db.session.delete(task)
    db.session.flush()
    db.session.expire(project, ['tasks'])
    refresh_project_progress(project)
    db.session.commit()
    audit('project_task_delete', 'project_task', task_id, f'wbs={wbs},title={title}')

    if wants_json():
        return jsonify({
            'status': 'ok',
            'message': f'فعالیت {wbs} ({title}) با موفقیت حذف شد.',
            'project_progress': project.progress,
            'kpis': kpi_payload(project),
        })
    flash(f'فعالیت {wbs} با موفقیت حذف شد.', 'success')
    return redirect(url_for('projects.index', project_id=project.id))


@bp.route('/tasks/<int:task_id>/progress', methods=['POST'])
@require_permissions('projects.view', 'projects.manage')
def task_update_progress(task_id):
    task, denied = accessible_task_or_deny(task_id)
    if denied:
        return denied
    set_progress(task, request_data().get('progress', 0))
    refresh_project_progress(task.project)
    db.session.commit()
    audit('project_task_progress', 'project_task', task.id, f'wbs={task.wbs},prog={task.progress}')

    if wants_json():
        return jsonify({
            'status': 'ok',
            'task_id': task.id,
            'task_progress': task.progress,
            'task_status': task.status,
            'project_progress': task.project.progress,
            'kpis': kpi_payload(task.project),
            'message': f'پیشرفت فعالیت {task.wbs} به {task.progress}٪ تغییر یافت.',
        })
    flash('پیشرفت فعالیت به‌روزرسانی شد.', 'success')
    return redirect(url_for('projects.index', project_id=task.project_id))


@bp.route('/tasks/<int:task_id>/status', methods=['POST'])
@require_permissions('projects.view', 'projects.manage')
def task_update_status(task_id):
    task, denied = accessible_task_or_deny(task_id)
    if denied:
        return denied
    if set_status(task, request_data().get('status', 'pending')):
        refresh_project_progress(task.project)
        db.session.commit()
        audit('project_task_status', 'project_task', task.id, f'wbs={task.wbs},status={task.status}')

    if wants_json():
        return jsonify({
            'status': 'ok',
            'task_id': task.id,
            'task_status': task.status,
            'task_progress': task.progress,
            'project_progress': task.project.progress,
            'kpis': kpi_payload(task.project),
            'message': f'وضعیت فعالیت به «{STATUS_LABELS.get(task.status, task.status)}» تغییر یافت.',
        })
    flash('وضعیت فعالیت تغییر کرد.', 'success')
    return redirect(url_for('projects.index', project_id=task.project_id))
