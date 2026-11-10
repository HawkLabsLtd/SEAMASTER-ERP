import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, g, abort, send_from_directory
from datetime import datetime
from app_pkg.models import db, Meeting, Resolution, User
from app_pkg.audit import audit
from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.uploads import save_upload, extension_of, UploadError
from app_pkg.utils.dates_fa import from_farsi_digits, jalali_to_gregorian
import app_pkg.services.audio_signaling as audio_sig

bp = Blueprint('meetings_bp', __name__)

RECORDINGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'instance', 'recordings')
AUDIO_EXTENSIONS = {'webm', 'ogg', 'oga', 'mp3', 'wav', 'm4a', 'mp4'}

@bp.route('/meetings')
@require_permissions('meetings.view', 'meetings.manage')
def meeting_list():
    page = 1
    try:
        page = int(request.args.get('page', '1'))
    except Exception:
        page = 1
    per_page = 10
    q = (request.args.get('q') or '').strip()
    query = Meeting.query
    if q:
        query = query.filter(Meeting.title.like(f"%{q}%"))
    total_count = query.count()
    meetings = query.order_by(Meeting.scheduled_at.desc()).offset((page-1)*per_page).limit(per_page).all()
    has_prev = page > 1
    has_next = (page * per_page) < total_count
    return render_template('meetings/list.html', meetings=meetings, page=page, per_page=per_page, total_count=total_count, has_prev=has_prev, has_next=has_next, q=q)

