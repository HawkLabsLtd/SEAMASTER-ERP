from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from datetime import datetime, date
from app_pkg.models import db, Resolution, Meeting, User
from app_pkg.audit import audit
from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.dates_fa import from_farsi_digits, jalali_to_gregorian, format_jalali_date_any, to_farsi_digits
from app_pkg.utils.status import status_label_fa

bp = Blueprint('resolutions_bp', __name__)

def is_ajax():
    return (request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 
            request.is_json or 
            request.args.get('ajax') == '1' or 
            request.form.get('ajax') == '1' or
            'application/json' in request.headers.get('Accept', ''))

@bp.route('/resolutions/<int:res_id>/approve', methods=['POST'])
@require_roles('manager','admin')
def resolution_approve(res_id):
    res = Resolution.query.get_or_404(res_id)
    approver_id = request.form.get('approved_by_user_id')
    res.status = 'approved'
    res.approved_at = datetime.utcnow()
    res.approved_by_user_id = int(approver_id) if approver_id else None
    db.session.commit()
    audit('resolution_approve', 'resolution', res_id, f'approved_by={approver_id or ""}')
    if is_ajax():
        return jsonify({'status': 'ok', 'res_status': res.status, 'status_label': status_label_fa(res.status), 'message': 'مصوبه تأیید شد.'})
    flash('مصوبه تأیید شد.', 'info')
    return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))

@bp.route('/resolutions/<int:res_id>/assign', methods=['POST'])
@require_roles('manager','admin')
def resolution_assign(res_id):
    res = Resolution.query.get_or_404(res_id)
    assignee_id = request.form.get('assigned_to_user_id')
    due_date_str = request.form.get('due_date')
    res.assigned_to_user_id = int(assignee_id) if assignee_id else None
    if due_date_str:
        try:
            ascii_str = from_farsi_digits(due_date_str)
            parts = ascii_str.split('-')
            if len(parts) == 3:
                jy, jm, jd = map(int, parts)
                gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                res.due_date = date(gy, gm, gd)
            else:
                raise ValueError()
        except Exception:
            if is_ajax():
                return jsonify({'status': 'error', 'message': 'فرمت تاریخ سررسید شمسی نامعتبر است.'}), 400
            flash('فرمت تاریخ سررسید شمسی نامعتبر است.', 'danger')
            return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))
    if res.status == 'pending':
        res.status = 'in_progress' if res.assigned_to_user_id else 'approved'
    db.session.commit()
    audit('resolution_assign', 'resolution', res_id, f'assigned_to={assignee_id or ""}')
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'assigned_to': res.assigned_to.name if res.assigned_to else 'تعیین نشده',
            'due_date': format_jalali_date_any(res.due_date) if res.due_date else 'تعیین نشده',
            'res_status': res.status,
            'status_label': status_label_fa(res.status),
            'message': 'مصوبه واگذار شد.'
        })
    flash('مصوبه واگذار شد.', 'success')
    return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))

@bp.route('/resolutions/<int:res_id>/progress', methods=['POST'])
@require_roles('manager','admin')
def resolution_progress(res_id):
    res = Resolution.query.get_or_404(res_id)
    try:
        progress = int(request.form.get('progress', '0'))
        progress = max(0, min(100, progress))
    except ValueError:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'پیشرفت باید عددی بین ۰ تا ۱۰۰ باشد.'}), 400
        flash('پیشرفت باید عددی بین ۰ تا ۱۰۰ باشد.', 'danger')
        return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))
    res.progress = progress
    if progress >= 100:
        res.status = 'completed'
    elif res.status == 'approved':
        res.status = 'in_progress'
    db.session.commit()
    audit('resolution_progress', 'resolution', res_id, f'progress={res.progress}')
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'progress': res.progress,
            'progress_farsi': to_farsi_digits(res.progress),
            'res_status': res.status,
            'status_label': status_label_fa(res.status),
            'message': 'پیشرفت به‌روزرسانی شد.'
        })
    flash('پیشرفت به‌روزرسانی شد.', 'success')
    return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))

@bp.route('/resolutions/<int:res_id>/complete', methods=['POST'])
@require_roles('manager','admin')
def resolution_complete(res_id):
    res = Resolution.query.get_or_404(res_id)
    res.status = 'completed'
    res.progress = 100
    db.session.commit()
    audit('resolution_complete', 'resolution', res_id)
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'progress': 100,
            'progress_farsi': to_farsi_digits(100),
            'res_status': 'completed',
            'status_label': status_label_fa('completed'),
            'message': 'مصوبه تکمیل شد.'
        })
    flash('مصوبه تکمیل شد.', 'success')
    return redirect(url_for('meetings_bp.meeting_detail', meeting_id=res.meeting_id))

