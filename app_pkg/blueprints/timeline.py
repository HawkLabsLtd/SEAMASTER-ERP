from flask import Blueprint, render_template, request, jsonify
from datetime import date
from app_pkg.auth import require_permissions, require_roles
from app_pkg.utils.dates_fa import (
    format_jalali_date_any, 
    from_farsi_digits, 
    jalali_to_gregorian
)

bp = Blueprint('timeline', __name__)

@bp.route('/timeline')
@require_permissions('timeline.view')
def timeline_page():
    return render_template('timeline.html')

@bp.route('/api/timeline-data')
@require_permissions('timeline.view')
def get_timeline_data():
    source = request.args.get('source', 'presidency')
    
    # Query meetings and resolutions
    # Join CouncilMeeting and CouncilResolution
    # Order by date desc
    
    from app_pkg.models import CouncilMeeting
    
    meetings = CouncilMeeting.query.filter_by(type=source).order_by(CouncilMeeting.date.desc()).all()
    
    data = []
    for m in meetings:
        resolutions = []
        for r in m.resolutions:
            resolutions.append({
                'id': r.id,
                'topic': r.topic,
                'responsible': r.responsible,
                'progress': r.progress,
                'status': r.status,
                'description': r.description,
                'due_date': r.due_date,
                'letter_number': r.letter_number
            })
        
        # Format date
        date_str = format_jalali_date_any(m.date) if m.date else 'نامشخص'
        
        data.append({
            'id': m.id,
            'number': m.number,
            'date': date_str,
            'resolutions': resolutions
        })
        
    return jsonify(data)

@bp.route('/api/timeline/update-resolution-progress', methods=['POST'])
@require_roles('manager','admin')
def api_timeline_update_resolution_progress():
    try:
        payload = request.get_json(silent=True) or {}
        res_id = payload.get('resolution_id') or request.form.get('resolution_id')
        progress = payload.get('progress') or request.form.get('progress')
        if not res_id:
            return jsonify({'ok': False, 'error': 'شناسه مصوبه الزامی است.'}), 400
        try:
            progress = int(progress)
        except Exception:
            return jsonify({'ok': False, 'error': 'درصد پیشرفت نامعتبر است.'}), 400
        progress = max(0, min(100, progress))
        from app_pkg.models import db, CouncilResolution
        res = CouncilResolution.query.get(int(res_id))
        if not res:
            return jsonify({'ok': False, 'error': 'مصوبه یافت نشد.'}), 404
        res.progress = progress
        db.session.commit()
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@bp.route('/api/timeline/create-meeting', methods=['POST'])
@require_roles('manager','admin')
def api_timeline_create_meeting():
    try:
        payload = request.get_json(silent=True) or {}
        m_type = (payload.get('type') or '').strip() or (request.form.get('type') or '').strip()
        number = (payload.get('number') or '').strip() or (request.form.get('number') or '').strip()
        date_str = (payload.get('date') or '').strip() or (request.form.get('date') or '').strip()

        if m_type not in {'presidency','representatives','managerial'}:
            return jsonify({'ok': False, 'error': 'نوع جلسه نامعتبر است.'}), 400

        g_date = None
        if date_str:
            try:
                ascii_str = from_farsi_digits(date_str)
                parts = ascii_str.split('-')
                if len(parts) == 3:
                    jy, jm, jd = map(int, parts)
                    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
                    g_date = date(gy, gm, gd)
                else:
                    raise ValueError('invalid date')
            except Exception:
                return jsonify({'ok': False, 'error': 'فرمت تاریخ شمسی نامعتبر است. مثال: ۱۴۰۴-۰۸-۱۵'}), 400

        from app_pkg.models import db, CouncilMeeting
        meeting = CouncilMeeting(number=number if number else None, date=g_date, type=m_type)
        db.session.add(meeting)
        db.session.commit()
        return jsonify({'ok': True, 'id': meeting.id})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@bp.route('/api/timeline/create-resolution', methods=['POST'])
@require_roles('manager','admin')
def api_timeline_create_resolution():
    try:
        payload = request.get_json(silent=True) or {}
        meeting_id = payload.get('meeting_id') or request.form.get('meeting_id')
        topic = (payload.get('topic') or '').strip() or (request.form.get('topic') or '').strip()
        responsible = (payload.get('responsible') or '').strip() or (request.form.get('responsible') or '').strip()
        status = (payload.get('status') or '').strip() or (request.form.get('status') or '').strip()
        progress = payload.get('progress') or request.form.get('progress') or 0
        description = (payload.get('description') or '').strip() or (request.form.get('description') or '').strip()
        letter_number = (payload.get('letter_number') or '').strip() or (request.form.get('letter_number') or '').strip()
        due_date = (payload.get('due_date') or '').strip() or (request.form.get('due_date') or '').strip()

        if not meeting_id:
            return jsonify({'ok': False, 'error': 'شناسه جلسه الزامی است.'}), 400
        if not topic:
            return jsonify({'ok': False, 'error': 'موضوع مصوبه الزامی است.'}), 400

        try:
            progress = int(progress)
        except Exception:
            progress = 0
        progress = max(0, min(100, progress))

        from app_pkg.models import db, CouncilMeeting, CouncilResolution
        meeting = CouncilMeeting.query.get(int(meeting_id))
        if not meeting:
            return jsonify({'ok': False, 'error': 'جلسه یافت نشد.'}), 404

        res = CouncilResolution(
            meeting_id=meeting.id,
            topic=topic,
            responsible=responsible or None,
            status=status or None,
            progress=progress,
            description=description or None,
            letter_number=letter_number or None,
            due_date=due_date or None
        )
        db.session.add(res)
        db.session.commit()
        return jsonify({'ok': True, 'id': res.id})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500