@bp.route('/meetings/new', methods=['GET', 'POST'])
@require_roles('manager','admin')
def meeting_new():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('scheduled_at', '').strip()
        if not title:
            flash('عنوان الزامی است.', 'danger')
            return redirect(url_for('meetings_bp.meeting_new'))
        try:
            if date_str:
                ascii_str = from_farsi_digits(date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    scheduled_at = datetime(gy, gm, gd)
                else:
                    raise ValueError()
            else:
                scheduled_at = datetime.utcnow()
        except Exception:
            flash('فرمت تاریخ شمسی نامعتبر است.', 'danger')
            return redirect(url_for('meetings_bp.meeting_new'))
        meeting = Meeting(title=title, description=description, scheduled_at=scheduled_at)
        db.session.add(meeting)
        db.session.commit()
        audit('meeting_create', 'meeting', meeting.id, f'title={title}')
        flash('جلسه ایجاد شد.', 'success')
        return redirect(url_for('meetings_bp.meeting_list'))
    return render_template('meetings/form.html', meeting=None)

@bp.route('/meetings/<int:meeting_id>/edit', methods=['GET', 'POST'])
@require_roles('manager','admin')
def meeting_edit(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_str = request.form.get('scheduled_at', '').strip()
        if not title:
            flash('عنوان الزامی است.', 'danger')
            return redirect(url_for('meetings_bp.meeting_edit', meeting_id=meeting.id))
        try:
            if date_str:
                ascii_str = from_farsi_digits(date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    scheduled_at = datetime(gy, gm, gd)
                else:
                    raise ValueError()
            else:
                scheduled_at = meeting.scheduled_at
        except Exception:
            flash('فرمت تاریخ شمسی نامعتبر است.', 'danger')
            return redirect(url_for('meetings_bp.meeting_edit', meeting_id=meeting.id))
        meeting.title = title
        meeting.description = description
        meeting.scheduled_at = scheduled_at
        db.session.commit()
        audit('meeting_update', 'meeting', meeting.id)
        flash('جلسه ویرایش شد.', 'success')
        return redirect(url_for('meetings_bp.meeting_list'))
    return render_template('meetings/form.html', meeting=meeting)

def is_ajax():
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

@bp.route('/meetings/<int:meeting_id>/delete', methods=['POST'])
@require_roles('manager','admin')
def meeting_delete(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    db.session.delete(meeting)
    db.session.commit()
    audit('meeting_delete', 'meeting', meeting_id)
    if is_ajax():
        return jsonify({'status': 'ok', 'meeting_id': meeting_id, 'message': 'جلسه با موفقیت حذف شد.'})
    flash('جلسه حذف شد.', 'success')
    return redirect(url_for('meetings_bp.meeting_list'))

@bp.route('/meetings/<int:meeting_id>')
@require_permissions('meetings.view', 'meetings.manage')
def meeting_detail(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    users = User.query.order_by(User.name.asc()).all()
    active_audio_participants = audio_sig.get_room_participants(meeting_id)
    return render_template('meetings/detail.html', meeting=meeting, users=users, active_audio_participants=active_audio_participants)

@bp.route('/meetings/<int:meeting_id>/resolutions/new', methods=['POST'])
@require_roles('manager', 'admin')
def resolution_new(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    if not title:
        if is_ajax():
            return jsonify({'status': 'error', 'message': 'عنوان مصوبه الزامی است.'}), 400
        flash('عنوان مصوبه الزامی است.', 'danger')
        return redirect(url_for('meetings_bp.meeting_detail', meeting_id=meeting.id))
    res = Resolution(meeting_id=meeting.id, title=title, description=description, status='pending', progress=0)
    db.session.add(res)
    db.session.commit()
    audit('resolution_create', 'resolution', res.id, f'meeting_id={meeting_id}')
    if is_ajax():
        return jsonify({
            'status': 'ok',
            'resolution': {
                'id': res.id,
                'title': res.title,
                'description': res.description or '',
                'status': res.status,
                'progress': res.progress,
                'meeting_id': res.meeting_id
            },
            'message': 'مصوبه جدید با موفقیت افزوده شد.'
        })
    flash('مصوبه افزوده شد.', 'success')
    return redirect(url_for('meetings_bp.meeting_detail', meeting_id=meeting.id))

# =========================================================================
# WebRTC Meeting Audio Room Signaling Endpoints
# =========================================================================

@bp.route('/meetings/<int:meeting_id>/audio/join', methods=['POST'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_join(meeting_id):
    meeting = Meeting.query.get_or_404(meeting_id)
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    result = audio_sig.join_room(
        meeting_id=meeting.id,
        user_id=user.id,
        user_name=user.name or f"User {user.id}",
        role=user.role or 'member'
    )
    return jsonify(result)

@bp.route('/meetings/<int:meeting_id>/audio/leave', methods=['POST'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_leave(meeting_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    audio_sig.leave_room(meeting_id, user.id)
    return jsonify({'status': 'left', 'user_id': user.id})

@bp.route('/meetings/<int:meeting_id>/audio/signal', methods=['POST'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_signal(meeting_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    to_user_id = data.get('to_user_id')
    signal_data = data.get('signal_data')
    
    if not signal_data:
        return jsonify({'error': 'signal_data is required'}), 400
        
    success = audio_sig.send_signal(
        meeting_id=meeting_id,
        from_user_id=user.id,
        from_user_name=user.name or f"User {user.id}",
        to_user_id=int(to_user_id) if to_user_id is not None else None,
        signal_data=signal_data
    )
    return jsonify({'status': 'sent' if success else 'failed'})

@bp.route('/meetings/<int:meeting_id>/audio/poll', methods=['GET'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_poll(meeting_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    result = audio_sig.poll_signals(meeting_id, user.id)
    return jsonify(result)

@bp.route('/meetings/<int:meeting_id>/audio/status', methods=['POST'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_status(meeting_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json() or {}
    is_muted = data.get('is_muted')
    is_speaking = data.get('is_speaking')
    
    updated = audio_sig.update_status(
        meeting_id=meeting_id,
        user_id=user.id,
        is_muted=is_muted,
        is_speaking=is_speaking
    )
    return jsonify({'status': 'updated', 'participant': updated})

@bp.route('/meetings/<int:meeting_id>/audio/recordings/upload', methods=['POST'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_recording_upload(meeting_id):
    user = getattr(g, 'current_user', None)
    if not user:
        return jsonify({'error': 'Unauthorized'}), 401
    
    meeting = Meeting.query.get_or_404(meeting_id)
    
    file = request.files.get('audio_file')
    if not file:
        return jsonify({'error': 'No audio file provided'}), 400
    if not file.filename:
        file.filename = 'recording.webm'  # MediaRecorder blobs may arrive unnamed

    ts = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    ext = extension_of(file.filename) or 'webm'
    filename = f"meeting_{meeting.id}_{ts}.{ext}"
    try:
        save_upload(file, RECORDINGS_DIR, AUDIO_EXTENSIONS, filename=filename)
    except UploadError as e:
        return jsonify({'error': str(e)}), 400

    download_url = url_for('meetings_bp.audio_recording_download', meeting_id=meeting.id, filename=filename)
    return jsonify({
        'status': 'saved',
        'filename': filename,
        'download_url': download_url,
        'message': 'فایل ضبط با موفقیت در سرور ذخیره شد.'
    })

@bp.route('/meetings/<int:meeting_id>/audio/recordings/<filename>', methods=['GET'])
@require_permissions('meetings.view', 'meetings.manage')
def audio_recording_download(meeting_id, filename):
    if not filename.startswith(f"meeting_{meeting_id}_"):
        abort(404)
    return send_from_directory(RECORDINGS_DIR, filename, as_attachment=True)