@bp.route('/resolutions')
@require_permissions('resolutions.view', 'resolutions.manage')
def resolutions_list():
    page = 1
    try:
        page = int(request.args.get('page', '1'))
    except Exception:
        page = 1
    try:
        per_page = int(request.args.get('per_page', '10'))
    except Exception:
        per_page = 10
    per_page = max(5, min(200, per_page))
    q = (request.args.get('q') or '').strip()
    status = (request.args.get('status') or '').strip()
    query = Resolution.query
    if q:
        query = query.filter(Resolution.title.like(f"%{q}%"))
    if status in ['pending','approved','in_progress','completed']:
        query = query.filter(Resolution.status == status)
    total_count = query.count()
    resolutions = query.order_by(Resolution.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    has_prev = page > 1
    has_next = (page * per_page) < total_count
    users = User.query.all()
    return render_template('resolutions/list.html',
                           resolutions=resolutions,
                           users=users,
                           page=page,
                           per_page=per_page,
                           total_count=total_count,
                           has_prev=has_prev,
                           has_next=has_next,
                           status=status,
                           q=q)

@bp.route('/resolutions/new', methods=['GET', 'POST'])
@require_roles('manager','admin')
def resolutions_new():
    meetings = Meeting.query.order_by(Meeting.scheduled_at.desc()).all()
    users = User.query.order_by(User.name.asc()).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        meeting_id = request.form.get('meeting_id')
        assigned_to_user_id = request.form.get('assigned_to_user_id')
        due_date_str = request.form.get('due_date')
        status = request.form.get('status', 'pending')
        progress_str = request.form.get('progress', '0')
        if not title:
            flash('عنوان مصوبه الزامی است.', 'danger')
            return redirect(url_for('resolutions_bp.resolutions_new'))
        if not meeting_id:
            flash('انتخاب جلسه الزامی است.', 'danger')
            return redirect(url_for('resolutions_bp.resolutions_new'))
        res = Resolution(
            meeting_id=int(meeting_id),
            title=title,
            description=description,
            status=status if status in ['pending','approved','in_progress','completed'] else 'pending',
        )
        if assigned_to_user_id:
            res.assigned_to_user_id = int(assigned_to_user_id)
            if res.status == 'pending':
                res.status = 'in_progress'
        if due_date_str:
            try:
                ascii_str = from_farsi_digits(due_date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    res.due_date = date(gy, gm, gd)
                else:
                    raise ValueError()
            except Exception:
                flash('فرمت تاریخ سررسید شمسی نامعتبر است.', 'danger')
                return redirect(url_for('resolutions_bp.resolutions_new'))
        try:
            progress = int(progress_str)
            res.progress = max(0, min(100, progress))
        except ValueError:
            res.progress = 0
        if res.progress >= 100:
            res.status = 'completed'
        db.session.add(res)
        db.session.commit()
        audit('resolution_create', 'resolution', res.id)
        flash('مصوبه افزوده شد.', 'success')
        return redirect(url_for('resolutions_bp.resolutions_list'))
    return render_template('resolutions/form.html', resolution=None, meetings=meetings, users=users)

@bp.route('/resolutions/<int:res_id>/edit', methods=['GET', 'POST'])
@require_roles('manager','admin')
def resolutions_edit(res_id):
    res = Resolution.query.get_or_404(res_id)
    meetings = Meeting.query.order_by(Meeting.scheduled_at.desc()).all()
    users = User.query.order_by(User.name.asc()).all()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        meeting_id = request.form.get('meeting_id')
        assigned_to_user_id = request.form.get('assigned_to_user_id')
        due_date_str = request.form.get('due_date')
        status = request.form.get('status', res.status)
        progress_str = request.form.get('progress', str(res.progress))
        if not title:
            flash('عنوان مصوبه الزامی است.', 'danger')
            return redirect(url_for('resolutions_bp.resolutions_edit', res_id=res.id))
        if not meeting_id:
            flash('انتخاب جلسه الزامی است.', 'danger')
            return redirect(url_for('resolutions_bp.resolutions_edit', res_id=res.id))
        res.title = title
        res.description = description
        res.meeting_id = int(meeting_id)
        res.assigned_to_user_id = int(assigned_to_user_id) if assigned_to_user_id else None
        if due_date_str:
            try:
                ascii_str = from_farsi_digits(due_date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    res.due_date = date(gy, gm, gd)
                else:
                    raise ValueError()
            except Exception:
                flash('فرمت تاریخ سررسید شمسی نامعتبر است.', 'danger')
                return redirect(url_for('resolutions_bp.resolutions_edit', res_id=res.id))
        else:
            res.due_date = None
        res.status = status if status in ['pending','approved','in_progress','completed'] else res.status
        try:
            progress = int(progress_str)
            res.progress = max(0, min(100, progress))
        except ValueError:
            pass
        if res.progress >= 100:
            res.status = 'completed'
        elif res.status == 'pending' and res.assigned_to_user_id:
            res.status = 'in_progress'
        db.session.commit()
        audit('resolution_update', 'resolution', res.id)
        flash('مصوبه ویرایش شد.', 'success')
        return redirect(url_for('resolutions_bp.resolutions_list'))
    return render_template('resolutions/form.html', resolution=res, meetings=meetings, users=users)
